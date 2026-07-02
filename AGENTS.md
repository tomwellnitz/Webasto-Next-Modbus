# 🤖 AI Agent Guide for Webasto Next

This document provides context and guidelines for AI agents working on this codebase. It summarizes the architecture, tooling, and coding standards to ensure consistent and high-quality contributions.

## 🌍 Project Overview

**Webasto Next** is a custom integration for Home Assistant that communicates with Webasto Next and Ampure Unite wallboxes via Modbus TCP (for real-time charging data) and REST API (for configuration, diagnostics, and advanced features).

- **Domain**: `webasto_next_modbus`
- **Communication**:
  - **Primary**: Modbus TCP (using `pymodbus`) - real-time charging data
  - **Optional**: REST API (using `aiohttp`) - configuration & diagnostics
- **IoT Class**: Local Polling
- **Config Flow**: UI-based configuration with auto-discovery (Zeroconf).

## 🛠️ Tech Stack & Tooling

- **Language**: Python 3.13.2+
- **Framework**: Home Assistant (Custom Component)
- **Dependency Management**: `uv` (replaces pip/poetry)
- **Linting & Formatting**: `ruff`
- **Type Checking**: `mypy` (Strict mode)
- **Testing**: `pytest` with `pytest-homeassistant-custom-component`
- **Security**: `bandit`
- **Dead Code**: `vulture`
- **Spelling**: `codespell`

## 📂 Project Structure

```text
.
├── custom_components/webasto_next_modbus/  # Main integration code
│   ├── __init__.py                         # Component setup & unload
│   ├── config_flow.py                      # Config & Options flow (UI)
│   ├── const.py                            # Constants & Register definitions
│   ├── coordinator.py                      # DataUpdateCoordinator (polling)
│   ├── hub.py                              # Modbus communication logic
│   ├── rest_client.py                      # REST API client (optional features)
│   ├── entity.py                           # Base entity class
│   └── ...                                 # Platform files (sensor, number, button)
├── tests/                                  # Test suite
├── virtual_wallbox/                        # Simulator for testing/development
├── scripts/                                # Utility scripts
│   └── check.sh                            # Main CI check script
├── docs/                                   # Documentation
│   ├── rest-api.md                         # REST API specification
│   ├── rest-api-integration-plan.md        # Integration roadmap
│   └── rest-api-reverse-engineering.md     # How to probe new REST endpoints
└── pyproject.toml                          # Project configuration
```

## ⚡ Development Workflow

**Always** use the provided check script before committing changes. It runs the full suite of QA tools.

```bash
./scripts/check.sh
```

This script executes:

1. `deptry` (Dependencies)
1. `ruff` (Lint/Format)
1. `codespell` (Spelling)
1. `yamllint` (YAML)
1. `bandit` (Security)
1. `vulture` (Dead code)
1. `mypy` (Type checking)
1. `pytest` (Tests)

## 📏 Coding Standards

### 1. Typing

- All code must be fully typed.
- Use `from __future__ import annotations`.
- Avoid `Any` where possible.
- `mypy` is configured to be strict.

### 2. Async/Await

- This integration is fully async.
- Blocking I/O (like Modbus calls) must be run in the executor or use async libraries (`pymodbus` async client is used here).
- Use `asyncio.sleep` instead of `time.sleep`.

### 3. Error Handling

- Catch specific exceptions (e.g., `ConnectionError`, `ModbusException`).
- Wrap external calls in `try/except` blocks within the `Hub` class.
- Raise `HomeAssistantError` derivatives in `config_flow.py` for UI feedback.

### 4. Home Assistant Patterns

- Use `DataUpdateCoordinator` for fetching data.
- Entities should inherit from `CoordinatorEntity`.
- Use `device_info` to group entities under one device.
- Register definitions are centralized in `const.py`.
- Per-entry runtime objects live on `entry.runtime_data` (typed `WebastoConfigEntry = ConfigEntry[RuntimeData]`). Do not introduce `hass.data[DOMAIN][entry.entry_id]` style storage.
- `OptionsFlow` subclasses must not store their own `config_entry`; rely on the base class's `self.config_entry` injection (HA 2024.12+).

### 5. Dependency Pinning

