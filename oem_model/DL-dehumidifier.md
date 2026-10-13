# DL-dehumidifier — Device API Reference

Reverse-engineered from live API output (`discover.py`) across three DDSX220 devices.
The same `oem_model` string is expected to apply to the DDSX225WF and other models in the same family.

---

## Device Identity

| Field | Value |
|---|---|
| `oem_model` | `"DL-dehumidifier"` |
| `appliance_model` (from properties) | `"DDSX220"` |
| `appliance` | `"Dehumidifiers"` |
| `device_type` | `"Wifi"` |

---

## Complete Property Schema

Properties delivered via `apiv1/dsns/{dsn}/properties.json`.

### Legend
- **rw** = writable — POST to `apiv1/dsns/{dsn}/properties/{name}/datapoints.json`
- **ro** = read-only
- **÷10** = raw integer must be divided by 10 to get real-world value

### Core Control Properties

| Property | Type | rw/ro | Notes |
|---|---|---|---|
| `device_status` | integer | ro | `1`=ON, `2`=OFF (normal), `3`=FAULT-STOP (halted by alarm). Use only `1` for `is_on`. |
| `set_status` | integer | rw | `1`=ON, `2`=OFF — command setter. Holds last command, not actual state. Always read `device_status`. |
| `device_mode` | integer | rw | Operating mode — see [Device Mode](#device-mode) |
| `humidity_setpoint` | decimal | rw | Target humidity %; range 30–80 |
| `rotation_speed` | integer | rw | Fan speed setter — `1`=Low, `2`=Medium, `3`=High (per app constants). Writes are accepted by the cloud but **have no effect on observed units (DDSX220)** — `current_speed` never follows. Not exposed in De'Longhi's own app either. |

### Sensor Properties

| Property | Type | rw/ro | Notes |
|---|---|---|---|
| `current_humidity` | decimal | ro | Current room humidity % — no scaling needed |
| `room_temp` | integer | ro | **÷10** to get °C |
| `current_speed` | integer | ro | Actual running fan speed readback; `0` when off. Different scale to `rotation_speed`. |
| `heat_exchanger_temp` | integer | ro | **÷10** to get °C — internal evaporator temp; diagnostic only |
| `alarm_state` | integer | ro | Bitmask — see [Alarm State](#alarm-state) |

### Filter Properties

| Property | Type | rw/ro | Notes |
|---|---|---|---|
| `filter_life` | integer | ro | Opaque counter — constant since registration (observed `458960`); never read by the app. Not exposed. |
| `filter_change_alarm` | boolean | ro | Alarm-change flag; read by the app. Observed constant `0` on DDSX220. |
| `filter_status` | boolean | ro | Filter condition as used by the app (`0`=OK, `1`=needs attention). Complement with `alarm_state == 5`. |
| `filter_reset` | boolean | rw | Write `1` to reset the filter-life counter (exposed as a button). |

### Feature Switches

| Property | Type | rw/ro | Notes |
|---|---|---|---|
| `swing` | boolean | rw | Louvre oscillation — `1`=on, `0`=off. Accepted by the cloud but has no physical effect on units without a motorized louvre (observed on DDSX220) |
| `set_eco` | boolean | rw | Eco mode — `1`=on, `0`=off |
| `activate_schedule` | boolean | rw | Whether the timer schedule is active |

### Version / Identity Properties (ro)

| Property | Notes |
|---|---|
| `appliance_model` | Model string e.g. `"DDSX220"` |
| `firmware_version` | MCU firmware |
| `hardware_version` | Hardware revision |
| `mcu_host_version` | Wi-Fi module version |
| `software_version` | Full IoT software version string |
| `serial_number` | Device serial |

### Opaque / Not Implemented Properties

| Property | Notes |
|---|---|
| `activate_realfeel` | RealFeel activation payload — base64 of `[flag, 2, 3, 10, 18, 23, 28, 70, 60, 50, 40]`; `flag` `1`=on, `0`=off. The app writes this companion value with **every** `device_mode` change (ON when the target mode is RealFeel): `AQIDChIXHEY8Mig=` / `AAIDChIXHEY8Mig=` |
| `set_schedule` / `get_schedule` | Base64-encoded timer schedule blob |
| `status_history` | Base64-encoded historical state log |
| `set_temp_unit` | Celsius/Fahrenheit toggle — always `null` in observed data |
| `color` | RealFeel colour indicator — always `null` in observed data |
| `voice1` / `voice2` | Voice assistant room name labels |

---

## Device Mode

`device_mode` is directly readable **and** writable (no `get_`/`set_` prefix split).

Write target: `apiv1/dsns/{dsn}/properties/device_mode/datapoints.json`

| Value | App name | Behaviour |
|---|---|---|
| `1` | Humidity | Target-humidity mode — runs until `humidity_setpoint` is reached |
| `2` | Laundry | Max dehumidification — ignores `humidity_setpoint`, runs continuously |
| `3` | Air | Fan only — no dehumidification |
| `4` | RealFeel | Automatic comfort mode |

Values confirmed against app constants (`DdsxProperty$DDSX_DEVICE_MODE`: 1=HUMIDITY, 2=LAUNDRY, 3=AIR, 4=REAL_FEEL).

**Implementation:** `SelectEntity` with options `["Dehumidify", "Dry", "Fan only", "Real Feel"]` (display names double as option values).

---

## On/Off Control

| Direction | Property | Values |
|---|---|---|
| Write (command) | `set_status` | `1`=ON, `2`=OFF |
| Read (actual state) | `device_status` | `1`=ON, `2`=OFF (normal), `3`=FAULT-STOP |

`set_status` holds the last user command — the schedule or an alarm can override it without updating `set_status`. Always use `device_status` for `is_on`.

**Command delivery is best-effort.** Writes land cloud-side immediately, but the device may re-report its current state before a queued command is delivered, overwriting it (appears as a "revert"). Critical commands (power, mode, humidity setpoint, eco) are therefore verified against the device-reported value and re-sent up to `COMMAND_RETRY_ATTEMPTS` (8) polls (~2 min) by the integration.

Different from the A/C (`set_device_status` / `get_device_status`) but same as the heater (`set_status`).

---

## Temperature Scaling

`room_temp` and `heat_exchanger_temp` are raw integers that must be divided by 10 to get °C.
This is a firmware-level encoding. Apply `÷10` only in dehumidifier-specific entity code — do not apply globally as it may break the A/C device.

---

## Alarm State

Enum — compare the whole value (verified against app constants `DdsxProperty$ALARM_STATE`).

| Value | Meaning |
|---|---|
| `0` | No alarm |
| `1` | Error E1 |
| `2` | Error E2 |
| `3` | Water tank full |
| `4` | Frost protection |
| `5` | Filter needs changing |

- Tank full: `alarm_state == 3`
- Filter warning: `alarm_state == 5`
- All clear: `alarm_state == 0`

Errors E1/E2 (`1`/`2`) and frost (`4`) are exposed as binary sensors (`error`, `frost`).

---

## Comparison: Dehumidifier vs A/C Property Names

| Concept | A/C property | Dehumidifier property |
|---|---|---|
| Power on/off (write) | `set_device_status` | `set_status` |
| Power state (read) | `get_device_status` | `device_status` |
| Operating mode | `get_device_mode` / `set_device_mode` | `device_mode` (single rw property) |
| Fan speed (write) | `set_int_fan_speed` | `rotation_speed` |
| Fan speed (read) | `get_int_fan_speed` | `current_speed` |
| Current humidity | `room_hum` | `current_humidity` |
| Target humidity | `humidity_setpoint` | `humidity_setpoint` ✓ same |
| Current temp | `room_temp` | `room_temp` ✓ same name, scaling needed |
| Silent mode | `set_silent_function` / `get_silent_function` | *(absent)* |
| Temp setpoint | `temp_setpoint` / `set_temp_setpoint` | *(absent)* |

---

## Proposed HA Entity Mapping

| HA Entity | Platform | Property | Notes |
|---|---|---|---|
| Primary control | `HumidifierEntity` (`device_class=DEHUMIDIFIER`) | `device_status`, `set_status`, `humidity_setpoint`, `current_humidity` | Main entity |
| Mode | `SelectEntity` | `device_mode` | `1`=Dehumidification, `2`=Dry Mode, `3`=Fan Only |
| Room temperature | `SensorEntity` (TEMPERATURE) | `room_temp ÷ 10` | |
| Room humidity | `SensorEntity` (HUMIDITY) | `current_humidity` | Useful for automations alongside humidifier entity |
| Eco mode | `SwitchEntity` | `set_eco` | |
| Swing (louvre) | `SwitchEntity` | `swing` | |
| Filter warning | `BinarySensorEntity` (PROBLEM) | `alarm_state & 4` | |
| Tank full | `BinarySensorEntity` (PROBLEM) | `alarm_state & 2` | |
| Current fan speed | `SensorEntity` | `current_speed` | Diagnostic |
| Heat exchanger temp | `SensorEntity` (TEMPERATURE) | `heat_exchanger_temp ÷ 10` | Diagnostic, disabled by default |
| Alarm state (raw) | `SensorEntity` | `alarm_state` | Diagnostic, disabled by default |

---

## Weekly Schedule

`set_schedule` (read/write) carries a base64 payload. Decoded it is a
104-character hex string (52 bytes):

* 20 hex chars (80 bits) — header:
  `[hour:5][day:3][minute:6][timer_type:2][x:8][y:8][z:8]`
  `[humidity_A:8 (value ×2)][humidity_B:8][humidity_C:8]`
  `[fan_A:4][fan_B:4][fan_C:4][0000:4]`
  (hour/day/minute are the phone time at the last write; the device executes
  on its own clock, so the HA codec preserves these fields from the existing
  payload.)
* 84 hex chars — the weekly grid: 7 day-blocks × 48 bits, each block 24
  one-hour slots of 2 bits, hour 0 first, most-significant bits first.

Slot codes: `00` = off, `11` = preset A, `10` = preset B, `01` = preset C
(as 2-bit integers: 0 = off, 1 = C, 2 = B, 3 = A).

The physical block order is rotated: logical day `d` (0-based) is stored in
block `(d + 1) % 7`. Day 0 is assumed to be Monday.

`activate_schedule` (0/1) enables or disables the schedule.

HA surface (implemented in `schedule.py` + `switch.py` + `sensor.py` +
`services.py`):

| Entity / service | Purpose |
|---|---|
| `switch.<dehumidifier>_schedule` | `activate_schedule` — enable/disable the schedule |
| `sensor.<dehumidifier>_weekly_schedule` | Summary state; decoded days/modes in attributes |
| `text.<dehumidifier>_schedule_monday` … `_sunday` | Editable 24-char row per day (hours 0-23, chars `0`/`A`/`B`/`C`) |
| `number.<dehumidifier>_preset_a_humidity` (…b/c) | Preset humidity targets (30-80 %, step 5) |
| `select.<dehumidifier>_preset_a_fan` (…b/c) | Preset fans (Off/Low/Medium/High) |
| `calendar.<dehumidifier>_schedule` | Weekly schedule expanded into calendar events (view) |
| `delonghi_comfort.set_schedule` | Write a schedule: `week` (7 rows of 24 chars, `0`/`A`/`B`/`C`), `modes` (per-preset humidity/fan), `activate` |

Notes:

* The official app also keeps its own cloud copy (an Ayla datum) of the
  schedule; writes done from HA update the device but not that app copy, so
  the app UI may show a stale schedule.
* Codec verified bit-exact against the device's own payload (round-trip on
  the live `set_schedule` value, and a crafted payload written to the unit
  reads back unchanged).

---

## Open Questions

*None.*
