## Changes

### Added

- **Translations**: Added full support for entity name translations. Entity names are now automatically translated based on the Home Assistant language (English and German supported).
- **Enum Translations**: All state values for enum sensors (e.g., Charge Point State, Error Codes) are now translated.

### Changed

- **Charge Point State**: Updated mapping for `charge_point_state` to correctly reflect the Webasto Modbus specification (Charging is now 3, Suspended is 4).
- **Time Formatting**: Session start and end times are now formatted as `HH:MM:SS` instead of raw integers.
