"""Deterministic serialization and validation for execution plans.

Ensures that a :class:`Plan` can be round-tripped through JSON without
information loss and that the serialised form is byte-identical for identical
inputs (sorted keys, stable indentation).
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from core_engine.models.plan import Plan


def serialize_plan(plan: Plan) -> str:
    """Serialize a plan to a deterministic JSON string.

    The output uses sorted keys and 2-space indentation so that identical plans
    always produce byte-identical JSON.  This is critical for content-addressed
    caching and audit trails.

    Parameters
    ----------
    plan:
        The plan to serialize.

    Returns
    -------
    str
        A pretty-printed JSON string with sorted keys.
    """
    # Pydantic's ``model_dump_json`` does not support ``sort_keys``, so we
    # round-trip through a Python dict first to leverage ``json.dumps`` with
    # ``sort_keys=True``.
    raw = plan.model_dump(mode="json")
    return json.dumps(raw, indent=2, sort_keys=True, ensure_ascii=False)


def deserialize_plan(json_str: str) -> Plan:
    """Deserialize a JSON string into a :class:`Plan` instance.

    Parameters
    ----------
    json_str:
        A JSON string previously produced by :func:`serialize_plan` (or any
        JSON representation that conforms to the Plan schema).

    Returns
    -------
    Plan
        The hydrated plan object.

    Raises
    ------
    pydantic.ValidationError
        If the JSON does not conform to the Plan schema.
    ValueError
        If the string is not valid JSON.
    """
    return Plan.model_validate_json(json_str)


def validate_plan_schema(json_str: str) -> list[str]:
    """Validate a JSON string against the Plan schema without raising.

    Parameters
    ----------
    json_str:
        A JSON string to validate.

    Returns
    -------
    list[str]
        A list of human-readable validation error messages.  An empty list
        indicates the JSON is valid and conforms to the Plan schema.
    """
    try:
        Plan.model_validate_json(json_str)
    except ValidationError as exc:
        return [
            f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" if err.get("loc") else err["msg"]
            for err in exc.errors()
        ]
    except (ValueError, TypeError) as exc:
        return [f"Invalid JSON: {exc}"]

    return []
