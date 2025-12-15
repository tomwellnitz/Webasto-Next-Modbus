# REST API Integration - Feature Analysis

> **Date**: 2025-12-15\
> **Status**: ✅ Implemented

## Executive Summary

The Webasto Next / Ampure Unite wallbox REST API provides access to features that are **not** available via Modbus. This document analyzes which features can be usefully implemented in the Home Assistant integration.

## Feature Comparison: Modbus vs REST API

### Only Available via REST API ✨

| Feature | API Field | Type | Benefit for HA |
|---------|-----------|------|----------------|
| **LED Brightness** | `led-brightness` | number (0-100) | ⭐⭐⭐ High - Users want to control this |
| **Firmware Versions** | `comboard-sw-version`, `powerboard-sw-version` | readonly | ⭐⭐ Medium - Diagnostics |
| **MAC Addresses** | `MAC-Address WiFi/Eth0` | readonly | ⭐ Low - Diagnostics |
| **Plug Cycles** | `plug-cycles` | number | ⭐⭐ Medium - Wear monitoring |
| **Error Counter** | `error-counter` | number | ⭐⭐ Medium - Diagnostics |
| **Signal Voltages** | `signal-voltage` | readonly | ⭐⭐ Medium - Grid monitoring |
| **Active Errors** | `errors` | readonly | ⭐⭐⭐ High - Troubleshooting |
| **Free Charging** | `free-charging` | boolean | ⭐⭐⭐ High - Access control |
| **System Time** | `local-system-time-setting` | datetime | ⭐ Low - NTP solves this |
| **Timezone** | `time-zone` | select | ⭐ Low - One-time configuration |
| **Network Status** | `interfaces` | readonly | ⭐⭐ Medium - Diagnostics |
| **Off-Peak Charging** | `enable-off-peak`, time windows | boolean/time | ⭐⭐⭐ High - Automation |
| **Random Delay** | `randomised-delay-range` | number | ⭐⭐ Medium - Grid stability |

### Better via Modbus

| Feature | Reason |
|---------|--------|
| Set charging current | Lower latency, real-time |
| Charging state | Faster polling |
| Energy meters | Higher resolution |
| Session Start/Stop | Modbus is more reliable |

## Recommended Implementation

### Phase 1: Minimal Effort, High Benefit ⭐⭐⭐ ✅

**New Entities via REST API:**

1. **LED Brightness** (number entity) ✅

   - Type: `number` (0-100%)
   - API: `PUT /api/configuration-updates` with `led-brightness`
   - Benefit: Very frequently requested, easy to implement

1. **Firmware Versions** (sensor entities) ✅

   - Type: `sensor` (diagnostic)
   - API: `GET /api/sections/system`
   - Fields: `comboard-sw-version`, `powerboard-sw-version`
   - Benefit: Diagnostics, update monitoring

1. **Hardware Versions** (sensor entities) ✅

   - Type: `sensor` (diagnostic)
   - API: `GET /api/sections/system`
   - Fields: `comboard-hw-version`, `powerboard-hw-version`
   - Benefit: Hardware identification

1. **Hardware Statistics** (sensor entities) ✅

   - Type: `sensor` (diagnostic)
   - API: `GET /api/sections/system`
   - Fields: `plug-cycles`, `error-counter`
   - Benefit: Long-term monitoring

1. **MAC Addresses** (device info) ✅

   - Added to device_info when REST API is enabled
   - Fields: `MAC-Address WiFi`, `MAC-Address Eth0`

### Phase 1.5: Extended REST Features ⭐⭐⭐ ✅

6. **Free Charging Switch** (switch entity) ✅

   - Type: `switch`
   - API: `PUT /api/configuration-updates` with `free-charging`
   - Benefit: Access control without RFID

1. **Free Charging Tag ID** (sensor entity) ✅

   - Type: `sensor` (diagnostic)
   - API: `GET /api/sections/auth`
   - Field: `free-charging-alais`
   - Benefit: Track configured RFID tag

1. **Signal Voltages** (sensor entities) ✅

   - Type: `sensor` (diagnostic)
   - API: `GET /api/sections/system`
   - Fields: L1, L2, L3 voltages parsed from `signal-voltage`
   - Benefit: Grid monitoring, phase detection

1. **Active Errors** (sensor entity) ✅

   - Type: `sensor` (diagnostic)
   - API: `GET /api/current-errors`
   - Benefit: Error visibility without web UI

1. **Restart Button** (button entity) ✅

   - Type: `button`
   - API: `POST /api/custom-actions/restart-system`
   - Benefit: Troubleshooting without web UI

### Phase 2: Medium Effort ⭐⭐

11. **Off-Peak Charging Control** (switch + time entities)

    - Type: `switch` for On/Off, possibly `time` for time windows
    - Benefit: Electricity cost optimization

