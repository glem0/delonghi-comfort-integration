"""Number platform for De'Longhi Comfort integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

NUMBER_DESCRIPTIONS = (
    NumberEntityDescription(
        key="temp_setpoint",
        translation_key="temperature_setpoint",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=16,
        native_max_value=32,
        native_step=1,
        mode=NumberMode.BOX,
    ),
    NumberEntityDescription(
        key="humidity_setpoint",
        translation_key="humidity_setpoint",
        device_class=NumberDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=30,
        native_max_value=80,
        native_step=5,
        mode=NumberMode.BOX,
    ),
)


DEHUMIDIFIER_NUMBER_DESCRIPTIONS = (
    NumberEntityDescription(
        key="preset_a_humidity",
        translation_key="preset_a_humidity",
        icon="mdi:water-percent",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=30,
        native_max_value=80,
        native_step=5,
        mode=NumberMode.SLIDER,
    ),
    NumberEntityDescription(
        key="preset_b_humidity",
        translation_key="preset_b_humidity",
        icon="mdi:water-percent",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=30,
        native_max_value=80,
        native_step=5,
        mode=NumberMode.SLIDER,
    ),
    NumberEntityDescription(
        key="preset_c_humidity",
        translation_key="preset_c_humidity",
        icon="mdi:water-percent",
        entity_category=EntityCategory.CONFIG,
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=30,
        native_max_value=80,
        native_step=5,
        mode=NumberMode.SLIDER,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi number entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    airconditioner_coordinators = data["airconditioner_coordinators"]

    entities = []

    for coordinator in airconditioner_coordinators:
        entities.extend(
            [
                DeLonghiNumber(
                    coordinator=coordinator,
                    description=description,
                )
                for description in NUMBER_DESCRIPTIONS
            ]
        )

    for coordinator in data["dehumidifier_coordinators"]:
        entities.extend(
            DehumidifierPresetHumidityNumber(
                coordinator=coordinator,
                description=description,
            )
            for description in DEHUMIDIFIER_NUMBER_DESCRIPTIONS
        )

    async_add_entities(entities)


class DeLonghiNumber(CoordinatorEntity, NumberEntity):
    """Representation of a De'Longhi number entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        description: NumberEntityDescription,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.dsn}_{description.key}"

        # Device information
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.dsn)},
            "name": coordinator.device_name,
            "manufacturer": "De'Longhi",
            "model": coordinator.device_model,
            "sw_version": coordinator.device_version,
        }

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        return self.coordinator.data.get(self.entity_description.key)

    async def async_set_native_value(self, value: float) -> None:
        """Set the value."""
        if self.entity_description.key == "temp_setpoint":
            success = await self.coordinator.api.set_temperature_setpoint(
                self.coordinator.dsn, value
            )
        elif self.entity_description.key == "humidity_setpoint":
            success = await self.coordinator.api.set_humidity_setpoint(
                self.coordinator.dsn, value
            )
        else:
            success = False

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set %s to %s", self.entity_description.key, value)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )


_PRESET_LETTERS = {
    "preset_a_humidity": "A",
    "preset_b_humidity": "B",
    "preset_c_humidity": "C",
}


class DehumidifierPresetHumidityNumber(CoordinatorEntity, NumberEntity):
    """Preset humidity number entity for De'Longhi dehumidifiers (preset A/B/C)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        description: NumberEntityDescription,
    ) -> None:
        """Initialize the preset humidity number entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._preset_letter = _PRESET_LETTERS[description.key]
        self._attr_unique_id = (
            f"delonghi_dehumidifier_{coordinator.dsn}_{description.key}"
        )
        self._attr_device_info = coordinator.get_device_info()

    @property
    def native_value(self) -> int | None:
        """Return the preset humidity, or None when unavailable."""
        schedule = self.coordinator.schedule
        if schedule is None:
            return None
        return schedule["modes"][self._preset_letter]["humidity"]

    async def async_set_native_value(self, value: float) -> None:
        """Update the preset humidity and write the schedule back."""
        decoded = self.coordinator.schedule
        if decoded is None:
            raise HomeAssistantError("Device has not reported a schedule yet")
        decoded["modes"][self._preset_letter]["humidity"] = int(value)
        await self.coordinator.async_write_schedule(decoded)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return super().available and self.coordinator.data is not None
