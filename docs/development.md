# Developer Guide

This document describes how to set up a local development environment, run the tooling suite, and inspect diagnostic data when iterating on the Webasto Next Modbus integration.

## Prerequisites

- Python 3.12 or newer
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

### Optional: Home Assistant test instance via Docker Compose

For manual testing a lean Docker Compose stack is available:

```bash
docker compose -f docker/docker-compose.yml up -d
```

The compose file mounts `ha-config/` as `/config` and bind-mounts `custom_components/` plus `blueprints/` directly from your checkout. Code changes immediately propagate into the running container; restart to reload Python modules:

```bash
docker compose -f docker/docker-compose.yml restart homeassistant
```

On first start Home Assistant seeds the entire configuration inside `ha-config/`. The folder is ignored by git (except for `.gitkeep`) so personal settings remain local.

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

## Virtual wallbox simulator

The repository bundles a lightweight Modbus simulator under `virtual_wallbox/`. It mirrors the register map of the real device and powers the automated tests. You can use it in three ways:

1. **Pytest fixtures** – Import `register_virtual_wallbox` or consume the `default_virtual_wallbox` fixture defined in `tests/conftest.py` to back integration tests with a deterministic register set.
2. **Ad-hoc scripts** – Create a scenario and patch the integration to rely on `virtual_wallbox.simulator.FakeAsyncModbusTcpClient`, e.g.:

   ```python
   import asyncio

   from custom_components.webasto_next_modbus.hub import ModbusBridge
   from virtual_wallbox.simulator import (
       FakeAsyncModbusTcpClient,
       FakeModbusException,
       Scenario,
       register_virtual_wallbox,
   )

   # Point the bridge to a simulated wallbox.
   from custom_components.webasto_next_modbus import hub as hub_module

   hub_module._ASYNC_CLIENT_CLASS = None
   hub_module._MODBUS_EXCEPTION_CLASS = None
   hub_module._ensure_pymodbus = lambda: (FakeAsyncModbusTcpClient, FakeModbusException)

   with register_virtual_wallbox(scenario=Scenario(values={"charging_state": 1})):  # host=127.0.0.1:15020
       bridge = ModbusBridge("127.0.0.1", 15020, 255)
       data = asyncio.get_event_loop().run_until_complete(bridge.async_read_data())
   ```

3. **Custom scenarios** – Extend `Scenario(write_actions=...)` to emulate state transitions (e.g. `session_command` start/stop) by updating multiple registers atomically.

The simulator ensures you can iterate on new registers or triggers without waiting for physical hardware. When the actual wallbox becomes available, keep the simulator in CI while adding periodic hardware smoke tests for regression coverage.

### Run the simulator as a Modbus TCP server

Install the package in editable mode (as described above) and run:

```bash
virtual-wallbox --host 0.0.0.0 --port 15020
```

Useful options:

- `--scenario path/to/file.json` loads a JSON description with `values` and optional `write_actions`.
- `--set key=value` (repeatable) overrides individual registers before the server starts.
- `--unit 42` advertises a custom Modbus unit ID.

The server shares the same logic as the test fixtures, so changes to register definitions automatically flow into the CLI. Press `Ctrl+C` to stop the process.

### Automated smoke test against Home Assistant

Once Home Assistant is connected to the integration and the virtual wallbox, run the smoke-test CLI to exercise the critical code paths (`set_current`, `set_failsafe`, `send_keepalive`, `start_session`, `stop_session`) and verify entity updates (`charging_state`, `charge_power`, fail-safe numbers).

Prerequisites:

- Running Home Assistant instance with the integration configured against the virtual wallbox.
- Long-lived access token with administrator privileges (**Profile → Security → Create Token**).
- Copy the token verbatim (no smart quotes or ellipses) to avoid HTTP header parsing issues.

Example invocation (adapt host/port/token to your setup):

```bash
HA_TOKEN="<your-token>" webasto-smoke \
    --ha-url http://127.0.0.1:8123 \
    --device-host 127.0.0.1 \
    --unit-id 255 \
    --set-current 18 \
    --failsafe-amps 14 \
    --failsafe-timeout 90 \
    --entity-prefix webasto_next_wallbox
```

The script exits successfully once all expected state transitions propagate. Failures are surfaced with actionable messages (missing entities, authentication errors, Modbus values not updating). Increase `--timeout` or `--poll-interval` if your environment updates slowly.

If entities were renamed, adjust `--entity-prefix` to the new name (for example `webasto_next_garage_wallbox`). The prefix covers everything after the entity domain (`sensor.`, `number.`, etc.).

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
