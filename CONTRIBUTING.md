# Contributing

Thanks for taking the time to improve Webasto Next! The notes below summarise how to get set up, how to propose changes, and where to ask questions.

## Quick start

1. **Fork and clone** this repository:

   ```bash
   gh repo fork tomwellnitz/Webasto-Next-Modbus --clone
   cd Webasto-Next-Modbus
   ```

1. **Install dependencies** using `uv`:

   ```bash
   uv sync
   source .venv/bin/activate
   ```

1. **Create a feature branch**:

   ```bash
   git checkout -b feature/your-feature-name
   ```

1. **Make your changes** and verify quality:

   ```bash
   ./scripts/check.sh
   ```

1. **Commit and push**:

   ```bash
   git add .
   git commit -m "Add your feature"
   git push origin feature/your-feature-name
   ```

1. **Open a Pull Request** on GitHub and wait for CI checks to pass.

More detailed instructions live in [`docs/development.md`](docs/development.md).

## Branch protection & workflow

This repository uses **branch protection** on `main`:

- ✅ All changes must go through Pull Requests
- ✅ CI checks must pass before merging
- ✅ One approval required (for external contributors)
- ✅ Linear history enforced (squash merge only)
- ✅ Branch protection applies to **everyone** (including admins)

**This means**: Even maintainers work on feature branches and create PRs. Direct pushes to `main` are blocked.

## Opening an issue

- Use the GitHub issue templates for bugs and feature requests.
- For how-to questions or broader ideas, prefer the [discussions board](https://github.com/tomwellnitz/Webasto-Next-Modbus/discussions) instead of an issue.
- Please include relevant logs, config entries, or reproduction steps. If sensitive data is involved, redact hostnames and serial numbers.

## Pull request guidelines

- Keep changes focused and describe the motivation in the pull request template.
- Update tests and documentation when behaviour changes. The README and files under `docs/` should mirror the user experience.
- Follow the existing code style (100-character line length, type hints, async patterns). Let `ruff` fix imports and formatting where possible.
- Verify that `./scripts/check.sh` passes locally. This script runs all CI checks (tests, linting, types, security).

## Release workflow

Releases follow the checklist in [`docs/development.md`](docs/development.md#release-checklist). If you are preparing a release PR, make sure to:

- Bump the version in `custom_components/webasto_next_modbus/manifest.json` and `pyproject.toml`.
- Update `CHANGELOG.md` with a concise summary of the changes.
- Run the full test suite and linting locally.

## Code of conduct

We follow the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). Be welcoming, constructive, and respectful when interacting with other contributors.

If you have questions about this guide, open a discussion topic with the `maintenance` category or mention `@tomwellnitz` on GitHub.
