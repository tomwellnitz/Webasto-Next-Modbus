# Developer Guide

This document describes how to set up a local development environment, run the tooling suite, and inspect diagnostic data when iterating on the Webasto Next Modbus integration.

## Prerequisites

- Python 3.11 or newer
- Access to a Home Assistant test installation (optional but recommended for manual validation)
- A Webasto Next / Ampure Unite wallbox reachable over the network when performing end-to-end tests

## Environment setup

```bash
# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the project in editable mode with development dependencies
pip install -e '.[dev]'
```

If you prefer Poetry or another environment manager, make sure the packages listed in the `dev` extra (pytest, pytest-homeassistant-custom-component, ruff, mypy, etc.) are available in your environment.

## Tooling commands

Run the full test suite:

```bash
python -m pytest
```

Lint the codebase (sensors, numbers, tests, etc.):

```bash
python -m ruff check custom_components/webasto_next_modbus tests
```

Lint only the integration package:

```bash
python -m ruff check custom_components/webasto_next_modbus
```

Execute a subset of tests while iterating on a feature:

```bash
python -m pytest -k services
```

## Debug logging in Home Assistant

Add the following to your Home Assistant `configuration.yaml` (or merge it with an existing logger configuration) to surface debug logs from the integration:

```yaml
logger:
  default: info
  logs:
    custom_components.webasto_next_modbus: debug
```

After reloading Home Assistant, detailed Modbus requests, retries, and trigger dispatches will be visible in the log.

## Manual verification workflow

1. Install the integration (via HACS or manual copy) and restart Home Assistant.
2. Complete the config flow with your wallbox’s host, port, unit ID, scan interval, and variant.
3. Confirm that the new device and all entities appear in **Settings → Devices & Services** and that sensor values update.
4. Invoke the helper services (`webasto_next_modbus.set_current`, `webasto_next_modbus.set_failsafe`, `webasto_next_modbus.send_keepalive`, `webasto_next_modbus.start_session`, `webasto_next_modbus.stop_session`) from the Developer Tools and watch for immediate entity refreshes plus device triggers.
5. Create a test automation for each device trigger to ensure dispatcher events fire as expected (`charging_started`, `charging_stopped`, `connection_lost`, `connection_restored`, `keepalive_sent`).
6. (Optional) Import the bundled FastCharge/FullCharge blueprint and confirm that toggling the assigned helpers triggers the new start/stop services.

## Release checklist

Before tagging a release or submitting to HACS:

1. Update `custom_components/webasto_next_modbus/manifest.json` with the new version.
2. Run `python -m ruff check` and `python -m pytest` to confirm the codebase is clean.
3. Document the changes in `CHANGELOG.md` under the appropriate heading.
4. Commit and push the release branch.
5. Tag the release (`git tag vX.Y.Z` + `git push origin vX.Y.Z`).
6. Draft a GitHub release that references the tag and includes the changelog excerpt.
7. Ensure the repository visibility is set to public before advertising the release.
8. If the repository is not yet part of the HACS default list, remind users to add it as a custom repository.
