#!/usr/bin/env bash
# Run every quality check CI runs.
#
#   ./scripts/check.sh          fix lint/format/Markdown issues in place, then check
#   ./scripts/check.sh --check  never modify files; fail on anything unformatted (CI)
set -euo pipefail

# Ensure we are in the project root
cd "$(dirname "$0")/.."

mode="fix"
case "${1:-}" in
  "") ;;
  --check) mode="check" ;;
  *)
    echo "usage: $0 [--check]" >&2
    exit 2
    ;;
esac

echo "🚀 Starting checks (${mode} mode)..."

echo "📦 Checking dependencies (deptry)..."
uv run deptry .

echo "🧹 Linting (ruff)..."
if [ "$mode" = "check" ]; then
  uv run ruff check .
  uv run ruff format --check .
else
  uv run ruff check --fix .
  uv run ruff format .
fi

echo "📝 Checking spelling (codespell)..."
uv run codespell

echo "📑 Formatting Markdown (mdformat)..."
# Only tracked files: `mdformat .` would also walk .venv.
mapfile -t markdown_files < <(git ls-files '*.md')
if [ "$mode" = "check" ]; then
  uv run mdformat --check "${markdown_files[@]}"
else
  uv run mdformat "${markdown_files[@]}"
fi

echo "📄 Checking YAML (yamllint)..."
uv run yamllint --strict .

echo "⚙️ Checking GitHub workflows (actionlint)..."
uv run actionlint

echo "🔒 Checking security (bandit)..."
uv run bandit -c pyproject.toml -r custom_components/webasto_next_modbus

echo "💀 Checking for dead code (vulture)..."
uv run vulture custom_components/webasto_next_modbus .vulture_whitelist.py

echo "🔍 Checking types (mypy)..."
uv run mypy custom_components/webasto_next_modbus

echo "🧪 Running tests with coverage (pytest)..."
uv run pytest --cov

echo "✅ All checks passed!"
