# 👨‍💻 Developer Guide

This guide covers how to set up your environment, run tests, and release new versions.

## 🛠️ Environment Setup

We use **uv** for fast dependency management.

1. **Install uv** (if not installed):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

1. **Sync Dependencies**:

   ```bash
   uv sync
   source .venv/bin/activate
   ```

### 🐳 Local Testing (Docker)

Want to test your changes in a real Home Assistant instance?

```bash
docker compose -f docker/docker-compose.yml up -d
```

- **URL**: <http://localhost:8123>

- **Config**: `ha-config/` (mapped to `/config`)

- **Code**: `custom_components/` is mounted live. Restart HA to apply changes:

  ```bash
  docker compose -f docker/docker-compose.yml restart homeassistant
  ```

## 🧪 Testing & Linting

We use a comprehensive suite of tools to ensure code quality. The easiest way to run all checks is:

```bash
./scripts/check.sh          # fixes lint, formatting and Markdown in place, then checks
./scripts/check.sh --check  # read-only, exactly what CI runs
```

This script runs the following tools in order:

| Tool | Command | Description |
| :--- | :--- | :--- |
| **Deptry** | `uv run deptry .` | Checks for unused or missing dependencies. |
| **Ruff** | `uv run ruff check .` / `uv run ruff format .` | Lints and formats Python (including code blocks in Markdown). |
| **Codespell** | `uv run codespell` | Checks for spelling errors (configured in `pyproject.toml`). |
| **Mdformat** | `uv run mdformat <tracked .md files>` | Formats Markdown files. |
| **Yamllint** | `uv run yamllint --strict .` | Lints YAML files, including `.github/`. |
| **Actionlint** | `uv run actionlint` | Lints the GitHub workflows. |
| **Bandit** | `uv run bandit -c pyproject.toml -r custom_components/webasto_next_modbus` | Checks for security issues. |
| **Vulture** | `uv run vulture ...` | Finds dead/unused code. |
| **Mypy** | `uv run mypy custom_components/webasto_next_modbus` | Static type checking (strict). |
| **Pytest** | `uv run pytest --cov` | Runs the test suite; fails below the coverage threshold in `pyproject.toml`. |

If you want to run a specific check individually, you can use the `uv run <tool>` commands listed above.

The same tools are available as optional [pre-commit](https://pre-commit.com) hooks (`pre-commit install`); they run through `uv run`, so they use the locked versions.

### Dependencies and the lock file

`uv.lock` is committed and CI installs with `uv sync --locked`, so every run tests exactly the locked versions. After changing dependencies in `pyproject.toml`, run `uv lock` (or `uv sync`) and commit the updated `uv.lock` in the same change. Dependabot updates both files together.

### Snapshot tests

`tests/test_snapshots.py` records every entity (registry entry and state), the device and the diagnostics download for both models in `tests/snapshots/`. When a change is intended, regenerate the snapshots and review the diff:

```bash
uv run pytest tests/test_snapshots.py --snapshot-update
```

## 📦 Release Playbook (Maintainers)

1. **Update Version**:

   - Bump `version` in `custom_components/webasto_next_modbus/manifest.json`.
   - Bump `version` in `pyproject.toml` (keep it in sync with the manifest).
   - Move the `## [Unreleased]` section in `CHANGELOG.md` to the new `## [X.Y.Z] - YYYY-MM-DD` (the release notes are generated from this section).

1. **Verify**:

   Run the full check suite to ensure everything is correct:

   ```bash
   ./scripts/check.sh --check
   ```

1. **Tag & Release**:

   - Create the tag: `git tag -a vX.Y.Z -m "vX.Y.Z"` and push it: `git push origin vX.Y.Z`.
   - The **Release** workflow runs on the tag. It first checks that the tag matches the `manifest.json` and `pyproject.toml` versions and, for a final release, that `CHANGELOG.md` has a `## [X.Y.Z]` section, and stops otherwise. It then runs `./scripts/check.sh --check`, builds `webasto_next_modbus.zip` (for manual installs; HACS installs from the tagged source), extracts the matching `CHANGELOG.md` section and publishes the GitHub Release.
   - For a pre-release, use a tag with a suffix (e.g. `vX.Y.Z-beta.1`) and keep the plain `X.Y.Z` in `manifest.json` / `pyproject.toml`; the workflow marks it as a GitHub pre-release (HACS offers it only under "Show beta versions") and pulls notes from the `[Unreleased]` section.

1. **Branding**:

   - Submit icon updates to [home-assistant/brands](https://github.com/home-assistant/brands).
