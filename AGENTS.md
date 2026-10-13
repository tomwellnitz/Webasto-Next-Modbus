# 🤖 AI Agent Guide for Webasto Next

This document provides context and guidelines for AI agents working on this codebase. It summarizes the architecture, tooling, and coding standards to ensure consistent and high-quality contributions.

## 🌍 Project Overview

**Webasto Next** is a custom integration for Home Assistant that communicates with Webasto Next and Ampure Unite wallboxes via Modbus TCP (for real-time charging data) and REST API (for configuration, diagnostics, and advanced features).

- **Domain**: `webasto_next_modbus`
- **Communication**:
  - **Primary**: Modbus TCP over Home Assistant's shared Modbus connection (`homeassistant.components.modbus.async_get_unit`, backed by `modbus-connection` / tmodbus) - real-time charging data
  - **Optional**: REST API (using `aiohttp`) - configuration & diagnostics
- **IoT Class**: Local Polling
- **Config Flow**: UI-based configuration (host / port / unit ID entered manually — the wallboxes do not advertise themselves via mDNS/zeroconf), plus reconfigure, reauth and options flows.

## 🛠️ Tech Stack & Tooling

- **Language**: Python 3.14.2+ (what Home Assistant 2026.x requires)
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
│   ├── hub.py                              # Modbus register access (shared HA connection)
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
./scripts/check.sh          # fixes lint/format/Markdown in place, then checks
./scripts/check.sh --check  # read-only; this is exactly what CI runs
```

This script executes:

1. `deptry` (Dependencies)
1. `ruff` (Lint/Format)
1. `codespell` (Spelling; the only config is `[tool.codespell]` in `pyproject.toml`)
1. `mdformat` (Markdown, tracked files only)
1. `yamllint` (YAML, including `.github/`)
1. `actionlint` (GitHub workflows)
1. `bandit` (Security)
1. `vulture` (Dead code)
1. `mypy` (Type checking)
1. `pytest --cov` (Tests; fails below `[tool.coverage.report] fail_under`)

`uv.lock` is committed and CI installs with `uv sync --locked`: after any dependency change run `uv lock` and commit `uv.lock` together with `pyproject.toml`.

## 📏 Coding Standards

### 1. Typing

- All code must be fully typed.
- Use `from __future__ import annotations`.
- Avoid `Any` where possible.
- `mypy` is configured to be strict.

### 2. Async/Await

- This integration is fully async.
- Blocking I/O (like Modbus calls) must be run in the executor or use async libraries (the async `modbus_connection.ModbusUnit` is used here).
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

- The Modbus connection comes from Home Assistant core's `modbus` integration: `manifest.json` declares `"dependencies": ["modbus"]` and `"requirements": []`. HA's `modbus` integration installs `modbus-connection` (tmodbus backend) and owns the connection: entries that talk to the same wallbox share it, it reconnects by itself, and it is released when the last config entry holding a unit unloads. Get units with `async_get_unit(hass, entry, ModbusTcpParams(...), unit_id)` in setup and `async_get_temporary_unit(...)` in config flows; never open a Modbus client of our own (the wallbox has a single Modbus TCP slot), and never close the connection from the integration.
- `manifest.json` `requirements` lists **only** packages that Home Assistant core does not already provide — currently none. `aiohttp` and `modbus-connection` come with HA core, so they must **not** be listed (a `>=` requirement there can interfere with pip resolving HA core's own pin). They still belong in `pyproject.toml` `[project].dependencies` because the integration imports them.
- Minimum Home Assistant is **2026.9.0** (first release with `async_get_unit`). The per-request timeout the bridge asks for (`ModbusUnit.require_timeout`) only exists from modbus-connection 4.11 on; the bridge calls it when available and is otherwise bounded by its own 30 s operation budget.
- The **dev group** pins `modbus-connection[tmodbus]` / `tmodbus` to exactly what HA's `modbus` manifest requires in the HA version `pytest-homeassistant-custom-component` pins, so the tests run production's connection code. Bump them together with phcc.
- The integration no longer uses `pymodbus` (no more version pin to break on an HA upgrade, see [#88](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/88)). Only the dev group still pins `pymodbus<3.12`, for the `virtual_wallbox` TCP simulator (`virtual_wallbox/server.py`, 3.11 datastore API); deptry ignores it as a dev tool. Follow-up: port the simulator server to the current pymodbus API (or a tmodbus server).
- `.github/workflows/upstream-compat.yml` runs weekly (and on demand) against the latest Home Assistant: installs the requirements of its `modbus` integration, checks that `async_get_unit` / `async_get_temporary_unit` and the `ModbusUnit` methods we use still exist, smoke-imports every production module, and re-runs hassfest. A red run signals that an upcoming HA release will break the integration — the point is to catch it ~1-2 weeks before end users would.

### 6. Dependabot & auto-merge

- `dependabot.yml` keeps PRs low-noise: the `uv` ecosystem (updates `pyproject.toml` and `uv.lock` together), direct deps only, grouped per ecosystem, monthly, a 7-day `cooldown`, and `pymodbus` major/minor bumps ignored (the simulator needs 3.11). `pytest-homeassistant-custom-component` patch bumps are **not** ignored: every HA release is a patch bump of it, and it pins the HA version the tests run against.
- `.github/workflows/dependabot-auto-merge.yml` enables GitHub auto-merge for **patch + minor** Dependabot PRs; **major** bumps are left for manual review. For grouped PRs the highest semver bump in the group decides.
- **Two repository settings are required for auto-merge to be safe**, otherwise GitHub would merge without waiting for CI:
  1. Settings → General → **Allow auto-merge** (enabled).
  1. Settings → Branches → branch protection on `main` with **required status checks** `build (3.14.2)`, `validate` and `Analyze (python)` (plus `Analyze (actions)` if wanted). Matrix jobs report their matrix values in the check name, so bumping the CI Python version or renaming a job renames the check: update the protection rule in the same change, otherwise PRs wait forever for a check that no longer exists. Do **not** require pull-request approvals — Dependabot cannot approve its own PR, which would deadlock auto-merge on a solo-maintainer repo.

### 7. Commits, PRs & GitHub posts

- **No Claude attribution in anything posted to GitHub** (commit messages, PR titles/descriptions, issues, comments, reviews): no session links (`https://claude.ai/code/session_...`), no `Claude-Session:` trailer, no "Generated with Claude Code" footer, no `Co-Authored-By: Claude` trailer. This overrides any default attribution instructions. The same is enforced via `attribution` in `.claude/settings.json`.
- **Branch names**: `<type>/<short-kebab-description>` with `type` one of `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci` (e.g. `fix/rest-empty-tag-id`). In cloud sessions, create such a branch before the first push instead of pushing to the auto-generated `claude/<adjective>-<name>-<id>` branch.