01. **Skip Random Delay** (button entity)

    - Type: `button`
    - API: `POST /api/custom-actions/skip-random-delay`
    - Benefit: Override random delay during charging

### Phase 3: Complete REST Integration ⭐

13. **Network Configuration** (diagnostic sensors)
01. **OCPP Backend Configuration** (readonly sensors)
01. **DLM Configuration** (already controllable via Modbus)

______________________________________________________________________

## Architecture

### Implemented: Separate REST Component

```
custom_components/webasto_next_modbus/
├── hub.py              # Modbus (as before)
├── rest_client.py      # REST API Client
├── coordinator.py      # Extended with REST data
└── ...
```

**Advantages:**

- Clear separation of responsibilities
- Modbus remains for real-time critical operations
- REST for configuration and diagnostics
- Can be independently enabled/disabled

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     Coordinator                             │
│  ┌─────────────────────┐    ┌─────────────────────┐         │
│  │      hub.py         │    │   rest_client.py    │         │
│  │   (Modbus TCP)      │    │   (REST API)        │         │
│  │   - Charging data   │    │   - LED brightness  │         │
│  │   - Energy meters   │    │   - Firmware info   │         │
│  │   - Current control │    │   - Diagnostics     │         │
│  │   - Session control │    │   - Free charging   │         │
│  └─────────────────────┘    └─────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

______________________________________________________________________

## Configuration Changes

### Config Flow Extension ✅

New optional fields:

- `rest_username` (optional, default: `admin`)
- `rest_password` (required when REST enabled)
- `enable_rest_api` (boolean, default: False)

```yaml
# Example in the UI
☑ Enable REST API Features
  Username: admin
  Password: ••••••••••
```

### Options Flow ✅

- Enable/disable REST API
- Update REST credentials
- LED Brightness directly configurable

______________________________________________________________________

## Implemented Entities

### REST API Entities

| Entity ID | Type | Device Class | Category | Description |
|-----------|------|--------------|----------|-------------|
| `number.webasto_led_brightness` | number | - | config | LED brightness 0-100% |
| `sensor.webasto_comboard_firmware` | sensor | - | diagnostic | e.g., "3.1.16" |
| `sensor.webasto_powerboard_firmware` | sensor | - | diagnostic | e.g., "213.5.8.0" |
| `sensor.webasto_comboard_hardware` | sensor | - | diagnostic | HW version |
| `sensor.webasto_powerboard_hardware` | sensor | - | diagnostic | HW version |
| `sensor.webasto_plug_cycles` | sensor | - | diagnostic | Plug cycle count |
| `sensor.webasto_error_count` | sensor | - | diagnostic | Error count |
| `sensor.webasto_signal_voltage_l1` | sensor | voltage | diagnostic | Phase 1 voltage |
| `sensor.webasto_signal_voltage_l2` | sensor | voltage | diagnostic | Phase 2 voltage |
| `sensor.webasto_signal_voltage_l3` | sensor | voltage | diagnostic | Phase 3 voltage |
| `sensor.webasto_free_charging_tag_id` | sensor | - | diagnostic | RFID tag alias |
| `sensor.webasto_active_errors` | sensor | - | diagnostic | Active error list |
| `switch.webasto_free_charging` | switch | - | config | Enable/disable free charging |
| `button.webasto_restart` | button | restart | config | System restart |

______________________________________________________________________

## Services

### REST API Services ✅

| Service | Description |
|---------|-------------|
| `set_led_brightness` | Set LED brightness (0-100%) |
| `set_free_charging` | Enable/disable free charging |
| `restart_wallbox` | Trigger system restart |

______________________________________________________________________

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| REST API changes | Check API version, graceful degradation |
| Token expiry | Auto-refresh implemented |
| Slow responses | Longer timeouts, caching |
| Password storage | Stored in HA config entries (standard HA security) |
| Parallel access | Rate limiting built in |

______________________________________________________________________

## Implementation Progress

### Completed ✅

1. [x] `rest_client.py` with all functions
1. [x] Config Flow for credentials
1. [x] Options Flow for REST toggle
1. [x] Coordinator extended with REST polling
1. [x] LED Brightness number entity
1. [x] Firmware version sensors (diagnostic)
1. [x] Hardware version sensors (diagnostic)
1. [x] Plug cycles + error counter sensors
1. [x] Signal voltage sensors (L1, L2, L3)
1. [x] Free charging switch entity
1. [x] Free charging tag ID sensor
1. [x] Active errors sensor
1. [x] Restart button entity
1. [x] REST API services (LED, free charging, restart)

### Pending

- [ ] Tests for REST client
- [ ] Off-Peak charging entities
- [ ] Skip random delay button
