from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum


@dataclass(frozen=True)
class ResidentContext:
    resident_id: str
    billing_unit_id: str
    occupancy_id: str
    residential_unit_number: str
    residential_unit_id: str
    address: "Address | None" = None
    occupancy_from: date | None = None
    occupancy_to: date | None = None


@dataclass(frozen=True)
class Address:
    """A residential unit address as returned by the KALO portal."""

    street: str | None = None
    house_number: str | None = None
    zip_code: str | None = None
    city: str | None = None
    location: str | None = None

    @property
    def display_name(self) -> str:
        """Return a human-readable label without internal identifiers."""
        street = " ".join(part for part in (self.street, self.house_number) if part)
        locality = " ".join(part for part in (self.zip_code, self.city) if part)
        return ", ".join(part for part in (street, locality, self.location) if part)


class ConsumptionType(str, Enum):
    """Consumption types supported by the integration."""

    HEAT = "HEAT"
    WARM_WATER = "WARM_WATER"


@dataclass(frozen=True)
class MonthlyConsumption:
    """One normalized monthly consumption value."""

    period: date
    consumption_type: ConsumptionType
    value: Decimal
    unit: str
    estimated: bool
    reference_value: Decimal | None
