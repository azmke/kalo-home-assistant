"""Home Assistant specific KALO data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .api.models import Address, ResidentContext


@dataclass(frozen=True)
class ConsumptionValue:
    """A single provider consumption value."""

    period: date
    value: Decimal
    estimated: bool
    reference_value: Decimal | None


@dataclass(frozen=True)
class UnitData:
    """The latest data and complete monthly series for one residential unit."""

    unit_key: str
    context: ResidentContext
    values: dict[str, dict[date, ConsumptionValue]]
    current: dict[str, ConsumptionValue]
    previous: dict[str, ConsumptionValue]
    percentages: dict[str, tuple[int | float | None, int | float | None]]

    @property
    def display_name(self) -> str:
        """Return an address-first label suitable for Home Assistant."""
        address: Address | None = self.context.address
        if address is not None and address.display_name:
            return address.display_name
        return (
            f"KALO Wohneinheit {self.context.residential_unit_number} "
            f"· Abrechnung {self.context.billing_unit_id}"
        )
