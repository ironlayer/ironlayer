# IronLayer Core Engine

Deterministic SQL transformation planning and execution engine for Databricks.

## Features

- **Plan/Apply workflow** for SQL model changes with full dependency resolution
- **DAG-based execution** with topological ordering and parallel chunk execution
- **Git-aware diffing** to detect what changed between branches or commits
- **DuckDB local execution** for safe, sandboxed testing before production deployment
- **Multi-tenant** with PostgreSQL Row-Level Security

## Installation

```bash
pip install ironlayer-core
```

## Usage

This package provides the core engine used by the [IronLayer CLI](https://pypi.org/project/ironlayer/). For most users, install the CLI instead:

```bash
pip install ironlayer
```

## License

Apache License 2.0 -- see [LICENSE](LICENSE) for details.
