#!/usr/bin/env bash
# =============================================================================
# IronLayer Development Environment Setup
#
# Installs all packages in editable mode using pip.
# Poetry path dependencies require installing core_engine first,
# then the dependent packages with --no-deps to avoid resolution conflicts.
#
# Usage: ./scripts/dev_setup.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
blue()  { printf '\033[0;34m%s\033[0m\n' "$*"; }
red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }

blue "Installing IronLayer packages in editable mode..."

# Step 1: Install core_engine first (it has no internal deps)
blue "  → Installing core-engine..."
pip install -e "$ROOT_DIR/core_engine" --quiet
green "  ✓ core-engine installed"

# Step 2: Install ai_engine (no internal deps)
blue "  → Installing ai-engine..."
pip install -e "$ROOT_DIR/ai_engine" --quiet
green "  ✓ ai-engine installed"

# Step 3: Install api (depends on core-engine, already installed)
blue "  → Installing ironlayer-api..."
pip install -e "$ROOT_DIR/api" --quiet
green "  ✓ ironlayer-api installed"

# Step 4: Install cli (depends on core-engine, already installed)
blue "  → Installing ironlayer-cli..."
pip install -e "$ROOT_DIR/cli" --quiet
green "  ✓ ironlayer-cli installed"

# Step 5: Install dev dependencies
blue "  → Installing dev dependencies..."
pip install pytest pytest-cov pytest-asyncio pytest-mock ruff black mypy httpx --quiet
green "  ✓ dev dependencies installed"

echo ""
green "All packages installed successfully!"
blue "  Verify: python -c 'import core_engine; import api; import ai_engine; import cli; print(\"All imports OK\")'"
