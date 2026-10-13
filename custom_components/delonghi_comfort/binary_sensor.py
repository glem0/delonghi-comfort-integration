"""Binary sensor platform for De'Longhi dehumidifier devices."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# alarm_state is an enum (verified against app constants DdsxProperty$ALARM_STATE):
# 0 = none, 1 = E1, 2 = E2, 3 = tank full, 4 = frost, 5 = change filter
DEHUMIDIFIER_BINARY_SENSOR_DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="alarm_tank_full",
        translation_key="tank_full",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="alarm_filter_warning",
        translation_key="filter_warning",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

_ALARM_VALUES = {
    "alarm_tank_full": 3,
    "alarm_filter_warning": 5,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi binary sensor entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    entities = [
        DehumidifierBinarySensor(coordinator, description)
        for coordinator in data["dehumidifier_coordinators"]
        for description in DEHUMIDIFIER_BINARY_SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class DehumidifierBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor derived from the alarm_state enum."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description: BinarySensorEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"delonghi_dehumidifier_{coordinator.dsn}_{description.key}"
        self._attr_device_info = coordinator.get_device_info()

    @property
    def is_on(self) -> bool | None:
        alarm_state = self.coordinator.data.get("alarm_state")
        if alarm_state is None:
            return None
        return alarm_state == _ALARM_VALUES[self.entity_description.key]

    @property
    def available(self) -> bool:
        return super().available and "alarm_state" in self.coordinator.data
