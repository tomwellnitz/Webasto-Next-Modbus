# 👨‍💻 Developer Guide

This guide covers how to set up your environment, run tests, and release new versions.

## 🛠️ Environment Setup

We use **uv** for fast dependency management.

1. **Install uv** (if not installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Sync Dependencies**:
   ```bash
   uv sync
   source .venv/bin/activate
   ```

### 🐳 Local Testing (Docker)

Want to test your changes in a real Home Assistant instance?

```bash
docker compose -f docker/docker-compose.yml up -d
```

- **URL**: http://localhost:8123
- **Config**: `ha-config/` (mapped to `/config`)
- **Code**: `custom_components/` is mounted live. Restart HA to apply changes:
  ```bash
  docker compose -f docker/docker-compose.yml restart homeassistant
  ```

## 🧪 Testing & Linting

Always run these before submitting a PR!

| Command | Description |
| :--- | :--- |
| `uv run pytest` | Runs the full test suite. |
| `uv run ruff check .` | Checks for code style and errors. |
| `uv run ruff format .` | Auto-formats your code. |

## 📦 Release Playbook (Maintainers)

1. **Update Version**:
   - Bump version in `custom_components/webasto_next_modbus/manifest.json`.
   - Update `CHANGELOG.md`.

2. **Verify**:
   ```bash
   uv run ruff check .
   uv run pytest
   ```

3. **Tag & Release**:
   - Create a signed tag: `git tag -s vX.Y.Z -m "Release vX.Y.Z"`
   - Push: `git push origin vX.Y.Z`
   - Create a GitHub Release (auto-generates notes).

4. **Branding**:
   - Submit icon updates to [home-assistant/brands](https://github.com/home-assistant/brands).
