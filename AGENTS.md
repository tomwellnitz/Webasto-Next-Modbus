# 🤖 AI Agent Guide for Webasto Next Modbus

This document provides context and guidelines for AI agents working on this codebase. It summarizes the architecture, tooling, and coding standards to ensure consistent and high-quality contributions.

## 🌍 Project Overview

**Webasto Next Modbus** is a custom integration for Home Assistant that communicates with Webasto Next and Ampure Unite wallboxes via Modbus TCP.

- **Domain**: `webasto_next_modbus`
- **Communication**: Modbus TCP (using `pymodbus`)
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
│   ├── entity.py                           # Base entity class
│   └── ...                                 # Platform files (sensor, number, button)
├── tests/                                  # Test suite
├── virtual_wallbox/                        # Simulator for testing/development
├── scripts/                                # Utility scripts
│   └── check.sh                            # Main CI check script
├── docs/                                   # Documentation
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

## 🧪 Testing Strategy

- **Unit Tests**: Cover all config flows, sensor parsing, and coordinator logic.
- **Mocking**: Use `unittest.mock` to mock the `ModbusBridge` and `pymodbus` client.
- **Virtual Wallbox**: The `virtual_wallbox` module provides a fake Modbus server for end-to-end testing or local development without hardware.

## 🔑 Key Files to Know

- **`custom_components/webasto_next_modbus/const.py`**: Contains the `RegisterDefinition` dataclasses and all register addresses. **Edit this file to add new sensors.**
- **`custom_components/webasto_next_modbus/hub.py`**: Handles the low-level Modbus TCP connection, reading/writing registers, and the background Life Bit loop.
- **`custom_components/webasto_next_modbus/coordinator.py`**: Manages the polling interval and data distribution to entities.
- **`custom_components/webasto_next_modbus/__init__.py`**: Component setup/teardown, service registration, connection retries.
- **`custom_components/webasto_next_modbus/config_flow.py`**: UI configuration and options flow.

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
