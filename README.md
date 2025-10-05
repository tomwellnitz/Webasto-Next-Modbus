# Webasto Next Modbus for Home Assistant

> Bring Webasto Next / Ampure Unite wallboxes into Home Assistant with a production-ready Modbus TCP integration.

[![Release](https://img.shields.io/github/v/release/tomwellnitz/Webasto-Next-Modbus?display_name=release)](https://github.com/tomwellnitz/Webasto-Next-Modbus/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/tomwellnitz/Webasto-Next-Modbus/ci.yaml?branch=main)](https://github.com/tomwellnitz/Webasto-Next-Modbus/actions/workflows/ci.yaml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange)](https://hacs.xyz)

## At a glance

- Guided onboarding flow with live connection validation and duplicate protection.
- Rich entity set backed by an async coordinator for stable refreshes and immediate state updates after writes.
- First-class service helpers for session start/stop, keep-alive frames, dynamic current, and fail-safe parameters.
- Device triggers and an optional automation blueprint to jump-start home automations.
- Comprehensive tests, a virtual wallbox simulator, and documented release workflows for confident production rollouts.

## Table of contents

- [Quick start](#quick-start)
- [Configuration & usage](#configuration--usage)
- [Monitoring & automations](#monitoring--automations)
- [Troubleshooting & diagnostics](#troubleshooting--diagnostics)
- [Localization](#localization)
- [Development & testing](#development--testing)
- [Operations & release playbook](#operations--release-playbook)
- [Project resources](#project-resources)
- [License](#license)

## Quick start

### Requirements

- Home Assistant 2024.6 or newer (tested against the current stable release).
- A Webasto Next or Ampure Unite wallbox reachable over Modbus TCP (default port `502`).
- Network reachability from Home Assistant to the wallbox and the correct Modbus unit ID (factory default `255`).

### Installation via HACS (recommended)

1. Open HACS in Home Assistant and browse to **Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/tomwellnitz/Webasto-Next-Modbus` as a custom repository of type **Integration**.
3. Install **Webasto Next Modbus** and restart Home Assistant when prompted.

### Manual installation

1. Create `custom_components/webasto_next_modbus` inside your Home Assistant configuration directory.
2. Copy the contents of `custom_components/webasto_next_modbus/` from this repository into that directory.
3. Restart Home Assistant to load the integration.

### Optional: local Home Assistant stack with Docker Compose

A minimal Docker Compose file in `docker/docker-compose.yml` starts Home Assistant with this repository mounted live:

```bash
docker compose -f docker/docker-compose.yml up -d
```

The compose stack binds `ha-config/` as `/config` and mounts `custom_components/` and `blueprints/` directly from your checkout, so code edits are instantly available. Restart the container to reload Python modules:

```bash
docker compose -f docker/docker-compose.yml restart homeassistant
```

Prerequisites:

- Docker Desktop (macOS/Windows) or a compatible Docker Engine.
- Port `8123` on the host must be free.

Access the UI at <http://localhost:8123>. Duplicate the compose file with a different `ha-config` mount when you need multiple sandboxes.

### Post-installation checklist

- Add the integration through **Settings → Devices & Services → Add Integration** and search for “Webasto Next Modbus”.
- Confirm that the onboarding wizard validates the Modbus connection and stores the expected host/port/unit ID combination.
- Verify that the new device exposes sensors, numbers, and buttons after the first coordinator refresh.

## Configuration & usage

During the onboarding wizard you will be asked for:

- **Host** – IP address or DNS hostname of the wallbox.
- **Port** – Modbus TCP port (default `502`).
- **Unit ID** – Modbus unit ID/slave ID (default `255`).
- **Scan interval** – Polling interval in seconds (`2–60`, default `5`).
- **Variant** – Hardware tier (11 kW/16 A or 22 kW/32 A). Write actions are automatically clamped to the selected limit.

The config flow validates credentials by reading a known register set and stores a deterministic unique ID (`<host>-<unit_id>`) to avoid duplicate entries.

### Entity overview

| Category | Highlights |
| --- | --- |
| Sensors | Charging state, IEC 61851 status, per-phase current/voltage, instantaneous power, session energy, EV limits, timestamps, serial number, charge point ID, firmware, rated power, phase configuration. |
| Numbers | Dynamic charging current, fail-safe current, fail-safe timeout. |
| Buttons | `Send Keepalive`, `Start Charging`, `Stop Charging` for quick manual overrides. |

All entities are delivered through a shared `DataUpdateCoordinator` to guarantee consistent snapshots for dashboards and automations.

### Service helpers

The following services are available under the `webasto_next_modbus` domain. When multiple wallboxes are configured provide `config_entry_id` to target a specific device.

| Service | Description |
| --- | --- |
| `webasto_next_modbus.set_current` | Set the dynamic charging current (`0–32 A`, clamped to the configured variant). |
| `webasto_next_modbus.set_failsafe` | Configure fail-safe current and optional timeout (`6–120 s`). |
| `webasto_next_modbus.send_keepalive` | Trigger the keep-alive frame to maintain connectivity without changing the charging state. |
| `webasto_next_modbus.start_session` | Start a charging session (mirrors the on-wallbox FastCharge helper). |
| `webasto_next_modbus.stop_session` | Stop the active charging session (mirrors the FullCharge helper). |

Each service writes to the appropriate Modbus register and forces an immediate refresh so dashboards reflect state changes right away.

## Monitoring & automations

### Device triggers

| Trigger ID | Description |
| --- | --- |
| `charging_started` | Wallbox transitioned from idle to charging. |
| `charging_stopped` | Charging session ended, wallbox returned to idle. |
| `connection_lost` | Coordinator detected a communication failure. |
| `connection_restored` | Connection recovered after a failure. |
| `keepalive_sent` | Manual keep-alive frame was dispatched. |

Create automations via **Settings → Automations & Scenes → Add Automation → Device Trigger** and select your wallbox device.

### Blueprint

`blueprints/automation/webasto_next_modbus/fastcharge_fullcharge.yaml` links two helpers (for example “FastCharge” and “FullCharge”) to the `start_session` and `stop_session` services. Import the blueprint through Home Assistant’s Blueprint UI, select the config entry ID of your wallbox, and pick two toggles to act as virtual buttons.

### Virtual wallbox simulator

Install the project with the `dev` extra and run the CLI to expose a Modbus TCP simulator:

```bash
virtual-wallbox --host 0.0.0.0 --port 15020
```

Point a development Home Assistant instance to the simulator for regression testing or feature development. Scenario files and advanced options are documented in `docs/development.md`.

## Troubleshooting & diagnostics

- **Connection failures** – Check reachability with `ping`, verify TCP port `502` is open, and make sure the unit ID matches the wallbox configuration.
- **Stale data** – The coordinator retries transient errors three times and raises a persistent notification if connectivity remains down. Review the Home Assistant log for detailed stack traces.
- **Diagnostics export** – Download diagnostics via **Settings → Devices & Services → Webasto Next Modbus → ⋮ → Download diagnostics** to inspect register snapshots and error history.
- **Debug logging** – Add the following to `configuration.yaml` to surface detailed Modbus traces:

  ```yaml
  logger:
    default: info
    logs:
      custom_components.webasto_next_modbus: debug
  ```

## Localization

English is the default language. A German translation ships in `translations/de.json`; other locales fall back to English.

## Development & testing

- Create a virtual environment, install the project with `pip install -e '.[dev]'`, and run `pytest` to execute the full test suite.
- Use `python -m ruff check` for static analysis and formatting guardrails.
- The virtual wallbox simulator (see above) mirrors the register map and powers both automated and manual tests.
- `docker/docker-compose.yml` provides an opt-in Home Assistant sandbox that mounts the integration live for UI-level testing.
- Development documentation lives in `docs/development.md`.

## Operations & release playbook

- Track notable changes in `CHANGELOG.md` and keep the integration version in `custom_components/webasto_next_modbus/manifest.json` aligned with releases.
- Run `pytest` and `ruff` before tagging a release to ensure parity with CI.
- Tag releases (`git tag vX.Y.Z`) and publish GitHub release notes referencing the changelog entry.
- Submit branding assets to the upstream [`home-assistant/brands`](https://github.com/home-assistant/brands) repository—this integration no longer bundles local icons.

## Project resources

- [`docs/architecture.md`](docs/architecture.md) – register map, coordinator internals, and future work.
- [`docs/development.md`](docs/development.md) – environment setup, tooling, and smoke tests.
- [`CHANGELOG.md`](CHANGELOG.md) – release history.
- [Issue tracker](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues) – questions, bug reports, feature requests.

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for details.
