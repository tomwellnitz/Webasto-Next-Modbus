# Changelog

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
- **MAC Addresses**: Added separate diagnostic sensors for LAN and WLAN MAC addresses.
- **Charge Point State**: Corrected mapping per Webasto specification.

### Changed

- **Integration Name**: Renamed to "Webasto Next" to reflect multi-protocol support.
- **Documentation**: Updated to cover both Modbus TCP and REST API.
- **Time Formatting**: Session times now formatted as `HH:MM:SS`.

______________________________________________________________________

## [1.0.0] - 2024-03-20

### Added

- Initial release with Modbus TCP support.
