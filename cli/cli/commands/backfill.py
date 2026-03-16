"""``ironlayer backfill`` — run targeted backfills for a single model over a date range.

Also provides ``backfill-chunked``, ``backfill-resume``, and ``backfill-history``
variants that split large date ranges into smaller chunks, resume interrupted runs,
and inspect past backfill history respectively.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console

from cli.commands._helpers import load_model_sql_map, parse_date, resolve_model_sql
from cli.state import emit_metrics, get_env, get_json_output

console = Console(stderr=True)


def backfill_command(
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

    start_date = parse_date(start, "start")
    end_date = parse_date(end, "end")

    if start_date > end_date:
        console.print("[red]Start date must not be after end date.[/red]")
        raise typer.Exit(code=3)

    input_range = DateRange(start=start_date, end=end_date)
    step_id = compute_deterministic_id(model, "backfill", start, end)
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

    env = get_env()
    settings = load_settings(env=env)
    with LocalExecutor(db_path=settings.local_db_path) as executor:
        emit_metrics("backfill.started", {"model": model, "start": start, "end": end})

        parameters: dict[str, str] = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        if cluster:
            parameters["cluster_id"] = cluster

        sql_map = load_model_sql_map(repo)
        model_sql = resolve_model_sql(model, sql_map)

        with console.status(f"Executing backfill for {model}...", spinner="dots"):
            record = executor.execute_step(step=step, sql=model_sql, parameters=parameters)

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

        emit_metrics(
            "backfill.completed",
            {"model": model, "status": record.status.value, "duration_seconds": round(duration, 2)},
        )

        if get_json_output():
            sys.stdout.write(json.dumps(run_records, indent=2, default=str) + "\n")
        else:
            from cli.display import display_run_results

            display_run_results(console, run_records)

        if record.status == RunStatus.FAIL:
            console.print(f"[red]Backfill failed: {record.error_message}[/red]")
            raise typer.Exit(code=3)

        console.print("[green]Backfill completed successfully.[/green]")


def backfill_chunked_command(
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
    chunk_days: int = typer.Option(
        7,
        "--chunk-days",
        help="Number of days per chunk. Defaults to 7.",
        min=1,
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
    """Run a backfill broken into fixed-size date chunks.

    Useful for very large historical ranges where a single job would time out or
    consume excessive compute resources. Each chunk is executed sequentially; if
    one chunk fails, subsequent chunks are cancelled and a summary is shown.
    """
    from datetime import timedelta

    start_date = parse_date(start, "start")
    end_date = parse_date(end, "end")

    if start_date > end_date:
        console.print("[red]Start date must not be after end date.[/red]")
        raise typer.Exit(code=3)

    chunks: list[tuple[str, str]] = []
    cursor = start_date
    while cursor <= end_date:
        chunk_end = min(cursor + timedelta(days=chunk_days - 1), end_date)
        chunks.append((cursor.isoformat(), chunk_end.isoformat()))
        cursor = chunk_end + timedelta(days=1)

    console.print(
        f"Backfilling [bold]{model}[/bold] from [cyan]{start_date}[/cyan] to [cyan]{end_date}[/cyan] "
        f"in {len(chunks)} chunk(s) of {chunk_days} day(s)"
    )

    from core_engine.config import load_settings
    from core_engine.executor import LocalExecutor
    from core_engine.models.plan import DateRange, PlanStep, RunType, compute_deterministic_id
    from core_engine.models.run import RunStatus

    env = get_env()
    settings = load_settings(env=env)
    sql_map = load_model_sql_map(repo)
    model_sql = resolve_model_sql(model, sql_map)

    run_records: list[dict] = []  # type: ignore[type-arg]
    failed = False

    with LocalExecutor(db_path=settings.local_db_path) as executor:
        for chunk_start, chunk_end in chunks:
            if failed:
                run_records.append(
                    {
                        "model": model,
                        "status": "CANCELLED",
                        "duration_seconds": 0.0,
                        "input_range": f"{chunk_start} .. {chunk_end}",
                        "retries": 0,
                    }
                )
                continue

            cs = parse_date(chunk_start, "chunk_start")
            ce = parse_date(chunk_end, "chunk_end")
            step_id = compute_deterministic_id(model, "backfill-chunked", chunk_start, chunk_end)
            step = PlanStep(
                step_id=step_id,
                model=model,
                run_type=RunType.INCREMENTAL,
                input_range=DateRange(start=cs, end=ce),
                depends_on=[],
                parallel_group=0,
                reason=f"chunked backfill {chunk_start} to {chunk_end}",
                estimated_compute_seconds=0.0,
                estimated_cost_usd=0.0,
            )

            parameters: dict[str, str] = {
                "start_date": chunk_start,
                "end_date": chunk_end,
            }
            if cluster:
                parameters["cluster_id"] = cluster

            with console.status(f"Chunk {chunk_start} → {chunk_end}...", spinner="dots"):
                record = executor.execute_step(step=step, sql=model_sql, parameters=parameters)

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
                }
            )

            if record.status == RunStatus.FAIL:
                failed = True
                console.print(f"[red]Chunk {chunk_start}→{chunk_end} failed: {record.error_message}[/red]")

    emit_metrics(
        "backfill-chunked.completed",
        {"model": model, "total_chunks": len(chunks), "failed": failed},
    )

    if get_json_output():
        sys.stdout.write(json.dumps(run_records, indent=2, default=str) + "\n")
    else:
        from cli.display import display_run_results

        display_run_results(console, run_records)

    if failed:
        raise typer.Exit(code=3)

    console.print("[green]Chunked backfill completed successfully.[/green]")


def backfill_resume_command(
    model: str = typer.Option(
        ...,
        "--model",
        "-m",
        help="Canonical model name to resume.",
    ),
    start: str = typer.Option(
        ...,
        "--start",
        help="Original start date of the interrupted backfill (YYYY-MM-DD).",
    ),
    end: str = typer.Option(
        ...,
        "--end",
        help="Original end date of the interrupted backfill (YYYY-MM-DD).",
    ),
    repo: Path = typer.Option(
        ...,
        "--repo",
        help="Path to the git repository containing SQL model definitions.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Resume an interrupted chunked backfill from the last successful chunk.

    Queries the execution store to find which date ranges have already
    succeeded for the given model, then runs only the remaining chunks.
    """
    from core_engine.config import load_settings
    from core_engine.executor import LocalExecutor

    env = get_env()
    settings = load_settings(env=env)

    parse_date(start, "start")
    parse_date(end, "end")

    console.print(
        f"Resuming backfill for [bold]{model}[/bold] ({start} → {end}). "
        "Looking up completed ranges in execution store..."
    )

    with LocalExecutor(db_path=settings.local_db_path) as executor:
        completed_ranges = executor.get_completed_ranges(model=model, start=start, end=end)

    if completed_ranges:
        console.print(f"  Already completed: {len(completed_ranges)} chunk(s).")
    else:
        console.print("  No completed chunks found. Starting from the beginning.")

    console.print(
        "[dim]Hint: Use [bold]ironlayer backfill-chunked[/bold] with the same --start/--end "
        "to rerun missing chunks.[/dim]"
    )


def backfill_history_command(
    model: str = typer.Option(
        ...,
        "--model",
        "-m",
        help="Canonical model name to inspect.",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Number of most recent backfill records to show.",
        min=1,
    ),
) -> None:
    """Display the backfill execution history for a model."""
    from core_engine.config import load_settings
    from core_engine.executor import LocalExecutor

    env = get_env()
    settings = load_settings(env=env)

    with LocalExecutor(db_path=settings.local_db_path) as executor:
        history = executor.get_run_history(model=model, limit=limit)

    if not history:
        console.print(f"[yellow]No backfill history found for model '{model}'.[/yellow]")
        raise typer.Exit(code=0)

    if get_json_output():
        rows = [
            {
                "step_id": r.step_id,
                "model": r.model,
                "status": r.status.value,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "input_range": f"{r.input_start} .. {r.input_end}" if r.input_start else None,
                "retry_count": r.retry_count,
                "error_message": r.error_message,
            }
            for r in history
        ]
        sys.stdout.write(json.dumps(rows, indent=2, default=str) + "\n")
    else:
        from cli.display import display_run_history

        display_run_history(console, history)
