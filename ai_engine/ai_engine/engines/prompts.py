"""Versioned prompt template registry for LLM interactions.

Every prompt used by the LLM client is registered here as a frozen
dataclass with a version string.  The version is logged alongside every
LLM call so that prompt changes are traceable in the audit trail and
SIEM logs without requiring a database-backed registry.

Git history serves as the version control mechanism.  When prompts are
updated, bump the ``version`` field so that log correlation is
unambiguous.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptTemplate:
    """An immutable, versioned prompt template."""

    key: str
    version: str
    content: str
    description: str


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROMPT_REGISTRY: dict[str, PromptTemplate] = {}


def _register(template: PromptTemplate) -> PromptTemplate:
    """Register a template and return it for module-level assignment."""
    PROMPT_REGISTRY[template.key] = template
    return template


def get_prompt(key: str) -> PromptTemplate:
    """Retrieve a registered prompt template by key.

    Raises
    ------
    KeyError
        If no template is registered under *key*.
    """
    try:
        return PROMPT_REGISTRY[key]
    except KeyError:
        raise KeyError(f"Unknown prompt key '{key}'. Registered keys: {sorted(PROMPT_REGISTRY)}")


# ---------------------------------------------------------------------------
# Registered templates
# ---------------------------------------------------------------------------

CLASSIFY_CHANGE_SYSTEM = _register(
    PromptTemplate(
        key="classify_change_system",
        version="v1",
        content=(
            "You are a SQL change classifier for a data platform.  "
            "Given the old and new SQL for a model, classify the change.  "
            "Respond ONLY with valid JSON: "
            '{"change_type": "<non_breaking|breaking|metric_semantic|rename_only|partition_shift|cosmetic>", '
            '"confidence": <0.0-1.0>, "reasoning": "<short explanation>"}'
        ),
        description="System prompt for the SQL change classifier LLM call.",
    )
)

SUGGEST_OPTIMIZATION_SYSTEM = _register(
    PromptTemplate(
        key="suggest_optimization_system",
        version="v1",
        content=(
            "You are a SQL performance engineer for Databricks / Spark SQL.  "
            "Given a SQL query, suggest concrete optimisations.  "
            "Respond ONLY with a JSON array where each element has: "
            '{"suggestion_type": "<string>", "description": "<string>", '
            '"rewritten_sql": "<string or null>", "confidence": <0.0-1.0>}'
        ),
        description="System prompt for the SQL optimisation suggester LLM call.",
    )
)
