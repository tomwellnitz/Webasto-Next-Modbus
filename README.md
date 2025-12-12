# Webasto Next Modbus for Home Assistant

> Bring Webasto Next / Ampure Unite wallboxes into Home Assistant with a Modbus TCP integration.

[![Release](https://img.shields.io/github/v/release/tomwellnitz/Webasto-Next-Modbus?display_name=release)](https://github.com/tomwellnitz/Webasto-Next-Modbus/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/tomwellnitz/Webasto-Next-Modbus/ci.yaml?branch=main)](https://github.com/tomwellnitz/Webasto-Next-Modbus/actions/workflows/ci.yaml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange)](https://hacs.xyz)
[![License](https://img.shields.io/github/license/tomwellnitz/Webasto-Next-Modbus.svg)](LICENSE)
[![Maintenance](https://img.shields.io/maintenance/yes/2025.svg)](https://github.com/tomwellnitz/Webasto-Next-Modbus/commits/main)

> 📚 **Documentation Portal**: Start with [`docs/README.md`](docs/README.md) for architecture notes, development guides, and support resources.
>
> ⚠️ **Disclaimer**: This project is a community-maintained integration that is not affiliated with, endorsed, or supported by Webasto, Ampure, or the Home Assistant project.

## ✨ Features

- 🔌 **Guided Onboarding**: Live connection validation and duplicate protection.
- ⚡ **Rich Entities**: Async coordinator for stable refreshes and immediate state updates.
- ��️ **Service Helpers**: Session start/stop, keep-alive frames, dynamic current, and fail-safe parameters.
- 🤖 **Automations**: Device triggers and powerful blueprints included.
- 🛡️ **Reliable**: Comprehensive tests, virtual wallbox simulator, and robust error handling.

## 🚀 Quick Start

### Requirements

- **Home Assistant**: 2024.6 or newer.
- **Hardware**: Webasto Next or Ampure Unite wallbox.
- **Network**: Reachable over Modbus TCP (default port `502`).

### Installation

<details open>
<summary><b>Option 1: HACS (Recommended)</b></summary>

1. Open HACS in Home Assistant.
2. Go to **Integrations** → **⋮** → **Custom repositories**.
3. Add `https://github.com/tomwellnitz/Webasto-Next-Modbus` as type **Integration**.
4. Install **Webasto Next Modbus** and restart Home Assistant.

</details>

<details>
<summary><b>Option 2: Manual Installation</b></summary>

1. Create `custom_components/webasto_next_modbus` in your config directory.
2. Copy the contents of `custom_components/webasto_next_modbus/` from this repo.
3. Restart Home Assistant.

</details>

### Configuration

1. Go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **Webasto Next Modbus**.
3. Enter your wallbox details:
    - **Host**: IP address or hostname.
    - **Port**: Default `502`.
    - **Unit ID**: Default `255`.
    - **Variant**: Select your hardware (11kW or 22kW).

## 📊 Usage

### Entities

| Category | Description |
| :--- | :--- |
| **Sensors** | Charging state, IEC status, current/power per phase, session energy, EV limits, serial number, firmware. |
| **Numbers** | Dynamic charging current limit, fail-safe current, fail-safe timeout. |
| **Buttons** | `Start Charging`, `Stop Charging`, `Send Keepalive`. |

### Services

Available under the `webasto_next_modbus` domain:

| Service | Description |
| :--- | :--- |
| `set_current` | Set dynamic charging current (0–32 A). |
| `set_failsafe` | Configure fail-safe current and timeout (6–120 s). |
| `start_session` | Start charging (FastCharge). |
| `stop_session` | Stop charging (FullCharge). |
| `send_keepalive` | Manually trigger keep-alive frame. |

> **Note**: The integration automatically handles the "Life Bit" keepalive in the background to prevent failsafe mode.

## �� Automations & Blueprints

This integration includes blueprints to jump-start your smart charging. Import them via **Settings** → **Automations** → **Blueprints**.

### 🎯 Charge Target (kWh)
Charges a specific amount of energy (e.g., 10 kWh) and then stops.
- **Requires**: `input_number` (Target), `input_boolean` (Active Switch).

### 🔋 Charge Until Full (Auto-Stop)
Detects when the battery is full (power drops below threshold) and stops.
- **Requires**: Wallbox power sensor.

### ☀️ Solar Surplus Optimizer
Adjusts charging current based on grid export to maximize self-consumption.
- **Requires**: Grid power sensor (negative = export).

### ⚡ FastCharge/FullCharge (Legacy)
Simple toggle control.
- **Requires**: Two `input_boolean` helpers.

## 🛠️ Troubleshooting

- **Connection Failed**: Check IP, Port (502), and Unit ID (255). Verify network reachability.
- **Stale Data**: Check logs. The integration retries transient errors automatically.
- **Diagnostics**: Go to the integration entry → **⋮** → **Download diagnostics**.

For detailed support, see [`docs/support.md`](docs/support.md).

## 👨‍💻 Development

Want to contribute? Great!

1. **Setup**: Install `uv` and run `uv sync`.
2. **Test**: Run `uv run pytest`.
3. **Lint**: Run `uv run ruff check .`.
4. **Simulate**: Use `virtual-wallbox` to test without hardware.

See [`docs/development.md`](docs/development.md) for the full guide.

## 📄 License & Credits

- **License**: MIT. See [`LICENSE`](LICENSE).
- **Credits**: Special thanks to **[@cdrfun](https://github.com/cdrfun)** for inspiration on the advanced blueprints.
