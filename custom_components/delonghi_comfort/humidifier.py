"""Humidifier platform for De'Longhi dehumidifier devices."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.humidifier import (
    HumidifierDeviceClass,
    HumidifierEntity,
    HumidifierEntityDescription,
    HumidifierEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEHUMIDIFIER_ENTITY_DESCRIPTION = HumidifierEntityDescription(
    key="dehumidifier",
    translation_key="dehumidifier",
    device_class=HumidifierDeviceClass.DEHUMIDIFIER,
)

# Display names double as the option values (HA renders them as-is; avoids
# relying on custom-integration translation loading for the select card).
DEVICE_MODE_TO_DEHUMIDIFIER = {
    1: "Dehumidify",
    2: "Dry",
    3: "Fan only",
    4: "Real Feel",
}
DEHUMIDIFIER_TO_DEVICE_MODE = {v: k for k, v in DEVICE_MODE_TO_DEHUMIDIFIER.items()}

# RealFeel activation payload — base64 of an 11-byte array:
# [flag, 2, 3, 10, 18, 23, 28, 70, 60, 50, 40]. Byte 0 toggles RealFeel; the
# rest is a constant parameter block. Mirrors the app's setDDsxDeviceMode,
# which writes this companion value on every mode change.
REALFEEL_ON = "AQIDChIXHEY8Mig="
REALFEEL_OFF = "AAIDChIXHEY8Mig="


async def async_write_device_mode(coordinator, value: int) -> bool:
    """Write device_mode with its companion flag; verify/retry via the coordinator."""
    flag = REALFEEL_ON if value == 4 else REALFEEL_OFF
    if not await coordinator.api.set_device_property(
        coordinator.dsn, "activate_realfeel", flag
    ):
        _LOGGER.warning("Failed to write activate_realfeel flag on %s", coordinator.dsn)
    return await coordinator.async_send_command("device_mode", value)



async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi dehumidifier entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        DeLonghiDehumidifier(coordinator)
        for coordinator in data["dehumidifier_coordinators"]
    )


class DeLonghiDehumidifier(CoordinatorEntity, HumidifierEntity):
    """De'Longhi dehumidifier."""

    entity_description = DEHUMIDIFIER_ENTITY_DESCRIPTION
    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "dehumidifier"
    _attr_supported_features = HumidifierEntityFeature.MODES
    _attr_available_modes = list(DEVICE_MODE_TO_DEHUMIDIFIER.values())
    _attr_min_humidity = 30
    _attr_max_humidity = 80

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"delonghi_dehumidifier_{coordinator.dsn}"
        self._attr_device_info = coordinator.get_device_info()

    @property
    def is_on(self) -> bool | None:
        """Return True only when device is actively running."""
        return self.coordinator.data.get("device_status") == 1

    @property
    def current_humidity(self) -> float | None:
        return self.coordinator.data.get("current_humidity")

    @property
    def target_humidity(self) -> float | None:
        return self.coordinator.data.get("humidity_setpoint")

    @property
    def mode(self) -> str | None:
        value = self.coordinator.data.get("device_mode")
        return DEVICE_MODE_TO_DEHUMIDIFIER.get(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if await self.coordinator.async_send_command(
            "set_status", 1, verify_prop="device_status", verify_value=1
        ):
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn on dehumidifier %s", self.coordinator.dsn)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if await self.coordinator.async_send_command(
            "set_status", 2, verify_prop="device_status", verify_value=2
        ):
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to turn off dehumidifier %s", self.coordinator.dsn)

    async def async_set_humidity(self, humidity: int) -> None:
        # App seekbar covers 30-80 continuously (value = progress + 30) — clamp only.
        humidity = max(30, min(80, int(humidity)))
        if await self.coordinator.async_send_command("humidity_setpoint", humidity):
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set humidity setpoint on %s", self.coordinator.dsn)

    async def async_set_mode(self, mode: str) -> None:
        value = DEHUMIDIFIER_TO_DEVICE_MODE.get(mode)
        if value is None:
            _LOGGER.error("Unknown dehumidifier mode: %s", mode)
            return
        if await async_write_device_mode(self.coordinator, value):
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error("Failed to set dehumidifier mode to %s", mode)
