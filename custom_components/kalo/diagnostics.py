"""Diagnostics for the KALO integration without personal account data."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import KaloDataUpdateCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return operational diagnostics while excluding credentials and identifiers."""
    coordinator: KaloDataUpdateCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    return {
        "configured_unit_count": len(coordinator.data or {}) if coordinator else 0,
        "polling_stopped": coordinator.polling_stopped if coordinator else None,
        "failure_count": coordinator.failure_count if coordinator else None,
    }
