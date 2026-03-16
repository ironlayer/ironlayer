"""``ironlayer migrate`` — migrate SQL models from dbt, raw SQL, or SQLMesh to IronLayer format."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

console = Console(stderr=True)

# Top-level sub-app registered in app.py as ``migrate``
migrate_app = typer.Typer(
    name="migrate",
    help="Migrate SQL models from other frameworks to IronLayer format.",
    no_args_is_help=True,
)


@migrate_app.command("from-dbt")
def migrate_from_dbt(
    dbt_project: Annotated[
        Path,
        typer.Argument(
            help="Path to the dbt project root (must contain dbt_project.yml).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Output directory for generated IronLayer model files."),
    ] = Path("ironlayer_models"),
    target: Annotated[
        str,
        typer.Option("--target", "-t", help="dbt target profile to use when loading manifests."),
    ] = "dev",
    transpile_to: Annotated[
        str,
        typer.Option("--transpile-to", help="SQL dialect to transpile models to."),
    ] = "databricks",
) -> None:
    """Migrate a dbt Core project to IronLayer SQL model files.

    Reads ``dbt_project.yml`` and all model ``.sql`` files, infers model kind
    and materialization from dbt config, and writes IronLayer model definitions
    to the output directory.
    """
    from core_engine.migrate import migrate_from_dbt as _migrate_from_dbt

    console.print(f"Migrating dbt project at [bold]{dbt_project}[/bold] → [bold]{out}[/bold]")

    try:
        result = _migrate_from_dbt(
            project_root=dbt_project,
            output_dir=out,
            target=target,
            dialect=transpile_to,
        )
    except Exception as exc:
        console.print(f"[red]Migration failed: {exc}[/red]")
        raise typer.Exit(code=3) from exc

    console.print(f"[green]✓ Migrated {result.models_migrated} models to {out}[/green]")
    if result.warnings:
        for warning in result.warnings:
            console.print(f"  [yellow]⚠ {warning}[/yellow]")


@migrate_app.command("from-sql")
def migrate_from_sql(
    sql_dir: Annotated[
        Path,
        typer.Argument(
            help="Directory containing plain ``.sql`` files.",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Output directory for generated IronLayer model files."),
    ] = Path("ironlayer_models"),
    transpile_to: Annotated[
        str,
        typer.Option("--transpile-to", help="SQL dialect to transpile models to."),
    ] = "databricks",
) -> None:
    """Migrate plain SQL files to IronLayer model format.

    Scans the provided directory for ``*.sql`` files, infers model kind from SQL
    structure (e.g. incremental patterns), and writes IronLayer model definitions
    to the output directory.
    """
    from core_engine.migrate import migrate_from_sql as _migrate_from_sql

    console.print(f"Migrating SQL files from [bold]{sql_dir}[/bold] → [bold]{out}[/bold]")

    try:
        result = _migrate_from_sql(
            sql_dir=sql_dir,
            output_dir=out,
            dialect=transpile_to,
        )
    except Exception as exc:
        console.print(f"[red]Migration failed: {exc}[/red]")
        raise typer.Exit(code=3) from exc

    console.print(f"[green]✓ Migrated {result.models_migrated} models to {out}[/green]")
    if result.warnings:
        for warning in result.warnings:
            console.print(f"  [yellow]⚠ {warning}[/yellow]")


@migrate_app.command("from-sqlmesh")
def migrate_from_sqlmesh(
    sqlmesh_root: Annotated[
        Path,
        typer.Argument(
            help="Path to the SQLMesh project root (must contain ``config.yaml`` or ``config.py``).",
            exists=True,
            file_okay=False,
            resolve_path=True,
        ),
    ],
    out: Annotated[
        Path,
        typer.Option("--out", "-o", help="Output directory for generated IronLayer model files."),
    ] = Path("ironlayer_models"),
    transpile_to: Annotated[
        str,
        typer.Option("--transpile-to", help="SQL dialect to transpile models to."),
    ] = "databricks",
) -> None:
    """Migrate a SQLMesh project to IronLayer SQL model format.

    Reads SQLMesh model definitions (the ``MODEL()`` DDL block and SQL body),
    maps SQLMesh model kinds to IronLayer equivalents, and writes IronLayer model
    files to the output directory.
    """
    from core_engine.migrate import migrate_from_sqlmesh as _migrate_from_sqlmesh

    console.print(f"Migrating SQLMesh project at [bold]{sqlmesh_root}[/bold] → [bold]{out}[/bold]")

    try:
        result = _migrate_from_sqlmesh(
            project_root=sqlmesh_root,
            output_dir=out,
            dialect=transpile_to,
        )
    except Exception as exc:
        console.print(f"[red]Migration failed: {exc}[/red]")
        raise typer.Exit(code=3) from exc

    console.print(f"[green]✓ Migrated {result.models_migrated} models to {out}[/green]")
    if result.warnings:
        for warning in result.warnings:
            console.print(f"  [yellow]⚠ {warning}[/yellow]")
