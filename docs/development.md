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
./scripts/check.sh
```

This script runs the following tools in order:

| Tool | Command | Description |
| :--- | :--- | :--- |
| **Deptry** | `uv run deptry .` | Checks for unused or missing dependencies. |
| **Ruff** | `uv run ruff check .` | Lints and formats code (Python). |
| **Mdformat** | `uv run mdformat .` | Formats Markdown files. |
| **Codespell** | `uv run codespell` | Checks for spelling errors. |
| **Yamllint** | `uv run yamllint .` | Lints YAML files. |
| **Bandit** | `uv run bandit ...` | Checks for security issues. |
| **Vulture** | `uv run vulture ...` | Finds dead/unused code. |
| **Mypy** | `uv run mypy ...` | Static type checking. |
| **Pytest** | `uv run pytest` | Runs the test suite. |

If you want to run a specific check individually, you can use the `uv run <tool>` commands listed above.

## 📦 Release Playbook (Maintainers)

1. **Update Version**:

   - Bump version in `custom_components/webasto_next_modbus/manifest.json`.
   - Bump version in `custom_components/webasto_next_modbus/const.py` (`INTEGRATION_VERSION`).
   - Update `CHANGELOG.md`.

1. **Verify**:

   Run the full check suite to ensure everything is correct:

   ```bash
   ./scripts/check.sh
   ```

1. **Tag & Release**:

   - Create a signed tag: `git tag -s vX.Y.Z -m "Release vX.Y.Z"`
   - Push: `git push origin vX.Y.Z`
   - Create a GitHub Release (auto-generates notes).

1. **Branding**:

   - Submit icon updates to [home-assistant/brands](https://github.com/home-assistant/brands).
