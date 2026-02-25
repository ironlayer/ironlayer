"""Dependency fragility scorer -- graph-weighted failure propagation.

Computes a composite fragility score (0-10) for each model in the DAG
by combining three signals:

1. **own_risk** — the model's own failure probability.
2. **upstream_risk** — max failure probability propagated from ancestors
   with depth-based decay (``failure_prob * 0.8 ** depth``).
3. **cascade_risk** — the blast radius: how many downstream models
   would be affected, weighted by the model's own failure probability.

The scorer is fully deterministic: sorted traversals ensure reproducible
output for the same DAG and prediction inputs.

INVARIANT: This engine **never** mutates plans.  It only returns
advisory metadata.
"""

from __future__ import annotations

import logging
from collections import deque

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class FragilityScore(BaseModel):
    """Fragility analysis for a single model."""

    model_name: str = Field(..., description="Model being scored.")
    own_risk: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model's own failure probability.",
    )
    upstream_risk: float = Field(
        default=0.0,
        ge=0.0,
        description="Max decayed failure probability from ancestors.",
    )
    cascade_risk: float = Field(
        default=0.0,
        ge=0.0,
        description="Downstream count × own failure probability.",
    )
    fragility_score: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="Composite fragility score (0-10).",
    )
    critical_path: bool = Field(
        default=False,
        description="True if model sits on a path where all nodes have failure_prob > 0.3.",
    )
    risk_factors: list[str] = Field(
        default_factory=list,
        description="Human-readable contributing factors.",
    )


class FragilityScorer:
    """Compute graph-weighted fragility scores.

    The scorer is fully deterministic and stateless.

    Parameters
    ----------
    own_weight:
        Weight for the model's own risk in the composite score.
    upstream_weight:
        Weight for upstream propagation risk.
    cascade_weight:
        Weight for downstream cascade risk.
    """

    def __init__(
        self,
        own_weight: float = 0.4,
        upstream_weight: float = 0.3,
        cascade_weight: float = 0.3,
    ) -> None:
        self._w_own = own_weight
        self._w_upstream = upstream_weight
        self._w_cascade = cascade_weight

    def compute_fragility(
        self,
        model_name: str,
        dag: dict[str, list[str]],
        failure_predictions: dict[str, float],
    ) -> FragilityScore:
        """Compute the fragility score for a single model.

        Parameters
        ----------
        model_name:
            Target model to evaluate.
        dag:
            Adjacency list mapping ``model_name -> [upstream_dep, ...]``.
        failure_predictions:
            Mapping of ``model_name -> failure_probability`` (0.0-1.0).
        """
        own_prob = failure_predictions.get(model_name, 0.0)
        factors: list[str] = []

        # --- Own risk ---
        if own_prob > 0.0:
            factors.append(f"Own failure probability: {own_prob:.3f}")

        # --- Upstream risk (BFS with depth decay) ---
        upstream_risk = self._compute_upstream_risk(model_name, dag, failure_predictions)
        if upstream_risk > 0.0:
            factors.append(f"Max upstream propagated risk: {upstream_risk:.3f}")

        # --- Cascade risk (downstream count × own probability) ---
        reverse_dag = self._build_reverse_dag(dag)
        downstream = self._get_all_downstream(model_name, reverse_dag)
        cascade_raw = len(downstream) * own_prob
        if cascade_raw > 0.0:
            factors.append(f"Cascade: {len(downstream)} downstream × {own_prob:.3f} = {cascade_raw:.3f}")

        # --- Composite score ---
        # Normalise cascade to 0-1 range.
        max_cascade = max(len(dag), 1)
        cascade_normalised = min(cascade_raw / max_cascade, 1.0)

        raw_score = (
            self._w_own * own_prob + self._w_upstream * min(upstream_risk, 1.0) + self._w_cascade * cascade_normalised
        )
        fragility = round(min(raw_score * 10.0, 10.0), 2)

        # --- Critical path detection ---
        critical = self._is_on_critical_path(model_name, dag, failure_predictions, threshold=0.3)
        if critical:
            factors.append("Model sits on a critical path (all ancestors > 0.3)")

        return FragilityScore(
            model_name=model_name,
            own_risk=round(own_prob, 4),
            upstream_risk=round(upstream_risk, 4),
            cascade_risk=round(cascade_raw, 4),
            fragility_score=fragility,
            critical_path=critical,
            risk_factors=factors,
        )

    def compute_batch(
        self,
        dag: dict[str, list[str]],
        failure_predictions: dict[str, float],
    ) -> list[FragilityScore]:
        """Compute fragility scores for all models, sorted descending.

        Parameters
        ----------
        dag:
            Adjacency list mapping ``model_name -> [upstream_dep, ...]``.
        failure_predictions:
            Mapping of ``model_name -> failure_probability``.
        """
        scores = [self.compute_fragility(name, dag, failure_predictions) for name in sorted(dag.keys())]
        scores.sort(key=lambda s: s.fragility_score, reverse=True)
        return scores

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_upstream_risk(
        model_name: str,
        dag: dict[str, list[str]],
        predictions: dict[str, float],
    ) -> float:
        """BFS upstream, computing max(failure_prob × 0.8^depth)."""
        max_risk = 0.0
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()

        for parent in sorted(dag.get(model_name, [])):
            queue.append((parent, 1))

        while queue:
            node, depth = queue.popleft()
            if node in visited:
                continue
            visited.add(node)

            prob = predictions.get(node, 0.0)
            decayed = prob * (0.8**depth)
            max_risk = max(max_risk, decayed)

            for grandparent in sorted(dag.get(node, [])):
                if grandparent not in visited:
                    queue.append((grandparent, depth + 1))

        return max_risk

    @staticmethod
    def _build_reverse_dag(
        dag: dict[str, list[str]],
    ) -> dict[str, list[str]]:
        """Build a reverse adjacency list (parent → children)."""
        reverse: dict[str, list[str]] = {name: [] for name in dag}
        for child, parents in dag.items():
            for parent in parents:
                if parent not in reverse:
                    reverse[parent] = []
                reverse[parent].append(child)
        return reverse

    @staticmethod
    def _get_all_downstream(
        model_name: str,
        reverse_dag: dict[str, list[str]],
    ) -> set[str]:
        """BFS downstream from model_name."""
        visited: set[str] = set()
        queue: deque[str] = deque(sorted(reverse_dag.get(model_name, [])))

        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            for child in sorted(reverse_dag.get(node, [])):
                if child not in visited:
                    queue.append(child)

        return visited

    @staticmethod
    def _is_on_critical_path(
        model_name: str,
        dag: dict[str, list[str]],
        predictions: dict[str, float],
        threshold: float = 0.3,
    ) -> bool:
        """True if model_name's own prob > threshold AND all ancestors > threshold."""
        own_prob = predictions.get(model_name, 0.0)
        if own_prob <= threshold:
            return False

        # Check all ancestors.
        visited: set[str] = set()
        queue: deque[str] = deque(sorted(dag.get(model_name, [])))

        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)

            if predictions.get(node, 0.0) <= threshold:
                return False

            for parent in sorted(dag.get(node, [])):
                if parent not in visited:
                    queue.append(parent)

        return True  # all ancestors (if any) above threshold
