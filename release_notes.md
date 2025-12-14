## Changes

### Added

- **Optional Registers**: Added support for optional registers. If a register block is not supported by the wallbox (e.g. Smart Vehicle State on some models), it will be automatically removed from the polling loop after the first failure.

### Fixed

- **Energy Sensors**: Changed `state_class` to `total` for energy sensors to correctly support long-term statistics.
- **Fault Codes**: Added `device_class: enum` to fault code sensors for better UI representation.
