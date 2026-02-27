#!/usr/bin/env bash
# =============================================================================
# IronLayer Development Environment Setup
#
# Uses uv to install all workspace packages in development mode.
#
# Usage: ./scripts/dev_setup.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
blue()  { printf '\033[0;34m%s\033[0m\n' "$*"; }
red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }

# Check that uv is available
if ! command -v uv &>/dev/null; then
  red "uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

blue "Installing IronLayer packages via uv workspace..."

cd "$ROOT_DIR"
uv sync --all-packages
green "All packages installed successfully!"

echo ""
blue "  Verify: uv run python -c 'import core_engine; import api; import ai_engine; import cli; print(\"All imports OK\")'"
