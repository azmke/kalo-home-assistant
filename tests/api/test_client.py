from __future__ import annotations

from unittest.mock import Mock

import pytest
from conftest import RESIDENT_PAYLOAD, FakeResponse

from custom_components.kalo.api import ApiError, IdentityError, KaloClient


def authenticated_client() -> KaloClient:
    client = KaloClient()
    client._set_token({"access_token": "access", "token_type": "Bearer", "expires_in": 300})
    client._id_token_claims = {"sub": "resident"}
    return client


def test_current_methods_resolve_and_cache_resident_context():
    client = authenticated_client()
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
        "https://api.kalo.de/resident/v2/residents/resident/billing-units/654815/"
        "occupancies/occupancy/consumption-details",
        "https://api.kalo.de/resident/v2/residents/resident/billing-units/654815/"
        "residential-units/15/occupancies/occupancy/consumptions-report",
    ]


def test_current_resident_requires_login():
    with pytest.raises(IdentityError, match="login"):
        KaloClient().get_current_resident()


def test_current_resident_rejects_account_identity_mismatch():
    client = authenticated_client()
    client.api_session.get = Mock(
        return_value=FakeResponse(
            200,
            payload={**RESIDENT_PAYLOAD, "account": {"accountId": "other"}},
        )
    )

    with pytest.raises(IdentityError, match="does not match"):
        client.get_current_resident()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"account": {"accountId": "resident"}}, "occupancy data"),
        ({"account": {"accountId": "resident"}, "occupancyData": []}, "occupancy data"),
        ({"account": {"accountId": "resident"}, "occupancyData": [None]}, "invalid"),
        (
            {"account": {"accountId": "resident"}, "occupancyData": [{"uuid": "id"}]},
            "residential unit",
        ),
        (
            {
                "account": {"accountId": "resident"},
                "occupancyData": [
                    {"uuid": "id", "residentialUnit": {"billingUnitNumber": 1}}
                ],
            },
            "residential unit number",
        ),
    ],
)
def test_current_resident_rejects_incomplete_payload(payload: dict, message: str):
    client = authenticated_client()
    client.api_session.get = Mock(return_value=FakeResponse(200, payload=payload))

    with pytest.raises(IdentityError, match=message):
        client.get_current_resident()


def test_current_resident_rejects_multiple_occupancies():
    client = authenticated_client()
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


def test_consumption_paths_are_built_from_explicit_arguments():
    client = authenticated_client()
    client.api_session.get = Mock(return_value=FakeResponse(200, payload={}))

    client.get_consumption_details("resident", "billing", "occupancy")
    client.get_consumption_history("resident", "billing", "15", "occupancy")

    urls = [call.args[0] for call in client.api_session.get.call_args_list]
    assert urls == [
        "https://api.kalo.de/resident/v2/residents/resident/billing-units/billing/"
        "occupancies/occupancy/consumption-details",
        "https://api.kalo.de/resident/v2/residents/resident/billing-units/billing/"
        "residential-units/15/occupancies/occupancy/consumptions-report",
    ]


def test_path_identifiers_are_escaped():
    client = authenticated_client()
    client.api_session.get = Mock(return_value=FakeResponse(200, payload={}))

    client.get_resident("resident/id")

    assert client.api_session.get.call_args.args[0].endswith("residents/resident%2Fid")


def test_api_refreshes_once_after_401_and_uses_bearer_header():
    client = authenticated_client()
    client._token["refresh_token"] = "old-refresh"
    client.auth_session.refresh_token = Mock(
        return_value={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "token_type": "Bearer",
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
    assert client.api_session.get.call_args_list[0].kwargs["headers"] == {
        "Authorization": "Bearer access"
    }
    assert client.api_session.get.call_args_list[1].kwargs["headers"] == {
        "Authorization": "Bearer new-access"
    }


def test_api_errors_do_not_expose_response_body():
    client = authenticated_client()
    client.api_session.get = Mock(
        return_value=FakeResponse(403, payload={"private": "data"})
    )

    with pytest.raises(ApiError, match="Kalo API request failed") as error:
        client.get_resident("resident")

    assert error.value.status_code == 403
    assert "private" not in str(error.value)
