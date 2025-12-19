# Changelog

## [1.1.4] - 2025-12-19

### Fixed

- **Active Errors**: Fixed "Aktive Fehler" showing "None" in German translation. It now correctly shows "Keine Fehler" (or "No Error" in English) when no errors are present.

## [1.1.3] - 2025-12-16

### Fixed

- **Major Reconnection Fix**: Completely reworked Modbus connection handling to fix persistent reconnection issues after network interruptions.
  - Old client is now properly closed before creating a new connection, preventing orphaned TCP connections.
  - Added explicit timeout handling for connection attempts.
  - Connection errors (`OSError`, `ConnectionError`) now properly invalidate the client, forcing a clean reconnect.
  - Added pymodbus `reconnect_delay` parameters for automatic reconnection support.
  - Increased retry attempts from 3 to 5 with longer backoff (2s instead of 1s).

______________________________________________________________________

## [1.1.2] - 2025-12-15

### Changed

- **Zeroconf/Auto-Discovery**: Removed non-functional mDNS configuration - Webasto Next wallboxes do not advertise discoverable services. Manual configuration via IP address is required.

______________________________________________________________________

## [1.1.1] - 2025-12-15

### Fixed

- **Connection Handling**: Improved error handling for network disconnections - OSError is now properly caught during connection attempts, enabling the retry mechanism.
- **REST API**: Fixed potential crash when making requests without valid token - added proper token validation.
- **Free Charging Switch**: Fixed entity state updates by adding missing `super()._handle_coordinator_update()` call.

______________________________________________________________________

## [1.1.0] - 2025-12-15

### Added

- **REST API Integration**: Optional connection for LED control, firmware info, diagnostics, and more.
- **Community Standards**: Added CODE_OF_CONDUCT.md and SECURITY.md.
- **Quality Scale**: Declared "silver" quality scale in manifest.json.
- **Translations**: Full English and German support for all entities.

### Fixed

- **REST API**: Robust retry and error handling, fixed HTTP 405/400 errors on updates.
- **Signal Voltage**: Improved parsing for various firmware formats (comma-separated, labeled).
- **Free Charging Tag ID**: Fixed API field name typos and converted to editable text entity.
- **Charge Point State**: Corrected mapping per Webasto specification.

### Changed

- **Integration Name**: Renamed to "Webasto Next" to reflect multi-protocol support.
- **Documentation**: Updated to cover both Modbus TCP and REST API.
- **Time Formatting**: Session times now formatted as `HH:MM:SS`.

______________________________________________________________________

## [1.0.0] - 2024-03-20

### Added

- Initial release with Modbus TCP support.
