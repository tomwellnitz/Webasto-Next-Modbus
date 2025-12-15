# Webasto Next / Ampure Unite REST API Specification

> **Version**: 1.0.0\
> **Last Updated**: 2025-12-15\
> **Firmware Tested**: Comboard 3.1.16 / Powerboard 213.5.8.0

This document describes the REST API exposed by the Webasto Next and Ampure Unite wallbox web interface. The API is used by the React-based web interface and can be accessed programmatically.

## Overview

| Property | Value |
|----------|-------|
| **Base URL** | `https://<wallbox-ip>/api` |
| **Protocol** | HTTPS (self-signed certificate) |
| **Authentication** | JWT Bearer Token |
| **Content-Type** | `application/json` |

## Authentication

### Login

Obtain a JWT access token.

```http
POST /api/login
Content-Type: application/json

{
  "username": "admin",
  "password": "<password>"
}
```

**Response (200 OK)**:

```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

### Refresh Token

Refresh an expiring token.

```http
POST /api/refresh-token
Authorization: Bearer <access_token>
```

### Using the Token

Include the token in all subsequent requests:

```http
Authorization: Bearer <access_token>
Accept-Language: de  # Optional: de, en
```

______________________________________________________________________

## Dashboard Endpoints

### Get Dashboard Information

Returns the current status and summary information displayed on the dashboard.

```http
GET /api/dashboard-information
Authorization: Bearer <access_token>
```

**Response (200 OK)**:

```json
[
  {
    "key": "indicator",
    "label": "Status Indicator",
    "entries": [
      {
        "dashboardInformationEntryType": "simple-string-dashboard-information-entry",
        "key": "status-wallbox",
        "label": "Status Wallbox",
        "value": "OK",
        "color": "green",
        "isMainStatusEntry": true
      },
      {
        "key": "free-charging",
        "label": "Free Charging",
        "value": "ON"
      },
      {
        "key": "connectivity-status",
        "label": "Connectivity Status",
        "value": ""
      }
    ]
  },
  {
    "key": "summary",
    "label": "Summary",
    "entries": [
      {
        "key": "total-charging-sessions",
        "label": "Total Charging Sessions",
        "value": "28 Sessions"
      },
      {
        "key": "duration",
        "label": "Duration of current charging session",
        "value": "819.46 minutes"
      },
      {
        "key": "power",
        "label": "Current Energy",
        "value": "0.013 kWh"
      }
    ]
  },
  {
    "key": "ocpp-status",
    "label": "OCPP Status",
    "entries": [
      {
        "key": "charge-point-id",
        "label": "OCPP ChargeBoxIdentity (Charge PointID)",
        "value": "NEXT-WS110064"
      },
      {
        "key": "ocpp-state",
        "label": "OCPP State",
        "value": "SuspendedEV"
      }
    ]
  }
]
```

### Get Current Errors

Returns a list of currently active errors.

```http
GET /api/current-errors
Authorization: Bearer <access_token>
```

**Response (200 OK)**:

```json
[]
```

When errors are present:

```json
[
  {
    "errorCode": "ConnectorLockFailure",
    "errorDescription": "Lock mechanism failed",
    "timestamp": "2025-12-15T10:00:00Z"
  }
]
```

______________________________________________________________________

## Configuration Endpoints

### Get Configuration Structure

Returns the hierarchical structure of all configuration sections and groups.

```http
GET /api/configuration-structure
Authorization: Bearer <access_token>
```

**Response (200 OK)**:

```json
{
  "sections": [
    {
      "key": "auth",
      "label": "AUTHORIZATION",
      "groups": [
        {"key": "free-charging", "label": "Free Charging"}
      ]
    },
    {
      "key": "backend",
      "label": "BACKEND",
      "groups": [
        {"key": "connection", "label": "Connection"},
        {"key": "ocpp", "label": "OCPP"}
      ]
    },
    {
      "key": "hems",
      "label": "LOAD MANAGEMENT",
      "groups": [
        {"key": "modbus", "label": "Modbus"},
        {"key": "hems", "label": "HEMS - DLM"},
        {"key": "dlm", "label": "DLM"}
      ]
    },
    {
      "key": "network",
      "label": "NETWORK",
      "groups": [
        {"key": "wlan", "label": "WiFi"},
        {"key": "lan", "label": "LAN"}
      ]
    },
    {
      "key": "power",
      "label": "POWER",
      "groups": [
        {"key": "installation", "label": "Installation"},
        {"key": "randomised-Delay", "label": "Randomised Delay"},
        {"key": "Off-Peak-Charging", "label": "Off-Peak Charging"}
      ]
    },
    {
      "key": "profile",
      "label": "PROFILE",
      "groups": [
        {"key": "change-password", "label": "Change Password"}
      ]
    },
    {
      "key": "system",
      "label": "SYSTEM",
      "groups": [
        {"key": "general", "label": "General"},
        {"key": "statistics", "label": "Statistics"},
        {"key": "system-information", "label": "System Information"},
        {"key": "system-status", "label": "System State"},
        {"key": "firmware-update", "label": "Firmware Update"}
      ]
    }
  ]
}
```

### Get Section Configuration Fields

Returns all configuration fields for a specific section.

```http
GET /api/sections/{sectionKey}
Authorization: Bearer <access_token>
```

**Parameters**:

- `sectionKey`: One of `auth`, `backend`, `hems`, `network`, `power`, `profile`, `system`

**Response (200 OK)**:

```json
[
  {
    "fieldKey": "led-brightness",
    "fieldLabel": "LED brightness [%]",
    "groupKey": "general",
    "configurationFieldType": "number-configuration-field",
    "value": 10,
    "permission": {
      "permissionLevel": "WRITE"
    },
    "validation": {
      "min": 0,
      "max": 100
    }
  },
  {
    "fieldKey": "comboard-sw-version",
    "fieldLabel": "Comboard SW version",
    "groupKey": "system-information",
    "configurationFieldType": "readonly-configuration-field",
    "value": "3.1.16",
    "permission": {
      "permissionLevel": "READ"
    }
  }
]
```

### Update Configuration Fields

Update one or more configuration fields.

```http
POST /api/configuration-updates
Authorization: Bearer <access_token>
Content-Type: application/json

