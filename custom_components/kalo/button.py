"""Buttons for the KALO integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import KaloDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the KALO rediscovery button."""
    coordinator: KaloDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KaloRediscoverUnitsButton(coordinator)])


class KaloRediscoverUnitsButton(ButtonEntity):
    """Trigger an immediate account refresh and unit rediscovery."""

    _attr_has_entity_name = True
    _attr_translation_key = "rediscover_units"

    def __init__(self, coordinator: KaloDataUpdateCoordinator) -> None:
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.account_key}_rediscover_units"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.account_key)},
            name=f"KALO – {self.coordinator.entry.data['username']}",
            manufacturer="KALO",
            model="Resident portal",
        )

    async def async_press(self) -> None:
        """Refresh all units after an explicit user request."""
        await self.coordinator.async_resume()
