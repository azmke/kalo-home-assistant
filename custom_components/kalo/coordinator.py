"""Polling and historical-statistics support for KALO."""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import ApiError, IdentityError, KaloClient, LoginError, TokenError
from .api.models import ResidentContext
from .const import (
    CONF_MAX_RETRIES,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL_HOURS,
    CONF_USERNAME,
    CONSUMPTION_TYPES,
    DEFAULT_MAX_RETRIES,
    DEFAULT_POLL_INTERVAL_HOURS,
    DOMAIN,
    RETRY_INTERVAL,
)
from .models import ConsumptionValue, UnitData

_LOGGER = logging.getLogger(__name__)
_KALO_TIME_ZONE = ZoneInfo("Europe/Berlin")


def account_key(resident_id: str) -> str:
    """Return a non-reversible identifier for a KALO account."""
    return hashlib.sha256(f"kalo-account:{resident_id}".encode()).hexdigest()[:20]


def unit_key(resident_id: str, residential_unit_id: str) -> str:
    """Return a non-reversible identifier for a KALO residential unit."""
    value = f"kalo-unit:{resident_id}:{residential_unit_id}"
    return hashlib.sha256(value.encode()).hexdigest()[:20]


class KaloDataUpdateCoordinator(DataUpdateCoordinator[dict[str, UnitData]]):
    """Fetch KALO data once for all account entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._failure_count = 0
        self._polling_stopped = False
        self._store = Store[dict[str, Any]](hass, 1, f"{DOMAIN}.{entry.entry_id}")
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=self._normal_interval,
            always_update=False,
        )

    @property
    def account_key(self) -> str:
        """Return the safe account identifier stored in the config entry."""
        return self.entry.unique_id or "unknown"

    @property
    def failure_count(self) -> int:
        """Return the number of consecutive failed polling attempts."""
        return self._failure_count

    @property
    def polling_stopped(self) -> bool:
        """Return whether polling requires explicit user action to resume."""
        return self._polling_stopped

    @property
    def _normal_interval(self) -> timedelta:
        hours = self.entry.options.get(
            CONF_POLL_INTERVAL_HOURS, DEFAULT_POLL_INTERVAL_HOURS
        )
        return timedelta(hours=int(hours))

    @property
    def _max_retries(self) -> int:
        return int(self.entry.options.get(CONF_MAX_RETRIES, DEFAULT_MAX_RETRIES))

    async def async_initialize(self) -> None:
        """Restore the persisted circuit-breaker state."""
        state = await self._store.async_load() or {}
        self._failure_count = int(state.get("failure_count", 0))
        self._polling_stopped = bool(state.get("polling_stopped", False))
        if self._polling_stopped:
            self.update_interval = None

    async def async_resume(self) -> None:
        """Resume polling after an explicit user action."""
        self._failure_count = 0
        self._polling_stopped = False
        self.update_interval = self._normal_interval
        await self._save_state()
        await self.async_request_refresh()

    async def async_startup_refresh(self) -> None:
        """Refresh immediately when Home Assistant sets up or reloads the entry."""
        if self._polling_stopped:
            self._polling_stopped = False
            self.update_interval = self._normal_interval
            await self._save_state()
        await self.async_refresh()

    async def _async_update_data(self) -> dict[str, UnitData]:
        if self._polling_stopped:
            raise UpdateFailed("KALO polling is paused")

        try:
            unit_data = await self.hass.async_add_executor_job(self._fetch_account_data)
            await self._async_import_statistics(unit_data)
        except (LoginError, TokenError) as err:
            raise ConfigEntryAuthFailed("KALO authentication failed") from err
        except (ApiError, IdentityError, ValueError) as err:
            await self._register_failure()
            retry_after = None if self._polling_stopped else RETRY_INTERVAL.total_seconds()
            raise UpdateFailed(
                "Unable to update KALO consumption data", retry_after=retry_after
            ) from err

        self._failure_count = 0
        await self._save_state()
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id)
        return unit_data

    async def _register_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count > self._max_retries:
            self._polling_stopped = True
            self.update_interval = None
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._issue_id,
                data={"entry_id": self.entry.entry_id},
                is_fixable=True,
                severity=ir.IssueSeverity.ERROR,
                translation_key="polling_stopped",
            )
        await self._save_state()

    @property
    def _issue_id(self) -> str:
        """Return the entry-scoped repair issue identifier."""
        return f"polling_stopped_{self.entry.entry_id}"

    async def _save_state(self) -> None:
        await self._store.async_save(
            {
                "failure_count": self._failure_count,
                "polling_stopped": self._polling_stopped,
            }
        )

    def _fetch_account_data(self) -> dict[str, UnitData]:
        client = KaloClient()
        try:
            client.login(self.entry.data[CONF_USERNAME], self.entry.data[CONF_PASSWORD])
            contexts = client.get_current_resident_contexts()
            if not contexts:
                raise IdentityError("resident response has no occupancy data")
            return self._fetch_contexts(client, contexts)
        finally:
            try:
                client.logout()
            except TokenError:
                _LOGGER.debug("KALO token revocation failed")

    def _fetch_contexts(
        self, client: KaloClient, contexts: tuple[ResidentContext, ...]
    ) -> dict[str, UnitData]:
        grouped: dict[str, list[ResidentContext]] = defaultdict(list)
        for context in contexts:
            grouped[unit_key(context.resident_id, context.residential_unit_id)].append(context)

        result: dict[str, UnitData] = {}
        for key, unit_contexts in grouped.items():
            unit_contexts.sort(key=lambda item: item.occupancy_from or date.min)
            values: dict[str, dict[date, ConsumptionValue]] = {
                kind: {} for kind in CONSUMPTION_TYPES
            }
            current: dict[str, ConsumptionValue] = {}
            previous: dict[str, ConsumptionValue] = {}
            percentages: dict[str, tuple[int | float | None, int | float | None]] = {}
            for context in unit_contexts:
                history = client.get_consumption_history(
                    context.resident_id,
                    context.billing_unit_id,
                    context.residential_unit_number,
                    context.occupancy_id,
                )
                details = client.get_consumption_details(
                    context.resident_id,
                    context.billing_unit_id,
                    context.occupancy_id,
                )
                self._merge_history(values, history)
                self._merge_details(values, current, previous, percentages, details)
            result[key] = UnitData(
                unit_key=key,
                context=unit_contexts[-1],
                values=values,
                current=current,
                previous=previous,
                percentages=percentages,
            )
        return result

    @staticmethod
    def _merge_history(
        values: dict[str, dict[date, ConsumptionValue]], payload: dict[str, Any]
    ) -> None:
        consumptions = payload.get("consumptions")
        if not isinstance(consumptions, dict):
            raise ValueError("KALO history has no consumptions object")
        for period, records in consumptions.items():
            month = _parse_month(period)
            if not isinstance(records, list):
                raise ValueError("KALO history contains invalid monthly records")
            for record in records:
                kind, value = _parse_record(record, month)
                if kind in values:
                    values[kind][month] = value

    @staticmethod
    def _merge_details(
        values: dict[str, dict[date, ConsumptionValue]],
        current: dict[str, ConsumptionValue],
        previous: dict[str, ConsumptionValue],
        percentages: dict[str, tuple[int | float | None, int | float | None]],
        payload: dict[str, Any],
    ) -> None:
        consumptions = payload.get("currentConsumptions")
        if not isinstance(consumptions, dict):
            raise ValueError("KALO details has no current consumptions object")
        for kind, details in consumptions.items():
            if kind not in values or not isinstance(details, dict):
                continue
            unit = details.get("unit")
            current_value = _parse_detail_record(details.get("currentConsumption"), unit)
            previous_value = _parse_detail_record(details.get("previousConsumption"), unit)
            if current_value is not None:
                values[kind][current_value.period] = current_value
                current[kind] = current_value
            if previous_value is not None:
                values[kind][previous_value.period] = previous_value
                previous[kind] = previous_value
            percentages[kind] = (
                _number_or_none(details.get("percentageFromPrevious")),
                _number_or_none(details.get("percentageFromReference")),
            )

    async def _async_import_statistics(self, unit_data: dict[str, UnitData]) -> None:
        for unit in unit_data.values():
            for kind, values in unit.values.items():
                if values:
                    await self._async_import_unit_statistics(unit, kind, values)

    async def _async_import_unit_statistics(
        self, unit: UnitData, kind: str, values: dict[date, ConsumptionValue]
    ) -> None:
        statistic_id = f"{DOMAIN}:{unit.unit_key}_{kind.lower()}"
        existing = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            dt_util.utc_from_timestamp(0),
            None,
            {statistic_id},
            "month",
            None,
            {"start", "state"},
        )
        merged = _merge_monthly_values(existing.get(statistic_id, []), values)

        total = Decimal("0")
        statistics: list[StatisticData] = []
        for period, value in sorted(merged.items()):
            total += value
            start = datetime.combine(period, time.min, _KALO_TIME_ZONE).astimezone(dt_util.UTC)
            statistics.append(StatisticData(start=start, state=float(value), sum=float(total)))
        label = "Heating / Heizung" if kind == "HEAT" else "Warm water / Warmwasser"
        metadata = StatisticMetaData(
            statistic_id=statistic_id,
            source=DOMAIN,
            name=f"{unit.display_name} – {label}",
            unit_of_measurement="kWh",
            unit_class="energy",
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
        )
        async_add_external_statistics(self.hass, metadata, statistics)


def _merge_monthly_values(
    existing: list[dict[str, Any]], values: dict[date, ConsumptionValue]
) -> dict[date, Decimal]:
    """Merge recorder data with KALO values, keyed by calendar month."""
    merged: dict[date, Decimal] = {}
    for statistic in existing:
        start = dt_util.utc_from_timestamp(statistic["start"]).astimezone(_KALO_TIME_ZONE)
        if statistic.get("state") is not None:
            merged[date(start.year, start.month, 1)] = Decimal(str(statistic["state"]))
    merged.update({period: value.value for period, value in values.items()})
    return merged


def _parse_month(value: object) -> date:
    try:
        year, month = str(value).split("-", 1)
        return date(int(year), int(month), 1)
    except (TypeError, ValueError) as err:
        raise ValueError("KALO returned an invalid consumption month") from err


def _parse_record(record: object, period: date) -> tuple[str, ConsumptionValue]:
    if not isinstance(record, dict):
        raise ValueError("KALO history contains an invalid consumption record")
    kind = str(record.get("consumptionType", ""))
    return kind, _consumption_value(period, record, record.get("unit"))


def _parse_detail_record(record: object, unit: object) -> ConsumptionValue | None:
    if record is None:
        return None
    if not isinstance(record, dict):
        raise ValueError("KALO details contains an invalid consumption record")
    return _consumption_value(_parse_month(record.get("period")), record, unit)


def _consumption_value(period: date, record: dict[str, Any], unit: object) -> ConsumptionValue:
    if str(unit).upper() != "KWH":
        raise ValueError("KALO returned an unsupported consumption unit")
    try:
        value = Decimal(str(record["value"]))
        reference = record.get("referenceValue")
        reference_value = Decimal(str(reference)) if reference is not None else None
    except (InvalidOperation, KeyError) as err:
        raise ValueError("KALO returned an invalid consumption value") from err
    if value < 0:
        raise ValueError("KALO returned a negative consumption value")
    return ConsumptionValue(
        period=period,
        value=value,
        estimated=bool(record.get("estimated", False)),
        reference_value=reference_value,
    )


def _number_or_none(value: object) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
