"""IronLayer license enforcement module.

Provides Ed25519-signed license file verification, tier-based feature gating,
and limit enforcement for enterprise features.
"""

from core_engine.license.feature_flags import Feature, LicenseTier, is_feature_enabled
from core_engine.license.license_manager import LicenseFile, LicenseManager

__all__ = [
    "Feature",
    "LicenseFile",
    "LicenseManager",
    "LicenseTier",
    "is_feature_enabled",
]
