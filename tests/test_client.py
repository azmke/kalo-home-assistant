from __future__ import annotations

import time
from unittest.mock import Mock
from urllib.parse import quote

import pytest
from joserfc import jwt
from joserfc.jwk import generate_key

from kalo_api.client import (
    ApiError,
    IdentityError,
    KaloClient,
    KaloConfig,
    LoginError,
    TokenError,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int = 200,
        url: str = "",
        text: str = "",
        headers: dict[str, str] | None = None,
        payload: object | None = None,
    ):
        self.status_code = status_code
        self.url = url
        self.text = text
        self.headers = headers or {}
        self._payload = payload

    @property
    def is_redirect(self) -> bool:
        return self.status_code in (301, 302, 303, 307, 308)

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


LOGIN_HTML = """
<html>
  <form action="/auth/realms/consumer/login-actions/authenticate?session_code=current">
    <input type="hidden" name="execution" value="execution-value">
    <input type="hidden" name="tab_id" value="tab-value">
    <input type="text" name="username" value="">
    <input type="password" name="password" value="">
    <input type="hidden" name="credentialId" value="">
  </form>
</html>
"""


RESIDENT_PAYLOAD = {
    "account": {"accountId": "resident"},
    "occupancyData": [
        {
            "uuid": "occupancy",
            "residentialUnit": {
                "billingUnitNumber": 164965,
                "residentialUnitNumber": "048",
            },
        }
    ],
}


def test_login_preserves_form_state_and_pkce():
    config = KaloConfig()
    client = KaloClient(config)
    authorization = {}
    client.auth_session.create_authorization_url = Mock(
        side_effect=lambda url, **kwargs: (
            authorization.update(kwargs) or ("https://meine.kalo.de/login", kwargs["state"])
        )
    )
    client.auth_session.get = Mock(
        return_value=FakeResponse(
            url="https://meine.kalo.de/auth/realms/consumer/login",
            text=LOGIN_HTML,
        )
    )

    def post(url, data, **kwargs):
        assert url.endswith("session_code=current")
        assert kwargs["withhold_token"] is True
        assert data["execution"] == "execution-value"
        assert data["tab_id"] == "tab-value"
        assert data["username"] == "user"
        assert data["password"] == "password"
        callback = (
            f"{config.redirect_uri}?code=one-time&state={quote(authorization['state'])}"
            f"&iss={quote(config.issuer)}"
        )
        return FakeResponse(302, headers={"Location": callback})

    client.auth_session.post = Mock(side_effect=post)
    client.auth_session.fetch_token = Mock(
        return_value={
            "access_token": "access",
            "refresh_token": "refresh",
            "id_token": "id-token",
            "token_type": "Bearer",
            "expires_in": 300,
        }
    )
    client._validate_id_token = Mock(
        return_value={"iss": config.issuer, "sub": "resident"}
    )

    token = client.login("user", "password")

    assert token["access_token"] == "access"
    assert len(authorization["state"]) >= 40
    assert len(authorization["nonce"]) >= 40
    assert authorization["code_challenge_method"] == "S256"
    assert len(authorization["code_challenge"]) == 43
    token_kwargs = client.auth_session.fetch_token.call_args.kwargs
    assert token_kwargs["grant_type"] == "authorization_code"
    assert token_kwargs["redirect_uri"] == config.redirect_uri
    assert token_kwargs["code_verifier"]
    assert client._id_token_claims["sub"] == "resident"


def test_login_accepts_callback_from_authorization_redirect():
    config = KaloConfig()
    client = KaloClient(config)
    authorization = {}
    client.auth_session.create_authorization_url = Mock(
        side_effect=lambda url, **kwargs: (
            authorization.update(kwargs) or ("https://meine.kalo.de/login", kwargs["state"])
        )
    )

    def get_authorization_page(*args, **kwargs):
        callback = (
            f"{config.redirect_uri}?code=one-time&state={quote(authorization['state'])}"
            f"&iss={quote(config.issuer)}"
        )
        return FakeResponse(
            302,
            url="https://meine.kalo.de/auth/realms/consumer/auth",
            headers={"Location": callback},
        )

    client.auth_session.get = Mock(side_effect=get_authorization_page)
    client.auth_session.fetch_token = Mock(
        return_value={
            "access_token": "access",
            "id_token": "id-token",
            "token_type": "Bearer",
            "expires_in": 300,
        }
    )
    client._validate_id_token = Mock(
        return_value={"iss": config.issuer, "sub": "resident"}
    )

    assert client.login("user", "password")["access_token"] == "access"
    client.auth_session.fetch_token.assert_called_once()


def test_authorization_page_request_does_not_require_access_token():
    client = KaloClient()
    client.auth_session.get = Mock(
        return_value=FakeResponse(
            url="https://meine.kalo.de/auth/realms/consumer/login",
            text=LOGIN_HTML,
        )
    )

    client._load_authorization_page("https://meine.kalo.de/auth")

    assert client.auth_session.get.call_args.kwargs["withhold_token"] is True


def test_callback_state_mismatch_is_rejected():
    config = KaloConfig()
    client = KaloClient(config)
    client.auth_session.create_authorization_url = Mock(
        return_value=("https://meine.kalo.de/login", "state")
    )
    client.auth_session.get = Mock(
        return_value=FakeResponse(
            url="https://meine.kalo.de/auth/realms/consumer/login",
            text=LOGIN_HTML,
        )
    )
    callback = f"{config.redirect_uri}?code=one-time&state=wrong&iss={quote(config.issuer)}"
    client.auth_session.post = Mock(
        return_value=FakeResponse(302, headers={"Location": callback})
    )

    with pytest.raises(LoginError, match="state"):
        client.login("user", "password")


