"""Data update coordinator for De'Longhi Comfort integration."""

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeLonghiAPI
from .const import SCAN_INTERVAL, CONF_SCAN_INTERVAL, DOMAIN

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

        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        else:
            return data

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
