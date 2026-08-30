"""Tests for KALO data coordination and statistics parsing."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from custom_components.kalo.const import CONSUMPTION_TYPES
from custom_components.kalo.coordinator import (
    KaloDataUpdateCoordinator,
    _merge_monthly_values,
    _parse_month,
    account_key,
    unit_key,
)
from custom_components.kalo.models import ConsumptionValue


def test_monthly_history_is_keyed_by_month_without_duplicates() -> None:
    values = {kind: {} for kind in CONSUMPTION_TYPES}
    KaloDataUpdateCoordinator._merge_history(
        values,
        {
            "consumptions": {
                "2024-05": [
                    {
                        "consumptionType": "HEAT",
                        "value": 12.5,
                        "unit": "KWH",
                        "estimated": False,
                    }
                ]
            }
        },
    )
    KaloDataUpdateCoordinator._merge_history(
        values,
        {
            "consumptions": {
                "2024-05": [
                    {
                        "consumptionType": "HEAT",
                        "value": 13.0,
                        "unit": "KWH",
                        "estimated": True,
                    }
                ],
                "2024-06": [
                    {
                        "consumptionType": "WARM_WATER",
                        "value": 4,
                        "unit": "KWH",
                        "estimated": False,
                    }
                ],
            }
        },
    )

    assert values["HEAT"] == {
        date(2024, 5, 1): ConsumptionValue(
            period=date(2024, 5, 1),
            value=Decimal("13.0"),
            estimated=True,
            reference_value=None,
        )
    }
    assert len(values["WARM_WATER"]) == 1


def test_internal_identifiers_are_non_reversible_and_not_raw_identifiers() -> None:
    assert account_key("resident-uuid") != "resident-uuid"
    assert unit_key("resident-uuid", "unit-uuid") != "unit-uuid"
    assert len(unit_key("resident-uuid", "unit-uuid")) == 20


def test_parse_month_uses_the_first_day() -> None:
    assert _parse_month("2026-07") == date(2026, 7, 1)


def test_monthly_statistics_keep_expired_months_and_replace_overlaps() -> None:
    existing = [
        {"start": datetime(2024, 4, 30, 22, tzinfo=UTC).timestamp(), "state": 12.5},
        {"start": datetime(2024, 5, 31, 22, tzinfo=UTC).timestamp(), "state": 15.0},
    ]
    values = {
        date(2024, 6, 1): ConsumptionValue(
            period=date(2024, 6, 1),
            value=Decimal("16.0"),
            estimated=False,
            reference_value=None,
        ),
        date(2024, 7, 1): ConsumptionValue(
            period=date(2024, 7, 1),
            value=Decimal("18.0"),
            estimated=False,
            reference_value=None,
        ),
    }

    merged = _merge_monthly_values(existing, values)

    assert merged == {
        date(2024, 5, 1): Decimal("12.5"),
        date(2024, 6, 1): Decimal("16.0"),
        date(2024, 7, 1): Decimal("18.0"),
    }
