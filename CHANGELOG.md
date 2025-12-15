# Changelog

## [1.1.0-beta.2] - 2025-12-15

### Added

- **Community Standards**: Added CODE_OF_CONDUCT.md following Contributor Covenant 2.1.
- **Security Policy**: Added SECURITY.md with vulnerability reporting guidelines and security best practices.
- **Quality Scale**: Declared "silver" quality scale in manifest.json as per Home Assistant integration quality standards.

### Changed

- **Integration Name**: Simplified display name from "Webasto Next Modbus" to "Webasto Next" to reflect both Modbus TCP and REST API support.
- **Documentation**: Updated all user-facing documentation to reflect the integrated nature of Modbus TCP and REST API features.
- **Dependencies**: Added aiohttp to manifest.json requirements (was previously only in pyproject.toml).

### Technical

- **Manifest**: Added `quality_scale` field and consolidated all dependencies.
- **Translations**: Updated integration title in English and German translation files.

## [1.1.0-beta.1] - 2025-12-15

### Added

- **REST API Integration**: Optional connection to wallbox REST API for features not available via Modbus.
  - **LED Brightness Control**: Number entity to set LED brightness (0-100%).
  - **Firmware Information**: Diagnostic sensors for Comboard and Powerboard SW/HW versions.
  - **Hardware Statistics**: Diagnostic sensors for plug cycles and error counter.
  - **Signal Voltages**: Diagnostic sensors for L1, L2, L3 grid voltages.
  - **Free Charging Control**: Switch entity to enable/disable free charging mode without RFID.
  - **Free Charging Tag ID**: Sensor showing configured RFID tag alias.
  - **Active Errors**: Sensor listing all currently active errors.
  - **Restart Button**: Button entity to trigger wallbox system restart.
  - **MAC Addresses**: Device info now includes Ethernet and WiFi MAC addresses when REST is enabled.
- **REST API Services**: Three new services for REST API control:
  - `set_led_brightness`: Set LED brightness (0-100%).
  - `set_free_charging`: Enable/disable free charging mode.
  - `restart_wallbox`: Trigger system restart.
- **Switch Platform**: New platform for toggle entities (currently used for Free Charging).
- **Config Flow**: REST API credentials can be configured during initial setup or later via Options Flow.
- **Options Flow**: Enable/disable REST API and update credentials without removing the integration.

### Changed

- **Device Info**: When REST API is enabled, device info includes firmware version, hardware version, and MAC addresses.
- **Documentation**: Updated all documentation to English and added comprehensive REST API documentation.

### Technical

- **Dependencies**: Added `aiohttp` for REST API communication.
- **Architecture**: REST API client uses JWT authentication with automatic token refresh.
- **Coordinator**: Extended to fetch both Modbus and REST API data in parallel.

## [1.0.0] - 2025-12-15

### Added

- **Translations**: Full support for English and German translations for all entities and status values.
- **Optional Registers**: Automatic detection and handling of unsupported registers (e.g. for different hardware variants).

### Changed

- **Charge Point State**: Corrected state mapping to match Webasto Modbus specification.
- **Time Formatting**: Session times are now formatted as `HH:MM:SS`.

### Fixed

- **Build**: Corrected versioning in build artifacts.
- **Translations**: Fixed issues with German translation keys and JSON structure.

## [0.4.0-beta.15] - 2025-12-14

### Fixed

- **Build**: Fixed version mismatch in `pyproject.toml` causing release artifacts to have the wrong version number.

## [0.4.0-beta.14] - 2025-12-14

### Fixed

- **Translations**: Fixed an issue where German translations were not being applied because the `translation_key` was missing in the register definitions.
- **JSON Structure**: Corrected the structure of the German translation file (`de.json`) to ensure all keys are properly nested.

## [0.4.0-beta.13] - 2025-12-14

### Added

- **Translations**: Added full support for entity name translations. Entity names are now automatically translated based on the Home Assistant language (English and German supported).
- **Enum Translations**: All state values for enum sensors (e.g., Charge Point State, Error Codes) are now translated.

### Changed

- **Charge Point State**: Updated mapping for `charge_point_state` to correctly reflect the Webasto Modbus specification (Charging is now 3, Suspended is 4).
- **Time Formatting**: Session start and end times are now formatted as `HH:MM:SS` instead of raw integers.

## [0.4.0-beta.12] - 2025-12-14

