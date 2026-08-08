from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResidentContext:
    resident_id: str
    billing_unit_id: str
    occupancy_id: str
    residential_unit_number: str
