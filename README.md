# Webasto Next Modbus for Home Assistant

> Mature custom integration that brings Webasto Next / Ampure Unite wallboxes into Home Assistant via Modbus TCP.

## Overview

This project exposes the complete Modbus register map of Webasto Next–series wallboxes to Home Assistant. It bundles a polished config flow, rich entities, built-in services, and automation triggers so you can monitor and control charging sessions without writing any low-level Modbus code yourself.

## Feature highlights

- Guided setup with automatic connection testing and duplicate protection.
- Coordinator-driven sensor, number, and button entities that cover all relevant holding/input registers.
- Write helpers for dynamic charging current, fail-safe settings, and manual keep-alive frames.
- Device triggers for charging state changes, connectivity events, and manual keep-alive actions.
- Extensive unit-test coverage and reusable development tooling based on `pytest` and `ruff`.

## Requirements

- Home Assistant 2024.12 or newer (tested against 2025.10 dev builds).
- Webasto Next or Ampure Unite wallbox reachable via Modbus TCP.
- Network access to TCP port 502 and the correct Modbus unit ID (factory default: `255`).

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant and navigate to **Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/tomwellnitz/Webasto-Next-Modbus` with the category **Integration**.
3. Install “Webasto Next Modbus” and restart Home Assistant when prompted.

### Manual installation

1. Create `custom_components/webasto_next_modbus` inside your Home Assistant configuration directory.
2. Copy the contents of this repository’s `custom_components/webasto_next_modbus/` folder into the directory you just created.
3. Restart Home Assistant to load the integration.

After the restart, go to **Settings → Devices & Services → Add Integration**, search for “Webasto Next Modbus”, and follow the on-screen wizard.

## Configuration

During onboarding you will be asked for:

- **Host** – IP address or hostname of the wallbox.
- **Port** – Modbus TCP port (default `502`).
- **Unit ID** – Modbus unit/slave ID (default `255`).
- **Scan interval** – Polling interval in seconds (`2–60`, default `5`).
- **Variant** – Choose between the 11 kW (16 A) and 22 kW (32 A) hardware tiers. The integration automatically clamps writable currents to this limit.

The config flow validates the connection immediately and stores a deterministic unique ID (`<host>-<unit_id>`) to prevent duplicate entries.

## Usage

### Entities

Once configured you will see:

- **Sensors** for charging state, per-phase current/voltage, power, energy totals, and diagnostic registers.
- **Number** entities for failsafe current, failsafe timeout, and the write-only charging current limit.
- **Button** entity (`Send Keepalive`) to manually trigger the wallbox keep-alive frame.

Refer to `custom_components/webasto_next_modbus/const.py` for the exact register mapping.

### Services

Three helper services live under the `webasto_next_modbus` domain:

```yaml
# Adjust the dynamic charging current (amps 0–32, clamped per variant)
service: webasto_next_modbus.set_current
data:
  amps: 16
  config_entry_id: YOUR_CONFIG_ENTRY_ID  # Only required if multiple wallboxes are configured

# Configure fail-safe current and optional timeout (seconds 6–120)
service: webasto_next_modbus.set_failsafe
data:
  amps: 20
  timeout_s: 60

# Send a manual keep-alive frame to the wallbox
service: webasto_next_modbus.send_keepalive
```

Every service writes the underlying Modbus register, raises the appropriate device trigger, and forces an immediate data refresh so entity state updates quickly.

### Automations and device triggers

The integration exposes five device triggers you can use in automations:

| Trigger | Description |
| ------- | ----------- |
| `charging_started` | Charger transitioned from idle to charging. |
| `charging_stopped` | Charging session ended. |
| `connection_lost` | Coordinator detected connectivity loss. |
| `connection_restored` | Connectivity recovered after a failure. |
| `keepalive_sent` | Manual keep-alive frame was triggered (button or service). |

Create automations via **Settings → Automations & Scenes → Add Automation → Device Trigger** and select the wallbox device.

## Manual verification checklist

1. Install the integration (HACS or manual) and restart Home Assistant.
2. Complete the config flow, then confirm device and entities are present and updating.
3. Create a test automation for one of the device triggers (for example `charging_started`) and verify the automation trace fires when expected.
4. Call the helper services from the Developer Tools and observe entity updates plus trigger emissions in the logbook.
5. (Optional) Enable debug logging to inspect Modbus requests and retry behaviour (see the [developer guide](docs/development.md) for instructions).

## Troubleshooting

- **Connection failures** – Verify the wallbox responds to `ping`, ensure TCP port 502 is reachable, and confirm the Modbus unit ID matches the wallbox configuration.
- **Stale data** – Watch Home Assistant’s log; the coordinator retries transient errors three times and raises a persistent notification if communication remains down.
- **Diagnostics** – Download the diagnostics dump from **Settings → Devices & Services → Webasto Next Modbus → ⋮ → Download diagnostics** for timestamps and error history.

## Development

Looking to contribute or run the integration locally? The complete developer workflow—including environment setup, lint/test commands, debug logging, manual verification, and the release checklist—is documented in [`docs/development.md`](docs/development.md).

## Localization

English strings ship as the default language; a full German translation is bundled in `translations/de.json`. When Home Assistant runs in another language it falls back to English automatically.

## Documentation

- `docs/architecture.md` explains the Modbus register mapping, coordinator layout, and planned enhancements.
- `CHANGELOG.md` captures release notes and noteworthy behaviour changes.

## Release process (HACS compatible)

1. Update the `version` field in `custom_components/webasto_next_modbus/manifest.json`.
2. Ensure `python -m ruff check` and `python -m pytest` succeed locally and document changes in `CHANGELOG.md`.
3. Commit the release and push to GitHub.
4. Create a Git tag matching the version (for example `v0.2.0`) and push it (`git push origin v0.2.0`).
5. Draft a GitHub release that references the tag and includes the changelog fragment.
6. Make the repository public (Settings → General → Change visibility) before publishing or submitting to HACS.
7. If the repository is not part of the HACS default list, remind users to add it as a custom repository; otherwise HACS will pick up the release automatically.

## Support and feedback

Please open a GitHub issue for questions, bug reports, or feature requests. Public tracking keeps discussions transparent and ensures improvements benefit everyone.
