# Support & Troubleshooting

## Before Opening a Ticket

1. **Check the Basics**: Ensure your wallbox is powered on and reachable via network.

1. **Download Diagnostics**:

   - Go to **Settings** → **Devices & Services** → **Webasto Next**.
   - Click the **⋮** menu → **Download diagnostics**.
   - *Attach this JSON file to your issue!*

1. **Enable Debug Logging**:
   Add this to your `configuration.yaml` to see what's happening under the hood:

   ```yaml
   logger:
     default: info
     logs:
       custom_components.webasto_next_modbus: debug
   ```

## Where to Ask

| Topic | Channel |
| :--- | :--- |
| **"How do I...?"** | [GitHub Discussions](https://github.com/tomwellnitz/Webasto-Next-Modbus/discussions) |
| **"It's broken!"** | [GitHub Issues](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues) (Please attach diagnostics!) |
| **"I have an idea!"** | [Feature Requests](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues) |

## Known limitations

See the [Known limitations](../README.md#known-limitations) section in the README for the verified, up-to-date list (single Modbus client at a time, Modbus off by default, no auto-discovery, REST self-signed certificate, Unite three-phase switching firmware-dependent, …).

## Security

Found a vulnerability? Please report it via **GitHub Security Advisories** or open a private issue if available. Do not post public exploits.
