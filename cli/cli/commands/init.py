"""``platform init`` -- interactive project bootstrap.

Scaffolds a complete IronLayer project from scratch, including:

  * ``.ironlayer/config.yaml`` -- project settings
  * ``.env`` -- environment variables (secrets, connection strings)
  * ``models/`` -- directory with starter example models
  * ``.gitignore`` -- ignores local state and secrets

Designed to give a developer a working project in under 60 seconds with
zero external dependencies (no Docker, no Postgres).
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _render_template(template_name: str, context: dict) -> str:
    """Render a Jinja2-style template using simple string substitution.

    We use Python's built-in ``string.Template``-style rendering via a
    lightweight Jinja2 import to avoid adding complex dependencies while
    still supporting conditionals and loops in templates.
    """
    try:
        from jinja2 import Environment, FileSystemLoader
    except ImportError:
        # Fallback: read template and do basic substitution
        template_path = _TEMPLATES_DIR / template_name
        content = template_path.read_text(encoding="utf-8")
        for key, value in context.items():
            content = content.replace("{{ " + key + " }}", str(value))
        return content

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_name)
    return template.render(**context)


# ---------------------------------------------------------------------------
# Example model content
# ---------------------------------------------------------------------------

_EXAMPLE_MODELS: dict[str, str] = {
    "raw/source_orders.sql": """\
-- name: raw.source_orders
-- kind: FULL_REFRESH
-- materialization: TABLE
-- owner: data-platform
-- tags: raw, orders, source

SELECT
    order_id,
    customer_id,
    order_date,
    status,
    total_amount,
    created_at
FROM catalog.raw_orders
WHERE _ingested_at >= '{{ start_date }}'
    AND _ingested_at < '{{ end_date }}'
""",
    "staging/stg_orders.sql": """\
-- name: staging.stg_orders
-- kind: FULL_REFRESH
-- materialization: TABLE
-- owner: data-platform
-- tags: staging, orders
-- dependencies: raw.source_orders

SELECT
    order_id,
    customer_id,
    order_date,
    status,
    total_amount,
    CURRENT_TIMESTAMP() AS _loaded_at
FROM {{ ref('raw.source_orders') }}
WHERE order_date >= '{{ start_date }}'
""",
    "analytics/orders_daily.sql": """\
-- name: analytics.orders_daily
-- kind: INCREMENTAL_BY_TIME_RANGE
-- materialization: INSERT_OVERWRITE
-- time_column: order_date
-- partition_by: order_date
-- owner: analytics
-- tags: analytics, orders, daily
-- dependencies: staging.stg_orders

SELECT
    order_date,
    COUNT(*) AS total_orders,
    SUM(total_amount) AS revenue,
    COUNT(DISTINCT customer_id) AS unique_customers,
    AVG(total_amount) AS avg_order_value
FROM {{ ref('staging.stg_orders') }}
WHERE order_date >= '{{ start_date }}'
    AND order_date < '{{ end_date }}'
GROUP BY order_date
""",
    "analytics/revenue_summary.sql": """\
-- name: analytics.revenue_summary
-- kind: FULL_REFRESH
-- materialization: TABLE
-- owner: analytics
-- tags: analytics, revenue, summary
-- dependencies: analytics.orders_daily

SELECT
    DATE_TRUNC('month', order_date) AS month,
    SUM(total_orders) AS total_orders,
    SUM(revenue) AS total_revenue,
    SUM(unique_customers) AS total_customers,
    SUM(revenue) / NULLIF(SUM(total_orders), 0) AS avg_order_value
