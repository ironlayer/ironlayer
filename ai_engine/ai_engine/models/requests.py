"""Pydantic request models for every advisory endpoint.

All request models include input-size validators that prevent
oversized payloads from reaching the engine logic.  These validators
complement the ``RequestSizeLimitMiddleware`` (which guards total
body size) by enforcing per-field semantic limits.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, SecretStr, field_validator

# ---------------------------------------------------------------------------
# Size limit constants (bytes / counts)
# ---------------------------------------------------------------------------
_MAX_SQL_BYTES: int = 102_400  # 100 KB
_MAX_MODEL_NAME_CHARS: int = 256
_MAX_MODELS_IN_DAG: int = 500
_MAX_TABLE_STATS_BYTES: int = 51_200  # 50 KB
_MAX_TAG_LIST_LEN: int = 100
_MAX_DASHBOARD_LIST_LEN: int = 200


# ---------------------------------------------------------------------------
# Shared validators
# ---------------------------------------------------------------------------


def _check_sql_size(v: str, field_name: str) -> str:
    """Raise ``ValueError`` when a SQL string exceeds the limit."""
    if len(v.encode("utf-8")) > _MAX_SQL_BYTES:
        raise ValueError(f"{field_name} exceeds maximum size of {_MAX_SQL_BYTES} bytes (~{_MAX_SQL_BYTES // 1024} KB)")
    return v


def _check_model_name(v: str) -> str:
    """Raise ``ValueError`` when a model name exceeds the limit."""
    if len(v) > _MAX_MODEL_NAME_CHARS:
        raise ValueError(f"model_name exceeds maximum length of {_MAX_MODEL_NAME_CHARS} characters")
    return v


def _check_dag_size(v: dict[str, list[str]]) -> dict[str, list[str]]:
    """Raise ``ValueError`` when a DAG contains too many models."""
    if len(v) > _MAX_MODELS_IN_DAG:
        raise ValueError(f"DAG contains {len(v)} models; maximum is {_MAX_MODELS_IN_DAG}")
    return v


def _check_dict_serialised_size(v: dict | None, field_name: str, max_bytes: int) -> dict | None:
    """Raise ``ValueError`` when a dict's JSON representation is too large."""
    if v is None:
        return v
    size = len(json.dumps(v, separators=(",", ":")).encode("utf-8"))
    if size > max_bytes:
        raise ValueError(f"{field_name} exceeds maximum serialised size of {max_bytes} bytes (~{max_bytes // 1024} KB)")
    return v


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SemanticClassifyRequest(BaseModel):
    """Request body for ``POST /semantic_classify``."""

    old_sql: str = Field(
        ...,
        description=("The SQL of the model *before* the change.  Pass an empty string for brand-new models."),
    )
    new_sql: str = Field(
        ...,
        description="The SQL of the model *after* the change.",
    )
    schema_diff: dict | None = Field(
        default=None,
        description=("Optional column-level diff produced by the schema comparator.  Keys: added, removed, modified."),
    )
    column_lineage: dict | None = Field(
        default=None,
        description=("Optional upstream-to-downstream column lineage map."),
    )
    tenant_id: str | None = Field(
        default=None,
        description="Tenant identifier (passed through for tracing; not used in logic).",
    )
    llm_enabled: bool = Field(
        default=True,
        description="Whether LLM enrichment is enabled for this request (per-tenant opt-out).",
    )
    api_key: SecretStr | None = Field(
        default=None,
        description=(
            "Per-tenant LLM API key.  When provided, this key is used instead "
            "of the platform-level key.  The key is never logged or cached."
        ),
        json_schema_extra={"writeOnly": True},
    )

    @field_validator("old_sql")
    @classmethod
    def validate_old_sql_size(cls, v: str) -> str:
        return _check_sql_size(v, "old_sql")

    @field_validator("new_sql")
    @classmethod
    def validate_new_sql_size(cls, v: str) -> str:
        return _check_sql_size(v, "new_sql")

    @field_validator("schema_diff")
    @classmethod
    def validate_schema_diff_size(cls, v: dict | None) -> dict | None:
        return _check_dict_serialised_size(v, "schema_diff", _MAX_TABLE_STATS_BYTES)

    @field_validator("column_lineage")
    @classmethod
    def validate_column_lineage_size(cls, v: dict | None) -> dict | None:
        return _check_dict_serialised_size(v, "column_lineage", _MAX_TABLE_STATS_BYTES)


class CostPredictRequest(BaseModel):
    """Request body for ``POST /predict_cost``."""

    model_name: str = Field(..., description="Fully qualified model name.")
    partition_count: int = Field(..., ge=0, description="Number of partitions to process.")
    historical_runtime_avg: float | None = Field(
        default=None,
        ge=0.0,
        description="Historical average runtime in seconds, if available.",
    )
    data_volume_bytes: int | None = Field(
        default=None,
        ge=0,
        description="Approximate data volume in bytes.",
    )
    cluster_size: str = Field(
        ...,
        pattern=r"^(small|medium|large)$",
        description="Databricks cluster size tier: small, medium, or large.",
    )
    num_workers: int | None = Field(
        default=None,
        ge=1,
        description="Number of cluster workers, if known.",
    )
    tenant_id: str | None = Field(
        default=None,
        description="Tenant identifier (passed through for tracing).",
    )
    llm_enabled: bool = Field(
        default=True,
        description="Whether LLM features are enabled for this request.",
    )

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        return _check_model_name(v)


