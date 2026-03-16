"""Shared helper utilities used across multiple CLI command modules.

Kept separate to avoid duplication between apply, backfill, and other
commands that load models or manipulate date ranges.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import typer
from rich.console import Console

console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Model SQL loading
# ---------------------------------------------------------------------------


def load_model_sql_map(repo_path: Path) -> dict[str, str]:
    """Load all model definitions from a repo and return a {model_name: clean_sql} map."""
    from core_engine.loader import load_models_from_directory

    models_dir = repo_path / "models"
    if not models_dir.is_dir():
        models_dir = repo_path
    model_list = load_models_from_directory(models_dir)
    return {m.name: m.clean_sql for m in model_list}


def resolve_model_sql(
    model_name: str,
    sql_map: dict[str, str],
) -> str:
    """Look up model SQL from the preloaded map, raising on missing models."""
    sql = sql_map.get(model_name)
    if not sql:
        available = ", ".join(sorted(sql_map.keys())[:10])
        suffix = "..." if len(sql_map) > 10 else ""
        console.print(
            f"[red]Model '{model_name}' not found in repo. "
            f"Available models: {available}{suffix}[/red]"
        )
        raise typer.Exit(code=3)
    return sql


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def parse_date(value: str, label: str) -> date:
    """Parse a YYYY-MM-DD string into a :class:`date`, raising on failure."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        console.print(f"[red]Invalid {label} date '{value}': {exc}[/red]")
        raise typer.Exit(code=3) from exc


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_input_range(input_range: object) -> str:
    """Format an optional DateRange as a human-readable string."""
    if input_range is None:
        return "-"
    start = getattr(input_range, "start", None)
    end = getattr(input_range, "end", None)
    if start is not None and end is not None:
        return f"{start} .. {end}"
    return "-"
