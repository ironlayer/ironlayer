"""Cloud authentication and configuration management.

Stores API URL in ``~/.ironlayer/config.toml`` and API token in the OS
keychain (macOS Keychain, GNOME Keyring, Windows Credential Locker) when
the ``keyring`` package is installed.  Falls back to the TOML file for
token storage when keyring is unavailable (e.g. headless CI runners).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover – Python < 3.11 fallback
    import tomli as tomllib  # type: ignore[no-redef]

_CONFIG_DIR = Path.home() / ".ironlayer"
_CONFIG_FILE = _CONFIG_DIR / "config.toml"
_KEYRING_SERVICE = "ironlayer-cli"
_KEYRING_USERNAME = "api_token"


def _keyring_get() -> str | None:
    """Try to read the token from the OS keychain.  Returns ``None`` on any failure."""
    try:
        import keyring  # type: ignore[import-untyped]

        return keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
    except Exception:
        return None


def _keyring_set(token: str) -> bool:
    """Try to store the token in the OS keychain.  Returns ``True`` on success."""
    try:
        import keyring  # type: ignore[import-untyped]

        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, token)
        return True
    except Exception:
        return False


def _keyring_delete() -> None:
    """Try to remove the token from the OS keychain.  Silently ignores errors."""
    try:
        import keyring  # type: ignore[import-untyped]

        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
    except Exception:
        pass


def load_cloud_config() -> dict[str, Any]:
    """Load cloud configuration from ``~/.ironlayer/config.toml``.

    Returns an empty dict if the file does not exist or cannot be parsed.
    """
    if not _CONFIG_FILE.exists():
        return {}
    try:
        with open(_CONFIG_FILE, "rb") as fh:
            return tomllib.load(fh)
    except Exception:
        return {}


def load_stored_token() -> str | None:
    """Return the stored API token, or ``None`` if not authenticated.

    Checks the OS keychain first; falls back to the TOML file.
    """
    token = _keyring_get()
    if token is not None:
        return token
    config = load_cloud_config()
    return config.get("cloud", {}).get("api_token")


def load_api_url() -> str:
    """Return the configured API URL, defaulting to production."""
    config = load_cloud_config()
    return config.get("cloud", {}).get("api_url", "https://api.ironlayer.app")


def save_cloud_config(api_url: str, api_token: str) -> None:
    """Save cloud credentials with secure storage.

    The API token is stored in the OS keychain when ``keyring`` is
    available.  The TOML file always stores the API URL and is used as a
    fallback for the token when keychain is not available.

    The file is written with ``0o600`` (owner read/write only) to prevent
    other users on the system from reading any stored credentials.
    """
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    used_keyring = _keyring_set(api_token)

    # Always persist api_url in the TOML file.  Persist the token there
    # too when keyring is unavailable so the CLI still works headless.
    if used_keyring:
        content = f'[cloud]\napi_url = "{api_url}"\n'
    else:
        content = f'[cloud]\napi_url = "{api_url}"\napi_token = "{api_token}"\n'
    _CONFIG_FILE.write_text(content, encoding="utf-8")

    # Restrict permissions to owner only (0o600).
    os.chmod(_CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)


def clear_cloud_config() -> None:
    """Remove stored cloud credentials from both keychain and config file."""
    _keyring_delete()
    if _CONFIG_FILE.exists():
        _CONFIG_FILE.unlink()