### Added

- **Optional Registers**: Added support for optional registers. If a register block is not supported by the wallbox (e.g. Smart Vehicle State on some models), it will be automatically removed from the polling loop after the first failure.

### Fixed

- **Energy Sensors**: Changed `state_class` to `total` for energy sensors to correctly support long-term statistics.
- **Fault Codes**: Added `device_class: enum` to fault code sensors for better UI representation.

## [0.4.0-beta.11] - 2025-12-14

### Fixed

- **Connection Stability**: Fixed issue where disabling the integration in HA did not properly close the Modbus connection, blocking external tools from connecting.
- **Life Bit Loop**: Now starts after coordinator initialization to avoid race conditions.
- **Graceful Shutdown**: Added timeouts and proper lock handling for connection close to prevent hangs during unload.
- **CancelledError Handling**: Life bit loop and retry logic now properly propagate cancellation for clean shutdown.

### Changed

- **Config Flow**: Now reuses existing bridge connection when reconfiguring, preventing temporary second connections that would be rejected by the wallbox.
- **Diagnostics**: Now includes current register values for easier debugging.

### Improved

- Added debug logging throughout the unload process for better troubleshooting.

## [0.4.0-beta.10] - 2025-12-12

### Added

- **Auto-Discovery**: Automatically detects Webasto Next wallboxes in the network via Zeroconf/mDNS.
- **Tooling**: Added `mdformat` for Markdown formatting and `vulture` for dead code detection.
- **Documentation**: Added `AGENTS.md` for AI agents and updated developer guides.

### Fixed

- **Manifest**: Fixed validation errors in `manifest.json` (Zeroconf naming, key sorting) and `hacs.json`.

### Changed

- Improved CI pipeline with comprehensive checks (linting, types, spelling, security).
- Updated `pyproject.toml` dependencies and configuration.

## [0.4.0-beta.8] - 2025-12-12

### Added

- New automation blueprints to match and exceed competitor features:
  - **Charge Target (kWh)**: Automatically stop charging after a specific energy amount is delivered.
  - **Charge Until Full (Auto-Stop)**: Detect when the battery is full (power drop) and stop the session.
  - **Solar Surplus Optimizer**: Dynamically adjust charging current based on grid export/import.

### Changed

- Updated all blueprints to use modern Home Assistant syntax (`action` instead of `service`) for 2025.x compatibility.
- Validated and fixed YAML syntax/style in all blueprints (line lengths, formatting).

## [0.4.0-beta.7] - 2025-12-12

### Added

- Implemented robust "Life Bit" handshake (Write 1 -> Poll 0) to reliably prevent wallbox failsafe mode.
- Added connection retry logic (3 attempts) with user notifications during setup to handle transient network issues.

### Changed

- Migrated project tooling from `pip` to `uv` for faster and more reliable dependency management.
- Pinned project to Python 3.12 to ensure compatibility with all dependencies.
- Updated GitHub Actions workflows to use `uv`.

### Fixed

- Corrected Modbus register map based on vendor PDF: removed unsupported voltage sensors and fixed data types.
- Removed write-only `charge_power_w` register to prevent read errors.
- Fixed `KeyError` in simulator by removing obsolete registers from default scenario.

## [0.4.0-beta.6] - 2025-11-30

### Changed

- Improved connection stability: The "Life Bit" (keepalive) is now sent every 15 seconds (previously 20s) using `async_track_time_interval` for better reliability and to prevent timeouts on some firmware versions.
- Fixed potential issue where the keepalive timer was not correctly cancelled when unloading the integration.
- Updated documentation to clarify the automatic keepalive behavior.

## [0.4.0-beta.5] - 2025-10-24

### Added

- Automatic periodic write to Modbus register 6000 (Life Bit) every 20 seconds to prevent timeouts

### Changed

- Lint and formatting fixes (ruff compliance, line length)
- Version bump in all files for release consistency

### Fixed

- All tests pass, including HomeAssistantError handling

### Notes

- This pre-release is production-ready and strictly follows Webasto Modbus spec

## [0.4.0-beta.3] - 2025-10-24

### Changed

- Entfernt alle nicht offiziellen Modbus-Register unter Adresse 1000 aus der Integration
- Dev-Abhängigkeiten im pyproject.toml ergänzt und Python-Version auf 3.13 für Home Assistant-Kompatibilität festgelegt
- Integration und Tests laufen jetzt mit vollständigem, offiziellem Registersatz

