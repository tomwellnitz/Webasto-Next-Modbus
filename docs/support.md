# Support & troubleshooting

Borrowing inspiration from the Spook integration, this page centralises support information so issues can be triaged quickly and effectively.

## Before opening a ticket

1. **Check the README** – The [Troubleshooting section](../README.md#troubleshooting--diagnostics) lists common failure modes (connection loss, stale data, diagnostics exports, debug logging).
2. **Collect diagnostics** – From Home Assistant, open **Settings → Devices & Services → Webasto Next Modbus → ⋮ → Download diagnostics**. Attach the JSON payload when filing a bug; it contains register snapshots and error contexts.
3. **Enable debug logs** – Temporarily add the snippet below to `configuration.yaml` and reproduce the issue:

   ```yaml
   logger:
     default: info
     logs:
       custom_components.webasto_next_modbus: debug
   ```

   Remember to remove or downgrade the log level after the issue is resolved.

4. **Virtual wallbox** – When in doubt whether a regression stems from the integration or your hardware, use the bundled simulator (`virtual_wallbox/`) to compare behaviour.

## Where to ask questions

- **Usage questions or automation ideas** – Start a thread in the [GitHub discussions](https://github.com/tomwellnitz/Webasto-Next-Modbus/discussions) board.
- **Bugs** – Use the bug report template. Include diagnostics, relevant log excerpts, and the firmware version of your wallbox.
- **Feature requests** – Open a feature request issue or discussion with a clear use-case and the registers involved.

Issues that only contain a screenshot or a generic “doesn’t work” statement are hard to action. Providing the diagnostics export, configuration details, and exact reproduction steps dramatically speeds up responses.

## Known limitations

- Modbus connectivity does not recover automatically if the wallbox changes its IP address mid-session. Configure a DHCP reservation to keep the host stable.
- Firmware versions prior to 3.1 may omit the keep-alive register. The integration hides the button/service in that case.
- Energy Dashboard metadata is not exposed yet. Follow [this tracking issue](https://github.com/tomwellnitz/Webasto-Next-Modbus/issues) for updates.

## Security disclosures

If you discover a security vulnerability, do **not** open a public issue. Instead, email `security@tomwellnitz.de` with the findings, steps to reproduce, and mitigation suggestions.

## Need direct contact?

If the above channels do not address your question, mention `@tomwellnitz` in a discussion topic with the `support` label. Direct support is provided on a best-effort basis; please include as much context as possible so the community can help too.