FROM {{ ref('analytics.orders_daily') }}
GROUP BY DATE_TRUNC('month', order_date)
ORDER BY month DESC
""",
}


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _is_git_repo(directory: Path) -> bool:
    """Check if the directory is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            cwd=str(directory),
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _git_init(directory: Path) -> bool:
    """Initialise a new git repository in the directory.

    Returns True on success, False on failure.
    """
    try:
        result = subprocess.run(
            ["git", "init"],
            capture_output=True,
            text=True,
            cwd=str(directory),
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Init command
# ---------------------------------------------------------------------------


def init_command(
    directory: Path | None = typer.Argument(
        None,
        help="Directory to initialise. Defaults to the current directory.",
        resolve_path=True,
    ),
    project_name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Project name. Defaults to the directory name.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Skip all prompts and use defaults.",
    ),
    state_store: str | None = typer.Option(
        None,
        "--state-store",
        help="State store type: 'local' (SQLite) or 'postgres'.",
    ),
    databricks_host: str | None = typer.Option(
        None,
        "--databricks-host",
        help="Databricks workspace URL.",
    ),
    no_ai: bool = typer.Option(
        False,
        "--no-ai",
        help="Disable AI advisory engine.",
    ),
    no_git: bool = typer.Option(
        False,
        "--no-git",
        help="Skip git repository initialisation.",
    ),
) -> None:
    """Initialise a new IronLayer project."""
    console = Console(stderr=True)

    # Resolve target directory.
    target_dir = directory or Path.cwd()
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)

    # Determine project name.
    name = project_name or target_dir.name
    if not non_interactive and project_name is None:
        name = typer.prompt("Project name", default=name)

    # State store selection.
    store = state_store or "local"
    if not non_interactive and state_store is None:
        store = typer.prompt(
            "State store (local = SQLite, postgres = Docker PostgreSQL)",
            default="local",
        )
    store = store.strip().lower()
    if store not in ("local", "postgres"):
        console.print(f"[red]Invalid state store '{store}'. Must be 'local' or 'postgres'.[/red]")
        raise typer.Exit(code=3)

    # Databricks configuration (optional).
    db_host: str | None = databricks_host
    db_token: str | None = None
    db_warehouse: str | None = None

    if not non_interactive and databricks_host is None:
        configure_db = typer.confirm(
            "Configure Databricks connection?",
            default=False,
        )
        if configure_db:
            db_host = typer.prompt("Databricks host URL")
            db_token = typer.prompt("Databricks token", hide_input=True)
            db_warehouse = (
                typer.prompt(
                    "Databricks warehouse ID (optional, press Enter to skip)",
                    default="",
                )
                or None
            )

    # AI engine toggle.
    ai_enabled = not no_ai
    if not non_interactive and not no_ai:
        ai_enabled = typer.confirm(
            "Enable AI advisory engine?",
            default=True,
        )

    # -----------------------------------------------------------------------
    # Scaffold generation
    # -----------------------------------------------------------------------

    console.print()
    console.print(
        Panel(
            f"[bold]Initialising IronLayer project:[/bold] {name}\n"
            f"[dim]Directory:[/dim] {target_dir}\n"
            f"[dim]State store:[/dim] {store}\n"
            f"[dim]AI engine:[/dim] {'enabled' if ai_enabled else 'disabled'}\n"
            f"[dim]Databricks:[/dim] {'configured' if db_host else 'not configured'}",
            title="IronLayer Init",
            border_style="blue",
        )
    )

    steps_completed = 0

    # 1. Create .ironlayer/ directory and config.yaml.
    ironlayer_dir = target_dir / ".ironlayer"
    ironlayer_dir.mkdir(parents=True, exist_ok=True)

    template_context = {
        "project_name": name,
        "state_store": store,
        "databricks_host": db_host or "",
        "databricks_token": db_token or "",
        "databricks_warehouse_id": db_warehouse or "",
        "ai_enabled": str(ai_enabled),
    }

    config_content = _render_template("config.yaml.j2", template_context)
    config_path = ironlayer_dir / "config.yaml"
    config_path.write_text(config_content, encoding="utf-8")
    steps_completed += 1
    console.print(f"  [green]\u2713[/green] Created {config_path.relative_to(target_dir)}")

    # 2. Create .env file.
    env_content = _render_template("env.j2", template_context)
    env_path = target_dir / ".env"
    if env_path.exists():
        console.print("  [yellow]\u26a0[/yellow] .env already exists -- skipping (backup at .env.ironlayer.bak)")
        shutil.copy2(env_path, target_dir / ".env.ironlayer.bak")
    else:
        env_path.write_text(env_content, encoding="utf-8")
    steps_completed += 1
    console.print("  [green]\u2713[/green] Created .env")

    # 3. Create models/ directory with examples.
    models_dir = target_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    models_created = 0
    for rel_path, content in _EXAMPLE_MODELS.items():
        model_path = models_dir / rel_path
        model_path.parent.mkdir(parents=True, exist_ok=True)
        if not model_path.exists():
            model_path.write_text(content, encoding="utf-8")
            models_created += 1

    steps_completed += 1
    console.print(f"  [green]\u2713[/green] Created models/ with {models_created} example model(s)")

    # 4. Create .gitignore (merge with existing).
    gitignore_content = _render_template("gitignore.j2", template_context)
    gitignore_path = target_dir / ".gitignore"
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8")
        # Append only lines that don't already exist.
        existing_lines = set(existing.splitlines())
        new_lines = [line for line in gitignore_content.splitlines() if line.strip() and line not in existing_lines]
        if new_lines:
            with gitignore_path.open("a", encoding="utf-8") as fh:
                fh.write("\n# IronLayer\n")
                fh.write("\n".join(new_lines) + "\n")
    else:
        gitignore_path.write_text(gitignore_content, encoding="utf-8")

    steps_completed += 1
    console.print("  [green]\u2713[/green] Updated .gitignore")

    # 5. Git init (if not already in a repo and not disabled).
    if not no_git:
        if _is_git_repo(target_dir):
            console.print("  [dim]\u2713 Already inside a git repository[/dim]")
        else:
            if _git_init(target_dir):
                console.print("  [green]\u2713[/green] Initialised git repository")
            else:
                console.print("  [yellow]\u26a0[/yellow] Could not initialise git repository (is git installed?)")

    steps_completed += 1

    # 6. Verify: try loading models to confirm scaffold is valid.
    try:
        from core_engine.loader import load_models_from_directory

        loaded = load_models_from_directory(models_dir)
        console.print(f"  [green]\u2713[/green] Verification passed: {len(loaded)} model(s) loaded successfully")
    except Exception as exc:
        console.print(
            f"  [yellow]\u26a0[/yellow] Verification warning: {exc}\n    [dim]Models may need manual adjustment.[/dim]"
        )

    # Final summary.
    console.print()
    console.print(
        Panel(
            "[bold green]Project initialised successfully![/bold green]\n\n"
            "Next steps:\n"
            "  1. [bold]ironlayer dev[/bold]       -- Start local development server\n"
            "  2. [bold]ironlayer models .[/bold]  -- List discovered models\n"
            "  3. [bold]ironlayer plan . HEAD~1 HEAD[/bold]  -- Generate your first plan\n\n"
            "[dim]Edit models/ to add your SQL models. "
            "See docs/quickstart.md for the full walkthrough.[/dim]",
            title="Done",
            border_style="green",
        )
    )
