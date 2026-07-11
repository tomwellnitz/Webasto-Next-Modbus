# Reverse-engineering the wallbox web interface

The REST mapping shipped by this integration was reverse-engineered against a **Webasto Next**. The **Ampure / Webasto Unite** exposes a different REST surface — it serves all configuration through a single flat endpoint rather than the Next's per-section split, and the Next's section endpoints return `404` there ([discussion #96](https://github.com/tomwellnitz/Webasto-Next-Modbus/discussions/96), tracked in [#97](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/97)). Contributions adding Unite-specific REST support are welcome. This guide explains how to probe the wallbox's web API to discover endpoints that aren't yet covered.

> The endpoints in the examples below are the **Next's**. Where the Unite is known to differ it is called out inline. Treat every path as model- and firmware-specific until you have confirmed it against your own box.

## Prerequisites

- The wallbox reachable from your machine over the LAN.
- Web-interface credentials (default user `admin`; the password is set during commissioning).
- `curl` and `jq` (or any HTTP client). The wallbox uses a self-signed TLS certificate, so verification has to be disabled (`curl -k`).

## Step 1 — Authenticate

The web API is JWT-based. Log in once to obtain an `access_token` (valid for ~1 hour):

```bash
WALLBOX=https://192.168.1.50      # adjust
USER=admin
PASS='your-password'

TOKEN=$(curl -sk -X POST "$WALLBOX/api/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$USER\",\"password\":\"$PASS\"}" | jq -r .access_token)
echo "$TOKEN"
```

## Step 2 — Read the configuration fields

**Webasto Next** groups configuration fields into named sections. The integration currently reads `system` and `auth`:

```bash
curl -sk -H "Authorization: Bearer $TOKEN" "$WALLBOX/api/sections/system" | jq
curl -sk -H "Authorization: Bearer $TOKEN" "$WALLBOX/api/sections/auth"   | jq
curl -sk -H "Authorization: Bearer $TOKEN" "$WALLBOX/api/current-errors"  | jq
```

**Ampure / Webasto Unite** does *not* expose those section endpoints (they `404`). It serves every field in one flat call instead ([#96](https://github.com/tomwellnitz/Webasto-Next-Modbus/discussions/96)):

```bash
curl -sk -H "Authorization: Bearer $TOKEN" "$WALLBOX/api/configuration-fields/" | jq
```

Either way, each entry has a `fieldKey`, a `value` and metadata describing whether it's writable and what `configurationFieldUpdateType` to use when writing. If one form returns `404`, try the other — and note which model and firmware you are on.

## Step 3 — Discover new endpoints by watching the UI

The most reliable way to find Unite-specific or otherwise unknown endpoints is to observe what the **web UI itself** calls:

1. Open the wallbox web UI in your browser.
2. Open DevTools → **Network** tab, filter by `/api`.
3. Click through every screen (Settings, Charging, Network, Free Charging, Off-Peak, Time, …).
4. Note every URL the UI fetches. Each one is a candidate endpoint.

For systematic probing of a path like `/api/sections/<name>`, try plausible names taken from the UI's vocabulary (`network`, `time`, `off-peak`, `charging`, `phases`, …) and record which return data versus `404`.

## Step 4 — Identify the writes

For fields that the UI lets you change, watch the **Network** tab when you click *Save*. The integration uses two write endpoints today:

- `POST /api/configuration-updates` with a JSON **array** of `{fieldKey, value, configurationFieldUpdateType}` objects — used for settings updates (LED brightness, free charging, free-charging tag, …).
- `POST /api/custom-actions/<action>` — used for one-shot actions. The action name is model-specific: the Next uses `restart-system`, while the Unite was found to use `soft-reset` ([#96](https://github.com/tomwellnitz/Webasto-Next-Modbus/discussions/96)).

Capture the exact request payload and note the `configurationFieldUpdateType` value, which differs by field type — e.g. `number-configuration-field-update`, `boolean-configuration-field-update`, `simple-string-configuration-field-update`.

## What we're looking for (Unite especially)

- New `fieldKey` values not yet parsed in `custom_components/webasto_next_modbus/rest_client.py` (`_parse_system_fields` / `_parse_auth_fields`).
- New sections beyond `system` and `auth`.
- The endpoint(s) backing **Off-Peak Charging**, **Skip Random Delay** and any **phase-switching** controls exposed via REST.
- A scrubbed dump of the Unite's `GET /api/configuration-fields/` so its `fieldKey` values can be mapped to the integration's sensors (tracked in [#97](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues/97)).

## Privacy and sharing

Before posting any captures or HAR files:

- Scrub the wallbox host (IP / hostname / serial number).
- Strip the `Authorization: Bearer …` token. It's a JWT; even after expiry it leaks the wallbox identity.
- Redact MAC addresses, network interface details and any free-charging tag IDs.

Open an issue with the scrubbed findings (or a draft PR adding the parser) and tag it `enhancement`; mention which model and firmware version you probed against. The integration spec lives in [`rest-api.md`](rest-api.md) — keep that file in sync when adding a new endpoint.
