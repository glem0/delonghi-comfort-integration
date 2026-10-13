"""Data update coordinator for De'Longhi Comfort integration."""

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeLonghiAPI
from .const import SCAN_INTERVAL, CONF_SCAN_INTERVAL, DOMAIN
from .schedule import decode as schedule_decode, encode as schedule_encode

_LOGGER = logging.getLogger(__name__)

# Device-originated (output) properties — used to compute the last time the
# unit actually reported anything. Command/input properties are excluded so
# that our own writes do not count as device activity.
DEVICE_REPORT_PROPERTIES = {
    "device_status",
    "current_speed",
    "current_humidity",
    "room_temp",
    "heat_exchanger_temp",
    "status_history",
    "alarm_state",
    "filter_life",
    "filter_status",
    "filter_change_alarm",
    "color",
}

# Ayla command delivery is best-effort: a device state report can overwrite a
# queued command before the device sees it. Critical commands are verified
# against the device-reported value and re-sent up to this many polls.
COMMAND_RETRY_ATTEMPTS = 8


class DeLonghiCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage data updates for De'Longhi devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: DeLonghiAPI,
        dsn: str,
        device_info: dict[str, Any],
        config_entry,
    ) -> None:
        """Initialize the coordinator."""
        # Get scan interval from options, fallback to default
        scan_interval = config_entry.options.get(CONF_SCAN_INTERVAL, SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=f"delonghi_comfort_{dsn}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.dsn = dsn
        self.device_name = device_info.get("product_name", f"De'Longhi {dsn}")
        self.device_model = device_info.get("model", "Unknown")
        self.device_version = device_info.get("sw_version")
        self._pending_commands: dict[str, dict] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the API."""
        try:
            properties = await self.api.get_device_properties(self.dsn)

            # Parse properties into a more usable format
            data = {}
            last_report = None
            for prop in properties:
                if "property" in prop:
                    prop_info = prop["property"]
                    data[prop_info["name"]] = prop_info["value"]
                    if prop_info["name"] in DEVICE_REPORT_PROPERTIES:
                        ts = prop_info.get("data_updated_at")
                        if ts and (last_report is None or ts > last_report):
                            last_report = ts
            data["last_device_report"] = last_report

            # Re-send any commands the device has not confirmed yet.
            for prop, value in self._check_pending(data):
                _LOGGER.debug(
                    "Re-sending %s=%s (not yet confirmed by device)", prop, value
                )
                await self.api.set_device_property(self.dsn, prop, value)

        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        else:
            return data

    async def async_send_command(
        self,
        prop: str,
        value,
        verify_prop: str | None = None,
        verify_value=None,
    ) -> bool:
        """Write a property and register a verification expectation.

        The command is re-sent on subsequent polls until the device-reported
        value matches (see COMMAND_RETRY_ATTEMPTS).
        """
        success = await self.api.set_device_property(self.dsn, prop, value)
        if success:
            self._pending_commands[prop] = {
                "value": value,
                "verify_prop": verify_prop or prop,
                "verify_value": value if verify_value is None else verify_value,
                "attempts_left": COMMAND_RETRY_ATTEMPTS,
            }
        return success

    # ------------------------------------------------------------------
    # Weekly schedule (payload format: see schedule.py)
    # ------------------------------------------------------------------
    @property
    def schedule(self) -> dict[str, Any] | None:
        """Decoded weekly schedule, or None if the device has not reported one."""
        payload = self.data.get("set_schedule") if self.data else None
        if not payload:
            return None
        try:
            return schedule_decode(payload)
        except Exception:
            _LOGGER.warning("Could not decode set_schedule payload from %s", self.dsn)
            return None

    async def async_write_schedule(self, decoded: dict[str, Any]) -> None:
        """Encode and write a decoded schedule back to the device."""
        payload = schedule_encode(decoded)
        if not await self.api.set_device_property(self.dsn, "set_schedule", payload):
            raise HomeAssistantError("Failed to write schedule to the device")
        await self.async_request_refresh()

    def _check_pending(self, data: dict) -> list[tuple[str, object]]:
        """Return commands to re-send based on the latest device data."""
        rewrites: list[tuple[str, object]] = []
        for prop, pend in list(self._pending_commands.items()):
            current = data.get(pend["verify_prop"])
            if current == pend["verify_value"]:
                del self._pending_commands[prop]
                continue
            if pend["attempts_left"] <= 0:
                _LOGGER.warning(
                    "Command %s=%s not confirmed by device after retries (%s=%s)",
                    prop,
                    pend["value"],
                    pend["verify_prop"],
                    current,
                )
                del self._pending_commands[prop]
                continue
            pend["attempts_left"] -= 1
            rewrites.append((prop, pend["value"]))
        return rewrites

    def get_device_info(self) -> DeviceInfo:
        """Return device information for this coordinator."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.dsn)},
            manufacturer="De'Longhi",
            model=self.data.get("appliance_model"),
            name=self.device_name,
            hw_version=self.data.get("hardware_version"),
            sw_version=(
                f"Firmware MDH:{self.data.get('firmware_version')} / Wi-Fi Module:{self.data.get('mcu_host_version')}"
                + (f" / OEM:{self.data['oem_host_version']}" if self.data.get("oem_host_version") else "")
            ),
        )
