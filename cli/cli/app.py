"""IronLayer CLI application -- Typer-based developer interface.

Provides commands for plan generation, inspection, execution, backfill,
model listing, and lineage traversal.  Human-readable output goes to
*stderr* via Rich; machine-readable artefacts (plan JSON, metrics) go to
files on disk so that pipelines can compose cleanly.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from core_engine.models.model_definition import ModelDefinition

import typer
from rich.console import Console

from cli.display import (
    display_check_results,
    display_cross_model_column_lineage,
    display_lineage,
    display_migration_report,
    display_model_list,
    display_plan_summary,
    display_run_results,
)

# ---------------------------------------------------------------------------
# App & global state
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="ironlayer",
    help="IronLayer - AI-Native Databricks Transformation Control Plane",
    no_args_is_help=True,
)
console = Console(stderr=True)

migrate_app = typer.Typer(
    name="migrate",
    help="Import models from external tools into IronLayer format.",
    no_args_is_help=True,
)
app.add_typer(migrate_app, name="migrate")

mcp_app = typer.Typer(
    name="mcp",
    help="MCP (Model Context Protocol) server for AI assistant integration.",
    no_args_is_help=True,
)
app.add_typer(mcp_app, name="mcp")

# Register the init, dev, and check commands.
from cli.commands.check import check_command  # noqa: E402
from cli.commands.dev import dev_command  # noqa: E402
from cli.commands.init import init_command  # noqa: E402

app.command(name="init")(init_command)
app.command(name="dev")(dev_command)
app.command(name="check")(check_command)

# Mutable global options populated by the Typer callback.
_json_output: bool = False
_metrics_file: Path | None = None
_env: str = "dev"


# ---------------------------------------------------------------------------
# Callback -- global options
# ---------------------------------------------------------------------------


@app.callback()
def _global_options(
    json_mode: bool = typer.Option(
        False,
        "--json/--no-json",
        help="Emit structured JSON to stdout instead of human-readable output.",
    ),
    metrics_file: Path | None = typer.Option(
        None,
        "--metrics-file",
        help="Write metrics events to this file (JSONL).",
        envvar="PLATFORM_METRICS_FILE",
    ),
    env: str = typer.Option(
        "dev",
        "--env",
        help="Environment override (dev | staging | prod).",
        envvar="PLATFORM_ENV",
    ),
) -> None:
    """Global options applied to every command."""
    global _json_output, _metrics_file, _env  # noqa: PLW0603
    _json_output = json_mode
    _metrics_file = metrics_file
    _env = env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _emit_metrics(event: str, data: dict[str, Any]) -> None:
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
        # Read-only filesystem, disk full, permission denied, etc.
        # Never crash the CLI because metrics emission failed.
        pass


def _parse_date(value: str, label: str) -> date:
    """Parse a YYYY-MM-DD string into a :class:`date`, raising on failure."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        console.print(f"[red]Invalid {label} date '{value}': {exc}[/red]")
        raise typer.Exit(code=3) from exc


def _credentials_path() -> Path:
    """Return the path to the stored credentials file."""
    return Path.home() / ".ironlayer" / "credentials.json"


def _load_stored_token() -> str | None:
    """Load the access token from ``~/.ironlayer/credentials.json``."""
    cred_path = _credentials_path()
    if not cred_path.exists():
        return None
    try:
        data = json.loads(cred_path.read_text(encoding="utf-8"))
        return cast("str | None", data.get("access_token"))
    except Exception:
        return None