class RiskScoreRequest(BaseModel):
    """Request body for ``POST /risk_score``."""

    model_name: str = Field(..., description="Fully qualified model name.")
    downstream_depth: int = Field(..., ge=0, description="Number of downstream hops in the DAG.")
    sla_tags: list[str] = Field(
        default_factory=list,
        description="SLA tags attached to this model (e.g. ['gold', 'p1']).",
    )
    dashboard_dependencies: list[str] = Field(
        default_factory=list,
        description="Dashboards that read from this model.",
    )
    model_tags: list[str] = Field(
        default_factory=list,
        description="Arbitrary tags on the model (e.g. 'critical', 'revenue').",
    )
    historical_failure_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraction of runs that failed historically (0.0 - 1.0).",
    )
    tenant_id: str | None = Field(
        default=None,
        description="Tenant identifier (passed through for tracing).",
    )
    llm_enabled: bool = Field(
        default=True,
        description="Whether LLM features are enabled for this request.",
    )

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        return _check_model_name(v)

    @field_validator("sla_tags")
    @classmethod
    def validate_sla_tags(cls, v: list[str]) -> list[str]:
        if len(v) > _MAX_TAG_LIST_LEN:
            raise ValueError(f"sla_tags has {len(v)} entries; maximum is {_MAX_TAG_LIST_LEN}")
        return v

    @field_validator("dashboard_dependencies")
    @classmethod
    def validate_dashboard_dependencies(cls, v: list[str]) -> list[str]:
        if len(v) > _MAX_DASHBOARD_LIST_LEN:
            raise ValueError(f"dashboard_dependencies has {len(v)} entries; maximum is {_MAX_DASHBOARD_LIST_LEN}")
        return v

    @field_validator("model_tags")
    @classmethod
    def validate_model_tags(cls, v: list[str]) -> list[str]:
        if len(v) > _MAX_TAG_LIST_LEN:
            raise ValueError(f"model_tags has {len(v)} entries; maximum is {_MAX_TAG_LIST_LEN}")
        return v


class FragilityScoreRequest(BaseModel):
    """Request body for ``POST /fragility_score``."""

    model_name: str = Field(..., description="Target model to evaluate fragility for.")
    dag: dict[str, list[str]] = Field(
        ...,
        description=("DAG adjacency list: model_name → [upstream_dep_1, upstream_dep_2, ...]."),
    )
    failure_predictions: dict[str, float] = Field(
        ...,
        description=("Mapping of model_name → failure_probability (0.0-1.0).  Models not in this map default to 0.0."),
    )
    tenant_id: str | None = Field(
        default=None,
        description="Tenant identifier (passed through for tracing).",
    )

    @field_validator("model_name")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        return _check_model_name(v)

    @field_validator("dag")
    @classmethod
    def validate_dag_size(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        return _check_dag_size(v)


class FragilityBatchRequest(BaseModel):
    """Request body for ``POST /fragility_score/batch``."""

    dag: dict[str, list[str]] = Field(
        ...,
        description="DAG adjacency list for the entire model graph.",
    )
    failure_predictions: dict[str, float] = Field(
        ...,
        description="Mapping of model_name → failure_probability.",
    )
    tenant_id: str | None = Field(
        default=None,
        description="Tenant identifier (passed through for tracing).",
    )

    @field_validator("dag")
    @classmethod
    def validate_dag_size(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        return _check_dag_size(v)


class OptimizeSQLRequest(BaseModel):
    """Request body for ``POST /optimize_sql``."""

    sql: str = Field(..., description="SQL query to analyse for optimisations.")
    table_statistics: dict | None = Field(
        default=None,
        description=("Optional table-level statistics (row counts, partitioning info)."),
    )
    query_metrics: dict | None = Field(
        default=None,
        description=("Optional historical query metrics (avg runtime, bytes scanned)."),
    )
    tenant_id: str | None = Field(
        default=None,
        description="Tenant identifier (passed through for tracing).",
    )
    llm_enabled: bool = Field(
        default=True,
        description="Whether LLM features are enabled for this request.",
    )
    api_key: SecretStr | None = Field(
        default=None,
        description=(
            "Per-tenant LLM API key.  When provided, this key is used instead "
            "of the platform-level key.  The key is never logged or cached."
        ),
        json_schema_extra={"writeOnly": True},
    )

    @field_validator("sql")
    @classmethod
    def validate_sql_size(cls, v: str) -> str:
        return _check_sql_size(v, "sql")

    @field_validator("table_statistics")
    @classmethod
    def validate_table_statistics_size(cls, v: dict | None) -> dict | None:
        return _check_dict_serialised_size(v, "table_statistics", _MAX_TABLE_STATS_BYTES)

    @field_validator("query_metrics")
    @classmethod
    def validate_query_metrics_size(cls, v: dict | None) -> dict | None:
        return _check_dict_serialised_size(v, "query_metrics", _MAX_TABLE_STATS_BYTES)
