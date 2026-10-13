"""Codec regression tests for the set_schedule payload.

Run with pytest. Loads schedule.py standalone to avoid importing the
integration package (which requires Home Assistant).
"""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "delonghi_schedule",
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "delonghi_comfort"
    / "schedule.py",
)
schedule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(schedule)

# Real device payload captured 2026-10-14 (DDSX220, DSN AC000W031829218)
REAL_PAYLOAD = "lOFCAABkAHgTEAFUAAAAAAFUAAAAAAFUAAAAAAFUAAAAAAFUAAAAAAFUAAAAAAFUAAAAAA=="


def test_real_payload_roundtrip():
    assert schedule.encode(schedule.decode(REAL_PAYLOAD)) == REAL_PAYLOAD


def test_real_payload_fields():
    data = schedule.decode(REAL_PAYLOAD)
    assert data["header"] == {
        "hour": 18,
        "day": 4,
        "minute": 56,
        "timer_type": 1,
        "reserved": [66, 0, 0],
        "pad": "0000",
    }
    assert data["modes"]["A"] == {"humidity": 50, "fan": 1}
    assert data["modes"]["B"] == {"humidity": 0, "fan": 3}
    assert data["modes"]["C"] == {"humidity": 60, "fan": 1}
    assert len(data["days"]) == 7
    active = [(d, h) for d, slots in enumerate(data["days"]) for h, s in enumerate(slots) if s]
    assert len(active) == 28
    assert all(slots[h] == 1 for slots in data["days"] for h in (3, 4, 5, 6))


def test_slot_and_mode_edit_roundtrip():
    data = schedule.decode(REAL_PAYLOAD)
    data["days"][0][10] = 3
    data["modes"]["A"]["humidity"] = 70
    payload = schedule.encode(data)
    back = schedule.decode(payload)
    assert back["days"][0][10] == 3
    assert back["modes"]["A"]["humidity"] == 70
    assert back["header"] == data["header"]
    assert schedule.summarise(payload) == "29 h/week over 7 day(s)"
