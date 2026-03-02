"""Internal-only license key generation tool.

This script generates and signs IronLayer license files using Ed25519.
It is NOT shipped with the product -- it is used by IronLayer staff to
issue licenses to customers.

Usage:
    python -m core_engine.license.keygen generate-keypair
    python -m core_engine.license.keygen sign-license \\
        --tenant-id tenant-123 \\
        --tier enterprise \\
        --expires 2025-12-31 \\
        --max-models 500 \\
        --private-key private.key \\
        --output license.json
"""

from __future__ import annotations

import base64
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from core_engine.license.feature_flags import LicenseTier


def generate_keypair(output_dir: Path | None = None) -> tuple[bytes, bytes]:
    """Generate an Ed25519 keypair for license signing.

    Parameters
    ----------
    output_dir:
        If provided, writes ``private.key`` and ``public.key`` files.

    Returns
    -------
    tuple[bytes, bytes]
        (private_key_bytes, public_key_bytes) raw 32-byte keys.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    private_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public_bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "private.key").write_bytes(private_bytes)
        (output_dir / "public.key").write_bytes(public_bytes)
        print(f"Keypair written to {output_dir}/")
        print(f"Public key (hex):  {public_bytes.hex()}")
        print(f"Public key (b64):  {base64.b64encode(public_bytes).decode()}")

    return private_bytes, public_bytes


def sign_license(
    *,
    tenant_id: str,
    tier: LicenseTier,
    expires_at: datetime,
    max_models: int = 500,
    max_plan_runs_per_day: int = 100,
    ai_enabled: bool = True,
    features: list[str] | None = None,
    private_key_bytes: bytes,
) -> dict:
    """Create and sign a license file.

    Parameters
    ----------
    tenant_id:
        The tenant this license is issued to.
    tier:
        License tier.
    expires_at:
        Expiration timestamp.
    max_models:
        Maximum models allowed.
    max_plan_runs_per_day:
        Maximum plan runs per day.
    ai_enabled:
        Whether AI features are enabled.
    features:
        Optional explicit feature list.
    private_key_bytes:
        Raw 32-byte Ed25519 private key.

    Returns
    -------
    dict
        Complete license JSON data including signature.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    license_data = {
        "license_id": f"lic-{uuid.uuid4().hex[:12]}",
        "tenant_id": tenant_id,
        "tier": tier.value,
        "issued_at": datetime.now(UTC).isoformat(),
        "expires_at": expires_at.isoformat(),
        "max_models": max_models,
        "max_plan_runs_per_day": max_plan_runs_per_day,
        "ai_enabled": ai_enabled,
        "features": features or [],
    }

    # Canonical JSON for signing (sorted keys, no whitespace).
    canonical = json.dumps(license_data, sort_keys=True, separators=(",", ":"))
    message = canonical.encode("utf-8")

    private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)
    signature = private_key.sign(message)

    license_data["signature"] = base64.b64encode(signature).decode("ascii")
    return license_data


def main() -> None:
    """CLI entry point for license management."""
    if len(sys.argv) < 2:
        print("Usage: python -m core_engine.license.keygen <command>")
        print("Commands: generate-keypair, sign-license")
        sys.exit(1)

    command = sys.argv[1]

    if command == "generate-keypair":
        output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
        generate_keypair(output_dir)

    elif command == "sign-license":
        # Minimal CLI -- in practice, use argparse or a proper CLI framework.
        print("Use the sign_license() function programmatically.")
        print("See docstring for parameters.")
        sys.exit(1)

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
