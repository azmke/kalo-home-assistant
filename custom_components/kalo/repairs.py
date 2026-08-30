"""Repairs for the KALO integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .coordinator import KaloDataUpdateCoordinator


class ResumePollingRepairFlow(RepairsFlow):
    """Allow users to explicitly resume polling after exhausted retries."""

    def __init__(self, entry_id: str) -> None:
        """Initialize the repair flow."""
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        """Show the confirmation step."""
        if user_input is not None:
            coordinator: KaloDataUpdateCoordinator | None = self.hass.data.get(DOMAIN, {}).get(
                self._entry_id
            )
            if coordinator is None:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="entry_not_loaded"
                )
            await coordinator.async_resume()
            return self.async_create_entry(title="", data={})

        return self.async_show_form(step_id="init", data_schema=vol.Schema({}))


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create the repair flow for an exhausted polling retry budget."""
    if not issue_id.startswith("polling_stopped_") or not data:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="unknown_issue_id")
    entry_id = data.get("entry_id")
    if not isinstance(entry_id, str):
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="invalid_issue_data")
    return ResumePollingRepairFlow(entry_id)
