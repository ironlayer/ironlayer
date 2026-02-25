"""DAG construction and graph operations using NetworkX.

This module builds a directed acyclic graph (DAG) from a collection of
:class:`~core_engine.models.model_definition.ModelDefinition` objects,
provides topological ordering, upstream/downstream traversal, parallel
group assignment for execution scheduling, cycle detection, and DAG
validation against a known set of models.
"""

from __future__ import annotations

import heapq
import logging
from collections import deque

import networkx as nx

from core_engine.models.model_definition import ModelDefinition
from core_engine.telemetry.profiling import profile_operation

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CyclicDependencyError(Exception):
    """Raised when the dependency graph contains one or more cycles.

    Attributes
    ----------
    cycles:
        A list of cycles, where each cycle is a list of model names
        forming the loop (e.g. ``[["a", "b", "c"]]`` means a -> b -> c -> a).
    """

    def __init__(self, cycles: list[list[str]]) -> None:
        self.cycles = cycles
        formatted = "; ".join(" -> ".join(c + [c[0]]) for c in cycles)
        super().__init__(f"Cyclic dependencies detected: {formatted}")


# ---------------------------------------------------------------------------
# DAG construction
# ---------------------------------------------------------------------------


@profile_operation("dag.build")
def build_dag(models: list[ModelDefinition]) -> nx.DiGraph:
    """Build a directed graph from a list of model definitions.

    Each model becomes a node keyed by its ``name``.  Directed edges
    point **from** a dependency **to** the model that depends on it
    (i.e. ``dependency -> model``), encoding the constraint that the
    dependency must be materialised before the dependent.

    Edges are derived from two sources:

    1. ``model.referenced_tables`` -- tables discovered via SQL parsing.
    2. ``model.dependencies`` -- explicit upstream dependencies declared
       in the model header.

    Node data includes the full :class:`ModelDefinition` under key
    ``"model"``.

    Parameters
    ----------
    models:
        Model definitions to include in the graph.

    Returns
    -------
    nx.DiGraph
        A directed graph suitable for topological traversal.
    """
    dag = nx.DiGraph()
    model_names: set[str] = {m.name for m in models}

    # Add all models as nodes first so that even source models with no
    # inbound edges are represented.
    for model in models:
        dag.add_node(model.name, model=model)

    for model in models:
        # Collect all upstream names from both parsed tables and explicit deps.
        upstream_names: set[str] = set()
        for table_ref in model.referenced_tables:
            upstream_names.add(table_ref)
        for dep in model.dependencies:
            upstream_names.add(dep)

        for upstream in upstream_names:
            # Only add edges to models that exist in the graph.  External
            # source tables (not managed by IronLayer) are silently skipped
            # -- use :func:`validate_dag` to surface warnings about them.
            if upstream in model_names and upstream != model.name:
                dag.add_edge(upstream, model.name)

    return dag


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------


def _lexicographic_topological_sort(graph: nx.DiGraph) -> list[str]:
    """Stable topological sort with lexicographic tie-breaking.

    Replaces ``nx.lexicographic_topological_sort`` which was removed in
    NetworkX 3.4+.  Uses Kahn's algorithm with a min-heap so that among
    nodes with no ordering constraint the result is sorted alphabetically,
    ensuring reproducible plans across runs.
    """
    in_degree = dict(graph.in_degree())
    heap = sorted(n for n, d in in_degree.items() if d == 0)
    heapq.heapify(heap)
    result: list[str] = []
    while heap:
        node = heapq.heappop(heap)
        result.append(node)
        for successor in sorted(graph.successors(node)):
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                heapq.heappush(heap, successor)
    if len(result) != len(graph):
        raise nx.NetworkXUnfeasible("Graph contains a cycle")
    return result


@profile_operation("dag.topo_sort")
def topological_sort(dag: nx.DiGraph) -> list[str]:
    """Return a deterministic topological ordering of models in the DAG.

    Uses *lexicographic* topological sort so that among nodes with no
    ordering constraint the result is sorted alphabetically, ensuring
    reproducible plans across runs.

    Parameters
    ----------
    dag:
        A directed graph built by :func:`build_dag`.

    Returns
    -------
    list[str]
        Model names in topological (execution) order.

    Raises
    ------
    CyclicDependencyError
        If the graph contains one or more cycles.
    """
    try:
        return _lexicographic_topological_sort(dag)
    except nx.NetworkXUnfeasible:
        cycles = list(nx.simple_cycles(dag))
        raise CyclicDependencyError(cycles) from None


# ---------------------------------------------------------------------------
# Traversal helpers
# ---------------------------------------------------------------------------


