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
| `rotation_speed` | integer | rw | Fan speed setter — `1`=Low. Not exposed as HA entity (not controllable in app). |

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
| `filter_change_alarm` | boolean | ro | **Unused** — always `0` even when filter warning active. Ignore. |
| `filter_status` | boolean | ro | **Unreliable** — stale, does not update. Use `alarm_state & 4` instead. |
| `filter_reset` | boolean | rw | Write `1` to reset filter life counter |

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
| `activate_realfeel` | Base64-encoded schedule blob for "RealFeel" feature |
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

**Implementation:** `SelectEntity` with options `["dehumidify", "dry", "fan_only", "real_feel"]`.

---

## On/Off Control

| Direction | Property | Values |
|---|---|---|
| Write (command) | `set_status` | `1`=ON, `2`=OFF |
| Read (actual state) | `device_status` | `1`=ON, `2`=OFF (normal), `3`=FAULT-STOP |

`set_status` holds the last user command — the schedule or an alarm can override it without updating `set_status`. Always use `device_status` for `is_on`.

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

Errors E1/E2 (`1`/`2`) and frost (`4`) are not currently exposed as entities.

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

## Open Questions

*None.*