def test_id_token_is_verified_with_jwks():
    config = KaloConfig()
    client = KaloClient(config)
    key = generate_key("RSA", 2048, auto_kid=True)
    nonce = "nonce-value"
    claims = {
        "iss": config.issuer,
        "sub": "subject",
        "aud": config.client_id,
        "azp": config.client_id,
        "nonce": nonce,
        "exp": int(time.time()) + 300,
        "iat": int(time.time()),
    }
    id_token = jwt.encode(
        {"alg": "RS256", "kid": key.as_dict()["kid"]},
        claims,
        key,
    )
    client.public_session.get = Mock(
        return_value=FakeResponse(payload={"keys": [key.as_dict(private=False)]})
    )

    assert client._validate_id_token(id_token, nonce)["sub"] == "subject"
    with pytest.raises(TokenError):
        client._validate_id_token(id_token, "wrong-nonce")


def test_api_refreshes_once_after_401_and_uses_bearer_header():
    client = KaloClient()
    client._set_token(
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_in": 300,
        }
    )
    client.auth_session.refresh_token = Mock(
        return_value={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 300,
        }
    )
    client.api_session.get = Mock(
        side_effect=[
            FakeResponse(401),
            FakeResponse(200, payload={"account": {"accountId": "resident"}}),
        ]
    )

    payload = client.get_resident("resident")

    assert payload["account"]["accountId"] == "resident"
    first_headers = client.api_session.get.call_args_list[0].kwargs["headers"]
    second_headers = client.api_session.get.call_args_list[1].kwargs["headers"]
    assert first_headers == {"Authorization": "Bearer old-access"}
    assert second_headers == {"Authorization": "Bearer new-access"}
    client.auth_session.refresh_token.assert_called_once()


def test_current_methods_resolve_and_cache_resident_context():
    client = KaloClient()
    client._set_token({"access_token": "access", "expires_in": 300})
    client._id_token_claims = {"sub": "resident"}
    client.api_session.get = Mock(
        side_effect=[
            FakeResponse(200, payload=RESIDENT_PAYLOAD),
            FakeResponse(200, payload={"currentConsumptions": {"HEAT": {}}}),
            FakeResponse(200, payload={"consumptions": {"2026-07": {}}}),
        ]
    )

    resident = client.get_current_resident()
    details = client.get_current_consumption_details()
    history = client.get_current_consumption_history()

    assert resident == RESIDENT_PAYLOAD
    assert details["currentConsumptions"]["HEAT"] == {}
    assert history["consumptions"] == {"2026-07": {}}
    urls = [call.args[0] for call in client.api_session.get.call_args_list]
    assert urls == [
        "https://api.kalo.de/resident/v2/residents/resident",
        "https://api.kalo.de/resident/v2/residents/resident/billing-units/164965/"
        "occupancies/occupancy/consumption-details",
        "https://api.kalo.de/resident/v2/residents/resident/billing-units/164965/"
        "residential-units/048/occupancies/occupancy/consumptions-report",
    ]


def test_current_resident_requires_login():
    with pytest.raises(IdentityError, match="login"):
        KaloClient().get_current_resident()


def test_current_resident_rejects_account_identity_mismatch():
    client = KaloClient()
    client._set_token({"access_token": "access", "expires_in": 300})
    client._id_token_claims = {"sub": "resident"}
    client.api_session.get = Mock(
        return_value=FakeResponse(
            200,
            payload={**RESIDENT_PAYLOAD, "account": {"accountId": "other"}},
        )
    )

    with pytest.raises(IdentityError, match="does not match"):
        client.get_current_resident()


def test_current_resident_rejects_multiple_occupancies():
    client = KaloClient()
    client._set_token({"access_token": "access", "expires_in": 300})
    client._id_token_claims = {"sub": "resident"}
    client.api_session.get = Mock(
        return_value=FakeResponse(
            200,
            payload={
                **RESIDENT_PAYLOAD,
                "occupancyData": [RESIDENT_PAYLOAD["occupancyData"][0]] * 2,
            },
        )
    )

    with pytest.raises(IdentityError, match="multiple occupancy"):
        client.get_current_resident()


def test_consumption_paths_are_built_from_arguments():
    client = KaloClient()
    client._set_token({"access_token": "access", "expires_in": 300})
    client.api_session.get = Mock(return_value=FakeResponse(200, payload={}))

    client.get_consumption_details("resident", "billing", "occupancy")
    client.get_consumption_history("resident", "billing", "48", "occupancy")

    urls = [call.args[0] for call in client.api_session.get.call_args_list]
    assert urls == [
        "https://api.kalo.de/resident/v2/residents/resident/billing-units/billing/"
        "occupancies/occupancy/consumption-details",
        "https://api.kalo.de/resident/v2/residents/resident/billing-units/billing/"
        "residential-units/48/occupancies/occupancy/consumptions-report",
    ]


def test_api_errors_do_not_expose_response_body():
    client = KaloClient()
    client._set_token({"access_token": "access", "expires_in": 300})
    client.api_session.get = Mock(
        return_value=FakeResponse(403, payload={"private": "data"})
    )

    with pytest.raises(ApiError, match="Kalo API request failed") as error:
        client.get_resident("resident")

    assert error.value.status_code == 403
    assert "private" not in str(error.value)
