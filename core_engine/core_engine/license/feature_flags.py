"""Feature flags and tier-based entitlement gating.

Three license tiers control access to platform features:

* **Community** -- Free tier with core plan/apply functionality.
* **Team** -- Adds AI advisory, multi-model plans, and cost tracking.
* **Enterprise** -- Full feature set including SSO, multi-tenant RLS,
  failure prediction, and advanced security.
"""

from __future__ import annotations

from enum import Enum


class LicenseTier(str, Enum):
    """License tier determining feature access."""

    COMMUNITY = "community"
    TEAM = "team"
    ENTERPRISE = "enterprise"


class Feature(str, Enum):
    """Platform features that can be gated by license tier."""

    # Core features (community)
    PLAN_GENERATE = "plan_generate"
    PLAN_APPLY = "plan_apply"
    MODEL_LOADING = "model_loading"
    LINEAGE_VIEW = "lineage_view"
    BACKFILL = "backfill"
    LOCAL_DEV = "local_dev"

    # Team features
    AI_ADVISORY = "ai_advisory"
    COST_TRACKING = "cost_tracking"
    MULTI_MODEL_PLANS = "multi_model_plans"
    MIGRATION_TOOLS = "migration_tools"
    STRUCTURED_TELEMETRY = "structured_telemetry"
    API_ACCESS = "api_access"
    TEAM_MANAGEMENT = "team_management"

    # Enterprise features
    MULTI_TENANT = "multi_tenant"
    SSO_OIDC = "sso_oidc"
    COST_OPTIMIZATION = "cost_optimization"
    FAILURE_PREDICTION = "failure_prediction"
    AI_RESPONSE_CACHING = "ai_response_caching"
    AUDIT_LOG = "audit_log"
    RECONCILIATION = "reconciliation"
    CHECK_ENGINE = "check_engine"
    LLM_BUDGET_GUARDRAILS = "llm_budget_guardrails"
    CREDENTIAL_ENCRYPTION = "credential_encryption"
    RATE_LIMITING = "rate_limiting"


# Features available at each tier.  Higher tiers include all lower-tier
# features automatically.

_COMMUNITY_FEATURES: frozenset[Feature] = frozenset(
    {
        Feature.PLAN_GENERATE,
        Feature.PLAN_APPLY,
        Feature.MODEL_LOADING,
        Feature.LINEAGE_VIEW,
        Feature.BACKFILL,
        Feature.LOCAL_DEV,
    }
)

_TEAM_FEATURES: frozenset[Feature] = _COMMUNITY_FEATURES | frozenset(
    {
        Feature.AI_ADVISORY,
        Feature.COST_TRACKING,
        Feature.MULTI_MODEL_PLANS,
        Feature.MIGRATION_TOOLS,
        Feature.STRUCTURED_TELEMETRY,
        Feature.API_ACCESS,
        Feature.TEAM_MANAGEMENT,
        Feature.CHECK_ENGINE,
    }
)

_ENTERPRISE_FEATURES: frozenset[Feature] = _TEAM_FEATURES | frozenset(
    {
        Feature.MULTI_TENANT,
        Feature.SSO_OIDC,
        Feature.COST_OPTIMIZATION,
        Feature.FAILURE_PREDICTION,
        Feature.AI_RESPONSE_CACHING,
        Feature.AUDIT_LOG,
        Feature.RECONCILIATION,
        Feature.LLM_BUDGET_GUARDRAILS,
        Feature.CREDENTIAL_ENCRYPTION,
        Feature.RATE_LIMITING,
    }
)

TIER_FEATURES: dict[LicenseTier, frozenset[Feature]] = {
    LicenseTier.COMMUNITY: _COMMUNITY_FEATURES,
    LicenseTier.TEAM: _TEAM_FEATURES,
    LicenseTier.ENTERPRISE: _ENTERPRISE_FEATURES,
}


def is_feature_enabled(tier: LicenseTier, feature: Feature) -> bool:
    """Check whether a feature is enabled for the given license tier.

    Parameters
    ----------
    tier:
        The active license tier.
    feature:
        The feature to check.

    Returns
    -------
    bool
        ``True`` if the feature is included in the tier's entitlements.
    """
    return feature in TIER_FEATURES.get(tier, _COMMUNITY_FEATURES)


def get_tier_features(tier: LicenseTier) -> frozenset[Feature]:
    """Return the set of features available at a given tier.

    Parameters
    ----------
    tier:
        The license tier to query.

    Returns
    -------
    frozenset[Feature]
        All features enabled for the tier.
    """
    return TIER_FEATURES.get(tier, _COMMUNITY_FEATURES)


def get_required_tier(feature: Feature) -> LicenseTier:
    """Return the minimum tier required for a feature.

    Parameters
    ----------
    feature:
        The feature to look up.

    Returns
    -------
    LicenseTier
        The lowest tier that includes the feature.
    """
    for tier in (LicenseTier.COMMUNITY, LicenseTier.TEAM, LicenseTier.ENTERPRISE):
        if feature in TIER_FEATURES[tier]:
            return tier
    return LicenseTier.ENTERPRISE
