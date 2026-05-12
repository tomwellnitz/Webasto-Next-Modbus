# Changelog

## [1.1.7] - 2026-05-11

### Added

- A diagnostic **"Connected"** binary sensor (`device_class: connectivity`) that reports whether the integration is currently reaching the wallbox. Unlike the regular entities (which go `unavailable` when the wallbox is offline) it stays available and reads `off`, so it can be used directly in automations and dashboards.

### Changed

- **Modern config entry handling**: Runtime data is now stored on `entry.runtime_data` (typed `ConfigEntry[RuntimeData]`) instead of `hass.data[DOMAIN][entry.entry_id]`. Platforms (`button`, `sensor`, `number`, `switch`, `text`) and diagnostics read it directly from the entry.
- **Options flow**: No longer assigns `self.config_entry` explicitly; the base class injects it automatically (Home Assistant 2024.12+). Removes a deprecation warning that would otherwise become an error.
- **Config flow**: `_abort_if_unique_id_configured(reload_on_update=False)` is now passed explicitly to opt out of the implicit reload-on-update path. Combined with the existing update listener this future-proofs us against the deprecation that turns into an error in Home Assistant 2026.12.
- **Service resolver**: Looks up loaded entries via `hass.config_entries.async_loaded_entries(DOMAIN)` and reads each entry's `runtime_data`, removing the last direct dependency on `hass.data[DOMAIN]`.
- `manifest.json` no longer lists `aiohttp` as a requirement: it is part of Home Assistant core, and a `>=` requirement in the manifest can interfere with pip resolving the core pin. It stays in `pyproject.toml` for the test environment.
- The **charging current limit** number is seeded from the wallbox's current register value (rather than starting blank on a fresh install); if the wallbox doesn't answer that read it falls back to the previously stored value. The read now runs as a background task after the entity is added, so a slow-to-respond wallbox can no longer delay the `number` platform setup (previously this could trip the "setup is taking over 10 seconds" warning).
- When the wallbox rejects the configured REST API credentials (HTTP 401), the integration now raises a **repair issue** ("REST API authentication failed") instead of only logging a warning, so it's visible and you know to update the password. The Modbus side keeps working regardless. A non-401 REST login failure (e.g. the wallbox web server still booting) is treated as a transient connection error and retried, not flagged as a credentials problem.

### Fixed

- **Diagnostics**: The REST API username and password are now redacted from the config-entry diagnostics download (previously only `host` was redacted, so the password stored in entry options was exposed).
- **Graceful handling of an offline / booting wallbox**: a Modbus *exception response* (the wallbox answered and rejected the request — common while it boots, or for a register a given firmware doesn't implement) is now distinguished from a transport error. Device exceptions no longer trigger a reconnect-and-retry storm (which caused pymodbus transaction-id desyncs and connection-refused floods), the bulk read bails out after the first failing block with a single "wallbox not responding" message instead of one warning per block, and error logs now include the actual Modbus exception code (e.g. "Illegal Data Address") instead of an opaque object reference.
- **Life-bit loop**: now backs off exponentially (up to 5 minutes) while the wallbox is unreachable — whether it's powered off (connection refused) or still booting (register writes rejected) — logging the failure once and then at debug level, and recovering automatically once the wallbox is up. The keep-alive window is still clamped to a sane minimum with a one-second floor between cycles.
- **REST client**: the aiohttp session is closed when `connect()` fails (no more "Unclosed client session"), and the TLS context is built without `load_default_certs()` so it no longer trips Home Assistant's blocking-call detector. If the initial REST connect fails because the wallbox is still booting, it is now retried automatically (about every 5 minutes) once the Modbus side reconnects, instead of staying disabled until the integration reloads. Repeated "failed to fetch REST data" messages are logged once and then at debug level.

### Internal

- Removed the unused, stale `INTEGRATION_VERSION` constant from `const.py` (the integration version lives in `manifest.json` / `pyproject.toml`).
- Removed a redundant `available` override on the Modbus register entity base class (it just returned the coordinator-entity default).
- Replaced a few private-attribute accesses with public accessors: external code now uses `WebastoDataCoordinator.rest_client` and `ModbusBridge.host` / `ModbusBridge.unit_id`.
- Bumped README maintenance badge to 2026.
- Documented the dependency-pinning conventions in `AGENTS.md` (`manifest.json` lists only packages HA core does not provide; `pymodbus` stays pinned to `<3.12`).
- Release workflow: pre-release tags (`v*-beta.*`, `v*-rc.*`, …) are now published as GitHub pre-releases so HACS only offers them under "Show beta versions".

## [1.1.6] - 2026-05-11

### Changed

- **Home Assistant 2026.5 compatibility**: Bumped minimum Python to 3.14.2 (now required by HA core), raised the minimum `aiohttp` to `3.13.5` to match HA core, and updated test dependencies (`homeassistant>=2026.5.1`, `pytest-homeassistant-custom-component==0.13.330`).
- **CI**: Pinned GitHub Actions matrix to Python 3.14.2 (CI and release workflows).

## [1.1.5] - 2025-12-19

### Fixed

- **HACS Validation**: Fixed a JSON syntax error (trailing comma) in `manifest.json` that caused HACS validation to fail.

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
