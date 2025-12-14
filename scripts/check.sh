#!/bin/bash
set -e

# Ensure we are in the project root
cd "$(dirname "$0")/.."

echo "🚀 Starting checks..."

echo "📦 Checking dependencies (deptry)..."
uv run deptry .

echo "🧹 Linting (ruff)..."
uv run ruff check .
uv run ruff format --check .

echo "📝 Checking spelling (codespell)..."
uv run codespell

echo "� Formatting Markdown (mdformat)..."
uv run mdformat --check .

echo "�📄 Checking YAML (yamllint)..."
uv run yamllint .

echo "🔒 Checking security (bandit)..."
uv run bandit -c pyproject.toml -r custom_components/webasto_next_modbus

echo "💀 Checking for dead code (vulture)..."
uv run vulture custom_components/webasto_next_modbus .vulture_whitelist.py

echo "types Checking types (mypy)..."
uv run mypy custom_components/webasto_next_modbus

echo "🧪 Running tests (pytest)..."
uv run pytest

echo "✅ All checks passed!"