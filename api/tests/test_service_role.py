"""Tests for the SERVICE role and identity_kind support (A6)."""

from __future__ import annotations

import pytest

from api.middleware.rbac import (
    Permission,
    Role,
    ROLE_PERMISSIONS,
    parse_role,
    role_has_permission,
)


class TestServiceRole:
    """Verify SERVICE role placement and permissions."""

    def test_service_role_value_is_10(self) -> None:
        assert Role.SERVICE == 10

    def test_service_role_is_outside_hierarchy(self) -> None:
        """SERVICE value (10) is outside the 0-3 VIEWER..ADMIN range."""
        assert Role.SERVICE > Role.ADMIN

    def test_service_role_in_permissions_dict(self) -> None:
        assert Role.SERVICE in ROLE_PERMISSIONS

    def test_service_role_has_expected_permissions(self) -> None:
        perms = ROLE_PERMISSIONS[Role.SERVICE]
        expected = {
            Permission.READ_PLANS,
            Permission.READ_MODELS,
            Permission.READ_RUNS,
            Permission.CREATE_PLANS,
            Permission.APPLY_PLANS,
        }
        assert perms == expected

    def test_service_role_cannot_approve(self) -> None:
        assert not role_has_permission(Role.SERVICE, Permission.APPROVE_PLANS)

    def test_service_role_cannot_manage_credentials(self) -> None:
        assert not role_has_permission(Role.SERVICE, Permission.MANAGE_CREDENTIALS)

    def test_service_role_cannot_manage_settings(self) -> None:
        assert not role_has_permission(Role.SERVICE, Permission.MANAGE_SETTINGS)

    def test_service_role_cannot_write_models(self) -> None:
        assert not role_has_permission(Role.SERVICE, Permission.WRITE_MODELS)

    def test_service_role_cannot_create_backfills(self) -> None:
        assert not role_has_permission(Role.SERVICE, Permission.CREATE_BACKFILLS)

    def test_service_role_can_read_plans(self) -> None:
        assert role_has_permission(Role.SERVICE, Permission.READ_PLANS)

    def test_service_role_can_apply_plans(self) -> None:
        assert role_has_permission(Role.SERVICE, Permission.APPLY_PLANS)


class TestParseRole:
    """Verify role parsing including the service role."""

    def test_parse_service(self) -> None:
        assert parse_role("service") == Role.SERVICE

    def test_parse_service_case_insensitive(self) -> None:
        assert parse_role("SERVICE") == Role.SERVICE
        assert parse_role("Service") == Role.SERVICE

    def test_parse_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown role"):
            parse_role("superadmin")


class TestIdentityKind:
    """Verify TokenClaims identity_kind field."""

    def test_default_identity_kind(self) -> None:
        from api.security import TokenClaims

        claims = TokenClaims(sub="user1", tenant_id="t1")
        assert claims.identity_kind == "user"

    def test_service_identity_kind(self) -> None:
        from api.security import TokenClaims

        claims = TokenClaims(sub="svc1", tenant_id="t1", identity_kind="service")
        assert claims.identity_kind == "service"

    def test_jti_generated_by_default(self) -> None:
        from api.security import TokenClaims

        claims = TokenClaims(sub="user1", tenant_id="t1")
        assert claims.jti is not None
        assert len(claims.jti) == 32  # uuid4().hex

    def test_jti_unique_per_instance(self) -> None:
        from api.security import TokenClaims

        c1 = TokenClaims(sub="user1", tenant_id="t1")
        c2 = TokenClaims(sub="user1", tenant_id="t1")
        assert c1.jti != c2.jti


class TestGenerateTokenWithIdentityKind:
    """Verify TokenManager.generate_token() passes identity_kind."""

    def test_generate_user_token(self) -> None:
        from pydantic import SecretStr

        from api.security import TokenConfig, TokenManager

        mgr = TokenManager(TokenConfig(jwt_secret=SecretStr("test-secret-key")))
        token = mgr.generate_token("user1", "t1")
        claims = mgr.validate_token(token)
        assert claims.identity_kind == "user"

    def test_generate_service_token(self) -> None:
        from pydantic import SecretStr

        from api.security import TokenConfig, TokenManager

        mgr = TokenManager(TokenConfig(jwt_secret=SecretStr("test-secret-key")))
        token = mgr.generate_token("svc1", "t1", identity_kind="service")
        claims = mgr.validate_token(token)
        assert claims.identity_kind == "service"
