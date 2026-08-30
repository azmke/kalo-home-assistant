from __future__ import annotations

import time
from unittest.mock import Mock
from urllib.parse import quote

import pytest
from conftest import LOGIN_HTML, FakeResponse
from joserfc import jwt
from joserfc.jwk import generate_key

from custom_components.kalo.api import KaloClient, KaloConfig, LoginError, TokenError


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
    assert token_kwargs["timeout"] == config.timeout
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


def test_logout_revokes_access_token_and_clears_local_state():
    config = KaloConfig()
    client = KaloClient(config)
    client._set_token(
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "token_type": "Bearer",
        }
    )
    client._id_token_claims = {"sub": "resident"}
    client._resident_context = Mock()
    client._resident_payload = {"account": {}}
    client.auth_session.post = Mock(return_value=FakeResponse(200))

    client.logout()

    assert client.auth_session.post.call_args.args[0] == config.revocation_endpoint
    assert client.auth_session.post.call_args.kwargs == {
        "data": {
            "client_id": config.client_id,
            "token": "access",
            "token_type_hint": "access_token",
        },
        "timeout": config.timeout,
        "withhold_token": True,
    }
    assert client._token is None
    assert client.auth_session.token is None
    assert client._id_token_claims is None
    assert client._resident_context is None
    assert client._resident_payload is None


def test_logout_without_token_only_clears_local_state():
    client = KaloClient()
    client.auth_session.post = Mock()

    client.logout()

    client.auth_session.post.assert_not_called()


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


def test_refresh_updates_validated_claims_when_id_token_is_returned():
    client = KaloClient()
    client._set_token(
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "id_token": "old-id-token",
            "token_type": "Bearer",
            "expires_in": 300,
        }
    )
    client._id_token_claims = {"sub": "resident", "preferred_username": "old"}
    client.auth_session.refresh_token = Mock(
        return_value={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "id_token": "new-id-token",
            "token_type": "Bearer",
            "expires_in": 300,
        }
    )
    client._validate_id_token = Mock(
        return_value={"sub": "resident", "preferred_username": "new"}
    )

    client._refresh()

    assert client._id_token_claims["preferred_username"] == "new"
    assert client._token["access_token"] == "new-access"
    assert client.auth_session.refresh_token.call_args.kwargs["timeout"] == client.config.timeout


def test_refresh_rejects_changed_identity():
    client = KaloClient()
    client._set_token(
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "token_type": "Bearer",
            "expires_in": 300,
        }
    )
    client._id_token_claims = {"sub": "resident"}
    client.auth_session.refresh_token = Mock(
        return_value={
            "access_token": "new-access",
            "token_type": "Bearer",
            "expires_in": 300,
            "id_token": "new-id-token",
        }
    )
    client._validate_id_token = Mock(return_value={"sub": "other"})

    with pytest.raises(TokenError, match="subject"):
        client._refresh()

    assert client._token["access_token"] == "old-access"
