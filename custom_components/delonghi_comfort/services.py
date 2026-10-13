"""Services for the De'Longhi Comfort integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError

from . import schedule as schedule_codec
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_SCHEDULE = "set_schedule"

SET_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Optional("dsn"): str,
        vol.Optional("week"): [str],
        vol.Optional("modes"): dict,
        vol.Optional("activate"): bool,
    }
)

VALID_SLOT_CHARS = {"0", "A", "B", "C"}


def _parse_week(week: list[str]) -> list[list[int]]:
    """Parse 7 day strings (Monday..Sunday, 24 chars of 0/A/B/C) into slots."""
    if len(week) != 7:
        raise HomeAssistantError("`week` must contain exactly 7 day strings (Monday..Sunday)")
    days = []
    for day, row in enumerate(week):
        row = str(row).strip().upper().replace(" ", "")
        if len(row) != 24 or any(ch not in VALID_SLOT_CHARS for ch in row):
            raise HomeAssistantError(
                f"day {day} must be 24 characters from 0/A/B/C (got {row!r})"
            )
        days.append([schedule_codec.CHAR_SLOTS[ch] for ch in row])
    return days


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_SCHEDULE):
        return

    async def _async_set_schedule(call: ServiceCall) -> None:
        coordinators = []
        for entry_data in hass.data.get(DOMAIN, {}).values():
            coordinators.extend(entry_data.get("dehumidifier_coordinators", []))
        dsn = call.data.get("dsn")
        if dsn:
            coordinators = [c for c in coordinators if c.dsn == dsn]
        if not coordinators:
            raise HomeAssistantError("No De'Longhi dehumidifier found")
        if len(coordinators) > 1:
            raise HomeAssistantError("Multiple dehumidifiers found — specify `dsn`")
        coordinator = coordinators[0]

        current = coordinator.data.get("set_schedule")
        if not current:
            raise HomeAssistantError("Device has not reported a schedule payload")
        decoded = schedule_codec.decode(current)

        if "week" in call.data:
            decoded["days"] = _parse_week(call.data["week"])
        if "modes" in call.data:
            for name, mode in call.data["modes"].items():
                key = str(name).upper()
                if key not in decoded["modes"]:
                    raise HomeAssistantError(f"Unknown preset {name!r} (use A, B or C)")
                if "humidity" in mode:
                    decoded["modes"][key]["humidity"] = int(mode["humidity"])
                if "fan" in mode:
                    decoded["modes"][key]["fan"] = int(mode["fan"])

        payload = schedule_codec.encode(decoded)
        if not await coordinator.api.set_device_property(
            coordinator.dsn, "set_schedule", payload
        ):
            raise HomeAssistantError("Failed to write schedule payload")

        if "activate" in call.data:
            await coordinator.async_send_command(
                "activate_schedule", 1 if call.data["activate"] else 0
            )

        await coordinator.async_request_refresh()
        _LOGGER.info(
            "Schedule written to %s (%s)", coordinator.dsn, schedule_codec.summarise(payload)
        )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_SCHEDULE, _async_set_schedule, schema=SET_SCHEDULE_SCHEMA
    )
