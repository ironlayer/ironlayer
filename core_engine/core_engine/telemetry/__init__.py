"""Telemetry collection, metrics emission, privacy, retention, and KPIs."""

from __future__ import annotations

from core_engine.telemetry.collector import capture_run_telemetry
from core_engine.telemetry.emitter import MetricsEmitter
from core_engine.telemetry.kpi import ALL_KPIS, KPIEvaluator, KPIStatus, KPIThreshold
from core_engine.telemetry.privacy import TelemetryConsent, TelemetryScrubber, scrub_pii
from core_engine.telemetry.retention import RetentionManager, RetentionPolicy

__all__ = [
    "ALL_KPIS",
    "KPIEvaluator",
    "KPIStatus",
    "KPIThreshold",
    "MetricsEmitter",
    "RetentionManager",
    "RetentionPolicy",
    "TelemetryConsent",
    "TelemetryScrubber",
    "capture_run_telemetry",
    "scrub_pii",
]
