"""Pre-defined Databricks cluster specifications for IronLayer execution.

Cluster templates map T-shirt sizes to concrete ``new_cluster`` specs accepted
by the Databricks Jobs API.  Cost rates are maintained alongside the templates
so that the planner can produce accurate USD estimates without calling the
cloud pricing API at plan-time.
"""

from __future__ import annotations

import copy
from typing import Any

# ---------------------------------------------------------------------------
# Raw template definitions
# ---------------------------------------------------------------------------

_SPARK_VERSION = "14.3.x-scala2.12"

_TEMPLATES: dict[str, dict[str, Any]] = {
    "small": {
        "spark_version": _SPARK_VERSION,
        "node_type_id": "Standard_DS3_v2",
        "num_workers": 2,
        "spark_conf": {
            "spark.databricks.delta.preview.enabled": "true",
        },
    },
    "medium": {
        "spark_version": _SPARK_VERSION,
        "node_type_id": "Standard_DS4_v2",
        "num_workers": 8,
        "spark_conf": {
            "spark.databricks.delta.preview.enabled": "true",
        },
    },
    "large": {
        "spark_version": _SPARK_VERSION,
        "node_type_id": "Standard_DS5_v2",
        "num_workers": 16,
        "spark_conf": {
            "spark.databricks.delta.preview.enabled": "true",
        },
    },
}

# USD per compute-second for each cluster size.
_COST_RATES: dict[str, float] = {
    "small": 0.0007,
    "medium": 0.0028,
    "large": 0.0112,
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_cluster_spec(
    size: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a ``new_cluster`` specification for the requested T-shirt size.

    Parameters
    ----------
    size:
        One of ``"small"``, ``"medium"``, or ``"large"`` (case-insensitive).
    overrides:
        Optional dictionary of keys to merge on top of the base template.
        Useful for injecting custom spark_conf or node type overrides.

    Returns
    -------
    dict
        A deep-copied cluster spec ready to embed in a Jobs API request.

    Raises
    ------
    ValueError
        If *size* does not match a known template.
    """
    key = size.lower()
    if key not in _TEMPLATES:
        raise ValueError(f"Unknown cluster size '{size}'. " f"Valid sizes: {sorted(_TEMPLATES.keys())}")
    spec = copy.deepcopy(_TEMPLATES[key])
    if overrides:
        spec.update(overrides)
    return spec


def get_cost_rate(size: str) -> float:
    """Return the estimated USD cost per compute-second for *size*.

    Parameters
    ----------
    size:
        One of ``"small"``, ``"medium"``, or ``"large"`` (case-insensitive).

    Raises
    ------
    ValueError
        If *size* is not recognised.
    """
    key = size.lower()
    if key not in _COST_RATES:
        raise ValueError(f"Unknown cluster size '{size}'. " f"Valid sizes: {sorted(_COST_RATES.keys())}")
    return _COST_RATES[key]


# ---------------------------------------------------------------------------
# Convenience wrapper class
# ---------------------------------------------------------------------------


class ClusterTemplates:
    """Object-oriented facade around the cluster template helpers.

    Provides the same functionality as the module-level functions but allows
    callers to pass a single ``ClusterTemplates`` instance through the
    dependency graph when that style is preferred.
    """

    @staticmethod
    def get_spec(
        size: str,
        overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a ``new_cluster`` specification for *size*."""
        return get_cluster_spec(size, overrides)

    @staticmethod
    def get_cost_rate(size: str) -> float:
        """Return USD per compute-second for *size*."""
        return get_cost_rate(size)

    @staticmethod
    def available_sizes() -> list[str]:
        """Return sorted list of available cluster size names."""
        return sorted(_TEMPLATES.keys())
