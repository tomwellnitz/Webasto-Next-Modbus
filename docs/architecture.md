# Webasto Next Modbus Home Assistant Integration

## Zielsetzung

Diese Integration bindet Webasto Next (bzw. Ampure Unite) Wallboxen per Modbus TCP in Home Assistant ein. Sie liefert strukturierte Sensoren, erlaubt das Setzen von Ladeparametern und stellt optionale Helfer bereit, ohne YAML-Anpassungen vorauszusetzen. Der Fokus liegt auf einem robusten, wartbaren Code mit kommentierten Schnittstellen sowie automatisierten Tests.

## Wichtige Anforderungen

- **Konfigurationsoberfläche**: Setup per Config Flow (Host, Port, Unit-ID, Update-Intervall) mit Eingangs-Validierung.
- **Modbus-Kommunikation**: Asynchroner TCP-Client (pymodbus) inkl. automatischer Bündelung der Registerabfragen, Fehlerhandhabung und Wiederverbindung.
- **Entitäten**:
  - Sensoren für Status, Ströme, Leistungen, Energie, Sitzungszeiten sowie statische Metadaten (Seriennummer, Charge-Point-ID, Marke/Modell, Firmware, Controller-Uhr, Nennleistung, Phasenkonfiguration).
  - Number-Entities für dynamisches Stromlimit sowie Fail-safe-Parameter.
  - Button (optional) zum manuellen Senden des Keepalive-Registers.
- **Services**: `webasto_next_modbus.set_current`, `webasto_next_modbus.set_failsafe`, `webasto_next_modbus.send_keepalive`, `webasto_next_modbus.start_session` und `webasto_next_modbus.stop_session` als Ergänzung zu den Entitäten.
- **Erweiterbarkeit**: Registerdefinitionen konzentrieren, damit neue Datenpunkte ohne großen Eingriff ergänzt werden können.
- **Tests**: Pytest-Suite mit Mocks für Modbus, Abdeckung von Config Flow, Entitäten und Service-Logik.
- **Dokumentation**: README mit Installations-, Konfigurations- und Troubleshooting-Hinweisen.

## Domänen- und Namenskonzept

- Domain: `webasto_next_modbus`
- Geräte-ID: Kombination aus Host und Unit-ID.
- Einheiten:
  - Ampere (A), Volt (V), Watt (W), Kilowattstunden (kWh), Sekunden (s).
  - Zustände mit Enum-Mapping (z. B. Charge Point State).

## Registermodell

Registerdaten basieren auf Community-Dokumentation und Hersteller-Unterlagen:

| Schlüssel | Adresse | Typ | Skalierung | Beschreibung |
|-----------|---------|-----|------------|--------------|
| `serial_number` | 100 | string | – | Seriennummer laut Controller |
| `charge_point_id` | 130 | string | – | Backend-/Charge-Point-ID |
| `charge_point_brand` | 190 | string | – | Markenname des EVSE |
| `charge_point_model` | 210 | string | – | Modellbezeichnung |
| `firmware_version` | 230 | string | – | Firmware-Version |
| `wallbox_date` | 290 | uint32 | – | Controller-Datum (YYYYMMDD) |
| `wallbox_time` | 294 | uint32 | – | Controller-Uhrzeit (HHMMSS) |
| `rated_power_w` | 400 | uint32 | – | Nennleistung laut Gerät |
| `phase_configuration` | 404 | uint16 | – | Phasenkonfiguration (0=1p, 1=3p) |
| `charge_point_state` | 1000 | uint16 | – | IEC 61851 Zustand (0–8) |
| `charging_state` | 1001 | uint16 | – | Ladeaktivität (0/1) |
| `equipment_state` | 1002 | uint16 | – | EVSE-Zustand |
| `cable_state` | 1004 | uint16 | – | Kabel- / Fahrzeugstatus |
| `fault_code` | 1006 | uint16 | – | Fehlercode |
| `current_l{1..3}` | 1008/1010/1012 | uint16 | ×0.001 | Phasenströme |
| `voltage_l{1..3}` | 1014/1016/1018 | uint16 | – | Phasenspannungen |
| `active_power_total` | 1020 | uint32 | – | Gesamtleistung |
| `active_power_l{1..3}` | 1024/1028/1032 | uint32 | – | Phasenleistungen |
| `energy_total` | 1036 | uint32 | ×0.001 | Zählerstand gesamt |
| `ev_max_current` | 1108 | uint16 | – | Maximal zulässiger EV-Strom laut Fahrzeug |
| `charged_energy_wh` | 1502 | uint16 | – | Energie je aktueller Sitzung |
| `session_*` | 1504–1512 | uint32 | – | Sitzungsdaten (Start, Dauer, Ende) |
| `failsafe_current` | 2000 | uint16 | – | Fail-safe Strom |
| `failsafe_timeout` | 2002 | uint16 | – | Fail-safe Timeout |
| `charge_power_w` | 5000 | uint32 | – | Momentane Ladeleistung (Holding, Read) |
| `set_current` | 5004 | uint16 | – | Dynamisches Stromlimit (Write) |
| `session_command` | 5006 | uint16 | – | Sitzungsstart/-stopp befehl (Write) |
| `alive` | 6000 | uint16 | – | Keepalive Toggle |

