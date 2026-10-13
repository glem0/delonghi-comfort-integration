"""The De'Longhi Comfort integration."""

import hashlib
import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.translation import async_load_integrations
from homeassistant.setup import async_setup_component

from .const import (
    DOMAIN,
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_LANGUAGE,
    CONF_SCAN_INTERVAL,
    DEFAULT_LANGUAGE,
    OEM_MODEL_HEATER,
    OEM_MODEL_DEHUMIDIFIER,
)
from .api import DeLonghiAPI
from .coordinator import DeLonghiCoordinator
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CARD_STATIC_URL = "/delonghi_comfort_static"
CARD_FILE_NAME = "schedule-card.js"
SCHEDULE_PANEL_PATH = "delonghi-schedule"


async def _async_register_schedule_card(hass: HomeAssistant) -> None:
    """Serve the schedule card/panel and auto-load the frontend module."""
    data = hass.data.setdefault(DOMAIN, {})
    if data.get("schedule_card_registered"):
        return

    card_file = Path(__file__).parent / "www" / CARD_FILE_NAME

    def _card_version() -> str | None:
        if not card_file.is_file():
            return None
        return hashlib.sha256(card_file.read_bytes()).hexdigest()[:10]

    version = await hass.async_add_executor_job(_card_version)
    if version is None:
        _LOGGER.warning("Schedule card file not found: %s", card_file)
        return

    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_STATIC_URL, str(card_file.parent), False)]
        )
    except RuntimeError:
        # Already registered (e.g. a reload without a full HA restart)
        pass

    module_url = f"{CARD_STATIC_URL}/{CARD_FILE_NAME}?v={version}"
    frontend.add_extra_js_url(hass, module_url)

    # Sidebar panel so the schedule can be viewed/edited as a page of its own.
    if SCHEDULE_PANEL_PATH not in hass.data.get(frontend.DATA_PANELS, {}):
        await async_setup_component(hass, "panel_custom", {})
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=SCHEDULE_PANEL_PATH,
            webcomponent_name="delonghi-schedule-card",
            sidebar_title="Dehumidifier",
            sidebar_icon="mdi:air-humidifier",
            module_url=module_url,
            config={},
            require_admin=False,
        )

    data["schedule_card_registered"] = True


PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.CLIMATE,
    Platform.HUMIDIFIER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up De'Longhi Comfort from a config entry."""
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    language = entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)

    session = async_get_clientsession(hass)
    api = DeLonghiAPI(username, password, session, language)

    # Test authentication
    if not await api.authenticate():
        _LOGGER.error("Failed to authenticate with De'Longhi API")
        return False

    # Get devices
    devices = await api.get_devices()
    if not devices:
        _LOGGER.error("No devices found")
        return False

    # Create coordinators for each device
    airconditioner_coordinators = []
    heater_coordinators = []
    dehumidifier_coordinators = []
    for device in devices:
        device_info = device["device"]
        dsn = device_info["dsn"]

        coordinator = DeLonghiCoordinator(hass, api, dsn, device_info, entry)
        await coordinator.async_config_entry_first_refresh()
        oem_model = device_info["oem_model"]
        if oem_model == OEM_MODEL_HEATER:
            heater_coordinators.append(coordinator)
        elif oem_model == OEM_MODEL_DEHUMIDIFIER:
            dehumidifier_coordinators.append(coordinator)
        else:
            airconditioner_coordinators.append(coordinator)

    # Store API instance, devices, and coordinators in hass data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "devices": devices,
        "airconditioner_coordinators": airconditioner_coordinators,
        "heater_coordinators": heater_coordinators,
        "dehumidifier_coordinators": dehumidifier_coordinators,
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register integration services (once)
    await async_setup_services(hass)

    # Serve and auto-load the schedule Lovelace card
    await _async_register_schedule_card(hass)

    # Preload integration strings into the translation cache so the frontend
    # websocket can serve entity.* keys (custom integrations are not always
    # loaded before the first UI translation fetch).
    await async_load_integrations(hass, {DOMAIN})

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        if SCHEDULE_PANEL_PATH in hass.data.get(frontend.DATA_PANELS, {}):
            frontend.async_remove_panel(hass, SCHEDULE_PANEL_PATH)
        hass.data.get(DOMAIN, {}).pop("schedule_card_registered", None)

    return unload_ok


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the De'Longhi Comfort integration."""
    # This integration is only configurable via config flow
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)
