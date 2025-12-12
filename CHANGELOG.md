# Changelog

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