Register werden in Gruppen bis max. 110 Register zusammengefasst, um Modbus-Overhead zu reduzieren.

## Softwarearchitektur

### Module

- `__init__.py`: Setup, Unload, Service-Registrierung, Coordinator-Initialisierung.
- `const.py`: Konstanten, Version, Register-Definitionen, Enum-Mappings.
- `coordinator.py` / `hub.py`: ModbusBridge mit asynchronem Client, Lese- und Schreibfunktionen, Fehlerbehandlung.
- `config_flow.py`: Benutzer- und Optionsdialoge, Validierung.
- Plattformdateien (`sensor.py`, `number.py`, `button.py`): Entity-Klassen mit Beschreibungen und Kommentaren.
- `services.yaml`: Definition der Custom Services.

### Datenfluss

1. Config Flow legt `host`, `port`, `unit_id` und `scan_interval` fest und prüft die Verbindung per Testleseauftrag.
2. Setup erstellt `ModbusBridge` und `DataUpdateCoordinator`.
3. Coordinator ruft zyklisch `bridge.read_data()` auf, dekodiert die Register und speichert das Ergebnis.
4. Entitäten subscriben auf Coordinator, nutzen Key aus Registerdefinition.
5. Number-Entitäten schreiben über `bridge.write_register()` und triggern Refresh.
6. Keepalive-Service oder -Button schreibt bei Bedarf 1 auf Register 6000 und löst einen sofortigen Refresh aus.

### Fehler- und Retry-Strategie

- Bei Kommunikationsfehlern: `UpdateFailed` mit Original-Fehler, Coordinator versucht beim nächsten Intervall erneut.
- Einzelne Register-Reads im Fehlerfall: markiert als `None`, loggt Warnung, blockiert aber nicht alle Werte.
- Write-Operationen clampen Werte auf definierte Grenzen und geben Exceptions an UI weiter.

## Tests

- Unit Tests für Config Flow (Happy Path, Connection Error, Unique-ID-Kollision).
- Tests für Update Coordinator mit simulierten Registerwerten und Fehlerfällen.
- Snapshot- bzw. Assertions für Entity-Registrierung (z. B. Anzahl Sensoren).
- Services werden mit Mock Bridge geprüft (Clamping, Refresh-Trigger, Fehlerfälle).

Pytest-Setup nutzt `pytest-homeassistant-custom-component` und Mocks (`pytest-mock`).

## Offene Fragen / Annahmen

- Standard-Port 502, Unit-ID 255 (laut Community). Config Flow erlaubt Anpassung.
- Firmware >3.1: Alive-Register optional; Button/Service funktionieren nur, wenn das Register vorhanden ist.
- Session-Zeitregister: Format (Unix Timestamp) wird dokumentiert, aber unverarbeitet (Rohwert). Optionale Template-Sensoren im README.

## Nächste Schritte

1. Diagnose- und Logbook-Einträge ergänzen (Diagnostics, Debug-Services).
2. Energy-Dashboard-Kompatibilität verifizieren und dokumentieren.
3. Übersetzungen vervollständigen und weitere Sprachen hinzufügen.
4. Paketierung für HACS/Release vorbereiten (Versionierung, Changelog).
5. Praxis-Tests mit realen Wallboxen durchführen und Registerliste validieren.
