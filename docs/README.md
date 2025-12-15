# Documentation portal

Welcome! This folder collects the human-facing documentation for the Webasto Next Modbus integration. Inspired by the structure of the [Spook](https://github.com/frenck/spook) project, the goal is to keep a single entry point that guides you to the right level of detail.

## Getting started

- **User guide** – The top-level [`README.md`](../README.md) covers installation (HACS and manual), configuration, entity overviews, and troubleshooting tips.
- **Quick install notes** – The [Quick start](../README.md#quick-start) section shows the fastest path from checkout to a running integration.

## Deep dives

- **Architecture** – [`architecture.md`](architecture.md) explains the register map, data flow, and design goals.
- **Development** – [`development.md`](development.md) documents local setup, tooling commands, the virtual wallbox simulator, and the release checklist.
- **REST API** – [`rest-api.md`](rest-api.md) provides the complete REST API specification for the wallbox web interface.
- **REST API Integration** – [`rest-api-integration-plan.md`](rest-api-integration-plan.md) describes the implemented REST API features and roadmap.

## Support & community

- Review the new [`support.md`](support.md) page for tips on collecting diagnostics, known limitations, and where to ask for help.
- Join the [GitHub discussions](https://github.com/tomwellnitz/Webasto-Next-Modbus/discussions) to share ideas or request enhancements.

## Release history

- Keep an eye on [`CHANGELOG.md`](../CHANGELOG.md) for user-visible changes per release.
- The [GitHub Releases page](https://github.com/tomwellnitz/Webasto-Next-Modbus/releases) links binary assets and highlights upgrade notes.

## Contributing

If you want to contribute or run the integration from source, start with [`CONTRIBUTING.md`](../CONTRIBUTING.md) and the development guide above. The tooling, testing strategy, and release playbook mirror the practices used by leading Home Assistant custom integrations.

Have an idea for more documentation? Open an issue or a discussion topic—we are keen to keep this portal comprehensive and friendly!