[
  {
    "fieldKey": "led-brightness",
    "value": 50,
    "configurationFieldUpdateType": "number-configuration-field-update"
  }
]
```

**Response (200 OK)**:

```json
{
  "success": true,
  "updatedFields": ["led-brightness"]
}
```

______________________________________________________________________

## Custom Actions

### Local Remote Start/Stop

Trigger a charging session start or stop.

```http
POST /api/custom-actions/local-remote-start
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "action": "start"  // or "stop"
}
```

### Restart System

Restart the wallbox.

```http
POST /api/custom-actions/restart-system
Authorization: Bearer <access_token>
```

### Factory Reset

Perform a factory reset (⚠️ destructive operation).

```http
POST /api/custom-actions/factory-reset
Authorization: Bearer <access_token>
```

### Skip Random Delay

Skip the current randomized delay during charging.

```http
POST /api/custom-actions/skip-random-delay
Authorization: Bearer <access_token>
```

______________________________________________________________________

## File Operations

### Upload File

Upload a file (e.g., firmware, certificates).

```http
POST /api/files/{fileKey}
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file: <binary data>
```

**Known file keys**:

- `upload-new-firmware` - Firmware update file
- `local-ca-cert` - Local CA certificate

______________________________________________________________________

## Complete Field Reference

### Section: auth (AUTHORIZATION)

| Field Key | Label | Type | Permission | Description |
|-----------|-------|------|------------|-------------|
| `free-charging` | Off/On | boolean | RW | Enable/disable free charging |
| `free-charging-alais` | ID tag for free charging | string | RW | RFID tag alias |
| `local-remote-start` | Local Remote Start/Stop | button | RW | Trigger action |

### Section: backend (BACKEND)

| Field Key | Label | Type | Permission | Description |
|-----------|-------|------|------------|-------------|
| `connection-type` | Connection type | select | RW | `no-backend`, `ocpp` |
| `connection-uri` | Connection URI | string | RW | OCPP backend URL |

### Section: hems (LOAD MANAGEMENT)

| Field Key | Label | Type | Permission | Description |
|-----------|-------|------|------------|-------------|
| `mode-modbus` | Mode | select | RW | `HEMS`, `DLM`, `OFF` |
| `communication-timeout-modbus` | Communication timeout [s] | number | RW | Timeout in seconds |
| `port-modbus` | Port | number | RW | Modbus TCP port (default: 502) |
| `connection-type-modbus` | Connection type | select | RW | `auto`, `tcp`, `rtu` |
| `safe-current-modbus-l1` | Safe current L1 [A] | number | RW | Fallback current L1 |
| `safe-current-modbus-l2` | Safe current L2 [A] | number | RW | Fallback current L2 |
| `safe-current-modbus-l3` | Safe current L3 [A] | number | RW | Fallback current L3 |
| `external-meter-ip-modbus` | External Meter IP | string | RW | DLM meter IP |
| `external-meter-port-modbus` | External Meter port | number | RW | DLM meter port |
| `external-meter-module-modbus` | External Meter Module | select | RW | Meter type |
| `external-meter-position-modbus` | External Meter position | select | RW | `including wallbox`, `excluding wallbox` |
| `free-buffer-modbus` | Free buffer [%] | number | RW | Safety margin |
| `register-refresh-interval-modbus` | Register refresh interval [s] | number | RW | Poll interval |
| `recalculation-interval-modbus` | Recalculation interval [s] | number | RW | DLM recalc interval |
| `current-limit-external-meter-modbus-l1` | Current limit L1 [A] | number | RW | Max current L1 |
| `current-limit-external-meter-modbus-l2` | Current limit L2 [A] | number | RW | Max current L2 |
| `current-limit-external-meter-modbus-l3` | Current limit L3 [A] | number | RW | Max current L3 |

### Section: network (NETWORK)

| Field Key | Label | Type | Permission | Description |
|-----------|-------|------|------------|-------------|
| `on-off-wlan` | WiFi Off/On | boolean | RW | Enable/disable WiFi |
| `wlan-ssid` | WiFi SSID | string | RW | Network name |
| `wlan-pre-shared-key` | Password | password | RW | WiFi password |
| `encryption-wlan` | Encryption | select | RW | `WPA2`, `WPA3` |
| `dhcp-on-off-wlan` | DHCP Off/On | boolean | RW | Use DHCP |
| `hostname-wlan` | Hostname | string | RW | WiFi hostname |
| `ip-address-wlan` | IP address (static) | string | RW | Static IP |
| `ip-subnet-wlan` | Subnet mask | string | RW | Subnet |
| `gateway-wlan` | Gateway | string | RW | Gateway IP |
| `dns-wlan` | DNS | string | RW | DNS server |
| `on-off-lan` | LAN Off/On | boolean | RW | Enable/disable LAN |
| `dhcp-on-off-lan` | DHCP Off/On | boolean | RW | Use DHCP |
| `hostname-lan` | Hostname | string | RW | LAN hostname |
| `ip-address-lan` | IP address (static) | string | RW | Static IP |
| `ip-subnet-lan` | Subnet mask | string | RW | Subnet |
| `gateway-lan` | Gateway | string | RW | Gateway IP |
| `dns-lan` | DNS | string | RW | DNS server |

### Section: power (POWER)

| Field Key | Label | Type | Permission | Description |
|-----------|-------|------|------------|-------------|
| `operator-current-limit` | Operator current limit [A] | number | RW | Max charging current |
| `phases-connected-to-charge-point` | Phases connected | number | RO | 1 or 3 |
| `installation-region` | Installation Region | select | RW | Grid standard |
| `randomised-delay-range` | Maximum Duration [s] | number | RW | Random delay range |
| `skip-randomized-delay` | Skip randomised Delay | button | RW | Skip action |
| `enable-off-peak` | Off-Peak Charging | boolean | RW | Enable/disable |
| `enable-off-peak-weekend` | Off-Peak on weekends | boolean | RW | Include weekends |
| `off-peak-period1-start` | Peak period 1 - Start | time | RW | HH:MM format |
| `off-peak-period1-stop` | Peak period 1 - Finish | time | RW | HH:MM format |
| `off-peak-period2-start` | Peak period 2 - Start | time | RW | HH:MM format |
| `off-peak-period2-stop` | Peak period 2 - Finish | time | RW | HH:MM format |

### Section: system (SYSTEM)

| Field Key | Label | Type | Permission | Description |
|-----------|-------|------|------------|-------------|
| `led-brightness` | LED brightness [%] | number | RW | 0-100 |
| `system-time-setting` | System Time-UTC | datetime | RO | Current UTC time |
| `local-system-time-setting` | Local System Time | datetime | RW | Local time |
| `time-zone` | Time zone | select | RW | Timezone string |
| `time-source` | Time source | select | RW | `NTP,HeartBeat` |
| `ntp-server-uri` | NTP server URI | string | RW | NTP server |
| `restart-system` | Restart system | button | RW | Trigger restart |
| `factory-reset` | Factory reset | button | RW | Trigger reset |
| `download-logfile` | Download Logfile | download | RW | Get logs |
| `volatile-loglevel` | Volatile log level | select | RW | Runtime log level |
| `persistent-loglevel` | Persistent log level | select | RW | Stored log level |
| `total-charging-sessions` | Charging session counter | number | RO | Total sessions |
| `duration-of-current-charging-session` | Duration [s] | number | RO | Current session |
| `power-of-current-charging-session` | Power [mW] | string | RO | L1, L2, L3 power |
| `error-counter` | Error counter | number | RO | Total errors |
| `plug-cycles` | Plug cycles | number | RO | Connector cycles |
| `manufacturer-serial-number` | Serial number | string | RO | Factory serial |
| `comboard-sw-version` | Comboard SW version | string | RO | Communication board FW |
| `powerboard-sw-version` | Powerboard SW version | string | RO | Power board FW |
| `comboard-hw-version` | Comboard HW version | string | RO | Communication board HW |
| `powerboard-hw-version` | Powerboard HW version | string | RO | Power board HW |
| `licensing-information` | Licensing information | download | RO | License info |
| `local-ca-cert` | Local CA certificate | download | RO | Certificate |
| `used-ocpp-version` | Used OCPP version | string | RO | V1.6J, V2.0, etc. |
| `ocpp-charge-box-identity-charge-point-id` | Charge point identity | string | RO | OCPP ID |
| `ocpp-state` | OCPP state | string | RO | Current OCPP state |
| `type-2-state` | Type2 state | string | RO | Connector state |
| `signal-current` | Signal current [A] | string | RO | L1, L2, L3 currents |
| `signal-voltage` | Signal voltage [V] | string | RO | L1, L2, L3 voltages |
| `ocpp-connection-state-backend` | OCPP connection state | string | RO | Backend status |
| `connected-interface-backend` | Connected interface | string | RO | Active interface |
| `free-charging-mode` | Free charging | string | RO | Enabled/Disabled |
| `errors` | List of active errors | string | RO | Error list |
| `interfaces` | List of interfaces | string | RO | Network interfaces |
| `MAC-Address WiFi` | MAC Address WiFi | string | RO | WiFi MAC |
| `MAC-Address Eth0` | MAC Address Ethernet | string | RO | Ethernet MAC |
| `upload-new-firmware` | Upload new firmware | upload | RW | Firmware file |

______________________________________________________________________

## Error Codes

| HTTP Status | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Invalid or expired token |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Endpoint does not exist |
| 500 | Internal Server Error |

______________________________________________________________________

## Rate Limiting

The wallbox web interface is designed for single-user access. Excessive API calls may cause:

- Slow responses (especially for `/api/sections/system`)
- Connection timeouts
- Temporary lockouts

**Recommended polling intervals**:

- Dashboard: 10-30 seconds
- Configuration: On-demand only
- Status checks: 5-10 seconds

______________________________________________________________________

## Security Considerations

1. **HTTPS with self-signed certificate**: Disable certificate verification in clients
1. **JWT tokens**: Store securely, implement refresh logic
1. **Password in plaintext**: The login API transmits passwords in plaintext (over HTTPS)
1. **No CORS**: API is designed for same-origin access only

______________________________________________________________________

## Comparison with Modbus Interface

| Feature | Modbus | REST API |
|---------|--------|----------|
| LED Brightness | ❌ | ✅ |
| Firmware Version | ❌ | ✅ |
| MAC Addresses | ❌ | ✅ |
| Plug Cycles | ❌ | ✅ |
| Error Counter | ❌ | ✅ |
| Network Config | ❌ | ✅ |
| Charging Current | ✅ | ✅ |
| Charging State | ✅ | ✅ |
| Energy Metering | ✅ | ✅ (less detail) |
| Real-time Updates | ✅ | ❌ (polling) |
| Local Control | ✅ | ✅ |
| Latency | Low | Higher |

______________________________________________________________________

## Example: Python Client

```python
import requests
import urllib3
urllib3.disable_warnings()

class WebastoAPI:
    def __init__(self, host: str, username: str, password: str):
        self.base_url = f"https://{host}/api"
        self.session = requests.Session()
        self.session.verify = False
        self._login(username, password)
    
    def _login(self, username: str, password: str):
        resp = self.session.post(
            f"{self.base_url}/login",
            json={"username": username, "password": password}
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        self.session.headers["Authorization"] = f"Bearer {token}"
    
    def get_dashboard(self) -> list:
        return self.session.get(f"{self.base_url}/dashboard-information").json()
    
    def get_section(self, section: str) -> list:
        return self.session.get(f"{self.base_url}/sections/{section}").json()
    
    def update_config(self, updates: list) -> dict:
        return self.session.post(
            f"{self.base_url}/configuration-updates",
            json=updates
        ).json()
    
    def set_led_brightness(self, brightness: int):
        return self.update_config([{
            "fieldKey": "led-brightness", 
            "value": brightness,
            "configurationFieldUpdateType": "number-configuration-field-update"
        }])
    
    def restart(self):
        return self.session.post(f"{self.base_url}/custom-actions/restart-system")

# Usage
api = WebastoAPI("192.168.178.109", "admin", "password")
print(api.get_dashboard())
api.set_led_brightness(50)
```