def get_downstream(dag: nx.DiGraph, model_name: str) -> set[str]:
    """Return all models transitively downstream of *model_name*.

    Performs a breadth-first traversal following successor edges.  The
    *model_name* itself is **not** included in the result set.

    Parameters
    ----------
    dag:
        A directed graph built by :func:`build_dag`.
    model_name:
        The starting node.

    Returns
    -------
    set[str]
        Names of all transitively downstream models.
    """
    if model_name not in dag:
        return set()

    visited: set[str] = set()
    queue: deque[str] = deque(dag.successors(model_name))

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(dag.successors(current))

    return visited


def get_upstream(dag: nx.DiGraph, model_name: str) -> set[str]:
    """Return all models transitively upstream of *model_name*.

    Performs a breadth-first traversal following predecessor edges.  The
    *model_name* itself is **not** included in the result set.

    Parameters
    ----------
    dag:
        A directed graph built by :func:`build_dag`.
    model_name:
        The starting node.

    Returns
    -------
    set[str]
        Names of all transitively upstream models.
    """
    if model_name not in dag:
        return set()

    visited: set[str] = set()
    queue: deque[str] = deque(dag.predecessors(model_name))

    while queue:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        queue.extend(dag.predecessors(current))

    return visited


# ---------------------------------------------------------------------------
# Parallel group assignment
# ---------------------------------------------------------------------------


def assign_parallel_groups(
    dag: nx.DiGraph,
    models_to_run: list[str],
) -> dict[str, int]:
    """Assign parallel execution groups to a subset of models.

    Within each group, models have no inter-dependencies and may execute
    concurrently.  Group numbers start at **1**.

    The algorithm computes the *longest-path depth* for each node in the
    subgraph induced by *models_to_run*.  Nodes at the same depth share
    a group number.

    Parameters
    ----------
    dag:
        The full directed graph built by :func:`build_dag`.
    models_to_run:
        Subset of model names that need to be executed.

    Returns
    -------
    dict[str, int]
        Mapping of model name to parallel group number (1-based).
    """
    run_set = set(models_to_run)
    if not run_set:
        return {}

    # Induce a subgraph containing only the models we need to run.
    subgraph = dag.subgraph(run_set).copy()

    # Compute the longest path depth for each node.  Roots (no
    # predecessors within the subgraph) start at depth 0.
    depth: dict[str, int] = {}

    try:
        order = _lexicographic_topological_sort(subgraph)
    except nx.NetworkXUnfeasible:
        cycles = list(nx.simple_cycles(subgraph))
        raise CyclicDependencyError(cycles) from None

    for node in order:
        preds = list(subgraph.predecessors(node))
        if not preds:
            depth[node] = 0
        else:
            depth[node] = max(depth[pred] for pred in preds) + 1

    # Convert 0-indexed depth to 1-indexed group.
    return {node: d + 1 for node, d in depth.items()}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def detect_cycles(dag: nx.DiGraph) -> list[list[str]]:
    """Detect cycles in the DAG and raise if any are found.

    Parameters
    ----------
    dag:
        A directed graph built by :func:`build_dag`.

    Returns
    -------
    list[list[str]]
        A list of cycles (each cycle is a list of node names).

    Raises
    ------
    CyclicDependencyError
        If one or more cycles are detected.
    """
    cycles = list(nx.simple_cycles(dag))
    if cycles:
        raise CyclicDependencyError(cycles)
    return cycles


def validate_dag(dag: nx.DiGraph, known_models: set[str]) -> list[str]:
    """Validate the DAG against a set of known model names.

    Checks every upstream reference reachable via edges to ensure the
    target node exists in *known_models*.  References to external tables
    (not managed by IronLayer) produce warnings but do not cause failure.

    Parameters
    ----------
    dag:
        A directed graph built by :func:`build_dag`.
    known_models:
        The complete set of model names that IronLayer manages.

    Returns
    -------
    list[str]
        Warning messages for any references to unknown models.  An empty
        list means the DAG is fully valid.
    """
    warnings: list[str] = []

    for node in dag.nodes:
        model_def: ModelDefinition | None = dag.nodes[node].get("model")
        if model_def is None:
            continue

        # Check all declared upstream dependencies.
        all_upstream_refs: set[str] = set(model_def.referenced_tables) | set(model_def.dependencies)
        for ref in sorted(all_upstream_refs):
            if ref not in known_models and ref not in dag.nodes:
                warnings.append(
                    f"Model '{node}' references '{ref}' which is not a known "
                    f"managed model. It may be an external source table."
                )

    return warnings
