"""Ed25519-signed license file management.

License files are JSON documents signed with Ed25519 private keys.
The platform embeds the corresponding public key and verifies signatures
on startup.  Invalid, expired, or tampered licenses cause the system to
fall back to Community tier (free, limited features).

License file format (JSON):

.. code-block:: json

    {
        "license_id": "lic-abc123",
        "tenant_id": "tenant-456",
        "tier": "enterprise",
        "issued_at": "2024-01-01T00:00:00Z",
        "expires_at": "2025-01-01T00:00:00Z",
        "max_models": 500,
        "max_plan_runs_per_day": 100,
        "ai_enabled": true,
        "features": ["multi_tenant", "sso_oidc", "failure_prediction"],
        "signature": "<base64-encoded-ed25519-signature>"
    }

The signature covers all fields except ``signature`` itself, serialized
as canonical JSON (sorted keys, no whitespace).
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core_engine.license.feature_flags import Feature, LicenseTier, is_feature_enabled

logger = logging.getLogger(__name__)


class LicenseFile(BaseModel):
    """Parsed license file data."""

    license_id: str
    tenant_id: str
    tier: LicenseTier
    issued_at: datetime
    expires_at: datetime
    max_models: int = Field(default=50, ge=1)
    max_plan_runs_per_day: int = Field(default=10, ge=1)
    ai_enabled: bool = True
    features: list[str] = Field(default_factory=list)
    signature: str = ""


class LicenseVerificationError(Exception):
    """Raised when license signature verification fails."""


class LicenseExpiredError(Exception):
    """Raised when a license has expired."""


class LicenseLimitExceededError(Exception):
    """Raised when a license limit is exceeded."""


class LicenseManager:
    """Loads, verifies, and enforces Ed25519-signed license files.

    Parameters
    ----------
    public_key_bytes:
        The raw 32-byte Ed25519 public key used to verify signatures.
        If ``None``, signature verification is skipped (for testing).
    """

    def __init__(self, public_key_bytes: bytes | None = None) -> None:
        self._public_key_bytes = public_key_bytes
        self._license: LicenseFile | None = None
        self._effective_tier: LicenseTier = LicenseTier.COMMUNITY

    @property
    def license(self) -> LicenseFile | None:
        """The currently loaded license, or ``None`` if none is loaded."""
        return self._license

    @property
    def effective_tier(self) -> LicenseTier:
        """The effective license tier (falls back to COMMUNITY)."""
        return self._effective_tier

    def load_license(self, license_path: Path) -> LicenseFile:
        """Load and verify a license file.

        Parameters
        ----------
        license_path:
            Path to the JSON license file.

        Returns
        -------
        LicenseFile
            The verified license data.

        Raises
        ------
        LicenseVerificationError
            If the signature is invalid.
        LicenseExpiredError
            If the license has expired.
        FileNotFoundError
            If the license file does not exist.
        """
        if not license_path.exists():
            raise FileNotFoundError(f"License file not found: {license_path}")

        raw = license_path.read_text(encoding="utf-8")
        data = json.loads(raw)

        # Parse the license file.
        license_file = LicenseFile(**data)

        # Verify the signature.
        self._verify_signature(data)

        # Check expiry.
        now = datetime.now(UTC)
        if license_file.expires_at.tzinfo is None:
            # Treat naive datetimes as UTC.
            expires_at = license_file.expires_at.replace(tzinfo=UTC)
        else:
            expires_at = license_file.expires_at

        if now > expires_at:
            raise LicenseExpiredError(f"License '{license_file.license_id}' expired at {expires_at.isoformat()}")

        self._license = license_file
        self._effective_tier = license_file.tier
        logger.info(
            "License loaded: id=%s tier=%s tenant=%s expires=%s",
            license_file.license_id,
            license_file.tier.value,
            license_file.tenant_id,
            expires_at.isoformat(),
        )

        return license_file

    def load_license_from_string(self, content: str) -> LicenseFile:
        """Load and verify a license from a JSON string.

        Parameters
        ----------
        content:
            Raw JSON license content.

        Returns
        -------
        LicenseFile
            The verified license data.
        """
        data = json.loads(content)
        license_file = LicenseFile(**data)

        self._verify_signature(data)

        now = datetime.now(UTC)
        expires_at = license_file.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if now > expires_at:
            raise LicenseExpiredError(f"License '{license_file.license_id}' expired at {expires_at.isoformat()}")

        self._license = license_file
        self._effective_tier = license_file.tier
        return license_file

    def _verify_signature(self, data: dict[str, Any]) -> None:
        """Verify the Ed25519 signature of the license data.

        The signature covers the canonical JSON representation of all
        fields except ``signature``.

        Parameters
        ----------
        data:
            The parsed license JSON dictionary.

        Raises
        ------
        LicenseVerificationError
            If verification fails.
        """
        if self._public_key_bytes is None:
            # Signature verification disabled (testing mode).
            return

        signature_b64 = data.get("signature", "")
        if not signature_b64:
            raise LicenseVerificationError("License file has no signature")

        try:
            signature_bytes = base64.b64decode(signature_b64)
        except Exception as exc:
            raise LicenseVerificationError(f"Invalid base64 signature: {exc}") from exc

        # Build the canonical payload (all fields except signature, sorted keys).
        payload_data = {k: v for k, v in data.items() if k != "signature"}
        canonical = json.dumps(payload_data, sort_keys=True, separators=(",", ":"))
        message = canonical.encode("utf-8")

        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )

            public_key = Ed25519PublicKey.from_public_bytes(self._public_key_bytes)
            public_key.verify(signature_bytes, message)
        except ImportError:
            # Fallback: if cryptography is not installed, skip verification
            # with a warning.  This should not happen in production.
            logger.warning("cryptography library not available; signature verification skipped")
        except Exception as exc:
            raise LicenseVerificationError(f"Signature verification failed: {exc}") from exc

    def check_entitlement(self, feature: Feature) -> bool:
        """Check if a feature is enabled under the current license.

        Parameters
        ----------
        feature:
            The feature to check.

        Returns
        -------
        bool
            ``True`` if the feature is available at the current tier.
        """
        return is_feature_enabled(self._effective_tier, feature)

    def require_entitlement(self, feature: Feature) -> None:
        """Require that a feature is enabled, raising if not.

        Parameters
        ----------
        feature:
            The feature to require.

        Raises
        ------
        LicenseLimitExceededError
            If the feature is not available at the current tier.
        """
        if not self.check_entitlement(feature):
            raise LicenseLimitExceededError(
                f"Feature '{feature.value}' requires a higher license tier. Current tier: {self._effective_tier.value}"
            )

    def check_model_limit(self, current_model_count: int) -> bool:
        """Check if the current model count is within license limits.

        Parameters
        ----------
        current_model_count:
            The number of models currently registered.

        Returns
        -------
        bool
            ``True`` if within limits.
        """
        if self._license is None:
            # Community default: 50 models.
            return current_model_count <= 50
        return current_model_count <= self._license.max_models

    def check_daily_plan_limit(self, plans_today: int) -> bool:
        """Check if the daily plan run count is within license limits.

        Parameters
        ----------
        plans_today:
            The number of plan runs executed today.

        Returns
        -------
        bool
            ``True`` if within limits.
        """
        if self._license is None:
            # Community default: 10 plans/day.
            return plans_today <= 10
        return plans_today <= self._license.max_plan_runs_per_day

    def is_ai_enabled(self) -> bool:
        """Check if AI features are enabled in the license.

        Returns
        -------
        bool
            ``True`` if AI is enabled (requires Team tier or higher).
        """
        if self._license is None:
            return False
        return self._license.ai_enabled and self.check_entitlement(Feature.AI_ADVISORY)

    def get_license_info(self) -> dict[str, Any]:
        """Return a summary of the current license state.

        Returns
        -------
        dict
            License information safe for API responses.
        """
        if self._license is None:
            return {
                "tier": LicenseTier.COMMUNITY.value,
                "licensed": False,
                "max_models": 50,
                "max_plan_runs_per_day": 10,
                "ai_enabled": False,
            }
        return {
            "tier": self._license.tier.value,
            "licensed": True,
            "license_id": self._license.license_id,
            "tenant_id": self._license.tenant_id,
            "expires_at": self._license.expires_at.isoformat(),
            "max_models": self._license.max_models,
            "max_plan_runs_per_day": self._license.max_plan_runs_per_day,
            "ai_enabled": self._license.ai_enabled,
        }
