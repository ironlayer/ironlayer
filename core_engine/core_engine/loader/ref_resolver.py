"""Resolve ``{{ ref('model_name') }}`` macros in SQL model files.

The resolver replaces every ``ref()`` call with the canonical table name
looked up from a model registry that maps short names to fully-qualified
identifiers.  Both single- and double-quoted arguments, arbitrary
whitespace inside the braces, and dotted ``schema.table`` names are
supported.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core_engine.models.model_definition import ModelDefinition

# ---------------------------------------------------------------------------
# Regex for matching ``{{ ref('...') }}`` / ``{{ ref("...") }}`` patterns
# ---------------------------------------------------------------------------
# Breakdown:
#   \{\{          – literal opening braces
#   \s*           – optional whitespace
#   ref\s*\(      – the word ``ref`` followed by optional whitespace and ``(``
#   \s*           – optional whitespace before the quote
#   (?:'([^']+)') – single-quoted model name  (capture group 1)
#   |             – OR
#   (?:"([^"]+)") – double-quoted model name  (capture group 2)
#   \s*           – optional whitespace after the closing quote
#   \)            – closing parenthesis
#   \s*           – optional whitespace
#   \}\}          – literal closing braces
_REF_PATTERN = re.compile(r"\{\{\s*ref\s*\(\s*(?:'([^']+)'|\"([^\"]+)\")\s*\)\s*\}\}")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class UnresolvedRefError(Exception):
    """Raised when a ``{{ ref('...') }}`` references an unknown model."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_model_registry(models: list[ModelDefinition]) -> dict[str, str]:
    """Build a mapping from model short names to canonical names.

    For a model with canonical name ``"analytics.orders_daily"`` the
    registry will contain **two** entries:

    * ``"orders_daily"`` -> ``"analytics.orders_daily"``
    * ``"analytics.orders_daily"`` -> ``"analytics.orders_daily"``

    If the canonical name has no schema prefix (e.g. ``"orders_daily"``),
    only one entry is created.

    Parameters
    ----------
    models:
        The list of parsed :class:`ModelDefinition` objects.

    Returns
    -------
    dict[str, str]
        A mapping from lookup key to canonical name.
    """
    registry: dict[str, str] = {}
    for model in models:
        canonical = model.name
        # Always register the full canonical name.
        registry[canonical] = canonical

        # If the name contains a dot, also register the short (suffix) form.
        if "." in canonical:
            short_name = canonical.rsplit(".", 1)[1]
            # If two models share the same short name the last one wins.
            # This is consistent with most SQL transformation frameworks.
            registry[short_name] = canonical

    return registry


def resolve_refs(sql: str, model_registry: dict[str, str]) -> str:
    """Replace every ``{{ ref('model_name') }}`` with the canonical table name.

    Parameters
    ----------
    sql:
        Raw SQL string potentially containing ``ref()`` macros.
    model_registry:
        Mapping produced by :func:`build_model_registry`.

    Returns
    -------
    str
        SQL with all ``ref()`` macros replaced by canonical table names.

    Raises
    ------
    UnresolvedRefError
        If any ``ref()`` argument does not exist in *model_registry*.
    """

    def _replace(match: re.Match[str]) -> str:
        # Exactly one of the two capture groups will be non-None.
        ref_name: str = match.group(1) or match.group(2)

        canonical = model_registry.get(ref_name)
        if canonical is None:
            raise UnresolvedRefError(
                f"Unresolved ref: '{{{{ ref('{ref_name}') }}}}'. "
                f"No model named '{ref_name}' exists in the registry. "
                f"Available models: {sorted(model_registry.keys())}"
            )
        return canonical

    return _REF_PATTERN.sub(_replace, sql)


def extract_ref_names(sql: str) -> list[str]:
    """Return an ordered, deduplicated list of model names referenced via ``ref()``.

    This is a convenience helper used by the loader to populate
    ``ModelDefinition.referenced_tables`` before the registry is
    available for full resolution.

    Parameters
    ----------
    sql:
        Raw SQL string potentially containing ``ref()`` macros.

    Returns
    -------
    list[str]
        Unique model names in the order they first appear.
    """
    seen: set[str] = set()
    names: list[str] = []
    for match in _REF_PATTERN.finditer(sql):
        name = match.group(1) or match.group(2)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names
