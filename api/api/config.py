"""API-layer configuration loaded from environment variables."""

from __future__ import annotations

from typing import Self

from core_engine.config import PlatformEnv
from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseSettings):
    """FastAPI application settings.

    All values can be overridden via environment variables prefixed with
    ``API_`` (e.g. ``API_HOST=0.0.0.0``) or through a ``.env`` file in the
    working directory.
    """

    model_config = SettingsConfigDict(
        env_prefix="API_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # PostgreSQL connection string (asyncpg driver).
    database_url: str = "postgresql+asyncpg://ironlayer:ironlayer_dev@localhost:5432/ironlayer"

    # AI advisory engine URL and request timeout.
    ai_engine_url: str = "http://localhost:8001"
    ai_engine_timeout: float = 10.0

    # Environment label used for approval gate logic.
    platform_env: PlatformEnv = PlatformEnv.DEV

    @field_validator("platform_env", mode="before")
    @classmethod
    def _normalize_platform_env(cls, v: str | PlatformEnv) -> PlatformEnv | str:
        """Accept \"production\" from API_PLATFORM_ENV and normalize to PROD."""
        if isinstance(v, str) and v.lower() == "production":
            return PlatformEnv.PROD
        return v

    # Origins permitted by the CORS middleware.
    cors_origins: list[str] = ["http://localhost:3000"]

    # Whether CORS responses include credentials (cookies, auth headers).
    cors_allow_credentials: bool = True

    @model_validator(mode="after")
    def _validate_cors_credentials_not_wildcard(self) -> Self:
        """Reject wildcard origins when credentials are enabled.

        Browsers silently reject ``Access-Control-Allow-Origin: *`` when
        ``Access-Control-Allow-Credentials: true`` is present.  This
        misconfiguration is a common source of hard-to-debug CORS errors
        and can mask security issues.  Fail fast at startup instead.
        """
        if self.cors_allow_credentials and "*" in self.cors_origins:
            raise ValueError(
                "Cannot use wildcard origins with credentials. "
                "Specify explicit origins instead of '*' when "
                "cors_allow_credentials=True."
            )
        return self

    # Request body size limit (bytes). Rejects requests with larger Content-Length.
    max_request_body_size: int = 1_048_576  # 1 MiB

    # Rate limiting.
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 60
    rate_limit_burst_multiplier: float = 1.5
    rate_limit_auth_endpoints_per_minute: int = 20

    # Token revocation.
    token_revocation_enabled: bool = True

    # JWT signing secret (env: JWT_SECRET, no API_ prefix). Required in staging/prod.
    jwt_secret: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("jwt_secret", "JWT_SECRET"),
    )

    # Allowed base directory for repo_path validation (path traversal prevention).
    allowed_repo_base: str = "/workspace"

    # Structured JSON logging for SIEM integration.
    structured_logging: bool = False

    # Encryption key for CredentialVault (LLM keys, secrets at rest).
    # Falls back to JWT_SECRET if not explicitly set.
    credential_encryption_key: SecretStr = SecretStr("ironlayer-dev-secret-change-in-production")

    # Stripe billing integration.
    billing_enabled: bool = False
    stripe_secret_key: SecretStr = SecretStr("")
    stripe_webhook_secret: SecretStr = SecretStr("")
    stripe_price_id_community: str = ""
    stripe_price_id_team: str = ""
    stripe_price_id_enterprise: str = ""
    stripe_metered_price_id: str = ""
    stripe_price_id_per_seat: str = ""

    # Invoice PDF storage path.
    invoice_storage_path: str = "/var/lib/ironlayer/invoices"


def load_api_settings() -> APISettings:
    """Construct settings from the environment / ``.env`` file."""
    return APISettings()
