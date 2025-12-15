## Changes in 1.1.0-beta.2

## Changes in 1.1.0-beta.3

### Changed

- **REST API**: Retry- und Error-Handling jetzt identisch robust wie bei Modbus. Nach Verbindungsabbrüchen werden Anfragen mehrfach mit Backoff neu versucht, Sessions werden sauber neu aufgebaut. Fehler werden nach maximalen Versuchen an Home Assistant weitergegeben.

### Technical

- **Code Quality**: REST-Client nutzt jetzt explizites Session-Reset und Logging für alle Verbindungsfehler. Asyncio-Cancellation wird korrekt behandelt. Kein endloses Blockieren bei Ausfall.

### Added

- **Community Standards**: Added CODE_OF_CONDUCT.md and SECURITY.md for better community governance.
- **Quality Scale**: Integration now declares "silver" quality scale in manifest.

### Changed

- **Integration Name**: Simplified to "Webasto Next" (was "Webasto Next Modbus") to reflect both Modbus TCP and REST API support.
- **Documentation**: Updated all documentation to mention both communication protocols.
- **Dependencies**: Added aiohttp to manifest.json requirements.

______________________________________________________________________

## Changes in 1.1.0-beta.1

### Added

- **REST API Integration**: Optional connection for LED control, firmware info, diagnostics, and more.
- **Translations**: Full English and German support for all entities.

### Changed

- **Charge Point State**: Corrected mapping per Webasto specification.
- **Time Formatting**: Session times now formatted as `HH:MM:SS`.
