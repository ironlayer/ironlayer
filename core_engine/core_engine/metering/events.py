"""Usage event definitions for the metering pipeline.

Each event represents a billable or quota-relevant action taken by a
tenant.  Events are collected in-memory, flushed to a sink (database or
file), and aggregated for usage summaries.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class UsageEventType(str, Enum):
    """Types of metered usage events."""

    PLAN_RUN = "plan_run"
    PLAN_APPLY = "plan_apply"
    AI_CALL = "ai_call"
    MODEL_LOADED = "model_loaded"
    BACKFILL_RUN = "backfill_run"
    API_REQUEST = "api_request"


class UsageEvent(BaseModel):
    """A single usage event for metering.

    Attributes
    ----------
    event_id:
        Unique identifier for this event.
    tenant_id:
        The tenant that generated this event.
    event_type:
        The type of metered event.
    timestamp:
        When the event occurred (UTC).
    quantity:
        Number of units consumed (e.g., 1 plan run, 150 tokens).
    metadata:
        Additional context (model names, plan IDs, etc.).
    """

    event_id: str = Field(default_factory=lambda: f"evt-{uuid.uuid4().hex[:12]}")
    tenant_id: str
    event_type: UsageEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    quantity: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)
