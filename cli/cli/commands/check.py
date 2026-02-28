"""``ironlayer check`` -- run quality checks against SQL models.

Executes registered check types (model tests, schema contracts, etc.)
and displays a summary of results.  Human-readable output goes to
stderr via Rich; JSON output goes to stdout in ``--json`` mode.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

logger = logging.getLogger(__name__)

console = Console(stderr=True)


def check_command(
    model_dir: Path = typer.Argument(
        ...,
        help="Path to the directory containing SQL model files.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    model_name: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Run checks for a specific model only.",
    ),
    check_type: str | None = typer.Option(
        None,
        "--type",
        "-t",
        help="Run only a specific check type (e.g. MODEL_TEST, SCHEMA_CONTRACT).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json/--no-json",
        help="Emit structured JSON to stdout.",
    ),
    fail_on_warn: bool = typer.Option(
        False,
        "--fail-on-warn",
        help="Treat warnings as failures (exit code 1).",
    ),
) -> None:
    """Run quality checks against SQL models.

    Executes all registered check types and reports results.  By default
    only blocking failures (CRITICAL/HIGH severity) cause a non-zero
    exit code.

    Examples::

        ironlayer check ./models
        ironlayer check ./models --model analytics.orders_daily
        ironlayer check ./models --type MODEL_TEST
        ironlayer check ./models --json
    """
    asyncio.run(
        _run_checks(
            model_dir=model_dir,
            model_name=model_name,
            check_type=check_type,
            json_output=json_output,
            fail_on_warn=fail_on_warn,
        )
    )


async def _run_checks(
    *,
    model_dir: Path,
    model_name: str | None,
    check_type: str | None,
    json_output: bool,
    fail_on_warn: bool,
) -> None:
    """Internal async implementation for the check command."""
    from core_engine.checks import CheckContext, CheckType, create_default_engine
    from core_engine.loader import load_models_from_directory

    # 1. Load models.
    try:
        models = load_models_from_directory(str(model_dir))
    except Exception as exc:
        console.print(f"[red]Failed to load models from {model_dir}: {exc}[/red]")
        raise typer.Exit(code=2) from exc

    if not models:
        console.print("[yellow]No models found.[/yellow]")
        raise typer.Exit(code=0)

    console.print(f"[dim]Loaded {len(models)} model(s) from {model_dir}[/dim]")

    # 2. Build context.
    check_types = None
    if check_type is not None:
        try:
            ct = CheckType(check_type)
            check_types = [ct]
        except ValueError:
            valid_types = ", ".join(t.value for t in CheckType)
            console.print(f"[red]Unknown check type '{check_type}'. Valid types: {valid_types}[/red]")
            raise typer.Exit(code=2)

    model_names = [model_name] if model_name is not None else None

    context = CheckContext(
        models=models,
        check_types=check_types,
        model_names=model_names,
    )

    # 3. Run checks.
    engine = create_default_engine()
    console.print("[dim]Running checks...[/dim]")
    summary = await engine.run(context)

    # 4. Output results.
    if json_output:
        output = {
            "total": summary.total,
            "passed": summary.passed,
            "failed": summary.failed,
            "warned": summary.warned,
            "errored": summary.errored,
            "skipped": summary.skipped,
            "blocking_failures": summary.blocking_failures,
            "duration_ms": summary.duration_ms,
            "results": [r.model_dump() for r in summary.results],
        }
        sys.stdout.write(json.dumps(output, sort_keys=True, indent=2, default=str) + "\n")
    else:
        _display_check_summary(summary)

    # 5. Exit code.
    if summary.has_blocking_failures:
        raise typer.Exit(code=1)
    if fail_on_warn and summary.warned > 0:
        raise typer.Exit(code=1)


def _display_check_summary(summary: "CheckSummary") -> None:  # noqa: F821
    """Render check results as a Rich table to stderr."""
    from core_engine.checks.models import CheckStatus

    # Summary panel.
    status_color = "green" if not summary.has_blocking_failures else "red"
    status_text = "ALL CHECKS PASSED" if not summary.has_blocking_failures else "CHECKS FAILED"

    summary_text = (
        f"[bold {status_color}]{status_text}[/bold {status_color}]\n"
        f"Total: {summary.total}  "
        f"Passed: [green]{summary.passed}[/green]  "
        f"Failed: [red]{summary.failed}[/red]  "
        f"Warned: [yellow]{summary.warned}[/yellow]  "
        f"Errors: [red]{summary.errored}[/red]  "
        f"Skipped: [dim]{summary.skipped}[/dim]  "
        f"Duration: {summary.duration_ms}ms"
    )
    console.print(Panel(summary_text, title="Check Engine Results", border_style=status_color))

    # Only show details for non-PASS, non-SKIP results.
    detail_results = [r for r in summary.results if r.status not in (CheckStatus.PASS, CheckStatus.SKIP)]
    if not detail_results:
        return

    table = Table(title="Check Details", show_lines=True)
    table.add_column("Model", style="cyan")
    table.add_column("Check Type", style="blue")
    table.add_column("Status")
    table.add_column("Severity")
    table.add_column("Message")

    status_styles = {
        CheckStatus.FAIL: "red",
        CheckStatus.WARN: "yellow",
        CheckStatus.ERROR: "red bold",
    }

    for r in detail_results:
        style = status_styles.get(r.status, "white")
        table.add_row(
            r.model_name,
            r.check_type.value,
            f"[{style}]{r.status.value}[/{style}]",
            r.severity.value,
            r.message,
        )

    console.print(table)
