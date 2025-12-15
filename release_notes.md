## Webasto Next Integration v1.1.0

This major update introduces optional **REST API support**, enabling advanced features not available via Modbus TCP.

### 🌟 New Features (REST API)

- **LED Control**: Adjust the wallbox LED brightness (0-100%).
- **Diagnostics**: View firmware versions, hardware info, and active errors.
- **Network Info**: See MAC addresses and IP configuration.
- **Free Charging**: Enable/disable free charging mode and manage the Tag ID alias.
- **System Control**: Restart the wallbox directly from Home Assistant.

### 🛠️ Improvements

- **Robustness**: Enhanced error handling and retry logic for network connections.
- **Compatibility**: Improved parsing for signal voltages across different firmware versions.
- **Usability**: Full German and English translations for all new entities.
- **Standards**: Added Code of Conduct and Security Policy; achieved "Silver" quality scale.

### 🐛 Fixes

- Corrected charge point state mappings.
- Fixed API communication for configuration updates.
- Handled API field name inconsistencies (typos in firmware).