### Fixed

- Fehlerhafte Registerabfragen und Import-Probleme durch fehlende Abhängigkeiten behoben
- Linting und Formatierung mit ruff, alle Tests laufen fehlerfrei

### Notes

- Release ist produktionssicher und entspricht exakt der Hersteller-Dokumentation

<!-- markdownlint-disable MD022 MD024 MD032 -->

All notable changes to this project are documented in this file. The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0-beta.2] - 2025-10-08

### Added

- Full Modbus register mapping and error code coverage based on manufacturer documentation
- Improved simulator mirroring and address normalization for production parity
- Lint and test automation (ruff, pytest) for CI/CD best practices
- Updated documentation and changelog workflow for maintainability

### Changed

- Refactored code for production readiness and best practices
- All constants, sensors, and error mappings now match official register tables
- Simulator and integration logic now fully aligned with real device behavior

### Fixed

- Addressed edge cases in register mirroring and error handling
- All tests pass for Python 3.12/3.13 matrix

### Notes

- This beta is production-ready: all registers, error codes, and behaviors are validated against manufacturer specs. Linting and tests are automated. See docs for integration and simulator usage.

## [0.4.0-beta.1] - 2025-10-08

### Added

- Bumped integration to 0.4.0-beta.1 with sensor handling improvements and translation updates.

### Changed

- Updated sensor platform behavior and restored translations; adjusted tests to match behavior changes.
- Integration version updated in manifest and constants.

## [0.3.0-beta.1] - 2025-10-05

### Added

- Configurable device name in the setup/options flow with end-to-end entity renaming support.
- Start and stop charging buttons plus corresponding service coverage and tests.
- Restore-on-start support for the charging current number entity to keep the last configured value.

### Changed

- Simplified repository assets now that branding lives in the upstream `home-assistant/brands` repository.
- Removed the local branding export helper script; rely solely on the upstream brands repository workflows.

## [0.2.4-beta] - 2025-10-04

### Added

- Standalone Modbus TCP simulator server with a `virtual-wallbox` CLI entry point.
- Virtual wallbox scenario overrides, JSON loading, and helper docs for headless testing.
- Comprehensive simulator test coverage, including Modbus data block behaviours and write actions.

### Changed

- Developer documentation and README now cover the simulator workflow and CLI usage.

## [0.2.3-beta] - 2025-10-03

### Fixed

- Pin `setuptools.packages` discovery to the integration module so editable installs succeed when blueprints are bundled.

### Changed

- Document the local workflow for validating both Python 3.12 and 3.13 matrix jobs before opening a pull request.

## [0.2.2-beta] - 2025-10-03

### Added

- Two explicit services (`webasto_next_modbus.start_session` / `stop_session`) and a bundled blueprint to toggle FastCharge/FullCharge helpers.
- Extended sensor coverage for static metadata (serial, firmware, backend IDs), EV max current, charged energy, and live charge power.
- Dedicated tests for Modbus string decoding and the new service helpers.

### Changed

- Lazily import `pymodbus` to improve diagnostics for missing dependencies.
- Decode string registers with UTF-8 trimming while preserving existing numeric handling.
- Surface additional register metadata in the developer documentation.

## [0.2.1-beta] - 2025-10-03

### Added

- Repository branding assets (logo/icon) rendered in HACS and documentation for easier discovery.

### Changed

- Declare minimum Home Assistant version and integration type in the manifest for HACS validation.
- Raise the minimum supported Python runtime to 3.12 and align dev tooling (coverage, pytest-cov, pytest-homeassistant-custom-component) with the latest compatible matrix.

## [0.2.0] - 2025-10-03

### Added

- Device automation triggers for charging events, connection changes, and manual keep-alive actions.
- Expanded documentation covering manual verification, release workflow, and debug logging.
- Consistent Material Design Icons for sensors, numbers, and button entities.

### Changed

- README restructured into production-ready guidance with clear installation, usage, and troubleshooting sections.

## [0.1.0] - 2025-10-03

### Added

- Initial Home Assistant integration for Webasto Next / Ampure Unite wallboxes with sensor, number, and button entities.
- Config flow including connection validation and variant-specific current clamping.
- Service helpers for dynamic current, fail-safe configuration, and keep-alive frames.
