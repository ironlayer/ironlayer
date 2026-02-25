#!/usr/bin/env bash
# IronLayer installer — https://ironlayer.app
# Usage: curl -fsSL https://ironlayer.app/install.sh | bash
#
# This script installs the IronLayer CLI and verifies the installation.
# It requires Python 3.11+, pip, and git.
#
# Environment variables:
#   IRONLAYER_INSTALL_METHOD  Override install method: "pypi" or "source" (default: auto)
#   IRONLAYER_VERSION         Pin to a specific version/tag (default: latest / main)

set -euo pipefail

BOLD="\033[1m"
DIM="\033[2m"
CYAN="\033[36m"
GREEN="\033[32m"
RED="\033[31m"
YELLOW="\033[33m"
RESET="\033[0m"

REPO_URL="${IRONLAYER_REPO_URL:-https://github.com/ironlayer/ironlayer.git}"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=11
INSTALL_METHOD="${IRONLAYER_INSTALL_METHOD:-auto}"
VERSION="${IRONLAYER_VERSION:-}"

info()  { printf "${CYAN}▸${RESET} %s\n" "$*"; }
ok()    { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
err()   { printf "${RED}✗${RESET} %s\n" "$*" >&2; }
fatal() { err "$@"; exit 1; }

banner() {
  printf "\n${BOLD}${CYAN}"
  cat <<'ART'
  ___              _
 |_ _|_ _ ___ _ _| |   __ _ _  _ ___ _ _
  | || '_/ _ \ ' \ |__/ _` | || / -_) '_|
 |___|_| \___/_||_____\__,_|\_, \___|_|
                             |__/
ART
  printf "${RESET}\n"
  printf "  ${DIM}AI-native transformation control plane for Databricks${RESET}\n\n"
}

# ── Detect Python ────────────────────────────────────────────────────────────

find_python() {
  local candidates=("python3.12" "python3.11" "python3" "python")
  for cmd in "${candidates[@]}"; do
    if command -v "$cmd" &>/dev/null; then
      PYTHON_CMD="$cmd"
      return 0
    fi
  done
  return 1
}

check_python_version() {
  local version major minor
  version=$("$PYTHON_CMD" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
  major=$("$PYTHON_CMD" -c "import sys; print(sys.version_info.major)")
  minor=$("$PYTHON_CMD" -c "import sys; print(sys.version_info.minor)")

  if [[ "$major" -lt "$MIN_PYTHON_MAJOR" ]] || { [[ "$major" -eq "$MIN_PYTHON_MAJOR" ]] && [[ "$minor" -lt "$MIN_PYTHON_MINOR" ]]; }; then
    fatal "Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ required (found $version). Install from https://python.org"
  fi

  ok "Python $version ($PYTHON_CMD)"
}

# ── Detect pip ───────────────────────────────────────────────────────────────

find_pip() {
  if "$PYTHON_CMD" -m pip --version &>/dev/null; then
    PIP_CMD="$PYTHON_CMD -m pip"
    return 0
  fi
  local candidates=("pip3" "pip")
  for cmd in "${candidates[@]}"; do
    if command -v "$cmd" &>/dev/null; then
      PIP_CMD="$cmd"
      return 0
    fi
  done
  return 1
}

# ── Detect git ───────────────────────────────────────────────────────────────

check_git() {
  if command -v git &>/dev/null; then
    ok "git $(git --version | awk '{print $3}')"
    return 0
  fi
  return 1
}

# ── Install from PyPI ────────────────────────────────────────────────────────

install_from_pypi() {
  info "Installing ironlayer from PyPI..."
  local pip_flags=("--upgrade")
  if [[ -z "${VIRTUAL_ENV:-}" ]] && [[ "$(id -u)" -ne 0 ]]; then
    pip_flags+=("--user")
  fi

  local pkg="ironlayer"
  if [[ -n "$VERSION" ]]; then
    pkg="ironlayer==${VERSION}"
  fi

  if $PIP_CMD install "${pip_flags[@]}" "$pkg" 2>&1; then
    ok "ironlayer installed from PyPI"
    return 0
  fi
  return 1
}

# ── Install from source ─────────────────────────────────────────────────────

install_from_source() {
  info "Installing ironlayer from source..."

  local tmpdir
  tmpdir=$(mktemp -d)
  trap "rm -rf '$tmpdir'" EXIT

  local branch="${VERSION:-main}"
  info "Cloning $REPO_URL (branch: $branch)..."
  if ! git clone --depth 1 --branch "$branch" "$REPO_URL" "$tmpdir/ironlayer" 2>&1; then
    err "git clone failed"
    return 1
  fi
  ok "Repository cloned"

  local pip_flags=("--upgrade")
  if [[ -z "${VIRTUAL_ENV:-}" ]] && [[ "$(id -u)" -ne 0 ]]; then
    pip_flags+=("--user")
  fi

  info "Installing core engine..."
  $PIP_CMD install "${pip_flags[@]}" "$tmpdir/ironlayer/core_engine/" 2>&1 || {
    err "core_engine install failed"
    return 1
  }
  ok "ironlayer-core installed"

  info "Installing CLI..."
  $PIP_CMD install "${pip_flags[@]}" "$tmpdir/ironlayer/cli/" 2>&1 || {
    err "CLI install failed"
    return 1
  }
  ok "ironlayer CLI installed"
}

# ── Verify ───────────────────────────────────────────────────────────────────

verify_installation() {
  local user_base
  user_base=$("$PYTHON_CMD" -m site --user-base 2>/dev/null || true)
  if [[ -n "$user_base" ]] && [[ -d "$user_base/bin" ]]; then
    export PATH="$user_base/bin:$PATH"
  fi

  if command -v ironlayer &>/dev/null; then
    local version
    version=$(ironlayer --version 2>/dev/null || echo "installed")
    ok "ironlayer CLI available: $version"
  else
    warn "ironlayer installed but not on PATH."
    echo ""
    echo "  Add this to your shell profile (~/.bashrc, ~/.zshrc, etc.):"
    echo ""
    if [[ -n "$user_base" ]]; then
      echo "    export PATH=\"$user_base/bin:\$PATH\""
    else
      echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
    echo ""
    echo "  Then restart your terminal or run: source ~/.bashrc"
  fi
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
  banner

  # 1. Python
  info "Checking Python..."
  if ! find_python; then
    fatal "Python not found. Install Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ from https://python.org"
  fi
  check_python_version

  # 2. pip
  info "Checking pip..."
  if ! find_pip; then
    fatal "pip not found. Install with: $PYTHON_CMD -m ensurepip --upgrade"
  fi
  ok "pip available ($PIP_CMD)"

  # 3. git (needed for source install)
  info "Checking git..."
  if ! check_git; then
    if [[ "$INSTALL_METHOD" == "source" ]]; then
      fatal "git is required for source installation. Install git first."
    fi
    warn "git not found — PyPI install only"
  fi

  # 4. Install
  local installed=false

  if [[ "$INSTALL_METHOD" == "pypi" ]]; then
    install_from_pypi && installed=true

  elif [[ "$INSTALL_METHOD" == "source" ]]; then
    install_from_source && installed=true

  else
    # Auto: try PyPI first, fall back to source
    if install_from_pypi 2>/dev/null; then
      installed=true
    else
      warn "PyPI package not found — installing from source"
      install_from_source && installed=true
    fi
  fi

  if [[ "$installed" != "true" ]]; then
    fatal "Installation failed. See errors above or try: IRONLAYER_INSTALL_METHOD=source bash install.sh"
  fi

  # 5. Verify
  info "Verifying installation..."
  verify_installation

  # 6. Done
  echo ""
  printf "${BOLD}${GREEN}Installation complete!${RESET}\n"
  echo ""
  echo "  Get started:"
  echo ""
  echo "    ironlayer init my-project    # scaffold a new project"
  echo "    ironlayer plan . HEAD~1 HEAD # generate a plan from git diff"
  echo "    ironlayer --help             # see all commands"
  echo ""
  echo "  Docs: https://ironlayer.app/docs/quickstart"
  echo ""
}

main "$@"
