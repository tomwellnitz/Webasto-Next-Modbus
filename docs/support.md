# 🆘 Support & Troubleshooting

Need help? We've got you covered.

## 🔍 Before Opening a Ticket

1. **Check the Basics**: Ensure your wallbox is powered on and reachable via network.
2. **Download Diagnostics**:
   - Go to **Settings** → **Devices & Services** → **Webasto Next Modbus**.
   - Click the **⋮** menu → **Download diagnostics**.
   - *Attach this JSON file to your issue!*
3. **Enable Debug Logging**:
   Add this to your `configuration.yaml` to see what's happening under the hood:
   ```yaml
   logger:
     default: info
     logs:
       custom_components.webasto_next_modbus: debug
   ```

## 💬 Where to Ask

| Topic | Channel |
| :--- | :--- |
| **"How do I...?"** | [GitHub Discussions](https://github.com/tomwellnitz/Webasto-Next-Modbus/discussions) |
| **"It's broken!"** | [GitHub Issues](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues) (Please attach diagnostics!) |
| **"I have an idea!"** | [Feature Requests](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues) |

## ⚠️ Known Limitations

- **Dynamic IP**: The integration expects a static IP. Please configure a DHCP reservation for your wallbox.
- **Old Firmware**: Firmware < 3.1 might not support all features (like Keepalive).

## 🔒 Security

Found a vulnerability? Please report it via **GitHub Security Advisories** or open a private issue if available. Do not post public exploits.
