# IronLayer CLI

AI-native Databricks transformation control plane. Plan, validate, and apply SQL model changes with deterministic execution and optional AI-powered risk analysis.

## Installation

```bash
pip install ironlayer
```

Requires Python 3.11+.

## Quick Start

```bash
# Initialize a project
ironlayer init

# List discovered models
ironlayer models ./my-repo

# Generate an execution plan from git changes
ironlayer plan ./my-repo main feature-branch

# Apply a plan
ironlayer apply plan.json --repo ./my-repo

# View model lineage
ironlayer lineage ./my-repo
```

## Cloud Features

Connect to IronLayer Cloud for AI-powered cost estimation, risk scoring, and team collaboration:

```bash
ironlayer login
```

## License

Apache License 2.0 -- see [LICENSE](LICENSE) for details.
