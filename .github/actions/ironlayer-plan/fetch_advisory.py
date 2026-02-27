"""
Fetch AI advisory metadata from the IronLayer Cloud API.

This is a standalone script (stdlib-only — no pip dependencies) that
optionally enriches a plan with AI-powered risk scoring, cost estimates,
and review notes.  It is designed to run as a GitHub Action step and
will **never** fail the workflow — if the API is unreachable or returns
an error, it writes an empty JSON object and exits with code 0.

Usage:
    python fetch_advisory.py \
        --api-url https://api.ironlayer.app \
        --api-token $IRONLAYER_API_TOKEN \
        --plan-json /path/to/plan.json \
        --output /path/to/advisory.json

Expected response shape:
    {
        "risk_score": 3,         # 0-10 integer
        "risk_label": "low",     # low | medium | high | critical
        "category": "schema_evolution",
        "review_notes": [
            "Column removal (legacy_flag) may break downstream consumers."
        ],
        "estimated_cost_usd": 0.63
    }
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def fetch_advisory(
    api_url: str,
    api_token: str,
    plan_path: Path,
) -> dict:
    """POST the plan to the advisory endpoint and return the response.

    Returns an empty dict on any error — advisory is always optional.
    """
    try:
        plan_data = json.loads(plan_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: could not read plan JSON: {exc}", file=sys.stderr)
        return {}

    url = f"{api_url.rstrip('/')}/api/v1/plan/advisory"
    payload = json.dumps(plan_data).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_token}",
            "User-Agent": "ironlayer-github-action/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        print(
            f"Warning: advisory API returned HTTP {exc.code}: {exc.reason}",
            file=sys.stderr,
        )
        return {}
    except urllib.error.URLError as exc:
        print(f"Warning: could not reach advisory API: {exc.reason}", file=sys.stderr)
        return {}
    except (json.JSONDecodeError, OSError, TimeoutError) as exc:
        print(f"Warning: advisory response error: {exc}", file=sys.stderr)
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch AI advisory from IronLayer Cloud API"
    )
    parser.add_argument(
        "--api-url",
        required=True,
        help="IronLayer Cloud API base URL.",
    )
    parser.add_argument(
        "--api-token",
        required=True,
        help="IronLayer API bearer token.",
    )
    parser.add_argument(
        "--plan-json",
        required=True,
        help="Path to the plan.json file.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the advisory JSON output.",
    )
    args = parser.parse_args()

    advisory = fetch_advisory(
        api_url=args.api_url,
        api_token=args.api_token,
        plan_path=Path(args.plan_json),
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(advisory, indent=2))

    if advisory:
        print(f"Advisory fetched: risk_score={advisory.get('risk_score', '?')}")
    else:
        print("No advisory data available (API unreachable or not configured).")


if __name__ == "__main__":
    main()
