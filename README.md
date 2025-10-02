# Webasto Next Modbus for Home Assistant

> ⚠️ The integration is still under construction; breaking changes may occur while we iterate. Feedback and test reports are welcome.

## Overview

This repository contains a custom Home Assistant integration that connects Webasto Next / Ampure Unite wallboxes via Modbus TCP. The integration is being implemented step-by-step in this session. The code already supports automatic discovery via config flow, entity platforms for sensors/numbers/buttons, and service helpers for advanced automation scenarios.

## Installation

### Via HACS (recommended once published)

1. Open HACS in Home Assistant and go to **Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/tomwellnitz/Webasto-Next-Modbus` with the category **Integration**.
3. HACS will list “Webasto Next Modbus”; install it and restart Home Assistant when prompted.

### Manual installation (development/testing)

1. Create the directory `custom_components/webasto_next_modbus` inside your Home Assistant configuration folder.
2. Copy the contents of `custom_components/webasto_next_modbus/` from this repository into that directory.
3. Restart Home Assistant to load the integration code.

After restarting, navigate to **Settings → Devices & Services → Add Integration** and search for “Webasto Next Modbus”. Follow the guided config flow to supply the connection details.

## Configuration

The config flow requests:

- **Host** – IP address or DNS name of the wallbox.
- **Port** – Modbus TCP port (defaults to `502`).
- **Unit ID** – Modbus unit/slave ID (factory default is `255`).
- **Scan interval** – Polling interval in seconds (2–60 seconds, defaults to `5`).

Validation happens immediately: the flow performs a test connection and prevents duplicate entries by generating a unique ID of `host-unit_id`.

## Development setup

The project ships with a `pyproject.toml` exposing a `dev` extra that installs Home Assistant, Modbus dependencies, and the full tooling stack (pytest, ruff, etc.). After creating and activating your virtual environment, run:

```bash
pip install -e '.[dev]'
```

Useful commands during development:

- Run the unit tests: `python -m pytest`
- Run the linter: `python -m ruff check custom_components/webasto_next_modbus tests`

For quick, repeatable checks, we recommend running both commands before committing changes.

## Development roadmap

- [x] Architecture outline
- [x] Core integration code
- [x] Config flow & options
- [x] Entity platforms (sensor, number, button)
- [x] Automated tests
- [x] Documentation polish

## Entities and services

After adding the integration via the config flow, Home Assistant will expose:

- Sensors for all readable Modbus registers, including power, current, and enumerated state values.
- Numbers for writable configuration registers such as fail-safe current, timeout, and the write-only charging current limit.
- A button entity to trigger the wallbox keep-alive frame on demand.

The integration also ships with three services under the `webasto_next_modbus` domain:

- `set_current` – adjust the dynamic charging current (0–32 A).
- `set_failsafe` – configure fail-safe current and optional timeout.
- `send_keepalive` – send a manual keep-alive frame, mirroring the button entity.

### Service payloads

Example YAML to set the charging current using the Home Assistant Services UI:

```yaml
service: webasto_next_modbus.set_current
data:
	amps: 16
	config_entry_id: YOUR_CONFIG_ENTRY_ID  # Required only if multiple wallboxes are configured
```

Setting fail-safe parameters with a timeout:

```yaml
service: webasto_next_modbus.set_failsafe
data:
	amps: 20
	timeout_s: 60
```

Sending an explicit keep-alive frame:

```yaml
service: webasto_next_modbus.send_keepalive
```

All services automatically clamp values to the safe ranges defined by the Modbus registers and trigger an immediate data refresh so entities update quickly.

## Testing and troubleshooting

- Run `python -m pytest -k services` to execute only the service-related unit tests while iterating on automations.
- Ensure the integration can reach the wallbox by pinging the host and verifying that TCP port 502 is open.
- If you encounter unexpected Modbus errors, enable Home Assistant’s debug logging for `custom_components.webasto_next_modbus` to inspect communication details.

## Further reading

- [Architecture notes](docs/architecture.md) provide background on register definitions, the coordinator design, and planned enhancements.

## Releasing via HACS

To publish a new version for HACS consumers:

1. Update the `version` field in `custom_components/webasto_next_modbus/manifest.json`.
2. Commit your changes and push to GitHub.
3. Create a Git tag matching the version (for example `v0.2.0`) and push it (`git push origin v0.2.0`).
4. Draft a GitHub release that references the tag and includes release notes.
5. If the repository is not part of the HACS default list, remind users to add it as a custom repository; otherwise HACS will automatically pick up the new release within an hour.

Stay tuned!
