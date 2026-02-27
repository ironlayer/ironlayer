"""Model definition schema for SQL model files."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class ModelTestType(str, Enum):
    """Types of declarative model tests."""

    NOT_NULL = "NOT_NULL"
    UNIQUE = "UNIQUE"
    ROW_COUNT_MIN = "ROW_COUNT_MIN"
    ROW_COUNT_MAX = "ROW_COUNT_MAX"
    ACCEPTED_VALUES = "ACCEPTED_VALUES"
    CUSTOM_SQL = "CUSTOM_SQL"


class TestSeverity(str, Enum):
    """How test failures are handled."""

    BLOCK = "BLOCK"  # Failure blocks plan apply
    WARN = "WARN"  # Failure logged but doesn't block


class ModelTestDefinition(BaseModel):
    """A declarative test assertion for a model."""

    test_type: ModelTestType
    column: str | None = None  # Required for NOT_NULL, UNIQUE, ACCEPTED_VALUES
    threshold: int | None = None  # Required for ROW_COUNT_MIN/MAX
    values: list[str] | None = None  # Required for ACCEPTED_VALUES
    sql: str | None = None  # Required for CUSTOM_SQL
    severity: TestSeverity = TestSeverity.BLOCK


class ModelKind(str, Enum):
    """Incremental strategy for a SQL model."""

    FULL_REFRESH = "FULL_REFRESH"
    INCREMENTAL_BY_TIME_RANGE = "INCREMENTAL_BY_TIME_RANGE"
    APPEND_ONLY = "APPEND_ONLY"
    MERGE_BY_KEY = "MERGE_BY_KEY"


class Materialization(str, Enum):
    """How the model output is written to the target warehouse."""

    TABLE = "TABLE"
    VIEW = "VIEW"
    MERGE = "MERGE"
    INSERT_OVERWRITE = "INSERT_OVERWRITE"


class SchemaContractMode(str, Enum):
    """Controls how schema contract violations are handled.

    * **DISABLED** — no enforcement (default for backward compatibility).
    * **WARN** — violations are surfaced in the plan but do not block apply.
    * **STRICT** — breaking violations prevent the plan from being applied.
    """

    DISABLED = "DISABLED"
    WARN = "WARN"
    STRICT = "STRICT"


class ColumnContract(BaseModel):
    """A declared type contract for a single output column.

    Column contracts allow model owners to assert that specific columns must
    exist with a declared data type and nullability.  Violations are detected
    at plan time when the model's actual output columns diverge from the
    contract.

    The ``data_type`` field uses warehouse-agnostic type names (STRING, INT,
    BIGINT, FLOAT, DOUBLE, BOOLEAN, DATE, TIMESTAMP, DECIMAL, etc.).
    """

    name: str = Field(
        ...,
        min_length=1,
        description="Column name as declared in the contract.",
    )
    data_type: str = Field(
        ...,
        min_length=1,
        description="Expected data type (STRING, INT, TIMESTAMP, etc.).",
    )
    nullable: bool = Field(
        default=True,
        description="Whether the column may contain NULLs.",
    )


class ModelDefinition(BaseModel):
    """Complete definition of a SQL model parsed from a ``.sql`` file.

    A ``ModelDefinition`` captures everything the planner and executor need to
    know about a single model: its incremental strategy, materialization mode,
    SQL source, and any artifacts produced during the parsing phase (content
    hash, referenced tables, output columns).
    """

    # -- Identity --
    name: str = Field(
        ...,
        min_length=1,
        description="Canonical model name, e.g. 'analytics.orders_daily'.",
    )
    kind: ModelKind = Field(
        ...,
        description="Incremental strategy that governs how re-runs are handled.",
    )
    materialization: Materialization = Field(
        default=Materialization.TABLE,
        description="Physical materialisation in the target warehouse.",
    )

    # -- Optional metadata --
    time_column: str | None = Field(
        default=None,
        description="Time column used for range-based incremental models.",
    )
    unique_key: str | None = Field(
        default=None,
        description="Unique key column used by MERGE_BY_KEY strategy.",
    )
    partition_by: str | None = Field(
        default=None,
        description="Partition column in the target warehouse.",
    )
    incremental_strategy: str | None = Field(
        default=None,
        description="Engine-specific incremental strategy hint.",
    )
    owner: str | None = Field(
        default=None,
        description="Team or individual responsible for this model.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Freeform tags for filtering and grouping.",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Explicit upstream dependencies declared in the SQL header.",
    )

    # -- File information --
    file_path: str = Field(
        ...,
        min_length=1,
        description="Relative path to the SQL file within the project.",
    )
    raw_sql: str = Field(
        ...,
        description="Original SQL content read from the file, including header.",
    )
    clean_sql: str = Field(
        default="",
        description="SQL after ref() macro substitution and header stripping.",
    )

    # -- Parsed artifacts (populated after initial construction) --
    content_hash: str = Field(
        default="",
        description="SHA-256 digest of the canonical (clean) SQL.",
    )
    referenced_tables: list[str] = Field(
        default_factory=list,
        description="Fully-qualified table names referenced in the SQL body.",
    )
    output_columns: list[str] = Field(
        default_factory=list,
        description="Column names produced by this model's SELECT statement.",
    )

    # -- Schema contracts --
    contract_mode: SchemaContractMode = Field(
        default=SchemaContractMode.DISABLED,
        description="How schema contract violations are handled (DISABLED, WARN, STRICT).",
    )
    contract_columns: list[ColumnContract] = Field(
        default_factory=list,
        description="Declared column-type contracts for this model's output schema.",
    )

    # -- Declarative tests --
    tests: list[ModelTestDefinition] = Field(
        default_factory=list,
        description="Declarative test assertions for this model.",
    )

    # -- Validators --

    @model_validator(mode="after")
    def validate_kind_requirements(self) -> ModelDefinition:
        """Ensure that fields required by specific model kinds are present."""
        if self.kind == ModelKind.INCREMENTAL_BY_TIME_RANGE and not self.time_column:
            raise ValueError(f"Model '{self.name}' has kind INCREMENTAL_BY_TIME_RANGE but no time_column specified.")
        if self.kind == ModelKind.MERGE_BY_KEY and not self.unique_key:
            raise ValueError(f"Model '{self.name}' has kind MERGE_BY_KEY but no unique_key specified.")
        return self

    # -- Convenience methods --

    def with_parsed_artifacts(
        self,
        clean_sql: str,
        content_hash: str,
        referenced_tables: list[str],
        output_columns: list[str],
    ) -> ModelDefinition:
        """Return a new instance with parsed-phase artifacts populated.

        This is the canonical way to "promote" a definition that was created
        from the raw file into one that carries all derived metadata.
        """
        return self.model_copy(
            update={
                "clean_sql": clean_sql,
                "content_hash": content_hash,
                "referenced_tables": referenced_tables,
                "output_columns": output_columns,
            }
        )
