"""Select platform for De'Longhi Comfort integration."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .humidifier import DEVICE_MODE_TO_DEHUMIDIFIER, DEHUMIDIFIER_TO_DEVICE_MODE

_LOGGER = logging.getLogger(__name__)

SELECT_DESCRIPTIONS = (
    SelectEntityDescription(
        key="get_device_mode",
        translation_key="device_mode",
        options=["cooling", "dehumidification", "fan_only"],
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi select entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    for coordinator in data["airconditioner_coordinators"]:
        entities.extend(
            DeLonghiSelect(coordinator=coordinator, description=description)
            for description in SELECT_DESCRIPTIONS
        )

    entities.extend(
        HeaterBrightness(coordinator=coordinator)
        for coordinator in data["heater_coordinators"]
    )

    for coordinator in data["dehumidifier_coordinators"]:
        entities.append(DehumidifierModeSelect(coordinator=coordinator))
        entities.append(DehumidifierFanSpeedSelect(coordinator=coordinator))

    async_add_entities(entities)


class DeLonghiSelect(CoordinatorEntity, SelectEntity):
    """Representation of a De'Longhi select entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        description: SelectEntityDescription,
    ) -> None:
        """Initialize the select entity."""
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
    def current_option(self) -> str | None:
        """Return the current option."""
        value = self.coordinator.data.get(self.entity_description.key)

        if value is None:
            return None

        # Convert device mode value to option
        mode_map = {1: "cooling", 2: "dehumidification", 3: "fan_only"}
        return mode_map.get(value)

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        # Convert option to device mode value
        option_map = {"cooling": 1, "dehumidification": 2, "fan_only": 3}

        device_mode = option_map.get(option)
        if device_mode is None:
            _LOGGER.error("Unknown option: %s", option)
            return

        success = await self.coordinator.api.set_device_mode(
            self.coordinator.dsn, device_mode
        )

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set device mode to %s", option)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            super().available and self.entity_description.key in self.coordinator.data
        )

class HeaterBrightness(CoordinatorEntity, SelectEntity):
    """Representation of a heater brightness entity."""
    _attr_has_entity_name = True
    _attr_icon = "mdi:brightness-6"
    _attr_name = "Display brightness"

    _attr_options = ["Level 1", "Level 2", "Level 3"]

    def __init__(self, coordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"delonghi_heater_{coordinator.dsn}_brightness"
        self._attr_device_info = coordinator.get_device_info()

    @property
    def current_option(self) -> str | None:
        """Return the current option."""
        value = self.coordinator.data.get(f"current_brightness")
        return None if value is None else self.options[value - 1]

    async def async_select_option(self, option: str) -> None:
        """Select an option."""
        value = self.options.index(option) + 1
        success = await self.coordinator.api.set_device_property(
            self.coordinator.dsn, f"set_brightness", value
        )

        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set device brightness to %s", option)


class DehumidifierModeSelect(CoordinatorEntity, SelectEntity):
    """Mode select for De'Longhi dehumidifier (Dehumidification / Dry Mode / Fan Only)."""

    _attr_has_entity_name = True
    _attr_translation_key = "dehumidifier_mode"
    _attr_options = list(DEVICE_MODE_TO_DEHUMIDIFIER.values())

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"delonghi_dehumidifier_{coordinator.dsn}_mode"
        self._attr_device_info = coordinator.get_device_info()

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data.get("device_mode")
        return DEVICE_MODE_TO_DEHUMIDIFIER.get(value)

    async def async_select_option(self, option: str) -> None:
        value = DEHUMIDIFIER_TO_DEVICE_MODE.get(option)
        if value is None:
            _LOGGER.error("Unknown dehumidifier mode: %s", option)
            return
        success = await self.coordinator.api.set_device_property(
            self.coordinator.dsn, "device_mode", value
        )
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set dehumidifier mode to %s", option)

    @property
    def available(self) -> bool:
        return super().available and "device_mode" in self.coordinator.data


# Fan speed control — writes rotation_speed; readback via current_speed.
# Values per app constants (DdsxFanSpeed: 1=Low, 2=Medium, 3=High).
FAN_SPEED_TO_ROTATION = {"Low": 1, "Medium": 2, "High": 3}
ROTATION_TO_FAN_SPEED = {v: k for k, v in FAN_SPEED_TO_ROTATION.items()}


class DehumidifierFanSpeedSelect(CoordinatorEntity, SelectEntity):
    """Fan speed select for De'Longhi dehumidifier (rotation_speed)."""

    _attr_has_entity_name = True
    _attr_translation_key = "dehumidifier_fan_speed"
    _attr_options = list(FAN_SPEED_TO_ROTATION)

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"delonghi_dehumidifier_{coordinator.dsn}_fan_speed"
        self._attr_device_info = coordinator.get_device_info()

    @property
    def current_option(self) -> str | None:
        return ROTATION_TO_FAN_SPEED.get(self.coordinator.data.get("rotation_speed"))

    async def async_select_option(self, option: str) -> None:
        value = FAN_SPEED_TO_ROTATION.get(option)
        if value is None:
            _LOGGER.error("Unknown dehumidifier fan speed: %s", option)
            return
        success = await self.coordinator.api.set_device_property(
            self.coordinator.dsn, "rotation_speed", value
        )
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set dehumidifier fan speed to %s", option)

    @property
    def available(self) -> bool:
        return super().available and "rotation_speed" in self.coordinator.data
