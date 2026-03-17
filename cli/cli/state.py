"""Global CLI state — shared mutable options set by the Typer callback.

All command modules import from this module rather than referencing
module-level globals directly.  This keeps the state centralised and
makes each command independently importable without side-effects.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Mutable state (set once by the global-options callback before any command runs)
# ---------------------------------------------------------------------------

_json_output: bool = False
_metrics_file: Path | None = None
_env: str = "dev"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def set_global_options(
    *,
    json_output: bool,
    metrics_file: Path | None,
    env: str,
) -> None:
    """Populate the global state from the Typer callback.

    Called exactly once per CLI invocation by the ``@app.callback`` handler
    in ``cli.app`` before any sub-command executes.
    """
    global _json_output, _metrics_file, _env  # noqa: PLW0603
    _json_output = json_output
    _metrics_file = metrics_file
    _env = env


def get_json_output() -> bool:
    """Return True when the ``--json`` flag is active."""
    return _json_output


def get_env() -> str:
    """Return the current environment string (dev | staging | prod)."""
    return _env


def get_metrics_file() -> Path | None:
    """Return the configured metrics file path, or None."""
    return _metrics_file


def emit_metrics(event: str, data: dict) -> None:  # type: ignore[type-arg]
    """Append a timestamped metrics event to the metrics file, if configured.

    Failures are logged but never propagate — metrics emission must never
    break the main command execution.
    """
    if _metrics_file is None:
        return
    record = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": data,
    }
    try:
        with _metrics_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except OSError:
        pass
