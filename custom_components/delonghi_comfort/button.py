"""Button platform for De'Longhi Comfort integration."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEHUMIDIFIER_BUTTON_DESCRIPTIONS = (
    ButtonEntityDescription(
        key="filter_reset",
        translation_key="filter_reset",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi button entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    entities = [
        DehumidifierButton(coordinator, description)
        for coordinator in data["dehumidifier_coordinators"]
        for description in DEHUMIDIFIER_BUTTON_DESCRIPTIONS
    ]
    async_add_entities(entities)


class DehumidifierButton(CoordinatorEntity, ButtonEntity):
    """Action button for a De'Longhi dehumidifier (writes 1 to the property)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, description: ButtonEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"delonghi_dehumidifier_{coordinator.dsn}_{description.key}"
        )
        self._attr_device_info = coordinator.get_device_info()

    async def async_press(self) -> None:
        success = await self.coordinator.api.set_device_property(
            self.coordinator.dsn, self.entity_description.key, 1
        )
        if success:
            await self.coordinator.async_request_refresh()
        else:
            _LOGGER.error(
                "Failed to press %s on %s",
                self.entity_description.key,
                self.coordinator.dsn,
            )