- `manifest.json` `requirements` lists **only** packages that Home Assistant core does not already provide — currently just `pymodbus`. `aiohttp` is part of HA core, so it must **not** be listed in the manifest (a `>=` requirement there can interfere with pip resolving HA core's own pin). It still belongs in `pyproject.toml` `[project].dependencies` because the test/dev environment imports it directly (`rest_client.py`).
- Where a package appears in **both** `pyproject.toml` and `manifest.json` (i.e. `pymodbus`), the version specifiers must stay in sync — HACS / hassfest validation flags drift. Update both in the same commit.
- `pymodbus` runtime constraint (both `manifest.json` and `pyproject.toml [project].dependencies`) is `>=3.11.2` — **no upper bound**. Home Assistant core dictates the installed pymodbus version via its bundled `modbus` integration, and every fixed ceiling we set eventually blocks the integration at load time when HA-Core moves past it (that is exactly what [#88](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/88) was: HA 2026.7 shipped `pymodbus==3.13.1`, our `<3.12` pin refused to resolve, HA refused to load us). Our production code is defensive against pymodbus API churn (`_invoke_with_unit` walks the `device_id` / `unit` / `slave` kwarg rename; no removed 3.12+ APIs are touched by the integration itself), so removing the ceiling is safer than eventually blocking every user again on the next HA release.
- The **dev group** in `pyproject.toml` still pins `pymodbus<3.12` because `virtual_wallbox/server.py` targets the 3.11 datastore API (`ModbusDeviceContext.store`/`decode`, dropped in 3.12+ in favour of `SimData`/`SimDevice`). Follow-up: port `virtual_wallbox` to the new API, then drop the dev pin so tests run against the same pymodbus as production.
- `.github/workflows/upstream-compat.yml` runs weekly (and on demand) against the latest Home Assistant and pymodbus releases: verifies the manifest requirement is still satisfied by what HA-Core resolves, smoke-imports the production modules, and re-runs hassfest. A red run signals that an upcoming HA release will break the integration — the point is to catch it ~1-2 weeks before end users would.

### 6. Dependabot & auto-merge

- `dependabot.yml` keeps PRs low-noise: direct deps only, grouped per ecosystem, a 7-day `cooldown`, `pymodbus` major/minor and `homeassistant` / `pytest-homeassistant-custom-component` patch bumps ignored (they just track HA point releases).
- `.github/workflows/dependabot-auto-merge.yml` enables GitHub auto-merge for **patch + minor** Dependabot PRs; **major** bumps are left for manual review. For grouped PRs the highest semver bump in the group decides.
- **Two repository settings are required for auto-merge to be safe**, otherwise GitHub would merge without waiting for CI:
  1. Settings → General → **Allow auto-merge** (enabled).
  1. Settings → Branches → branch protection on `main` with **required status checks** (`build`, `validate`, CodeQL `Analyze`). Do **not** require pull-request approvals — Dependabot cannot approve its own PR, which would deadlock auto-merge on a solo-maintainer repo.

## 🧪 Testing Strategy

- **Unit Tests**: Cover all config flows, sensor parsing, and coordinator logic.
- **Mocking**: Use `unittest.mock` to mock the `ModbusBridge` and `pymodbus` client.
- **Virtual Wallbox**: The `virtual_wallbox` module provides a fake Modbus server for end-to-end testing or local development without hardware.

## 🔑 Key Files to Know

- **`custom_components/webasto_next_modbus/const.py`**: Contains the `RegisterDefinition` dataclasses and all register addresses. **Edit this file to add new sensors.**
- **`custom_components/webasto_next_modbus/hub.py`**: Handles the low-level Modbus TCP connection, reading/writing registers, and the background Life Bit loop.
- **`custom_components/webasto_next_modbus/rest_client.py`**: Async REST API client for optional features (LED brightness, firmware info, diagnostics). Uses JWT authentication.
- **`custom_components/webasto_next_modbus/coordinator.py`**: Manages the polling interval and data distribution to entities. Combines Modbus and REST data.
- **`custom_components/webasto_next_modbus/__init__.py`**: Component setup/teardown, service registration, connection retries.
- **`custom_components/webasto_next_modbus/config_flow.py`**: UI configuration and options flow. Handles optional REST API credentials.

## 🚀 Common Tasks

### Adding a new Sensor

1. Define the register in `const.py` (add to `SENSOR_REGISTERS`, `NUMBER_REGISTERS`, or `BUTTON_REGISTERS`).
1. The entity will be auto-created based on the `entity` field in the definition.
1. Update `translations/en.json` and `de.json` if using `translation_key`.
1. Run `./scripts/check.sh` to verify types and tests.

### Updating Dependencies

1. Edit `pyproject.toml`.
1. Run `uv sync`.
1. Run `./scripts/check.sh`.

## 🌐 REST API Integration

The integration supports an **optional** REST API connection for features not available via Modbus.

### Features (REST API only)

| Feature | Entity Type | Description |
|---------|-------------|-------------|
| LED Brightness | `number` | Set LED brightness 0-100% |
| Firmware Versions | `sensor` (diagnostic) | Comboard & Powerboard SW versions |
| Hardware Versions | `sensor` (diagnostic) | Comboard & Powerboard HW versions |
| MAC Addresses | device_info | Ethernet & WiFi MAC |
| IP Address | device_info | Current network IP |
| Plug Cycles | `sensor` (diagnostic) | Connector usage count |
| Error Counter | `sensor` (diagnostic) | Total error count |
| Signal Voltages | `sensor` (diagnostic) | L1/L2/L3 grid voltages |
| Free Charging | `switch` | Enable/disable free charging mode |
| Free Charging Tag ID | `sensor` (diagnostic) | Configured RFID tag alias |
| Active Errors | `sensor` (diagnostic) | List of current errors |
| Restart System | `button` | Trigger wallbox restart |

### REST API Services

| Service | Description |
|---------|-------------|
| `set_led_brightness` | Set LED brightness (0-100%) |
| `set_free_charging` | Enable/disable free charging mode |
| `restart_wallbox` | Trigger system restart |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Coordinator                              │
│  ┌─────────────────────┐    ┌─────────────────────┐         │
│  │      hub.py         │    │   rest_client.py    │         │
│  │   (Modbus TCP)      │    │   (REST API)        │         │
│  │   - Charging data   │    │   - LED brightness  │         │
│  │   - Energy meters   │    │   - Firmware info   │         │
│  │   - Current control │    │   - Diagnostics     │         │
│  └─────────────────────┘    └─────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

### REST API Authentication

- **Endpoint**: `POST /api/login` with `{username, password}`
- **Token**: JWT Bearer token in `Authorization` header
- **Token Refresh**: Auto-refresh before expiry
- **Docs**: See `docs/rest-api.md` for full API specification

### Enabling REST API

REST API is optional and configured via:

1. **Config Flow**: Initial setup with credentials
1. **Options Flow**: Enable/disable and update credentials later

### Conditional Device Info

When REST API is enabled, additional attributes appear in device_info:

- `sw_version`: Comboard firmware version
- `hw_version`: Comboard hardware version
- MAC addresses (configuration_url uses IP)

These attributes are only available when REST is enabled and connected.
