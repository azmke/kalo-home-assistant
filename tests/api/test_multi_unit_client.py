from __future__ import annotations

from copy import deepcopy
from unittest.mock import Mock

import pytest
from conftest import RESIDENT_PAYLOAD, FakeResponse

from custom_components.kalo.api import IdentityError, KaloClient


def _authenticated_client() -> KaloClient:
    client = KaloClient()
    client._set_token({"access_token": "access", "token_type": "Bearer", "expires_in": 300})
    client._id_token_claims = {"sub": "resident"}
    return client


def test_current_resident_contexts_returns_all_units_with_address() -> None:
    payload = deepcopy(RESIDENT_PAYLOAD)
    payload["occupancyData"][0]["residentialUnit"]["address"] = {
        "street": "Example Street",
        "houseNumber": "1-2",
        "zipCode": "12345",
        "city": "Exampletown",
        "location": "1st floor",
    }
    payload["occupancyData"].append(
        {
            "uuid": "second-occupancy",
            "from": "2026-01-01",
            "residentialUnit": {
                "uuid": "second-unit",
                "billingUnitNumber": 987654,
                "residentialUnitNumber": 16,
                "address": {"street": "Second Street", "houseNumber": "3"},
            },
        }
    )
    client = _authenticated_client()
    client.api_session.get = Mock(return_value=FakeResponse(200, payload=payload))

    contexts = client.get_current_resident_contexts()

    assert len(contexts) == 2
    assert contexts[0].address is not None
    assert contexts[0].address.display_name == "Example Street 1-2, 12345 Exampletown, 1st floor"
    assert contexts[1].residential_unit_id == "second-unit"
    assert contexts[1].occupancy_from is not None


def test_legacy_current_methods_reject_multiple_units() -> None:
    payload = deepcopy(RESIDENT_PAYLOAD)
    payload["occupancyData"].append(deepcopy(payload["occupancyData"][0]))
    client = _authenticated_client()
    client.api_session.get = Mock(return_value=FakeResponse(200, payload=payload))

    with pytest.raises(IdentityError, match="multiple occupancy"):
        client.get_current_resident()
