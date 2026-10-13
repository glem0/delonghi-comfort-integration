"""Text platform for De'Longhi Comfort integration.

Exposes one editable text row per schedule day. Each row is a 24-character
string of slot codes (``0`` = off, ``C``/``B``/``A`` = preset C/B/A), hour 0
first. The codec and slot constants live in :mod:`schedule`.
"""

from __future__ import annotations

import logging

from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .schedule import CHAR_SLOTS, SLOT_CHARS

_LOGGER = logging.getLogger(__name__)

# One description per day; the tuple position is the day index
# (0 = Monday … 6 = Sunday), matching the codec's ``days`` layout.
SCHEDULE_TEXT_DESCRIPTIONS = (
    TextEntityDescription(
        key="schedule_monday",
        translation_key="schedule_monday",
        icon="mdi:calendar-edit",
    ),
    TextEntityDescription(
        key="schedule_tuesday",
        translation_key="schedule_tuesday",
        icon="mdi:calendar-edit",
    ),
    TextEntityDescription(
        key="schedule_wednesday",
        translation_key="schedule_wednesday",
        icon="mdi:calendar-edit",
    ),
    TextEntityDescription(
        key="schedule_thursday",
        translation_key="schedule_thursday",
        icon="mdi:calendar-edit",
    ),
    TextEntityDescription(
        key="schedule_friday",
        translation_key="schedule_friday",
        icon="mdi:calendar-edit",
    ),
    TextEntityDescription(
        key="schedule_saturday",
        translation_key="schedule_saturday",
        icon="mdi:calendar-edit",
    ),
    TextEntityDescription(
        key="schedule_sunday",
        translation_key="schedule_sunday",
        icon="mdi:calendar-edit",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi text entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    for coordinator in data["dehumidifier_coordinators"]:
        entities.extend(
            DeLonghiScheduleText(
                coordinator=coordinator,
                description=description,
                day_index=day_index,
            )
            for day_index, description in enumerate(SCHEDULE_TEXT_DESCRIPTIONS)
        )

    async_add_entities(entities)


class DeLonghiScheduleText(CoordinatorEntity, TextEntity):
    """Editable 24-hour schedule row for a De'Longhi dehumidifier."""

    _attr_has_entity_name = True
    # The visual card/panel is the primary schedule UI; keep these rows opt-in.
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator,
        description: TextEntityDescription,
        day_index: int,
    ) -> None:
        """Initialize the schedule text entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._day_index = day_index
        self._attr_unique_id = (
            f"delonghi_dehumidifier_{coordinator.dsn}_{description.key}"
        )
        self._attr_device_info = coordinator.get_device_info()

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None

    @property
    def native_value(self) -> str | None:
        """Return the 24-character row for this day, or None if unknown."""
        schedule = self.coordinator.schedule
        if schedule is None:
            return None
        return "".join(
            SLOT_CHARS[slot] for slot in schedule["days"][self._day_index]
        )

    async def async_set_value(self, value: str) -> None:
        """Write a 24-character row for this day back to the device."""
        normalized = value.strip().upper().replace(" ", "")
        if len(normalized) != 24 or any(ch not in CHAR_SLOTS for ch in normalized):
            raise ValueError(
                "Schedule value must be exactly 24 characters from '0ABC' "
                "(0=off, A/B/C=presets), e.g. '000CCCC000000000000000000'; "
                f"got '{value}'"
            )

        decoded = self.coordinator.schedule
        if decoded is None:
            raise HomeAssistantError("Device has not reported a schedule yet")

        decoded["days"][self._day_index] = [CHAR_SLOTS[ch] for ch in normalized]
        await self.coordinator.async_write_schedule(decoded)
