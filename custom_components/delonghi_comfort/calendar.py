"""Calendar platform for the De'Longhi Comfort integration.

Exposes the dehumidifier weekly schedule as a read-only calendar: each run of
contiguous hours that share the same preset becomes one event.
"""

from __future__ import annotations

import datetime
import logging

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .schedule import SLOT_LABELS

_LOGGER = logging.getLogger(__name__)

# Raw fan value -> label, mirroring the dehumidifier fan-speed readback.
FAN_LABELS = {0: "Off", 1: "Low", 2: "Medium", 3: "High"}

# Upper bound on the range expanded in a single async_get_events call.
MAX_EVENT_RANGE_DAYS = 90


def _fan_label(fan: int | None) -> str:
    """Return the human label for a raw fan value."""
    return FAN_LABELS.get(fan, str(fan))


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up De'Longhi calendar entities."""
    data = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        DehumidifierScheduleCalendar(coordinator)
        for coordinator in data["dehumidifier_coordinators"]
    )


class DehumidifierScheduleCalendar(CoordinatorEntity, CalendarEntity):
    """Weekly schedule of a De'Longhi dehumidifier as a calendar."""

    _attr_has_entity_name = True
    _attr_translation_key = "schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator) -> None:
        """Initialize the schedule calendar entity."""
        super().__init__(coordinator)
        self._attr_unique_id = (
            f"delonghi_dehumidifier_{coordinator.dsn}_schedule_calendar"
        )
        self._attr_device_info = coordinator.get_device_info()

    @property
    def available(self) -> bool:
        """Return if the entity is available."""
        return super().available and self.coordinator.data is not None

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next event."""
        now = dt_util.now()
        for event in self._build_events(now, now + datetime.timedelta(days=8)):
            if event.end_datetime_local > now:
                return event
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        """Return the schedule events within a datetime range."""
        return self._build_events(start_date, end_date)

    def _build_events(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
    ) -> list[CalendarEvent]:
        """Expand the weekly grid into events between two datetimes."""
        schedule = self.coordinator.schedule
        if schedule is None:
            return []

        tz = dt_util.DEFAULT_TIME_ZONE
        clip_end = min(end_date, start_date + datetime.timedelta(days=MAX_EVENT_RANGE_DAYS))

        events: list[CalendarEvent] = []
        date = start_date.astimezone(tz).date()
        while True:
            day_start = datetime.datetime.combine(date, datetime.time.min, tzinfo=tz)
            if day_start >= clip_end:
                break
            row = schedule["days"][date.weekday()]
            events.extend(self._day_events(date, row, schedule))
            date += datetime.timedelta(days=1)
        return events

    def _day_events(
        self,
        date: datetime.date,
        row: list[int],
        schedule: dict,
    ) -> list[CalendarEvent]:
        """Group one day's 24 hourly slots into contiguous events."""
        events: list[CalendarEvent] = []
        hour = 0
        while hour < 24:
            slot = row[hour]
            if slot == 0:
                hour += 1
                continue
            start_hour = hour
            while hour < 24 and row[hour] == slot:
                hour += 1
            events.append(
                self._make_event(date, start_hour, hour, slot, schedule)
            )
        return events

    def _make_event(
        self,
        date: datetime.date,
        start_hour: int,
        end_hour: int,
        slot: int,
        schedule: dict,
    ) -> CalendarEvent:
        """Build a single event spanning [start_hour, end_hour) hours."""
        tz = dt_util.DEFAULT_TIME_ZONE
        day_start = datetime.datetime.combine(date, datetime.time.min, tzinfo=tz)
        letter = SLOT_LABELS[slot]
        mode = schedule["modes"].get(letter, {})
        summary = (
            f"Preset {letter} — humidity {mode.get('humidity')}%, "
            f"fan {_fan_label(mode.get('fan'))}"
        )
        return CalendarEvent(
            start=day_start + datetime.timedelta(hours=start_hour),
            end=day_start + datetime.timedelta(hours=end_hour),
            summary=summary,
            description=f"{summary} on {date.strftime('%A')}",
            uid=f"{self.coordinator.dsn}-{date.isoformat()}-{start_hour}",
        )