def _save_credentials(
    api_url: str,
    access_token: str,
    refresh_token: str,
    email: str,
) -> None:
    """Persist credentials to ``~/.ironlayer/credentials.json`` (chmod 600)."""
    cred_path = _credentials_path()
    cred_path.parent.mkdir(parents=True, exist_ok=True)
    cred_path.write_text(
        json.dumps(
            {
                "api_url": api_url,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "email": email,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    cred_path.chmod(0o600)


def _api_request(
    method: str,
    api_url: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    """Send an HTTP request to the IronLayer API and return the JSON response.

    Uses ``httpx`` for synchronous calls.  Auth token is resolved in order:

    1. ``IRONLAYER_API_TOKEN`` environment variable (API key or JWT)
    2. Stored credentials from ``~/.ironlayer/credentials.json``
       (written by ``ironlayer login``)
    """
    import httpx

    headers: dict[str, str] = {"Content-Type": "application/json"}
    token = os.environ.get("IRONLAYER_API_TOKEN") or _load_stored_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{api_url.rstrip('/')}{path}"
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(
                method,
                url,
                headers=headers,
                json=body,
                params=params,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        console.print(f"[red]API error ({exc.response.status_code}): {detail}[/red]")
        raise typer.Exit(code=3) from exc
    except httpx.ConnectError as exc:
        console.print(f"[red]Cannot connect to API at {api_url}: {exc}[/red]")
        raise typer.Exit(code=3) from exc


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


@app.command()
def plan(
    repo: Path = typer.Argument(
        ...,
        help="Path to the git repository containing SQL models.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    base: str = typer.Argument(
        ...,
        help="Base git ref (commit SHA or branch) representing the current state.",
    ),
    target: str = typer.Argument(
        ...,
        help="Target git ref (commit SHA or branch) representing the desired state.",
    ),
    out: Path = typer.Option(
        Path("plan.json"),
        "--out",
        "-o",
        help="Output path for the generated plan JSON.",
    ),
    as_of_date: str | None = typer.Option(
        None,
        "--as-of-date",
        help="Reference date for date arithmetic (YYYY-MM-DD). Defaults to today.",
    ),
) -> None:
    """Generate a deterministic execution plan from a git diff."""
    from core_engine.config import load_settings
    from core_engine.diff import compute_structural_diff
    from core_engine.git import get_changed_files, get_file_at_commit, validate_repo
    from core_engine.graph import build_dag
    from core_engine.loader import load_models_from_directory
    from core_engine.parser import compute_canonical_hash
    from core_engine.planner import PlannerConfig, generate_plan, serialize_plan

    try:
        # 1. Validate git repo.
        validate_repo(repo)

        # 2. Load models from the target tree.
        models_dir = repo / "models"
        if not models_dir.is_dir():
            models_dir = repo  # Fall back to repo root if no models/ subdir.
        models = load_models_from_directory(models_dir)
        if not models:
            console.print("[yellow]No models found. Nothing to plan.[/yellow]")
            raise typer.Exit(code=0)

        # 3. Build DAG.
        dag = build_dag(models)

        # 4. Get changed files between base and target.
        changed_files = get_changed_files(repo, base, target)
        sql_changed = [cf for cf in changed_files if cf.path.endswith(".sql")]

        # 5. Compute content hashes at both commits for changed models.
        model_map = {m.name: m for m in models}
        changed_model_names = set()
        for cf in sql_changed:
            for m in models:
                if m.file_path.endswith(cf.path) or cf.path.endswith(m.file_path):
                    changed_model_names.add(m.name)

        previous_versions: dict[str, str] = {}
        current_versions: dict[str, str] = {}
        base_sql_map: dict[str, str] = {}
        for m in models:
            current_versions[m.name] = m.content_hash

        for m_name in changed_model_names:
            m_def = model_map[m_name]
            try:
                old_sql = get_file_at_commit(repo, m_def.file_path, base)
                base_sql_map[m_name] = old_sql
                previous_versions[m_name] = compute_canonical_hash(old_sql)
            except Exception:
                # File did not exist at base -- it is a new model.
                pass

        # Models not in changed set have identical hashes in both snapshots.
        for m in models:
            if m.name not in changed_model_names:
                previous_versions[m.name] = m.content_hash
                current_versions[m.name] = m.content_hash

        # 6. Compute structural diff.
        diff_result = compute_structural_diff(previous_versions, current_versions)

        # 6b. Compute AST diffs for modified models (column-level impact).
        from core_engine.diff.ast_diff import compute_ast_diff
        from core_engine.models.diff import ASTDiffDetail

        ast_diffs: dict[str, ASTDiffDetail] = {}
        for m_name in sorted(diff_result.modified_models):
            if m_name in model_map and m_name in base_sql_map:
                try:
                    ast_diffs[m_name] = compute_ast_diff(
                        base_sql_map[m_name],
                        model_map[m_name].clean_sql,
                    )
                except Exception:
                    pass  # Skip — step will still be included without diff detail.

        # 7. Resolve as-of date.
        ref_date = _parse_date(as_of_date, "as-of-date") if as_of_date else date.today()

        # 8. Load settings for planner config.
        settings = load_settings(env=_env)
        planner_config = PlannerConfig(
            default_lookback_days=settings.default_lookback_days,
        )

        # 9. Generate plan (watermarks and run_stats empty for fresh plans).
        execution_plan = generate_plan(
            models=model_map,
            diff_result=diff_result,
            dag=dag,
            watermarks={},
            run_stats={},
            config=planner_config,
            base=base,
            target=target,
            as_of_date=ref_date,
            base_sql=base_sql_map,
            ast_diffs=ast_diffs,
        )

        # 10. Serialize and write.
        plan_json = serialize_plan(execution_plan)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(plan_json, encoding="utf-8")

        _emit_metrics(
            "plan.generated",
            {
                "plan_id": execution_plan.plan_id,
                "total_steps": execution_plan.summary.total_steps,
                "estimated_cost_usd": execution_plan.summary.estimated_cost_usd,
            },
        )

        # 11. Display summary.
        if _json_output:
            sys.stdout.write(plan_json + "\n")
        else:
            display_plan_summary(console, execution_plan)
            console.print(f"\nPlan written to [bold]{out}[/bold]")

            # Subtle cloud upsell when not connected.
            if not _load_stored_token():
                from cli.cloud import load_stored_token as _cloud_token

                if not _cloud_token():
                    console.print(
                        "\n[dim]Tip: Get AI-powered cost estimates and risk scoring"
                        " -- run [bold]ironlayer login[/bold] to connect to"
                        " IronLayer Cloud.[/dim]"
                    )

        raise typer.Exit(code=0)

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Error generating plan: {exc}[/red]")
        _emit_metrics("plan.error", {"error": str(exc)})
        raise typer.Exit(code=3) from exc


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


@app.command()
def show(
    plan_path: Path = typer.Argument(
        ...,
        help="Path to a plan JSON file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Display a human-readable summary of a plan."""
    from core_engine.planner import deserialize_plan

    try:
        plan_json = plan_path.read_text(encoding="utf-8")
        execution_plan = deserialize_plan(plan_json)
    except Exception as exc:
        console.print(f"[red]Failed to read plan: {exc}[/red]")
        raise typer.Exit(code=3) from exc

    if _json_output:
        sys.stdout.write(plan_json.strip() + "\n")
    else:
        display_plan_summary(console, execution_plan)


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def _load_model_sql_map(repo_path: Path) -> dict[str, str]:
    """Load all model definitions from a repo and return a {model_name: clean_sql} map."""
    from core_engine.loader import load_models_from_directory

    models_dir = repo_path / "models"
    if not models_dir.is_dir():
        models_dir = repo_path
    model_list = load_models_from_directory(models_dir)
    return {m.name: m.clean_sql for m in model_list}


def _resolve_model_sql(
    model_name: str,
    sql_map: dict[str, str],
) -> str:
    """Look up model SQL from the preloaded map, raising on missing models."""
    sql = sql_map.get(model_name)
    if not sql:
        available = ", ".join(sorted(sql_map.keys())[:10])
        suffix = "..." if len(sql_map) > 10 else ""
        console.print(f"[red]Model '{model_name}' not found in repo. Available models: {available}{suffix}[/red]")
        raise typer.Exit(code=3)
    return sql


@app.command("apply")
def apply_plan(
    plan_path: Path = typer.Argument(
        ...,
        help="Path to the plan JSON file to execute.",
        exists=True,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    repo: Path = typer.Option(
        ...,
        "--repo",
        help="Path to the git repository containing SQL model definitions.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    approve_by: str | None = typer.Option(
        None,
        "--approve-by",
        help="Name of the person approving this plan execution.",
    ),
    auto_approve: bool = typer.Option(
        False,
        "--auto-approve",
        help="Skip manual approval (only allowed in dev environment).",
    ),
    override_cluster: str | None = typer.Option(
        None,
        "--override-cluster",
        help="Override the cluster/warehouse used for execution.",
    ),
) -> None:
    """Execute a previously generated plan."""
    from core_engine.config import load_settings
    from core_engine.executor import LocalExecutor
    from core_engine.models.run import RunRecord, RunStatus
    from core_engine.planner import deserialize_plan

    try:
        plan_json = plan_path.read_text(encoding="utf-8")
        execution_plan = deserialize_plan(plan_json)
    except Exception as exc:
        console.print(f"[red]Failed to read plan: {exc}[/red]")
        raise typer.Exit(code=3) from exc

    # Load model SQL definitions from the repository.
    try:
        sql_map = _load_model_sql_map(repo)
    except Exception as exc:
        console.print(f"[red]Failed to load models from repo: {exc}[/red]")
        raise typer.Exit(code=3) from exc

    # Approval gate: non-dev environments require explicit approval.
    if not auto_approve and _env != "dev":
        if not approve_by:
            console.print("[red]Non-dev environments require --approve-by or --auto-approve.[/red]")
            raise typer.Exit(code=3)
        console.print(f"Plan approved by: [bold]{approve_by}[/bold]")

    if execution_plan.summary.total_steps == 0:
        console.print("[green]Plan has zero steps -- nothing to execute.[/green]")
        raise typer.Exit(code=0)

    # Set up executor (context manager ensures cleanup even on exceptions).
    settings = load_settings(env=_env)

    _emit_metrics(
        "apply.started",
        {
            "plan_id": execution_plan.plan_id,
            "total_steps": execution_plan.summary.total_steps,
            "env": _env,
            "approved_by": approve_by or ("auto" if auto_approve else "dev-default"),
        },
    )

    # Execute each step sequentially, respecting depends_on ordering
    # (steps are already in topological order from the planner).
    run_records: list[dict[str, Any]] = []
    failed = False

    with LocalExecutor(db_path=settings.local_db_path) as executor:
        for idx, step in enumerate(execution_plan.steps, start=1):
            step_label = f"[{idx}/{execution_plan.summary.total_steps}] {step.model}"

            if failed:
                run_records.append(
                    {
                        "model": step.model,
                        "status": "CANCELLED",
                        "duration_seconds": 0.0,
                        "input_range": _format_input_range(step.input_range),
                        "retries": 0,
                    }
                )
                continue

            with console.status(f"Executing {step_label}...", spinner="dots"):
                # Build parameters for date range substitution.
                parameters: dict[str, str] = {}
                if step.input_range is not None:
                    parameters["start_date"] = step.input_range.start.isoformat()
                    parameters["end_date"] = step.input_range.end.isoformat()

                if override_cluster:
                    parameters["cluster_id"] = override_cluster

                model_sql = _resolve_model_sql(step.model, sql_map)
                record: RunRecord = executor.execute_step(
                    step=step,
                    sql=model_sql,
                    parameters=parameters,
                )

            duration = 0.0
            if record.started_at and record.finished_at:
                duration = (record.finished_at - record.started_at).total_seconds()

            run_records.append(
                {
                    "model": step.model,
                    "status": record.status.value,
                    "duration_seconds": round(duration, 2),
                    "input_range": _format_input_range(step.input_range),
                    "retries": record.retry_count,
                }
            )

            _emit_metrics(
                "step.completed",
                {
                    "plan_id": execution_plan.plan_id,
                    "step_id": step.step_id,
                    "model": step.model,
                    "status": record.status.value,
                    "duration_seconds": round(duration, 2),
                },
            )

            if record.status == RunStatus.FAIL:
                failed = True
                console.print(f"[red]Step {step_label} failed: {record.error_message}[/red]")

    _emit_metrics(
        "apply.completed",
        {
            "plan_id": execution_plan.plan_id,
            "failed": failed,
            "steps_executed": len([r for r in run_records if r["status"] != "CANCELLED"]),
        },
    )

    # Display results.
    if _json_output:
        sys.stdout.write(json.dumps(run_records, indent=2, default=str) + "\n")
    else:
        display_run_results(console, run_records)

    if failed:
        raise typer.Exit(code=3)


def _format_input_range(input_range: object) -> str:
    """Format an optional DateRange as a human-readable string."""
    if input_range is None:
        return "-"
    # input_range is a DateRange pydantic model with .start and .end attrs.
    start = getattr(input_range, "start", None)
    end = getattr(input_range, "end", None)
    if start is not None and end is not None:
        return f"{start} .. {end}"
    return "-"


# ---------------------------------------------------------------------------
# backfill
# ---------------------------------------------------------------------------


@app.command()
def backfill(
    model: str = typer.Option(
        ...,
        "--model",
        "-m",
        help="Canonical model name to backfill.",
    ),
    start: str = typer.Option(
        ...,
        "--start",
        help="Start date for the backfill range (YYYY-MM-DD, inclusive).",
    ),
    end: str = typer.Option(
        ...,
        "--end",
        help="End date for the backfill range (YYYY-MM-DD, inclusive).",
    ),
    repo: Path = typer.Option(
        ...,
        "--repo",
        help="Path to the git repository containing SQL model definitions.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    cluster: str | None = typer.Option(
        None,
        "--cluster",
        help="Override the cluster/warehouse used for execution.",
    ),
) -> None:
    """Run a targeted backfill for a single model over a date range."""
    from core_engine.config import load_settings
    from core_engine.executor import LocalExecutor
    from core_engine.models.plan import DateRange, PlanStep, RunType, compute_deterministic_id
    from core_engine.models.run import RunStatus

    start_date = _parse_date(start, "start")
    end_date = _parse_date(end, "end")

    if start_date > end_date:
        console.print("[red]Start date must not be after end date.[/red]")
        raise typer.Exit(code=3)

    input_range = DateRange(start=start_date, end=end_date)

    # Build a synthetic single-step plan for the backfill.
    step_id = compute_deterministic_id(model, "backfill", start, end)
    compute_deterministic_id("backfill", model, start, end)

    step = PlanStep(
        step_id=step_id,
        model=model,
        run_type=RunType.INCREMENTAL,
        input_range=input_range,
        depends_on=[],
        parallel_group=0,
        reason=f"manual backfill {start} to {end}",
        estimated_compute_seconds=0.0,
        estimated_cost_usd=0.0,
    )

    console.print(f"Backfilling [bold]{model}[/bold] from [cyan]{start_date}[/cyan] to [cyan]{end_date}[/cyan]")

    settings = load_settings(env=_env)
    with LocalExecutor(db_path=settings.local_db_path) as executor:
        _emit_metrics(
            "backfill.started",
            {
                "model": model,
                "start": start,
                "end": end,
            },
        )

        parameters: dict[str, str] = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        if cluster:
            parameters["cluster_id"] = cluster

        sql_map = _load_model_sql_map(repo)
        model_sql = _resolve_model_sql(model, sql_map)

        with console.status(f"Executing backfill for {model}...", spinner="dots"):
            record = executor.execute_step(
                step=step,
                sql=model_sql,
                parameters=parameters,
            )

        duration = 0.0
        if record.started_at and record.finished_at:
            duration = (record.finished_at - record.started_at).total_seconds()

        run_records = [
            {
                "model": model,
                "status": record.status.value,
                "duration_seconds": round(duration, 2),
                "input_range": f"{start_date} .. {end_date}",
                "retries": record.retry_count,
            }
        ]

        _emit_metrics(
            "backfill.completed",
            {
                "model": model,
                "status": record.status.value,
                "duration_seconds": round(duration, 2),
            },
        )

        if _json_output:
            sys.stdout.write(json.dumps(run_records, indent=2, default=str) + "\n")
        else:
            display_run_results(console, run_records)

        if record.status == RunStatus.FAIL:
            console.print(f"[red]Backfill failed: {record.error_message}[/red]")
            raise typer.Exit(code=3)

        console.print("[green]Backfill completed successfully.[/green]")


# ---------------------------------------------------------------------------
# backfill-chunked
# ---------------------------------------------------------------------------


@app.command("backfill-chunked")
def backfill_chunked(
    model: str = typer.Option(
        ...,
        "--model",
        "-m",
        help="Canonical model name to backfill.",
    ),
    start: str = typer.Option(
        ...,
        "--start",
        help="Start date for the backfill range (YYYY-MM-DD, inclusive).",
    ),
    end: str = typer.Option(
        ...,
        "--end",
        help="End date for the backfill range (YYYY-MM-DD, inclusive).",
    ),
    repo: Path = typer.Option(
        ...,
        "--repo",
        help="Path to the git repository containing SQL model definitions.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    chunk_days: int = typer.Option(
        7,
        "--chunk-days",
        help="Number of days per chunk (default 7).",
        min=1,
    ),
    cluster: str | None = typer.Option(
        None,
        "--cluster",
        help="Override the cluster/warehouse used for execution.",
    ),
) -> None:
    """Run a chunked backfill with checkpoint-based resume capability.

    Splits the date range into chunks and executes sequentially.  If a
    chunk fails, you can resume with ``backfill-resume``.
    """
    from datetime import timedelta

    from core_engine.config import load_settings
    from core_engine.executor import LocalExecutor
    from core_engine.models.plan import DateRange, PlanStep, RunType, compute_deterministic_id
    from core_engine.models.run import RunStatus

    start_date = _parse_date(start, "start")
    end_date = _parse_date(end, "end")

    if start_date > end_date:
        console.print("[red]Start date must not be after end date.[/red]")
        raise typer.Exit(code=3)

    # Compute chunks.
    chunks: list[tuple[date, date]] = []
    cursor = start_date
    while cursor <= end_date:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end_date)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)

    backfill_id = compute_deterministic_id(
        "chunked_backfill",
        model,
        start,
        end,
        str(chunk_days),
    )

    console.print(
        f"Chunked backfill [bold]{model}[/bold] "
        f"from [cyan]{start_date}[/cyan] to [cyan]{end_date}[/cyan] "
        f"({len(chunks)} chunks of {chunk_days} day(s))"
    )

    settings = load_settings(env=_env)
    with LocalExecutor(db_path=settings.local_db_path) as executor:
        sql_map = _load_model_sql_map(repo)
        model_sql = _resolve_model_sql(model, sql_map)

        _emit_metrics(
            "backfill_chunked.started",
            {
                "model": model,
                "start": start,
                "end": end,
                "chunk_days": chunk_days,
                "total_chunks": len(chunks),
            },
        )

        run_records: list[dict[str, Any]] = []
        failed = False
        completed_through: date | None = None

        for i, (chunk_start, chunk_end) in enumerate(chunks, start=1):
            chunk_label = f"[{i}/{len(chunks)}] {model} ({chunk_start} .. {chunk_end})"

            if failed:
                run_records.append(
                    {
                        "model": model,
                        "status": "CANCELLED",
                        "duration_seconds": 0.0,
                        "input_range": f"{chunk_start} .. {chunk_end}",
                        "retries": 0,
                        "chunk": i,
                    }
                )
                continue

            step_id = compute_deterministic_id(
                model,
                "chunk",
                chunk_start.isoformat(),
                chunk_end.isoformat(),
            )
            input_range = DateRange(start=chunk_start, end=chunk_end)
            step = PlanStep(
                step_id=step_id,
                model=model,
                run_type=RunType.INCREMENTAL,
                input_range=input_range,
                depends_on=[],
                parallel_group=0,
                reason=f"chunked backfill chunk {i}/{len(chunks)}",
                estimated_compute_seconds=0.0,
                estimated_cost_usd=0.0,
            )

            parameters: dict[str, str] = {
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
            }
            if cluster:
                parameters["cluster_id"] = cluster

            with console.status(f"Executing {chunk_label}...", spinner="dots"):
                record = executor.execute_step(
                    step=step,
                    sql=model_sql,
                    parameters=parameters,
                )

            duration = 0.0
            if record.started_at and record.finished_at:
                duration = (record.finished_at - record.started_at).total_seconds()

            run_records.append(
                {
                    "model": model,
                    "status": record.status.value,
                    "duration_seconds": round(duration, 2),
                    "input_range": f"{chunk_start} .. {chunk_end}",
                    "retries": record.retry_count,
                    "chunk": i,
                }
            )

            _emit_metrics(
                "backfill_chunked.chunk_completed",
                {
                    "model": model,
                    "chunk": i,
                    "total_chunks": len(chunks),
                    "status": record.status.value,
                    "duration_seconds": round(duration, 2),
                },
            )

            if record.status == RunStatus.FAIL:
                failed = True
                console.print(f"[red]Chunk {chunk_label} failed: {record.error_message}[/red]")
                console.print(
                    f"[yellow]Resume from this point with:[/yellow]\n"
                    f"  ironlayer backfill-resume --backfill-id {backfill_id}"
                )
            else:
                completed_through = chunk_end
                console.print(f"  [green]✓[/green] Chunk {i}/{len(chunks)} completed")

        _emit_metrics(
            "backfill_chunked.completed",
            {
                "model": model,
                "backfill_id": backfill_id,
                "failed": failed,
                "completed_chunks": len([r for r in run_records if r["status"] == "SUCCESS"]),
                "total_chunks": len(chunks),
            },
        )

        if _json_output:
            result = {
                "backfill_id": backfill_id,
                "model": model,
                "status": "FAILED" if failed else "COMPLETED",
                "completed_through": completed_through.isoformat() if completed_through else None,
                "total_chunks": len(chunks),
                "completed_chunks": len([r for r in run_records if r["status"] == "SUCCESS"]),
                "runs": run_records,
            }
            sys.stdout.write(json.dumps(result, indent=2, default=str) + "\n")
        else:
            display_run_results(console, run_records)

        if failed:
            raise typer.Exit(code=3)

        console.print("[green]All chunks completed successfully.[/green]")


# ---------------------------------------------------------------------------
# backfill-resume
# ---------------------------------------------------------------------------


@app.command("backfill-resume")
def backfill_resume(
    backfill_id: str = typer.Option(
        ...,
        "--backfill-id",
        help="Backfill identifier from a previous chunked backfill.",
    ),
    api_url: str = typer.Option(
        "http://localhost:8000",
        "--api-url",
        help="IronLayer API base URL.",
        envvar="IRONLAYER_API_URL",
    ),
) -> None:
    """Resume a previously failed chunked backfill.

    Connects to the IronLayer API to resume a backfill from the last
    successfully completed chunk.
    """
    console.print(f"Resuming backfill [bold]{backfill_id}[/bold]...")

    result = _api_request(
        "POST",
        api_url,
        f"/api/v1/backfills/{backfill_id}/resume",
    )

    _emit_metrics(
        "backfill_resume.completed",
        {
            "backfill_id": backfill_id,
        },
    )

    if _json_output:
        sys.stdout.write(json.dumps(result, indent=2, default=str) + "\n")
    else:
        runs = result.get("runs", [])
        if runs:
            display_run_results(console, runs)
        else:
            console.print("[green]Backfill resumed successfully.[/green]")


# ---------------------------------------------------------------------------
# backfill-history
# ---------------------------------------------------------------------------


@app.command("backfill-history")
def backfill_history(
    model: str = typer.Option(
        ...,
        "--model",
        "-m",
        help="Canonical model name to retrieve history for.",
    ),
    api_url: str = typer.Option(
        "http://localhost:8000",
        "--api-url",
        help="IronLayer API base URL.",
        envvar="IRONLAYER_API_URL",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        help="Maximum number of history entries to retrieve.",
        min=1,
        max=100,
    ),
) -> None:
    """Show backfill history for a model.

    Connects to the IronLayer API to retrieve and display the backfill
    history for the specified model.
    """
    from rich.table import Table

    console.print(f"Backfill history for [bold]{model}[/bold]")

    result = _api_request(
        "GET",
        api_url,
        f"/api/v1/backfills/history/{model}",
        params={"limit": limit},
    )

    if _json_output:
        sys.stdout.write(json.dumps(result, indent=2, default=str) + "\n")
    else:
        if not result:
            console.print("[yellow]No backfill history found.[/yellow]")
            return

        table = Table(title=f"Backfill History: {model}")
        table.add_column("Plan ID", style="dim", max_width=16)
        table.add_column("Start Date")
        table.add_column("End Date")
        table.add_column("Status")
        table.add_column("Created")

        for entry in result:
            plan_id = str(entry.get("plan_id", ""))[:16]
            start_date = entry.get("start_date", "-")
            end_date = entry.get("end_date", "-")
            status = entry.get("status", "-")
            created = entry.get("created_at", "-")
            if created and created != "-":
                try:
                    created = datetime.fromisoformat(created).strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    pass

            status_style = "green" if status == "SUCCESS" else "red" if status == "FAIL" else "yellow"
            table.add_row(
                plan_id,
                str(start_date),
                str(end_date),
                f"[{status_style}]{status}[/{status_style}]",
                str(created),
            )

        console.print(table)


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


@app.command()
def models(
    repo: Path = typer.Argument(
        ...,
        help="Path to the repository containing SQL models.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
) -> None:
    """List all models discovered in a repository."""
    from core_engine.loader import load_models_from_directory

    models_dir = repo / "models"
    if not models_dir.is_dir():
        models_dir = repo

    try:
        model_defs = load_models_from_directory(models_dir)
    except Exception as exc:
        console.print(f"[red]Failed to load models: {exc}[/red]")
        raise typer.Exit(code=3) from exc

    if not model_defs:
        console.print("[yellow]No models found.[/yellow]")
        raise typer.Exit(code=0)

    if _json_output:
        rows = [
            {
                "name": m.name,
                "kind": m.kind.value,
                "materialization": m.materialization.value,
                "time_column": m.time_column,
                "owner": m.owner,
                "tags": m.tags,
                "dependencies": m.dependencies,
            }
            for m in model_defs
        ]
        sys.stdout.write(json.dumps(rows, indent=2) + "\n")
    else:
        display_model_list(console, model_defs)


# ---------------------------------------------------------------------------
# lineage
# ---------------------------------------------------------------------------


@app.command()
def lineage(
    repo: Path = typer.Argument(
        ...,
        help="Path to the repository containing SQL models.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    model: str = typer.Option(
        ...,
        "--model",
        "-m",
        help="Canonical model name to trace lineage for.",
    ),
    column: str | None = typer.Option(
        None,
        "--column",
        "-c",
        help=(
            "Column name to trace.  When provided, switches to column-level "
            "lineage mode.  Without --column, shows table-level lineage."
        ),
    ),
    depth: int = typer.Option(
        50,
        "--depth",
        help="Maximum traversal depth for cross-model column tracing.",
        min=1,
        max=200,
    ),
) -> None:
    """Display upstream and downstream lineage for a model.

    By default shows table-level lineage (upstream/downstream models).
    Use --column/-c to switch to column-level lineage, tracing a
    specific output column back through the DAG to its source tables
    and columns.
    """
    from core_engine.graph import build_dag, get_downstream, get_upstream
    from core_engine.loader import load_models_from_directory

    models_dir = repo / "models"
    if not models_dir.is_dir():
        models_dir = repo

    try:
        model_defs = load_models_from_directory(models_dir)
    except Exception as exc:
        console.print(f"[red]Failed to load models: {exc}[/red]")
        raise typer.Exit(code=3) from exc

    if not model_defs:
        console.print("[yellow]No models found.[/yellow]")
        raise typer.Exit(code=0)

    dag = build_dag(model_defs)
    model_names = {m.name for m in model_defs}

    if model not in model_names:
        console.print(f"[red]Model '{model}' not found in repository.[/red]")
        available = ", ".join(sorted(model_names)[:10])
        if model_names:
            console.print(f"[dim]Available models: {available}[/dim]")
        raise typer.Exit(code=3)

    # ---------------------------------------------------------------
    # Column-level lineage mode
    # ---------------------------------------------------------------
    if column is not None:
        from core_engine.graph import (
            trace_column_across_dag,
        )
        from core_engine.sql_toolkit import Dialect

        # Build model_name -> clean_sql mapping.
        model_sql_map: dict[str, str] = {}
        for m in model_defs:
            sql = m.clean_sql if m.clean_sql else m.raw_sql
            if sql:
                model_sql_map[m.name] = sql

        if model not in model_sql_map:
            console.print(f"[red]No SQL found for model '{model}'.[/red]")
            raise typer.Exit(code=3)

        try:
            cross_lineage = trace_column_across_dag(
                dag=dag,
                target_model=model,
                target_column=column,
                model_sql_map=model_sql_map,
                dialect=Dialect.DATABRICKS,
                max_depth=depth,
            )
        except Exception as exc:
            console.print(f"[red]Column lineage failed: {exc}[/red]")
            raise typer.Exit(code=3) from exc

        if _json_output:
            result: dict[str, Any] = {
                "model": model,
                "column": column,
                "lineage_path": [
                    {
                        "column": node.column,
                        "source_table": node.source_table,
                        "source_column": node.source_column,
                        "transform_type": node.transform_type,
                        "transform_sql": node.transform_sql,
                    }
                    for node in cross_lineage.lineage_path
                ],
            }
            sys.stdout.write(json.dumps(result, indent=2) + "\n")
        else:
            display_cross_model_column_lineage(console, cross_lineage)
        return

    # ---------------------------------------------------------------
    # Table-level lineage mode (default)
    # ---------------------------------------------------------------
    upstream = sorted(get_upstream(dag, model))
    downstream = sorted(get_downstream(dag, model))

    if _json_output:
        result = {
            "model": model,
            "upstream": upstream,
            "downstream": downstream,
        }
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
    else:
        display_lineage(console, model, upstream, downstream)


# ---------------------------------------------------------------------------
# login -- authenticate and store credentials
# ---------------------------------------------------------------------------


@app.command()
def login(
    api_url: str = typer.Option(
        ...,
        "--api-url",
        help="IronLayer API base URL (e.g. https://api.ironlayer.app).",
        envvar="IRONLAYER_API_URL",
        prompt="IronLayer API URL",
    ),
    email: str = typer.Option(
        ...,
        "--email",
        help="Account email address.",
        prompt="Email",
    ),
    password: str = typer.Option(
        ...,
        "--password",
        help="Account password.",
        prompt="Password",
        hide_input=True,
    ),
) -> None:
    """Authenticate with a IronLayer API server and store credentials locally.

    Credentials are saved to ``~/.ironlayer/credentials.json`` (mode 0600).
    Subsequent CLI commands will automatically use the stored token when
    ``IRONLAYER_API_TOKEN`` is not set.
    """
    import httpx

    login_url = f"{api_url.rstrip('/')}/api/v1/auth/login"
    console.print(f"[dim]Authenticating with {api_url} …[/dim]")

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                login_url,
                json={"email": email, "password": password},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        console.print(f"[red]Login failed ({exc.response.status_code}): {detail}[/red]")
        raise typer.Exit(code=1) from exc
    except httpx.ConnectError as exc:
        console.print(f"[red]Could not connect to {api_url}. Check the URL and ensure the API is running.[/red]")
        raise typer.Exit(code=1) from exc

    access_token = data.get("access_token", "")
    refresh_token = data.get("refresh_token", "")
    user = data.get("user", {})

    if not access_token:
        console.print("[red]Login response did not include an access token.[/red]")
        raise typer.Exit(code=1)

    _save_credentials(api_url, access_token, refresh_token, email)

    cred_path = _credentials_path()
    console.print(f"[green]✓ Logged in as {user.get('display_name', email)}[/green]")
    console.print(f"[dim]  Tenant:      {data.get('tenant_id', 'unknown')}[/dim]")
    console.print(f"[dim]  Role:        {user.get('role', 'unknown')}[/dim]")
    console.print(f"[dim]  Credentials: {cred_path}[/dim]")


@app.command()
def logout() -> None:
    """Remove stored credentials.

    Clears the local credential file created by ``ironlayer login``.
    This does **not** revoke the token server-side; use ``ironlayer revoke``
    or the web UI for that.
    """
    cred_path = _credentials_path()
    if cred_path.exists():
        cred_path.unlink()
        console.print("[green]✓ Logged out — credentials removed.[/green]")
    else:
        console.print("[dim]No stored credentials found.[/dim]")


@app.command()
def whoami() -> None:
    """Show the currently authenticated user.

    Reads the stored credentials and fetches the user profile from the
    API to display the current identity.
    """
    cred_path = _credentials_path()
    if not cred_path.exists():
        console.print("[yellow]Not logged in. Run [bold]ironlayer login[/bold] first.[/yellow]")
        raise typer.Exit(code=1)

    try:
        creds = json.loads(cred_path.read_text(encoding="utf-8"))
    except Exception:
        console.print("[red]Could not read credentials file.[/red]")
        raise typer.Exit(code=1)

    api_url = creds.get("api_url", "")
    token = creds.get("access_token", "")
    stored_email = creds.get("email", "unknown")

    if not api_url or not token:
        console.print("[yellow]Credentials incomplete. Run [bold]ironlayer login[/bold] again.[/yellow]")
        raise typer.Exit(code=1)

    # Try to fetch the live profile; fall back to stored email if offline.
    import httpx

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(
                f"{api_url.rstrip('/')}/api/v1/auth/me",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            user = resp.json()
    except Exception:
        console.print(f"[dim]API URL:  {api_url}[/dim]")
        console.print(f"[dim]Email:   {stored_email}[/dim]")
        console.print("[yellow]Could not reach API — showing cached info only.[/yellow]")
        return

    console.print(f"[green]✓ {user.get('display_name', stored_email)}[/green]")
    console.print(f"[dim]  Email:   {user.get('email', stored_email)}[/dim]")
    console.print(f"[dim]  Tenant:  {user.get('tenant_id', 'unknown')}[/dim]")
    console.print(f"[dim]  Role:    {user.get('role', 'unknown')}[/dim]")
    console.print(f"[dim]  API URL: {api_url}[/dim]")


# ---------------------------------------------------------------------------
# migrate helpers
# ---------------------------------------------------------------------------

# Regex to extract table references from FROM and JOIN clauses in raw SQL.
# Handles optional schema qualification (schema.table), backtick/double-quote
# quoting, and aliases.  Captures the first non-keyword identifier after
# FROM/JOIN keywords.
_SQL_TABLE_REF_PATTERN = re.compile(
    r"""
    (?:FROM|JOIN)\s+               # FROM or JOIN keyword
    (?:`([^`]+)`                   # backtick-quoted identifier
    | "([^"]+)"                    # double-quote-quoted identifier
    | (                            # unquoted identifier
        [a-zA-Z_]\w*               # first segment
        (?:\.[a-zA-Z_]\w*)*        # optional dotted segments (schema.table)
      )
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# SQL keywords that can appear after FROM/JOIN but are not table names.
_SQL_KEYWORDS: frozenset[str] = frozenset(
    {
        "select",
        "where",
        "group",
        "order",
        "having",
        "limit",
        "union",
        "except",
        "intersect",
        "with",
        "on",
        "using",
        "as",
        "inner",
        "outer",
        "left",
        "right",
        "cross",
        "full",
        "natural",
        "lateral",
    }
)


def _extract_sql_table_refs(sql: str) -> list[str]:
    """Extract table references from FROM and JOIN clauses in raw SQL.

    Returns a deduplicated, sorted list of table identifiers found in
    the SQL text.  Subqueries (``FROM (SELECT ...)``) and common table
    expression references are **not** detected -- this is a best-effort
    heuristic for migration purposes.

    Parameters
    ----------
    sql:
        Raw SQL text to parse.

    Returns
    -------
    list[str]
        Sorted, deduplicated list of table references.
    """
    seen: set[str] = set()
    refs: list[str] = []

    for match in _SQL_TABLE_REF_PATTERN.finditer(sql):
        # Exactly one of the three groups will be non-None.
        table_name = match.group(1) or match.group(2) or match.group(3) or ""
        table_name = table_name.strip()

        if not table_name:
            continue

        # Skip SQL keywords that may appear after FROM/JOIN.
        if table_name.lower() in _SQL_KEYWORDS:
            continue

        # Skip subquery indicators.
        if table_name.startswith("("):
            continue

        if table_name not in seen:
            seen.add(table_name)
            refs.append(table_name)

    refs.sort()
    return refs


def _generate_ironlayer_file(
    model: ModelDefinition,
    output_dir: Path,
    original_sql: str | None = None,
) -> Path:
    """Generate a IronLayer-formatted ``.sql`` file from a ModelDefinition.

    The file uses the ``-- key: value`` comment header format that
    :func:`core_engine.loader.model_loader.parse_yaml_header` can parse.

    Parameters
    ----------
    model:
        The model definition containing all metadata and SQL.
    output_dir:
        Root directory where model files are written.  Subdirectories
        are created based on the model name (dots become path separators).
    original_sql:
        If provided, used as the SQL body.  Otherwise the model's
        ``clean_sql`` or ``raw_sql`` is used.

    Returns
    -------
    Path
        Absolute path to the written file.
    """
    # Derive relative path from model name: "staging.orders" -> staging/orders.sql
    parts = model.name.split(".")
    if len(parts) >= 2:
        rel_path = Path(*parts[:-1]) / f"{parts[-1]}.sql"
    else:
        rel_path = Path(f"{parts[0]}.sql")

    output_path = output_dir / rel_path

    # Build the header lines.
    header_lines: list[str] = [
        f"-- name: {model.name}",
        f"-- kind: {model.kind.value}",
        f"-- materialization: {model.materialization.value}",
    ]

    if model.time_column:
        header_lines.append(f"-- time_column: {model.time_column}")
    if model.unique_key:
        header_lines.append(f"-- unique_key: {model.unique_key}")
    if model.partition_by:
        header_lines.append(f"-- partition_by: {model.partition_by}")
    if model.incremental_strategy:
        header_lines.append(f"-- incremental_strategy: {model.incremental_strategy}")
    if model.owner:
        header_lines.append(f"-- owner: {model.owner}")
    if model.tags:
        header_lines.append(f"-- tags: {', '.join(model.tags)}")
    if model.dependencies:
        header_lines.append(f"-- dependencies: {', '.join(model.dependencies)}")

    # Determine the SQL body.
    sql_body = original_sql or model.clean_sql or model.raw_sql
    if not sql_body.strip():
        sql_body = f"-- No SQL body available for model: {model.name}"

    # Assemble the full file content.
    header = "\n".join(header_lines)
    file_content = f"{header}\n\n{sql_body}\n"

    # Write to disk.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(file_content, encoding="utf-8")

    return output_path


# ---------------------------------------------------------------------------
# migrate from-dbt
# ---------------------------------------------------------------------------


@migrate_app.command("from-dbt")
def migrate_from_dbt(
    project_path: Path = typer.Argument(
        ...,
        help="Path to the dbt project directory (contains dbt_project.yml).",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    output: Path = typer.Option(
        Path("./models"),
        "--output",
        "-o",
        help="Output directory for generated IronLayer model files.",
    ),
    tag_filter: str | None = typer.Option(
        None,
        "--tag",
        help="Only migrate models with this tag.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be migrated without writing files.",
    ),
) -> None:
    """Migrate models from a dbt project into IronLayer format."""
    from core_engine.loader.dbt_loader import (
        DbtManifestError,
        discover_dbt_manifest,
        load_models_from_dbt_manifest,
    )

    try:
        # 1. Discover the manifest.json.
        manifest_path = discover_dbt_manifest(project_path)
        if manifest_path is None:
            console.print(
                f"[red]No manifest.json found in '{project_path}'.[/red]\n"
                f"[dim]Run 'dbt compile' or 'dbt build' first to generate "
                f"the manifest artifact.[/dim]"
            )
            raise typer.Exit(code=3)

        console.print(f"Found manifest at [bold]{manifest_path}[/bold]")

        # 2. Load models from the manifest.
        tag_filter_list: list[str] | None = None
        if tag_filter:
            tag_filter_list = [t.strip() for t in tag_filter.split(",") if t.strip()]

        model_defs = load_models_from_dbt_manifest(
            manifest_path,
            tag_filter=tag_filter_list,
        )

        if not model_defs:
            msg = "No models found in the dbt manifest"
            if tag_filter:
                msg += f" matching tag '{tag_filter}'"
            console.print(f"[yellow]{msg}.[/yellow]")
            raise typer.Exit(code=0)

        # 3. Generate IronLayer files (or simulate in dry-run mode).
        migrated: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        warnings: list[str] = []

        output_dir = output.resolve()

        for model in model_defs:
            # Use the compiled SQL (clean_sql) as the body, since dbt
            # refs have already been resolved in it.
            sql_body = model.clean_sql or model.raw_sql

            if not sql_body.strip():
                skipped.append(
                    {
                        "name": model.name,
                        "source": model.file_path,
                        "reason": "no SQL content",
                    }
                )
                warnings.append(f"Model '{model.name}' has no SQL content and was skipped.")
                continue

            # Determine output path for reporting.
            parts = model.name.split(".")
            if len(parts) >= 2:
                rel_path = str(Path(*parts[:-1]) / f"{parts[-1]}.sql")
            else:
                rel_path = f"{parts[0]}.sql"
            out_path = output_dir / rel_path

            if dry_run:
                migrated.append(
                    {
                        "name": model.name,
                        "source": model.file_path,
                        "output": str(out_path),
                        "status": "dry-run",
                    }
                )
            else:
                written_path = _generate_ironlayer_file(
                    model,
                    output_dir,
                    original_sql=sql_body,
                )
                migrated.append(
                    {
                        "name": model.name,
                        "source": model.file_path,
                        "output": str(written_path),
                        "status": "migrated",
                    }
                )

        # 4. Display results.
        if _json_output:
            result = {
                "migrated": migrated,
                "skipped": skipped,
                "warnings": warnings,
            }
            sys.stdout.write(json.dumps(result, indent=2) + "\n")
        else:
            display_migration_report(console, migrated, skipped, warnings)
            if not dry_run and migrated:
                console.print(f"\nFiles written to [bold]{output_dir}[/bold]")

        _emit_metrics(
            "migrate.from_dbt",
            {
                "source": str(project_path),
                "migrated": len(migrated),
                "skipped": len(skipped),
                "dry_run": dry_run,
                "tag_filter": tag_filter,
            },
        )

    except typer.Exit:
        raise
    except DbtManifestError as exc:
        console.print(f"[red]dbt manifest error: {exc}[/red]")
        raise typer.Exit(code=3) from exc
    except Exception as exc:
        console.print(f"[red]Migration failed: {exc}[/red]")
        _emit_metrics("migrate.from_dbt.error", {"error": str(exc)})
        raise typer.Exit(code=3) from exc


# ---------------------------------------------------------------------------
# migrate from-sql
# ---------------------------------------------------------------------------


@migrate_app.command("from-sql")
def migrate_from_sql(
    sql_dir: Path = typer.Argument(
        ...,
        help="Directory containing raw .sql files.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    output: Path = typer.Option(
        Path("./models"),
        "--output",
        "-o",
        help="Output directory for generated IronLayer model files.",
    ),
    default_materialization: str = typer.Option(
        "TABLE",
        "--materialization",
        help="Default materialization for imported models (TABLE, VIEW, INSERT_OVERWRITE, MERGE).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be migrated without writing files.",
    ),
) -> None:
    """Migrate raw SQL files into IronLayer format with inferred dependencies."""
    from core_engine.models.model_definition import (
        Materialization,
        ModelDefinition,
        ModelKind,
    )

    try:
        # Validate the materialization option.
        mat_upper = default_materialization.upper().strip()
        try:
            materialization = Materialization(mat_upper)
        except ValueError:
            valid = ", ".join(m.value for m in Materialization)
            console.print(f"[red]Invalid materialization '{default_materialization}'. Valid options: {valid}[/red]")
            raise typer.Exit(code=3)

        # For simple TABLE/VIEW materializations, use FULL_REFRESH kind.
        if materialization in (Materialization.TABLE, Materialization.VIEW):
            kind = ModelKind.FULL_REFRESH
        elif materialization == Materialization.INSERT_OVERWRITE:
            kind = ModelKind.INCREMENTAL_BY_TIME_RANGE
        elif materialization == Materialization.MERGE:
            kind = ModelKind.MERGE_BY_KEY
        else:
            kind = ModelKind.FULL_REFRESH

        # 1. Discover SQL files.
        sql_files = sorted(sql_dir.rglob("*.sql"))
        if not sql_files:
            console.print(f"[yellow]No .sql files found under '{sql_dir}'.[/yellow]")
            raise typer.Exit(code=0)

        console.print(f"Found [bold]{len(sql_files)}[/bold] SQL file(s) under [bold]{sql_dir}[/bold]")

        # 2. Process each SQL file.
        migrated: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        warnings: list[str] = []

        output_dir = output.resolve()

        for sql_file in sql_files:
            try:
                sql_content = sql_file.read_text(encoding="utf-8")
            except OSError as exc:
                skipped.append(
                    {
                        "name": sql_file.name,
                        "source": str(sql_file),
                        "reason": f"read error: {exc}",
                    }
                )
                warnings.append(f"Could not read '{sql_file}': {exc}")
                continue

            if not sql_content.strip():
                skipped.append(
                    {
                        "name": sql_file.name,
                        "source": str(sql_file),
                        "reason": "empty file",
                    }
                )
                continue

            # Derive model name from relative path within sql_dir.
            # e.g., staging/orders.sql -> staging.orders
            rel_path = sql_file.relative_to(sql_dir)
            stem_parts = list(rel_path.parent.parts) + [rel_path.stem]
            model_name = ".".join(stem_parts)

            # Infer dependencies from FROM/JOIN clauses.
            dependencies = _extract_sql_table_refs(sql_content)

            # Build a ModelDefinition for file generation.
            # Use sensible defaults -- the user can refine after migration.
            # Skip the model_validator for INCREMENTAL_BY_TIME_RANGE
            # (which requires time_column) and MERGE_BY_KEY (which requires
            # unique_key) by falling back to FULL_REFRESH when those fields
            # are not available from raw SQL.
            effective_kind = kind
            effective_materialization = materialization
            if kind == ModelKind.INCREMENTAL_BY_TIME_RANGE:
                # We cannot infer a time_column from raw SQL, so fall back.
                effective_kind = ModelKind.FULL_REFRESH
                effective_materialization = Materialization.TABLE
                if not any(w.startswith("Materialization INSERT_OVERWRITE") for w in warnings):
                    warnings.append(
                        "Materialization INSERT_OVERWRITE requires a "
                        "time_column. Falling back to FULL_REFRESH/TABLE for "
                        "models without an explicit time_column. Edit the "
                        "generated headers to set time_column and kind."
                    )
            if kind == ModelKind.MERGE_BY_KEY:
                effective_kind = ModelKind.FULL_REFRESH
                effective_materialization = Materialization.TABLE
                if not any(w.startswith("Materialization MERGE") for w in warnings):
                    warnings.append(
                        "Materialization MERGE requires a unique_key. "
                        "Falling back to FULL_REFRESH/TABLE for models "
                        "without an explicit unique_key. Edit the generated "
                        "headers to set unique_key and kind."
                    )

            model_def = ModelDefinition(
                name=model_name,
                kind=effective_kind,
                materialization=effective_materialization,
                dependencies=dependencies,
                file_path=str(sql_file),
                raw_sql=sql_content,
                clean_sql=sql_content,
            )

            # Determine output path for reporting.
            name_parts = model_name.split(".")
            if len(name_parts) >= 2:
                out_rel = str(Path(*name_parts[:-1]) / f"{name_parts[-1]}.sql")
            else:
                out_rel = f"{name_parts[0]}.sql"
            out_path = output_dir / out_rel

            if dry_run:
                migrated.append(
                    {
                        "name": model_name,
                        "source": str(sql_file),
                        "output": str(out_path),
                        "status": "dry-run",
                    }
                )
            else:
                written_path = _generate_ironlayer_file(
                    model_def,
                    output_dir,
                    original_sql=sql_content,
                )
                migrated.append(
                    {
                        "name": model_name,
                        "source": str(sql_file),
                        "output": str(written_path),
                        "status": "migrated",
                    }
                )

        # 3. Display results.
        if _json_output:
            result_data = {
                "migrated": migrated,
                "skipped": skipped,
                "warnings": warnings,
            }
            sys.stdout.write(json.dumps(result_data, indent=2) + "\n")
        else:
            display_migration_report(console, migrated, skipped, warnings)
            if not dry_run and migrated:
                console.print(f"\nFiles written to [bold]{output_dir}[/bold]")

        _emit_metrics(
            "migrate.from_sql",
            {
                "source": str(sql_dir),
                "migrated": len(migrated),
                "skipped": len(skipped),
                "dry_run": dry_run,
                "materialization": mat_upper,
            },
        )

    except typer.Exit:
        raise
    except Exception as exc:
        console.print(f"[red]Migration failed: {exc}[/red]")
        _emit_metrics("migrate.from_sql.error", {"error": str(exc)})
        raise typer.Exit(code=3) from exc


# ---------------------------------------------------------------------------
# migrate from-sqlmesh
# ---------------------------------------------------------------------------


@migrate_app.command("from-sqlmesh")
def migrate_from_sqlmesh(
    project_path: Path = typer.Argument(
        ...,
        help="Path to the SQLMesh project root directory.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
    output: Path = typer.Option(
        Path("./models"),
        "--output",
        "-o",
        help="Output directory for generated IronLayer model files.",
    ),
    tag: str | None = typer.Option(
        None,
        "--tag",
        help="Only migrate models with this tag.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what would be migrated without writing files.",
    ),
) -> None:
    """Migrate a SQLMesh project into IronLayer format.

    Parses SQLMesh model files (SQL with MODEL headers and Python @model
    decorators) and converts them to IronLayer-compatible .sql files with
    YAML-style comment headers.
    """
    from core_engine.loader.sqlmesh_loader import (
        SQLMeshLoadError,
        discover_sqlmesh_project,
        load_models_from_sqlmesh_project,
    )

    try:
        # 1. Verify project.
        config_path = discover_sqlmesh_project(project_path)
        if config_path is None:
            console.print(
                f"[red]No SQLMesh config file found in '{project_path}'.[/red]\n"
                "Expected config.yaml, config.yml, or config.py."
            )
            raise typer.Exit(code=3)

        console.print(f"Found SQLMesh project: [bold]{config_path}[/bold]")

        # 2. Load models.
        model_defs = load_models_from_sqlmesh_project(
            project_path,
            tag_filter=tag,
        )

        if not model_defs:
            console.print("[yellow]No models found in the SQLMesh project.[/yellow]")
            if tag:
                console.print(f"[yellow]Tag filter: '{tag}'[/yellow]")
            raise typer.Exit(code=0)

        console.print(f"Found [bold]{len(model_defs)}[/bold] model(s) to migrate")

        # 3. Generate IronLayer files.
        migrated: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        warnings: list[str] = []

        output_dir = output.resolve()

        for model_def in model_defs:
            # Check for Python models that need manual conversion
            sql_body = model_def.clean_sql or model_def.raw_sql
            if sql_body and sql_body.startswith("-- Python model:"):
                warnings.append(f"Model '{model_def.name}' is a Python model. Manual SQL conversion required.")

            # Determine output path for reporting.
            name_parts = model_def.name.split(".")
            if len(name_parts) >= 2:
                out_rel = str(Path(*name_parts[:-1]) / f"{name_parts[-1]}.sql")
            else:
                out_rel = f"{name_parts[0]}.sql"
            out_path = output_dir / out_rel

            if dry_run:
                migrated.append(
                    {
                        "name": model_def.name,
                        "source": model_def.file_path or "",
                        "output": str(out_path),
                        "status": "dry-run",
                    }
                )
            else:
                written_path = _generate_ironlayer_file(model_def, output_dir)
                migrated.append(
                    {
                        "name": model_def.name,
                        "source": model_def.file_path or "",
                        "output": str(written_path),
                        "status": "migrated",
                    }
                )

        # 4. Display results.
        if _json_output:
            result_data = {
                "migrated": migrated,
                "skipped": skipped,
                "warnings": warnings,
            }
            sys.stdout.write(json.dumps(result_data, indent=2) + "\n")
        else:
            display_migration_report(console, migrated, skipped, warnings)
            if not dry_run and migrated:
                console.print(f"\nFiles written to [bold]{output_dir}[/bold]")

        _emit_metrics(
            "migrate.from_sqlmesh",
            {
                "source": str(project_path),
                "migrated": len(migrated),
                "skipped": len(skipped),
                "dry_run": dry_run,
                "tag_filter": tag,
            },
        )

    except typer.Exit:
        raise
    except SQLMeshLoadError as exc:
        console.print(f"[red]SQLMesh project error: {exc}[/red]")
        raise typer.Exit(code=3) from exc
    except Exception as exc:
        console.print(f"[red]Migration failed: {exc}[/red]")
        _emit_metrics("migrate.from_sqlmesh.error", {"error": str(exc)})
        raise typer.Exit(code=3) from exc


# ---------------------------------------------------------------------------
# MCP server commands
# ---------------------------------------------------------------------------


@mcp_app.command("serve")
def mcp_serve(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        "-t",
        help="Transport type: 'stdio' (default) or 'sse'.",
    ),
    port: int = typer.Option(
        3333,
        "--port",
        "-p",
        help="Port for SSE transport (ignored for stdio).",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind address for SSE transport. Use 0.0.0.0 for all interfaces.",
    ),
) -> None:
    """Start the IronLayer MCP server.

    The MCP server exposes IronLayer's SQL intelligence as tools that
    AI coding assistants can discover and invoke.

    \b
    For Claude Code / Cursor (stdio transport):
        ironlayer mcp serve

    \b
    For remote access (SSE transport):
        ironlayer mcp serve --transport sse --port 3333

    \b
    Claude Code config (~/.claude/claude_desktop_config.json):
        {
          "mcpServers": {
            "ironlayer": {
              "command": "ironlayer",
              "args": ["mcp", "serve"]
            }
          }
        }
    """
    import asyncio

    try:
        from cli.mcp.server import run_sse, run_stdio
    except SystemExit as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if transport == "stdio":
        if not _json_output:
            # Only print to stderr — stdout is reserved for MCP protocol.
            console.print("[dim]Starting IronLayer MCP server (stdio)...[/dim]")
        asyncio.run(run_stdio())
    elif transport == "sse":
        console.print(f"[bold]Starting IronLayer MCP server (SSE) on {host}:{port}[/bold]")
        asyncio.run(run_sse(host=host, port=port))
    else:
        console.print(f"[red]Unknown transport '{transport}'. Use 'stdio' or 'sse'.[/red]")
        raise typer.Exit(code=1)
