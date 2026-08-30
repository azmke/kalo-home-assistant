"""Sensors for KALO consumption data."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KaloDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up KALO consumption sensors."""
    coordinator: KaloDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    added: set[tuple[str, str]] = set()

    @callback
    def add_new_entities() -> None:
        entities = []
        for unit_key in coordinator.data or {}:
            for consumption_type in ("HEAT", "WARM_WATER"):
                key = (unit_key, consumption_type)
                if key not in added:
                    added.add(key)
                    entities.append(KaloConsumptionSensor(coordinator, unit_key, consumption_type))
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(add_new_entities))
    add_new_entities()


class KaloConsumptionSensor(CoordinatorEntity[KaloDataUpdateCoordinator], SensorEntity):
    """Represent the latest monthly KALO consumption for one unit."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: KaloDataUpdateCoordinator, unit_key: str, consumption_type: str
    ) -> None:
        super().__init__(coordinator)
        self._unit_key = unit_key
        self._consumption_type = consumption_type
        suffix = "heating_consumption" if consumption_type == "HEAT" else "warm_water_consumption"
        self._attr_unique_id = f"{unit_key}_{suffix}"
        self._attr_translation_key = suffix

    @property
    def _unit(self):
        return (self.coordinator.data or {}).get(self._unit_key)

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._unit is not None
            and self._consumption_type in self._unit.current
        )

    @property
    def device_info(self) -> DeviceInfo | None:
        unit = self._unit
        if unit is None:
            return None
        return DeviceInfo(
            identifiers={(DOMAIN, self._unit_key)},
            name=unit.display_name,
            manufacturer="KALO",
            model="Resident portal",
        )

    @property
    def native_value(self) -> float | None:
        unit = self._unit
        if unit is None or self._consumption_type not in unit.current:
            return None
        return float(unit.current[self._consumption_type].value)

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        unit = self._unit
        if unit is None:
            return None
        current = unit.current.get(self._consumption_type)
        if current is None:
            return None
        previous = unit.previous.get(self._consumption_type)
        from_previous, from_reference = unit.percentages.get(self._consumption_type, (None, None))
        attributes: dict[str, object] = {
            "period": current.period.isoformat()[:7],
            "estimated": current.estimated,
            "reference_value": float(current.reference_value)
            if current.reference_value is not None
            else None,
            "percentage_from_previous": from_previous,
            "percentage_from_reference": from_reference,
        }
        if previous is not None:
            attributes["previous_period"] = previous.period.isoformat()[:7]
            attributes["previous_value"] = float(previous.value)
        return attributes
