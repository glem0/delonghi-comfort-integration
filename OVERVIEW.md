# OVERVIEW

## Purpose
Home Assistant custom integration (HACS-compatible) that connects De'Longhi Comfort air conditioners, heaters, and dehumidifiers to Home Assistant via the De'Longhi cloud API.

## Stack
- **Python 3 / asyncio** under the Home Assistant custom component framework (`homeassistant>=2023.1.0`)
- **aiohttp** for all async HTTP — HA's `async_get_clientsession` used at runtime
- **Gigya OIDC + Ayla Networks** — two-vendor cloud auth chain; 8 sequential HTTP steps to obtain a usable `access_token`. Niche, undocumented externally.
- **HACS** distribution — no PyPI package, no build system
- Dev environment: Docker Compose (`docker-compose.yml`) running `ghcr.io/home-assistant/home-assistant:stable` with `custom_components/` bind-mounted

## Architecture
Standard HA custom component layout under `custom_components/delonghi_comfort/`:

| File | Role |
|---|---|
| `__init__.py` | Entry setup — authenticates, discovers devices, sorts into three coordinator buckets by `oem_model`, sets up platforms |
| `api.py` | All HTTP — full Gigya/Ayla auth flow + Ayla `ads-eu` datapoint read/write |
| `coordinator.py` | `DataUpdateCoordinator` subclass; polls `get_device_properties` on configurable interval |
| `climate.py` | A/C (`DeLonghiClimate`) and heater (`DeLonghiHeater`) entities |
| `humidifier.py` | Dehumidifier entity (`DehumidifierEntity`); also defines `DEVICE_MODE_TO_DEHUMIDIFIER` map imported by `select.py` |
| `binary_sensor.py` | Dehumidifier alarm bitmask entities (tank full, filter warning) |
| `sensor.py`, `switch.py`, `select.py`, `number.py` | Supporting platforms for all three device types |
| `oem_model/DL-dehumidifier.md` | Reverse-engineered API reference for dehumidifier devices |

**Device routing**: `__init__.py` sorts coordinators into `airconditioner_coordinators`, `heater_coordinators`, `dehumidifier_coordinators` by `oem_model` string. Each platform file has separate entity blocks per device type.

## Scale & Complexity
~15 Python files, ~2,450 lines. Technically dense in two areas:
1. **Auth flow** (`api.py`) — 8-step Gigya/Ayla OIDC chain with hardcoded browser fingerprints; fragile against API changes
2. **HA platform contracts** — each platform has strict interface requirements; wrong property types or missing attributes cause silent failures, not exceptions
3. **Dehumidifier property naming** diverges significantly from A/C — different property names, `÷10` temperature scaling, bitmask alarm state. Documented in `oem_model/DL-dehumidifier.md`.

No tests. No type-checking toolchain. Regressions are invisible until runtime.

## Key Files
1. `custom_components/delonghi_comfort/api.py` — auth flow and all device I/O
2. `custom_components/delonghi_comfort/__init__.py` — device discovery and coordinator routing
3. `custom_components/delonghi_comfort/humidifier.py` — dehumidifier primary entity and mode map
4. `oem_model/DL-dehumidifier.md` — dehumidifier API reference (property names, enums, bitmasks)
5. `custom_components/delonghi_comfort/coordinator.py` — data shape fed to all entities

## Routing Notes
- Requires solid knowledge of the **HA integration development pattern** (`ConfigEntry`, `DataUpdateCoordinator`, `CoordinatorEntity`, platform setup, translation file conventions). Models without HA-specific training produce plausible-looking but broken code.
- The Gigya + Ayla auth chain is niche — changes require reading existing code, not web lookup.
- The dehumidifier device type has a fully documented API in `oem_model/DL-dehumidifier.md`; read it before touching dehumidifier entities.
- No test suite — prefer models that reason carefully about async HA lifecycle and flag missing coverage.
