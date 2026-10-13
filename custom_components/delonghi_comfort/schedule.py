"""De'Longhi DDSX weekly-schedule payload codec.

The `set_schedule` property carries a base64 payload. Decoded, it is a
104-character hex string (52 bytes):

* 20 hex chars (80 bits) — header:
    [hour:5][day:3][minute:6][timer_type:2][x:8][y:8][z:8]
    [humidity_A:8 (value * 2)][humidity_B:8][humidity_C:8]
    [fan_A:4][fan_B:4][fan_C:4][0000:4 pad]
* 84 hex chars — the weekly grid: 7 day-blocks of 48 bits, each block
  24 hour-slots of 2 bits, hour 0 first, most-significant bits first.

Slot codes: "00"=off, "11"=preset A, "10"=preset B, "01"=preset C
(mapping from the app: MODE_A -> "11", MODE_B -> "10", MODE_C -> "01").

The physical day-block order in the payload is rotated: block p holds
logical day (p - 1) % 7, i.e. logical day d is stored in block (d + 1) % 7.

This was reverse-engineered from De'Longhi Comfort 5.1.5
(DdsxNewScheduleUtility / WeeklyTimerScheduleBitPayloadParser).
"""

from __future__ import annotations

import base64
from typing import Any

# 2-bit slot values: 0="00" (off), 1="01" (preset C), 2="10" (preset B), 3="11" (preset A)
SLOT_LABELS = {0: "off", 1: "C", 2: "B", 3: "A"}
LABEL_SLOTS = {v: k for k, v in SLOT_LABELS.items()}
# Single-character form used by the set_schedule service
CHAR_SLOTS = {"0": 0, "C": 1, "B": 2, "A": 3}

HEADER_HEX = 20  # chars
DAY_HEX = 12  # chars per day block


def _group_for_day(day_index: int) -> int:
    return (day_index + 1) % 7


def _day_for_group(group: int) -> int:
    return (group - 1) % 7


def decode(payload: str) -> dict[str, Any]:
    """Decode a set_schedule base64 payload into a structured dict."""
    raw = base64.b64decode(payload)
    hexs = raw.hex()
    if len(hexs) != HEADER_HEX + 7 * DAY_HEX:
        raise ValueError(f"unexpected schedule payload length: {len(hexs)} hex chars")

    prefix = bin(int(hexs[:HEADER_HEX], 16))[2:].zfill(80)
    result: dict[str, Any] = {
        "header": {
            "hour": int(prefix[0:5], 2),
            "day": int(prefix[5:8], 2),
            "minute": int(prefix[8:14], 2),
            "timer_type": int(prefix[14:16], 2),
            "reserved": [int(prefix[16:24], 2), int(prefix[24:32], 2), int(prefix[32:40], 2)],
            "pad": prefix[76:80],
        },
        "modes": {
            "A": {
                "humidity": int(prefix[40:48], 2) // 2,
                "fan": int(prefix[64:68], 2),
            },
            "B": {
                "humidity": int(prefix[48:56], 2) // 2,
                "fan": int(prefix[68:72], 2),
            },
            "C": {
                "humidity": int(prefix[56:64], 2) // 2,
                "fan": int(prefix[72:76], 2),
            },
        },
        "days": [],  # index 0-6 = logical day; each = 24 slot codes 0-3
    }
    days = [None] * 7
    for group in range(7):
        block = int(hexs[HEADER_HEX + group * DAY_HEX : HEADER_HEX + (group + 1) * DAY_HEX], 16)
        slots = [(block >> (2 * (23 - hour))) & 3 for hour in range(24)]
        days[_day_for_group(group)] = slots
    result["days"] = days
    return result


def encode(schedule: dict[str, Any]) -> str:
    """Encode a structured dict (as returned by decode) back into a payload."""
    header = schedule["header"]
    modes = schedule["modes"]
    days = schedule["days"]

    prefix_bits = (
        bin(int(header["hour"]))[2:].zfill(5)
        + bin(int(header["day"]))[2:].zfill(3)
        + bin(int(header["minute"]))[2:].zfill(6)
        + bin(int(header["timer_type"]))[2:].zfill(2)
        + bin(int(header["reserved"][0]))[2:].zfill(8)
        + bin(int(header["reserved"][1]))[2:].zfill(8)
        + bin(int(header["reserved"][2]))[2:].zfill(8)
        + bin(int(modes["A"]["humidity"]) * 2)[2:].zfill(8)
        + bin(int(modes["B"]["humidity"]) * 2)[2:].zfill(8)
        + bin(int(modes["C"]["humidity"]) * 2)[2:].zfill(8)
        + bin(int(modes["A"]["fan"]))[2:].zfill(4)
        + bin(int(modes["B"]["fan"]))[2:].zfill(4)
        + bin(int(modes["C"]["fan"]))[2:].zfill(4)
        + header.get("pad", "0000")
    )
    hexs = f"{int(prefix_bits, 2):020x}"

    for group in range(7):
        slots = days[_day_for_group(group)]
        block = 0
        for hour, slot in enumerate(slots):
            block |= (int(slot) & 3) << (2 * (23 - hour))
        hexs += f"{block:012x}"

    return base64.b64encode(bytes.fromhex(hexs)).decode()


def decode_for_display(payload: str) -> dict[str, Any]:
    """Decoded schedule with slot codes rendered as labels."""
    data = decode(payload)
    return {
        "modes": data["modes"],
        "days": {str(d): [SLOT_LABELS[s] for s in slots] for d, slots in enumerate(data["days"])},
        "header": data["header"],
    }


def summarise(payload: str) -> str:
    """One-line human summary of a schedule payload."""
    data = decode(payload)
    active_hours = sum(1 for day in data["days"] for slot in day if slot)
    if not active_hours:
        return "empty"
    active_days = sum(1 for day in data["days"] if any(day))
    return f"{active_hours} h/week over {active_days} day(s)"
