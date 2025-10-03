# Changelog

All notable changes to this project are documented in this file. The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- _Nothing yet_

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
