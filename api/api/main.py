"""FastAPI application entry-point for the IronLayer API Control Plane."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from api import __version__
from api.config import APISettings, PlatformEnv, load_api_settings
from api.dependencies import (
    dispose_ai_client,
    dispose_engine,
    dispose_metering,
    init_ai_client,
    init_engine,
    init_metering,
)
from api.middleware.auth import AuthenticationMiddleware, LicenseMiddleware
from api.middleware.body_limit import BodyLimitMiddleware
from api.middleware.csp import ContentSecurityPolicyMiddleware
from api.middleware.csrf import CSRFMiddleware
from api.middleware.logging import RequestLoggingMiddleware
from api.middleware.metering import MeteringMiddleware
from api.middleware.prometheus import PrometheusMiddleware
from api.middleware.rate_limit import RateLimitConfig, RateLimitMiddleware
from api.middleware.trace_context import TraceContextMiddleware, TraceLoggingFilter
from api.routers import (
    admin_analytics,
    approvals,
    audit,
    auth,
    backfills,
    billing,
    customer_health,
    environments,
    event_subscriptions,
    health,
    models,
    plans,
    reconciliation,
    reports,
    runs,
    simulation,
    team,
    tenant_config,
    tests,
    usage,
    webhooks,
)
from api.routers import metrics as metrics_router
from api.services.auth_service import AuthError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup / shutdown lifecycle.

    On startup:
    - Initialise the async database engine.
    - Create database tables if they do not exist (dev convenience;
      production should use Alembic migrations).
    - Initialise the AI service HTTP client.

    On shutdown:
    - Dispose the database engine connection pool.
    - Close the AI client.
    """
    import os as _os

    settings: APISettings = load_api_settings()

    # Fail fast: refuse to start in production/staging without JWT_SECRET.
    jwt_secret_val = settings.jwt_secret.get_secret_value() if settings.jwt_secret else ""
    if settings.platform_env in (PlatformEnv.STAGING, PlatformEnv.PROD) and not jwt_secret_val:
        raise RuntimeError(
            f"JWT_SECRET environment variable is required in {settings.platform_env.value} mode. Refusing to start."
        )

    # Fail fast: refuse to start in production/staging with default credential encryption key.
    _cred_default = "ironlayer-dev-secret-change-in-production"
    cred_key_val = settings.credential_encryption_key.get_secret_value()
    if settings.platform_env in (PlatformEnv.STAGING, PlatformEnv.PROD) and cred_key_val == _cred_default:
        raise RuntimeError(
            "credential_encryption_key (or CREDENTIAL_ENCRYPTION_KEY) must be set to a non-default value in "
            f"{settings.platform_env.value} mode. Refusing to start."
        )

    # Fail fast: if billing is enabled, require Stripe secrets.
    if settings.billing_enabled:
        stripe_key = settings.stripe_secret_key.get_secret_value()
        if not (stripe_key and stripe_key.strip()):
            raise RuntimeError(
                "billing_enabled is True but stripe_secret_key is not set. "
                "Set STRIPE_SECRET_KEY or disable billing. Refusing to start."
            )
        webhook_secret = settings.stripe_webhook_secret.get_secret_value()
        if not (webhook_secret and webhook_secret.strip()):
            raise RuntimeError(
                "billing_enabled is True but stripe_webhook_secret is not set. "
                "Set STRIPE_WEBHOOK_SECRET or disable billing. Refusing to start."
            )

    # Store settings on app.state for request-scoped dependencies.
    app.state.settings = settings

    # Database engine and session factory.
    engine, session_factory = init_engine(settings)
    app.state.engine = engine
    app.state.session_factory = session_factory
    is_local = settings.database_url.startswith("sqlite")
    logger.info(
        "Database engine initialised (%s, %s)",
        settings.database_url[:40] + "...",
        "local" if is_local else "postgres",
    )

    # Auto-create tables in dev or local SQLite mode (idempotent).
    if settings.platform_env == PlatformEnv.DEV or is_local:
        from core_engine.state.tables import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info(
            "Database tables ensured (%s)",
            "local SQLite" if is_local else "dev auto-migration",
        )

    # AI client.
    ai_client = init_ai_client(settings)
    app.state.ai_client = ai_client
    logger.info("AI service client initialised (%s)", settings.ai_engine_url)

    # Metering collector.
    metering = init_metering(session_factory)
    app.state.metering = metering
    logger.info("Metering collector initialised")

    # Token revocation checker.
    if settings.token_revocation_enabled:
        from api.middleware.auth import init_revocation_checker

        init_revocation_checker(session_factory)
        logger.info("Token revocation checker initialised")

    # License manager.
    import os

    from api.middleware.auth import init_license_manager

    license_path = os.environ.get("IRONLAYER_LICENSE_PATH") or getattr(settings, "license_path", None)
    init_license_manager(license_path)
    logger.info("License manager initialised")

    # Event bus for lifecycle hooks and webhook dispatch.
    from api.services.event_bus import init_event_bus

    event_bus = init_event_bus(session_factory=session_factory)
    logger.info("Event bus initialised with %d handler(s)", event_bus.handler_count)

    # Structured JSON logging for SIEM integration.
    if settings.structured_logging:
        from api.middleware.json_formatter import JSONFormatter

        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        handler.addFilter(TraceLoggingFilter())
        root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)
        logger.info("Structured JSON logging enabled for SIEM integration")

    yield

    # Shutdown.
    dispose_metering(app.state.metering)
    await dispose_ai_client(app.state.ai_client)
    await dispose_engine(app.state.engine)
    logger.info("Application shutdown complete")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    settings = load_api_settings()

    app = FastAPI(
        title="IronLayer API",
        description="Control Plane for deterministic SQL transformation orchestration.",
        version=__version__,
        lifespan=lifespan,
    )

    # -- Middleware (outermost first) ----------------------------------------

    app.add_middleware(PrometheusMiddleware)
    app.add_middleware(BodyLimitMiddleware, max_body_size=settings.max_request_body_size)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Correlation-ID",
            "X-CSRF-Token",
            "Accept",
        ],
    )
    app.add_middleware(ContentSecurityPolicyMiddleware, api_url=settings.ai_engine_url)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(AuthenticationMiddleware)
    app.add_middleware(TraceContextMiddleware)
    app.add_middleware(LicenseMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        config=RateLimitConfig(
            enabled=settings.rate_limit_enabled,
            default_requests_per_minute=settings.rate_limit_requests_per_minute,
            burst_multiplier=settings.rate_limit_burst_multiplier,
            auth_endpoints_per_minute=settings.rate_limit_auth_endpoints_per_minute,
        ),
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(MeteringMiddleware)

    # -- Routers -------------------------------------------------------------

    # Versioned API routes — all business endpoints live under /api/v1.
    app.include_router(health.router, prefix="/api/v1")
    app.include_router(plans.router, prefix="/api/v1")
    app.include_router(models.router, prefix="/api/v1")
    app.include_router(runs.router, prefix="/api/v1")
    app.include_router(backfills.router, prefix="/api/v1")
    app.include_router(approvals.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(reconciliation.router, prefix="/api/v1")
    app.include_router(tenant_config.router, prefix="/api/v1")
    app.include_router(tenant_config.settings_router, prefix="/api/v1")
    app.include_router(usage.router, prefix="/api/v1")
    app.include_router(billing.router, prefix="/api/v1")
    app.include_router(webhooks.router, prefix="/api/v1")
    app.include_router(environments.router, prefix="/api/v1")
    app.include_router(tests.router, prefix="/api/v1")
    app.include_router(event_subscriptions.router, prefix="/api/v1")
    app.include_router(simulation.router, prefix="/api/v1")
    app.include_router(admin_analytics.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(customer_health.router, prefix="/api/v1")
    app.include_router(team.router, prefix="/api/v1")

    # Metrics endpoint — outside /api/v1 versioning (Prometheus scrape).
    app.include_router(metrics_router.router)

    # Infrastructure endpoints — outside versioning (probes, root-level).
    app.include_router(health.readiness_router)

    # -- Exception handlers --------------------------------------------------

    @app.exception_handler(AuthError)
    async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        # Log the full error for debugging; return a safe message to the client.
        logger.warning("ValueError on %s: %s", request.url.path, exc)
        return JSONResponse(status_code=400, content={"detail": "Invalid request"})

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError) -> JSONResponse:
        logger.warning("PermissionError on %s: %s", request.url.path, exc)
        return JSONResponse(status_code=403, content={"detail": "Permission denied"})

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database error: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal database error"},
        )

    return app


# Module-level application instance used by ``uvicorn api.main:app``.
app = create_app()
