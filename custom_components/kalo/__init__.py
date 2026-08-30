"""The KALO Home Assistant integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN, PLATFORMS
from .coordinator import KaloDataUpdateCoordinator


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the legacy account device and rediscovery button."""
    if entry.version >= 2:
        return True

    entity_registry = er.async_get(hass)
    legacy_unique_id = f"{entry.unique_id}_rediscover_units"
    for entity_entry in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entity_entry.unique_id == legacy_unique_id:
            entity_registry.async_remove(entity_entry.entity_id)

    device_registry = dr.async_get(hass)
    account_device = device_registry.async_get_device(
        identifiers={(DOMAIN, entry.unique_id or "unknown")}
    )
    if account_device and not er.async_entries_for_device(
        entity_registry, account_device.id, include_disabled_entities=True
    ):
        device_registry.async_remove_device(account_device.id)

    hass.config_entries.async_update_entry(entry, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KALO from a config entry."""
    coordinator = KaloDataUpdateCoordinator(hass, entry)
    await coordinator.async_initialize()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_startup_refresh()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a KALO config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
