"""Config flow for KALO."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_MAX_RETRIES,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL_HOURS,
    CONF_USERNAME,
    DEFAULT_MAX_RETRIES,
    DEFAULT_POLL_INTERVAL_HOURS,
    DOMAIN,
    MAX_POLL_INTERVAL_HOURS,
    MAX_RETRIES,
    MIN_POLL_INTERVAL_HOURS,
)
from .coordinator import account_key
from .kalo_api import IdentityError, KaloClient, LoginError, TokenError


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Optional(
                CONF_POLL_INTERVAL_HOURS,
                default=defaults.get(CONF_POLL_INTERVAL_HOURS, DEFAULT_POLL_INTERVAL_HOURS),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(MIN_POLL_INTERVAL_HOURS, MAX_POLL_INTERVAL_HOURS),
            ),
            vol.Optional(
                CONF_MAX_RETRIES,
                default=defaults.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES),
            ): vol.All(vol.Coerce(int), vol.Range(0, MAX_RETRIES)),
        }
    )


async def _validate_credentials(hass: HomeAssistant, username: str, password: str) -> str:
    """Validate credentials and return the account's safe unique key."""

    def validate() -> str:
        client = KaloClient()
        try:
            client.login(username, password)
            contexts = client.get_current_resident_contexts()
            if not contexts:
                raise IdentityError("resident response has no occupancy data")
            return account_key(contexts[0].resident_id)
        finally:
            try:
                client.logout()
            except TokenError:
                pass

    return await hass.async_add_executor_job(validate)


class KaloConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle KALO configuration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle first-time setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                unique_id = await _validate_credentials(
                    self.hass, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except (LoginError, TokenError, IdentityError):
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"KALO – {user_input[CONF_USERNAME]}",
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                    options={
                        CONF_POLL_INTERVAL_HOURS: user_input[CONF_POLL_INTERVAL_HOURS],
                        CONF_MAX_RETRIES: user_input[CONF_MAX_RETRIES],
                    },
                )
        return self.async_show_form(step_id="user", data_schema=_schema(user_input), errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication for an existing entry."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Replace credentials after confirming the same account."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                unique_id = await _validate_credentials(
                    self.hass, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
            except (LoginError, TokenError, IdentityError):
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OptionsFlowWithReload:
        """Return the options flow."""
        return KaloOptionsFlow()


class KaloOptionsFlow(OptionsFlowWithReload):
    """Configure KALO polling behavior."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_POLL_INTERVAL_HOURS,
                    default=self.config_entry.options.get(
                        CONF_POLL_INTERVAL_HOURS, DEFAULT_POLL_INTERVAL_HOURS
                    ),
                ): vol.All(
                    vol.Coerce(int),
                    vol.Range(MIN_POLL_INTERVAL_HOURS, MAX_POLL_INTERVAL_HOURS),
                ),
                vol.Required(
                    CONF_MAX_RETRIES,
                    default=self.config_entry.options.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES),
                ): vol.All(vol.Coerce(int), vol.Range(0, MAX_RETRIES)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
