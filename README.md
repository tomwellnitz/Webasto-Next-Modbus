# Webasto Next for Home Assistant

> Bring Webasto Next / Ampure Unite wallboxes into Home Assistant via Modbus TCP and REST API.

[![Release](https://img.shields.io/github/v/release/tomwellnitz/Webasto-Next-Modbus?display_name=release)](https://github.com/tomwellnitz/Webasto-Next-Modbus/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/tomwellnitz/Webasto-Next-Modbus/ci.yaml?branch=main)](https://github.com/tomwellnitz/Webasto-Next-Modbus/actions/workflows/ci.yaml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange)](https://hacs.xyz)
[![License](https://img.shields.io/github/license/tomwellnitz/Webasto-Next-Modbus.svg)](LICENSE)
[![Maintenance](https://img.shields.io/maintenance/yes/2025.svg)](https://github.com/tomwellnitz/Webasto-Next-Modbus/commits/main)

> 📚 **Documentation Portal**: Start with [`docs/README.md`](docs/README.md) for architecture notes, development guides, and support resources.
>
> ⚠️ **Disclaimer**: This project is a community-maintained integration that is not affiliated with, endorsed, or supported by Webasto, Ampure, or the Home Assistant project.

## ✨ Features

- 🔌 **Guided Onboarding**: Auto-discovery (Zeroconf), live connection validation, and duplicate protection.
- ⚡ **Rich Entities**: Async coordinator for stable refreshes and immediate state updates.
- 🛠️ **Service Helpers**: Session start/stop, keep-alive frames, dynamic current, and fail-safe parameters.
- 🌐 **REST API Integration**: Optional connection to the wallbox REST API for LED control, diagnostics, and more.
- 🤖 **Automations**: Device triggers and powerful blueprints included.
- 🛡️ **Reliable**: Comprehensive tests, virtual wallbox simulator, and robust error handling.

## 🚀 Quick Start

### Requirements

- **Home Assistant**: 2026.5.0 or newer (requires Python 3.14.2; older HA users should stay on `1.1.5`).
- **Hardware**: Webasto Next or Ampure Unite wallbox.
- **Network**: Reachable over Modbus TCP (default port `502`).

### Installation

<details open>
<summary><b>Option 1: HACS (Recommended)</b></summary>

1. Open HACS in Home Assistant.
1. Go to **Integrations** → **⋮** → **Custom repositories**.
1. Add `https://github.com/tomwellnitz/Webasto-Next-Modbus` as type **Integration**.
1. Install **Webasto Next** and restart Home Assistant.

</details>

<details>
<summary><b>Option 2: Manual Installation</b></summary>

1. Create `custom_components/webasto_next_modbus` in your config directory.
1. Copy the contents of `custom_components/webasto_next_modbus/` from this repo.
1. Restart Home Assistant.

</details>

### Configuration

#### Option 1: Auto-Discovery (Recommended)

1. Ensure your wallbox is on the same network as Home Assistant.
1. Go to **Settings** → **Devices & Services**.
1. Look for the **Discovered** section.
1. Click **Configure** on the Webasto Next entry.

#### Option 2: Manual Setup

1. Go to **Settings** → **Devices & Services** → **Add Integration**.
1. Search for **Webasto Next**.
1. Enter your wallbox details:
   - **Host**: IP address or hostname (e.g., `192.168.1.50` or `webasto.local`).
   - **Port**: Default `502`.
   - **Unit ID**: Default `255`.
   - **Variant**: Select your hardware (11kW or 22kW).

#### Optional: REST API Configuration

The REST API provides additional features not available via Modbus (LED control, firmware info, diagnostics).

1. Go to the integration entry → **⋮** → **Configure**.
1. Enable **REST API Features**.
1. Enter your wallbox web interface credentials:
   - **Username**: Default `admin`.
   - **Password**: Your wallbox password.

> **Note**: REST API credentials are stored securely in Home Assistant's config entries.

## 📊 Usage

### Entities

| Category | Description |
| :--- | :--- |
| **Sensors** | Charge point state, charging state, EVSE state, cable state, fault code, current/power per phase, total energy, session energy, session times, EV limits, smart vehicle detection. |
| **Numbers** | Dynamic charging current limit (0–32 A), fail-safe current (6–32 A), fail-safe timeout (6–120 s). |
| **Buttons** | `Start Charging`, `Stop Charging`, `Send Keepalive`. |

#### REST API Entities (Optional)

When REST API is enabled, additional entities become available:

| Category | Description |
| :--- | :--- |
| **Sensors** | Firmware versions (Comboard/Powerboard SW & HW), plug cycles, error counter, signal voltages (L1/L2/L3), active errors, free charging tag ID. |
| **Numbers** | LED brightness (0–100%). |
| **Switches** | Free charging toggle. |
| **Buttons** | Restart wallbox. |

### Services

Available under the `webasto_next_modbus` domain:

| Service | Description |
| :--- | :--- |
| `set_current` | Set dynamic charging current (0–32 A). |
| `set_failsafe` | Configure fail-safe current (6–32 A) and optional timeout (6–120 s). |
| `start_session` | Start charging (FastCharge). |
| `stop_session` | Stop charging (FullCharge). |
| `send_keepalive` | Manually trigger keep-alive frame. |

#### REST API Services (Optional)

| Service | Description |
| :--- | :--- |
| `set_led_brightness` | Set LED brightness (0–100%). |
| `set_free_charging` | Enable or disable free charging mode. |
| `restart_wallbox` | Trigger a system restart. |

> **Note**: The integration automatically handles the "Life Bit" keepalive in the background to prevent failsafe mode.

## 🤖 Automations & Blueprints

This integration includes blueprints to jump-start your smart charging. Import them via **Settings** → **Automations** → **Blueprints**.

### ⚡ FastCharge / FullCharge Control

Start or stop charging sessions using simple toggle switches.

- **Required Helpers**:
  - `input_boolean` (e.g., `input_boolean.fastcharge`): Toggle to start charging.
  - `input_boolean` (e.g., `input_boolean.fullcharge`): Toggle to stop charging.

### 🎯 Charge Target (kWh)

Charges a specific amount of energy (e.g., 10 kWh) and then stops.

- **Required Helpers**:
  - `input_number` (e.g., `input_number.target_energy`): Set target amount (Unit: `kWh`).
  - `input_boolean` (e.g., `input_boolean.charge_target_active`): Master switch for this logic.

### 🔋 Charge Until Full (Auto-Stop)

Detects when the battery is full (power drops below threshold) and stops.

- **Requires**: Wallbox power sensor (provided by integration).

### ☀️ Solar Surplus Optimizer

Adjusts charging current based on grid export to maximize self-consumption.

- **Requires**: Grid power sensor (negative value = export).

## 🛠️ Troubleshooting

- **Connection Failed**: Check IP, Port (e.g. 502), and Unit ID (255). Verify network reachability.
- **Stale Data**: Check logs. The integration retries transient errors automatically.
- **Diagnostics**: Go to the integration entry → **⋮** → **Download diagnostics**.

For detailed support, see [`docs/support.md`](docs/support.md).

## 👨‍💻 Development

Want to contribute? Great!

1. **Setup**: Install `uv` and run `uv sync`.
1. **Test**: Run `uv run pytest`.
1. **Lint**: Run `uv run ruff check .`.
1. **Simulate**: Use `virtual-wallbox` to test without hardware.

See [`docs/development.md`](docs/development.md) for the full guide.

## 📄 License & Credits

- **License**: MIT. See [`LICENSE`](LICENSE).
- **Credits**: Special thanks to **[@cdrfun](https://github.com/cdrfun)** for inspiration on the advanced blueprints.
