"""Tests for the KALO configuration form."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

from custom_components.kalo import async_migrate_entry
from custom_components.kalo.config_flow import _SECTION_ADVANCED_OPTIONS, _schema
from custom_components.kalo.const import (
    CONF_MAX_RETRIES,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL_HOURS,
    CONF_USERNAME,
    DEFAULT_MAX_RETRIES,
    DEFAULT_POLL_INTERVAL_HOURS,
)


def test_setup_schema_requires_advanced_options_with_defaults() -> None:
    """Keep advanced values enabled without optional-field checkboxes."""
    validated = _schema()(
        {
            CONF_USERNAME: "max@example.com",
            CONF_PASSWORD: "secret",
            _SECTION_ADVANCED_OPTIONS: {},
        }
    )

    assert validated[_SECTION_ADVANCED_OPTIONS] == {
        CONF_POLL_INTERVAL_HOURS: DEFAULT_POLL_INTERVAL_HOURS,
        CONF_MAX_RETRIES: DEFAULT_MAX_RETRIES,
    }


def test_migration_removes_legacy_rediscovery_button_and_account_device() -> None:
    """Clean up the device hierarchy created by the removed button."""
    entry = SimpleNamespace(entry_id="entry", unique_id="account", version=1)
    hass = Mock()
    entity_registry = Mock()
    device_registry = Mock()
    legacy_entity = SimpleNamespace(
        entity_id="button.kalo_rediscover_residential_units",
        unique_id="account_rediscover_units",
    )
    account_device = SimpleNamespace(id="account-device")

    with (
        patch("custom_components.kalo.er.async_get", return_value=entity_registry),
        patch(
            "custom_components.kalo.er.async_entries_for_config_entry",
            return_value=[legacy_entity],
        ),
        patch("custom_components.kalo.dr.async_get", return_value=device_registry),
        patch("custom_components.kalo.er.async_entries_for_device", return_value=[]),
    ):
        device_registry.async_get_device.return_value = account_device

        assert asyncio.run(async_migrate_entry(hass, entry))

    entity_registry.async_remove.assert_called_once_with(legacy_entity.entity_id)
    device_registry.async_remove_device.assert_called_once_with(account_device.id)
    hass.config_entries.async_update_entry.assert_called_once_with(entry, version=2)