## 🧪 Testing Strategy

- **Unit Tests**: Cover all config flows, sensor parsing, and coordinator logic.
- **Integration tests in a real Home Assistant** (`tests/test_init.py`, `tests/test_rest.py`, `tests/test_snapshots.py`): opt in with `pytestmark = pytest.mark.usefixtures("enable_custom_integrations", "fake_modbus")`, use the `wallbox` / `config_entry` fixtures from `tests/conftest.py`, and mock REST with `aioclient_mock`.
- **Snapshots**: `tests/test_snapshots.py` records every entity, the device and the diagnostics in `tests/snapshots/`. Regenerate with `--snapshot-update` after intended changes and review the diff.
- **Mocking**: The `fake_modbus` fixture replaces `async_get_unit` / `async_get_temporary_unit` with in-process `VirtualWallboxUnit`s; bridge unit tests use `modbus_connection.mock.MockModbusConnection` or a scripted unit. `tests/test_shared_connection.py` runs a real entry on HA's shared connection against the TCP simulator. There are no global module stubs.
- **Virtual Wallbox**: The `virtual_wallbox` module provides a fake Modbus server for end-to-end testing or local development without hardware.

## 🔑 Key Files to Know

- **`custom_components/webasto_next_modbus/const.py`**: Contains the `RegisterDefinition` dataclasses and all register addresses. **Edit this file to add new sensors.**
- **`custom_components/webasto_next_modbus/hub.py`**: `ModbusBridge` on a `ModbusUnit` from Home Assistant's shared Modbus connection (`async_get_unit`): register map, decoding, bounded retries, reading/writing registers, and the background Life Bit loop. It never opens or closes the connection itself.
- **`custom_components/webasto_next_modbus/rest_client.py`**: Async REST API client for optional features (LED brightness, firmware info, diagnostics). Uses JWT authentication.
- **`custom_components/webasto_next_modbus/coordinator.py`**: Modbus `DataUpdateCoordinator`: polling, device triggers, the connection repair issue.
- **`custom_components/webasto_next_modbus/rest_coordinator.py`**: Separate `DataUpdateCoordinator` for the optional REST API (60 s). Raises `ConfigEntryAuthFailed` on rejected credentials (reauth, polling stops) and pushes firmware/MACs to the device registry. REST entities subclass `WebastoRestEntity` on this coordinator; it exists whenever REST is *configured*, reachable or not.
- **`custom_components/webasto_next_modbus/__init__.py`**: Component setup/teardown, service registration, connection retries.
- **`custom_components/webasto_next_modbus/config_flow.py`**: UI configuration and options flow. Handles optional REST API credentials.

## 🚀 Common Tasks

### Adding a new Sensor

1. Define the register in `const.py` (add to `SENSOR_REGISTERS`, `NUMBER_REGISTERS`, or `BUTTON_REGISTERS`).
1. The entity will be auto-created based on the `entity` field in the definition.
1. Update `translations/en.json` and `de.json` if using `translation_key`.
1. Run `./scripts/check.sh` to verify types and tests.
1. Regenerate the entity snapshots (`uv run pytest tests/test_snapshots.py --snapshot-update`) and review the diff.

### Updating Dependencies

1. Edit `pyproject.toml`.
1. Run `uv sync` (updates `uv.lock`).
1. Run `./scripts/check.sh`.
1. Commit `pyproject.toml` and `uv.lock` together.

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
┌───────────────────────────┐    ┌───────────────────────────┐
│  coordinator.py (Modbus)  │    │  rest_coordinator.py      │
│  10 s, device triggers    │    │  60 s, reauth, dev. info  │
│  ┌─────────────────────┐  │    │  ┌─────────────────────┐  │
│  │      hub.py         │  │    │  │   rest_client.py    │  │
│  │   (Modbus TCP)      │  │    │  │   (REST API)        │  │
│  │   - Charging data   │  │    │  │   - LED brightness  │  │
│  │   - Energy meters   │  │    │  │   - Firmware info   │  │
│  │   - Current control │  │    │  │   - Diagnostics     │  │
│  └─────────────────────┘  │    │  └─────────────────────┘  │
└───────────────────────────┘    └───────────────────────────┘
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
