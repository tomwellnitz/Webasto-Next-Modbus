# Changelog

## [Unreleased]

## [1.4.0] - 2026-10-04 - Unite REST API, stable device IDs, hardened Modbus and REST

### Upgrade notes

- **Make a Home Assistant backup before updating.** Device and entity IDs move from the host to the config entry (see *Fixed*). The migration runs once on the first start and keeps your entity IDs, history and automations, but it cannot be undone by downgrading.
- **Charging currents of 1–5 A are now rejected** by the *Charging current limit* number and the `set_current` service (IEC 61851 minimum is 6 A; `0` still pauses). Automations that set such values now fail with an error instead of being sent to the wallbox.
- *Charged energy* changes from `state_class: total` to `total_increasing`. The existing statistics continue; from now on the reset at the start of a session counts as a new cycle instead of negative energy.
- A few niche diagnostic entities are now disabled by default on **new** installations; existing entities stay as they are.

### Added

- **REST API support for the Ampure / Webasto Unite** ([#97](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/97), thanks @lonkhuijzen for the reverse-engineering). The Unite serves a different REST surface than the Next — a single flat `/api/configuration-fields/` endpoint with its own dotted field keys, and writes that take only `{fieldKey, value}` — so the REST client is now model-aware. On a Unite, enabling the REST API exposes the **Free charging** switch and **tag ID**, a new **LED dimming level** select (`veryLow`/`low`/`mid`/`high`/`timeBased`, since the Unite has no 0-100 brightness), and a **Randomised start delay** number (0-1800 s). The Next's firmware/diagnostic REST sensors have no Unite equivalent and are not created on a Unite; live telemetry is unaffected — it comes over Modbus.
- **Repair issue** when the wallbox stays unreachable; it clears itself on recovery.
- Devices left over from earlier IP changes can be deleted from their device page.
- **Solar surplus optimizer: phase-aware, with optional phase switching.** With the *Number of phases* sensor the blueprint converts watts to amps for the active phase mode (230 W/A single-phase, 690 W/A three-phase) instead of a fixed factor. On a Unite it can also switch to single-phase charging when the surplus can't carry 6 A on three phases, and back once it can (with headroom and a minimum interval between changes). The current is always lowered before a third phase is added, and while the phase sensor is unknown the blueprint falls back to the fixed factor and never switches. A new option chooses between keeping the minimum current and pausing (0 A) when the surplus is too small; with "keep", a current of 0 A set by hand is left alone.

### Changed

- **Setup** makes one connection attempt and leaves retrying to Home Assistant, instead of blocking startup for up to ~90 s with five attempts. The untranslated (German-only) persistent notifications are gone; a translated error explains a failed setup.
- Service names and descriptions are translated (English, German) and have icons; numeric sensors have a suggested display precision; current/duration numbers get their device class and the fail-safe numbers the *configuration* category.
- Config entries are migrated once (to version 1.3) instead of being rewritten on every setup.
- **`pymodbus` requirement without upper bound** (`>=3.11.2`, previously `<4`): Home Assistant decides the installed version, and a fixed ceiling blocks the integration whenever HA moves past it ([#88](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/88)).
- Tested against Home Assistant 2026.9 and 2026.10 (Probatio validation, new device registry types).

### Fixed

#### Device identity

- **Changing the wallbox's IP address no longer creates new entities.** Device and entity IDs were derived from the host, so *Reconfigure* after an IP change created a second device and `_2` entities, and history, dashboards, automations and device triggers lost their link. IDs are now based on the config entry; existing installations are migrated automatically (same entity IDs, same device).

#### Modbus

- **No more leaked Modbus connections after a network hiccup.** A client that failed mid-request was dropped without being closed, and pymodbus kept reconnecting it in the background, so one Wi-Fi drop could leave several sockets open and lock Home Assistant (or evcc) out of the wallbox's single Modbus TCP slot. Failed clients are now closed right away and pymodbus' auto-reconnect is disabled.
- **Service calls and number changes no longer hang for up to ~2 minutes** when the wallbox stops answering: pymodbus' hidden per-request retries are off, writes are attempted twice and reads three times, and every operation is bounded to 30 s.
- **The keep-alive follows the Modbus specification** ("writes 1 every 1/2 of comTimeout"). It used to wait for the wallbox to clear the bit before writing again, which could exceed short fail-safe timeouts, and after a long outage it could stay silent for up to 5 minutes while polling already worked again. The bit is no longer read back either: a Next on firmware 3.1.16 clears it about comTimeout/2 after each write, so the read only produced a misleading "Life bit still set" debug message.
- **Repeated start/stop commands take effect.** Register 5006 only reacts to a change, so a second *Start charging* after an earlier one was ignored. The command is now preceded by `0`, as the Modbus specification requires.
- **Unite firmwares without register 405 are polled again.** The optional phase-mode register was read first, and an unsupported first register made every poll report the wallbox as offline. Optional registers are now read after the core telemetry, and only dropped from polling when the wallbox reports them as unsupported (exception codes 1/2), not on a transient *busy*.
- Unload and timeouts are no longer swallowed while a Modbus request is in flight (pymodbus turns the cancellation into an I/O error, which the bridge used to retry), and closing the connection during a request no longer crashes it with an `AttributeError`.
- Changing options reloads the entry once instead of twice (two Modbus reconnects on a single-connection device).

#### REST API

- **The REST API can no longer stall Modbus updates.** REST was fetched inside the Modbus poll, so an unreachable web interface delayed every Modbus value by up to ~5 minutes. REST now has its own coordinator (every 60 s) and is fetched in the background at startup.
- **A slow or failing REST endpoint no longer makes every REST entity unavailable.** The Next's web server can take well over 10 s for the *system* section; a timeout there failed the whole poll, so e.g. *Active errors* and *Free charging* showed *unavailable* while the wallbox was reachable. Each endpoint now fails on its own (keeping its last values), the request timeout is 30 s again, timeouts are not retried, and a failed *system* section is tried again on the next poll instead of after 5 minutes.
- **REST entities are created even if the web interface is down at startup** (typical after a power cut) and recover on their own; before, they only appeared after a manual reload.
- **A failed REST poll keeps the last good values** instead of replacing them with empty ones, and *Active errors* shows *unknown* instead of *ok* when the errors couldn't be read.
- **A changed web-interface password starts the reauth flow** at runtime too (HTTP 401 and 403), and polling stops until new credentials are entered instead of retrying the login every few seconds (repeated failed logins can lock the account).
- *Restart wallbox* is sent once (it was retried up to 3×, often after the restart had already started), and a dropped connection while the wallbox goes down counts as success. Configuration writes are not retried either.
- Firmware, hardware versions and MAC addresses now actually appear on the device page; their values are always strings, which the device registry requires from HA 2026.12.
- Concurrent REST calls with an expired token log in only once; the token lifetime comes from the token itself.
- The options flow reports a wrong REST password as such instead of "cannot connect", and REST timeouts surface as translated errors.
- Free charging on the Next is parsed strictly (a `"false"` string read as on).
- The Next-only REST diagnostic sensors are no longer created (permanently unknown) on the Unite.
- IPv6 hosts work for the REST API.
- **Unite REST writes send only the payload verified on hardware** (`{fieldKey, value}`, FW 3.187, [#97](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/97)); the unconfirmed `configurationFieldUpdateType` property is dropped. The Next path is unchanged.

#### Entities, services and triggers

- **Device triggers now pass their data to automations.** The trigger variables were handed over in the wrong shape, so `trigger.id`, `trigger.fault_code`, `trigger.charging_state` etc. were empty. This also broke the bundled *event notifications* blueprint, which filters on `trigger.id`.
- **Enum sensors no longer break on undocumented values** (for example a fault code above 16): they report *unknown* instead of raising on every poll. Fault code 1 now shows its translated name.
- **Session energy statistics**: *Charged energy* resets every session and now uses `state_class: total_increasing`, so long-term statistics and the energy dashboard no longer count the reset as negative consumption.
- **Service calls accept rendered templates** such as `amps: "{{ states('input_number.x') }}"` (`16.0`) and normal booleans for `enabled`; an unknown `config_entry_id` is reported instead of silently ignored.
- A failed phase switch no longer leaves the switch showing a mode that was never applied.
- Writing the charging current via a service no longer updates the number entity from a worker thread, which Home Assistant flags as unsafe.

#### Blueprints

- **Three blueprints could not be used at all.** *Solar surplus optimizer*, *Charge target (kWh)* and *Charge until full* used `unit_of_measurement` in an entity selector, which Home Assistant does not accept, so it rejected the whole blueprint ("Invalid blueprint"). Every blueprint is now validated against Home Assistant's blueprint schema in the tests.
- The solar surplus optimizer now raises the current to the maximum when the surplus exceeds it; before, it kept the old current.

#### Diagnostics

- Diagnostics no longer contain the wallbox address (it was part of the last error message) or the RFID tag of the last session; a REST section with redacted network identifiers was added.

### Development

- **Every release has a title again.** Each CHANGELOG heading carries a short title (`## [X.Y.Z] - YYYY-MM-DD - Title`, `## [Unreleased] - Title` for pre-releases); the release workflow uses it as the release name (`vX.Y.Z - Title`, as shown by HACS and the releases page) and refuses a tag whose heading has none. Releases made by the workflow since 1.1.7 were named after the tag only.
- `uv.lock` is committed and CI installs with `uv sync --locked`; Dependabot uses the `uv` ecosystem and now also bumps `pytest-homeassistant-custom-component` patch releases (every HA release is one), so the tests follow Home Assistant.
- CI runs `./scripts/check.sh --check`, the same read-only script contributors run locally. The script no longer reformats Markdown inside `.venv`, and gained `mdformat`, `actionlint` and a coverage gate (80 % line + branch).
- End-to-end tests in a real Home Assistant; snapshot tests cover every entity (registry entry and state), the device and the diagnostics for both models; a static test checks every register's device class, state class and entity category. The global `pymodbus` / `voluptuous` test stubs are gone.
- **`upstream-compat.yml`** — a weekly canary against the latest Home Assistant: smoke-imports every module and re-runs hassfest, so an upcoming HA release that breaks the integration is caught ~1-2 weeks before users hit it.
- The release workflow refuses a tag that doesn't match the `manifest.json` / `pyproject.toml` version or (for a final release) has no `CHANGELOG.md` section, and runs the full check script.
- Workflows: least-privilege `permissions`, superseded PR runs are cancelled, CodeQL also scans the workflows (`actions`), and `.github/` is linted by yamllint and actionlint.
- Ruff additionally enforces `BLE`, `RUF`, `SIM` and `PT`; one codespell configuration in `pyproject.toml`; pre-commit hooks run the locked tools via `uv run`.
- `webasto-smoke` finds the entities by config entry (it failed with an `ImportError` after the identity change).

## [1.3.1] - 2026-07-02 - Home Assistant 2026.7 compatibility

### Fixed

- **Home Assistant 2026.7 compatibility** ([#88](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/88)) — HA 2026.7 pins `pymodbus==3.13.1`, but the 1.3.0 manifest required `pymodbus>=3.11.2,<3.12`. Home Assistant refused to load the integration with `Setup failed … Requirements for webasto_next_modbus not found: ['pymodbus>=3.11.2,<3.12']`. The manifest and the `pyproject.toml` runtime constraint are widened to `pymodbus>=3.11.2,<4` to cover all HA-Core-shipped pymodbus 3.x versions. No user-side changes required; a Home Assistant restart after updating is enough.

### Added

- `docs/rest-api-reverse-engineering.md` — a short guide explaining how to authenticate against the wallbox's web API, discover endpoints by watching the web UI's network calls, and identify the writes. Intended for contributors adding Unite-specific REST support, since the existing REST mapping was reverse-engineered against a Webasto Next.

### Changed

- Documentation aligned with the HA quality scale Gold/Platinum doc rules: new **Data updates** section (10 s Modbus / 60 s REST / Life Bit cadence) and a consolidated **Known limitations** section in the README; a copy-paste-ready custom YAML automation example using a service action and a device trigger; the Configuration list now documents the *Model* selector (Next vs Unite) and the *Reconfigure* / *Configure* entry points. A stale "a repair issue is raised" note in the README was replaced with the actual reauth-flow behaviour shipped in 1.3.0.
- `docs/architecture.md` updated to reflect the 1.3.0 surface: reconfigure & reauth flows, the Charging binary sensor, the eight device triggers, the Unite-specific register differences confirmed in [#37](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/37), and the Platinum quality scale rules (strict typing, `inject-websession`, icon/exception translations, action-setup).
- `docs/support.md`: the duplicated "Known limitations" subsection now defers to the README (which is now the single, sourced reference).
- HACS card (`info.md`) refreshed to reflect the 1.3.0 surface (Unite model selector, reconfigure/reauth flows, Charging binary sensor, device triggers, Platinum quality scale).

### Removed

- Stale `release_notes.md` from the repository root. The release workflow has long published from the matching `CHANGELOG.md` section instead.
- `webinterface_analysis.json` — one-off endpoint probe artifact from the original Next reverse-engineering session. Its information is already distilled into `docs/rest-api.md`, and the methodology is now captured in `docs/rest-api-reverse-engineering.md`. Kept in git history if needed.

## [1.3.0] - 2026-05-27 - Reconfigure and reauth flows, Platinum quality scale

### Added

- **Reconfigure flow**: change a wallbox's host, port, unit ID or name from *Settings → Devices & Services → ⋮ → Reconfigure* without removing and re-adding the integration.
- **Reauthentication flow**: when the wallbox rejects the REST API credentials, Home Assistant now starts a guided reauth dialog to enter new ones (replacing the previous repair issue). The Modbus side keeps working throughout.
- **Charging binary sensor** (`device_class: battery_charging`) — a simple on/off entity for dashboards and automations, alongside the existing Connected sensor.
- **New device triggers**: *cable connected*, *cable disconnected* and *fault occurred* (in addition to charging started/stopped, connection lost/restored and keep-alive sent). All device triggers are now translated (English/German), and the event-notification blueprint can fire on them.

### Changed

- **Quality scale raised to Platinum.** Every Bronze→Platinum rule is now met or exempt (tracked in `quality_scale.yaml`): the REST client uses Home Assistant's shared aiohttp session (`inject-websession`), the code is strictly typed (`strict` mypy + `py.typed`), entity icons and user-facing exceptions are translated, `PARALLEL_UPDATES` is declared on every platform, and service actions are registered in `async_setup`.

### Fixed

- **Forward-compatibility (HA 2026.6)**: the reconfigure/reauth flows update the entry and rely on the existing update listener for a single reload, avoiding the now-deprecated config-entry-listener-plus-reloading-method combination that becomes an error in 2026.12.
- **Example blueprints**: fixed the FastCharge/FullCharge, Charge-Target and Charge-Until-Full blueprints, which referenced blueprint inputs in templates in a way that failed at runtime; all four blueprints were modernised to the current `triggers`/`conditions`/`actions` syntax and are now guarded by a lint test.
- **REST API logging**: request timeouts are now retried like other transient errors instead of bubbling up as a blank `Failed to fetch <section> section:` warning, and per-section fetch failures (which keep partial/stale data) log at debug instead of repeating a warning every poll. Per-attempt retries also log at debug now (only the final outcome matters). Genuine REST outages are still surfaced once via the throttled coordinator warning.
- **Quieter startup**: the one-time "integration loaded from \<path>" message is now logged at debug instead of warning.

### Internal

- Dependabot tuned: monthly pip cadence, a 7-day cooldown, and auto-merge for low-risk (patch/minor) updates once CI passes.
- Entity icons moved to `icons.json`; exceptions carry translation keys.

## [1.2.0] - 2026-05-24 - Webasto / Ampure Unite support

### Added

- **Webasto / Ampure Unite support**: the config and options flows now have a *model* selector ("Webasto Next" / "Webasto / Ampure Unite"). Existing installs default to "Webasto Next" so nothing changes for current users. Selecting "Unite" switches to a corrected register map: the telemetry block (~100-1513) is read as input registers instead of holding registers, `energy_total_kwh` (1036) is scaled for the Unite's 0.1 kWh units, `charged_energy_wh` (1502) is read as a uint32, `charge_point_state` (1000) uses the Unite's 9-state enum, the Next-only registers (session user id 1600, smart-vehicle-detected 1620, start/stop-session command 5006) are dropped, and the Unite-only registers are added: per-phase voltage (1014/1016/1018), chargepoint power (400) and the active phase mode (405). Fixes the long-standing "all sensor values read 0 on a Unite" reports.
- **Unite phase switching**: a "Three-phase charging" switch (Unite only) toggles the wallbox between single- and three-phase via holding register 405 (`on` = three-phase). The register is undocumented and firmware-dependent (confirmed on FW 3.187, issue #37), so the entity is assumed-state. The "Number of Phases" sensor and the switch readback both reflect the active mode from register 405 (register 404 reports the installed phase count, which stays at 3 on a three-phase install).

### Changed

- The integration is now named **"Webasto Next / Unite"** to reflect that it supports both wallbox models. This is a display-name change only: the integration `domain` (`webasto_next_modbus`), all entity IDs and existing configurations are unchanged.

### Internal

- The virtual wallbox simulator is now model-aware: a Unite simulator serves its telemetry only on input registers (no holding mirror), so the test suite reproduces the real Next-vs-Unite behaviour and guards the Unite register map against regressions.

## [1.1.7] - 2026-05-12 - Offline wallbox handling, modern config entries

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
- **REST-controlled entities revert after a few seconds**: setting **LED brightness**, toggling **Free charging** or changing the **Free charging tag ID** now forces an immediate REST re-fetch (the regular REST poll is throttled to 60 s) and the entity keeps the optimistic value until the wallbox confirms it. Previously the value bounced back to the last cached one on the next Modbus poll. The matching `set_led_brightness` / `set_free_charging` services do the same now.
- **Stale Modbus socket after a failed setup**: if the first data poll fails (e.g. the wallbox is still booting), the Modbus connection is now closed before Home Assistant retries. These wallboxes typically accept only one Modbus TCP connection, so a leftover socket made the retry fail with "connection refused".

### Internal

- Removed the unused, stale `INTEGRATION_VERSION` constant from `const.py` (the integration version lives in `manifest.json` / `pyproject.toml`).
- Removed a redundant `available` override on the Modbus register entity base class (it just returned the coordinator-entity default).
- The **Free charging tag ID** text entity now uses the same `unique_id` scheme as the other REST entities (`<slug>-rest-free_charging_tag_id`); the old `host_unit_key` id is migrated automatically in the entity registry, so history and customisations are preserved.
- Replaced a few private-attribute accesses with public accessors: external code now uses `WebastoDataCoordinator.rest_client` and `ModbusBridge.host` / `ModbusBridge.unit_id`.
- Bumped README maintenance badge to 2026.
- Documented the dependency-pinning conventions in `AGENTS.md` (`manifest.json` lists only packages HA core does not provide; `pymodbus` stays pinned to `<3.12`).
- CI: third-party GitHub Actions are pinned to commit SHAs (with `# vX.Y.Z` comments so Dependabot still tracks them), and `dependabot.yml` was tightened (direct deps only, `pymodbus` major/minor held, grouped updates).
- Release workflow: pre-release tags (`v*-beta.*`, `v*-rc.*`, …) are now published as GitHub pre-releases so HACS only offers them under "Show beta versions".

## [1.1.6] - 2026-05-11 - Home Assistant 2026.5 compatibility

### Changed

- **Home Assistant 2026.5 compatibility**: Bumped minimum Python to 3.14.2 (now required by HA core), raised the minimum `aiohttp` to `3.13.5` to match HA core, and updated test dependencies (`homeassistant>=2026.5.1`, `pytest-homeassistant-custom-component==0.13.330`).
- **CI**: Pinned GitHub Actions matrix to Python 3.14.2 (CI and release workflows).

## [1.1.5] - 2025-12-19 - Fix HACS validation

### Fixed

- **HACS Validation**: Fixed a JSON syntax error (trailing comma) in `manifest.json` that caused HACS validation to fail.

## [1.1.4] - 2025-12-19 - Fix charged energy and translations

### Fixed

- **Active Errors**: Fixed "Aktive Fehler" showing "None" in German translation. It now correctly shows "Keine Fehler" (or "No Error" in English) when no errors are present.

## [1.1.3] - 2025-12-16 - Major reconnection fix

### Fixed

- **Major Reconnection Fix**: Completely reworked Modbus connection handling to fix persistent reconnection issues after network interruptions.
  - Old client is now properly closed before creating a new connection, preventing orphaned TCP connections.
  - Added explicit timeout handling for connection attempts.
  - Connection errors (`OSError`, `ConnectionError`) now properly invalidate the client, forcing a clean reconnect.
  - Added pymodbus `reconnect_delay` parameters for automatic reconnection support.
  - Increased retry attempts from 3 to 5 with longer backoff (2s instead of 1s).

______________________________________________________________________

## [1.1.2] - 2025-12-15 - Remove non-functional auto-discovery

### Changed

- **Zeroconf/Auto-Discovery**: Removed non-functional mDNS configuration - Webasto Next wallboxes do not advertise discoverable services. Manual configuration via IP address is required.

______________________________________________________________________

## [1.1.1] - 2025-12-15 - Bug fixes

### Fixed

- **Connection Handling**: Improved error handling for network disconnections - OSError is now properly caught during connection attempts, enabling the retry mechanism.
- **REST API**: Fixed potential crash when making requests without valid token - added proper token validation.
- **Free Charging Switch**: Fixed entity state updates by adding missing `super()._handle_coordinator_update()` call.

______________________________________________________________________

## [1.1.0] - 2025-12-15 - Optional REST API

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

## [1.0.0] - 2024-03-20 - Initial release

### Added

- Initial release with Modbus TCP support.
