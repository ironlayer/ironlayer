"""``ironlayer login / logout / whoami`` — authentication commands."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

console = Console(stderr=True)


def _credentials_path() -> Path:
    return Path.home() / ".ironlayer" / "credentials.json"


def _save_credentials(api_url: str, access_token: str, refresh_token: str, email: str) -> None:
    cred_dir = Path.home() / ".ironlayer"
    cred_dir.mkdir(parents=True, exist_ok=True)
    cred_path = cred_dir / "credentials.json"
    cred_data = {
        "api_url": api_url,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "email": email,
    }
    cred_path.write_text(json.dumps(cred_data, indent=2), encoding="utf-8")
    cred_path.chmod(0o600)


def _load_stored_token() -> str | None:
    cred_path = _credentials_path()
    if not cred_path.exists():
        return None
    try:
        creds = json.loads(cred_path.read_text(encoding="utf-8"))
        return creds.get("access_token")
    except Exception:
        return None


def login_command(
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
    """Authenticate with an IronLayer API server and store credentials locally.

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


def logout_command() -> None:
    """Remove stored credentials.

    Clears the local credential file created by ``ironlayer login``.
    This does **not** revoke the token server-side.
    """
    cred_path = _credentials_path()
    if cred_path.exists():
        cred_path.unlink()
        console.print("[green]✓ Logged out — credentials removed.[/green]")
    else:
        console.print("[dim]No stored credentials found.[/dim]")


def whoami_command() -> None:
    """Show the currently authenticated user."""
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
