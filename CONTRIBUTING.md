# Contributing

Thanks for taking the time to improve Webasto Next Modbus! The notes below summarise how to get set up, how to propose changes, and where to ask questions.

## Quick start

1. Clone this repository and install dependencies using `uv`:

   ```bash
   uv sync
   source .venv/bin/activate
   ```

2. Run the tooling suite before opening a pull request:

   ```bash
   uv run ruff check .
   uv run pytest
   ```

3. Optional: Start the bundled Home Assistant sandbox for manual verification (`docker/docker-compose.yml`).

More detailed instructions live in [`docs/development.md`](docs/development.md).

## Opening an issue

- Use the GitHub issue templates for bugs and feature requests.
- For how-to questions or broader ideas, prefer the [discussions board](https://github.com/tomwellnitz/Webasto-Next-Modbus/discussions) instead of an issue.
- Please include relevant logs, config entries, or reproduction steps. If sensitive data is involved, redact hostnames and serial numbers.

## Pull request guidelines

- Keep changes focused and describe the motivation in the pull request template.
- Update tests and documentation when behaviour changes. The README and files under `docs/` should mirror the user experience.
- Follow the existing code style (100-character line length, type hints, async patterns). Let `ruff` fix imports and formatting where possible.
- Verify that `uv run pytest` passes and that `uv run ruff check .` reports no new issues.

## Release workflow

Releases follow the checklist in [`docs/development.md`](docs/development.md#release-checklist). If you are preparing a release PR, make sure to:

- Bump the version in `custom_components/webasto_next_modbus/manifest.json` and `pyproject.toml`.
- Update `CHANGELOG.md` with a concise summary of the changes.
- Run the full test suite and linting locally.

## Code of conduct

We follow the [Home Assistant Code of Conduct](https://www.home-assistant.io/code-of-conduct/). Be welcoming, constructive, and respectful when interacting with other contributors.

If you have questions about this guide, open a discussion topic with the `maintenance` category or mention `@tomwellnitz` on GitHub.
