"""Prometheus metrics endpoint.

Exposes ``GET /metrics`` returning Prometheus text-format metrics.
This endpoint is registered WITHOUT the ``/api/v1`` prefix and
bypasses JWT authentication (added to ``_PUBLIC_PATHS``).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def prometheus_metrics() -> PlainTextResponse:
    """Return all registered Prometheus metrics in text exposition format."""
    try:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return PlainTextResponse(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )
    except ImportError:
        return PlainTextResponse(
            content="# prometheus_client not installed\n",
            media_type="text/plain",
        )
