"""``ironlayer mcp serve`` — start the IronLayer MCP server."""

from __future__ import annotations

import typer
from rich.console import Console

console = Console(stderr=True)

mcp_app = typer.Typer(
    name="mcp",
    help="MCP server management commands.",
    no_args_is_help=True,
)


@mcp_app.command("serve")
def serve_command(
    transport: str = typer.Option(
        "stdio",
        "--transport",
        "-t",
        help=(
            "MCP transport protocol. "
            "'stdio' (default) is used by Cursor and Claude Desktop. "
            "'sse' (Server-Sent Events) is for remote/HTTP deployments."
        ),
    ),
    port: int = typer.Option(
        3333,
        "--port",
        "-p",
        help="Port to listen on when using the 'sse' transport.",
    ),
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        help="Host interface to bind when using the 'sse' transport.",
    ),
) -> None:
    """Start the IronLayer MCP server.

    For Cursor / Claude Desktop, run::

        ironlayer mcp serve

    The default ``stdio`` transport communicates over stdin/stdout and is
    compatible with all MCP-aware clients.

    For remote / shared deployments run::

        ironlayer mcp serve --transport sse --port 3333

    The ``sse`` transport starts an HTTP server exposing the MCP protocol
    over Server-Sent Events.
    """
    if transport not in {"stdio", "sse"}:
        console.print(f"[red]Unknown transport '{transport}'. Choose 'stdio' or 'sse'.[/red]")
        raise typer.Exit(code=3)

    if transport == "stdio":
        _serve_stdio()
    else:
        _serve_sse(host=host, port=port)


def _serve_stdio() -> None:
    """Start the MCP server using the stdio transport."""
    try:
        from cli.mcp.server import create_mcp_server

        mcp_server = create_mcp_server()
        mcp_server.run_stdio()
    except ImportError as exc:
        console.print(
            "[red]MCP dependencies not installed. "
            "Install them with: [bold]pip install ironlayer\\[mcp\\][/bold][/red]"
        )
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]MCP server error: {exc}[/red]")
        raise typer.Exit(code=3) from exc


def _serve_sse(host: str, port: int) -> None:
    """Start the MCP server using the SSE/HTTP transport."""
    try:
        import uvicorn

        from cli.mcp.server import create_mcp_server

        mcp_server = create_mcp_server()
        starlette_app = mcp_server.as_asgi()

        console.print(f"IronLayer MCP server starting on [bold]http://{host}:{port}[/bold]")
        uvicorn.run(starlette_app, host=host, port=port, log_level="warning")
    except ImportError as exc:
        console.print(
            "[red]SSE transport dependencies not installed. "
            "Install them with: [bold]pip install ironlayer\\[mcp\\][/bold][/red]"
        )
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        console.print(f"[red]MCP server error: {exc}[/red]")
        raise typer.Exit(code=3) from exc
