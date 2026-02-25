"""Performance benchmarking tools for IronLayer core engine.

Provides synthetic graph generators for creating DAGs of configurable size
and shape, plus a profiler that measures execution time and memory usage
of core operations (DAG build, plan generation, SQL normalisation, etc.).

All generators are deterministic -- same inputs produce identical outputs.
"""

from __future__ import annotations

from core_engine.benchmarks.graph_generator import SyntheticGraphGenerator
from core_engine.benchmarks.profiler import BenchmarkProfiler, BenchmarkResult

__all__ = [
    "SyntheticGraphGenerator",
    "BenchmarkProfiler",
    "BenchmarkResult",
]
