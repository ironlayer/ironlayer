"""Unit tests for the IronLayer plan PR comment formatter."""
from __future__ import annotations

import json

import pytest

from format_comment import (
    _aggregate_column_counts,
    _build_impact_graph,
    _column_summary_cell,
    _compute_risk,
    format_empty,
    format_failed,
    format_success,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_step(
    model: str = "staging.stg_orders",
    run_type: str = "FULL_REFRESH",
    reason: str = "SQL logic changed",
    cost: float = 0.21,
    step_id: str = "abc123",
    depends_on: list[str] | None = None,
    contract_violations: list[dict] | None = None,
    diff_detail: dict | None = None,
) -> dict:
    return {
        "step_id": step_id,
        "model": model,
        "run_type": run_type,
        "reason": reason,
        "estimated_cost_usd": cost,
        "depends_on": depends_on or [],
        "parallel_group": 0,
        "contract_violations": contract_violations or [],
        "diff_detail": diff_detail,
    }


def _make_plan(
    steps: list[dict] | None = None,
    cosmetic_skipped: list[str] | None = None,
    breaking_count: int = 0,
) -> dict:
    steps = steps or []
    total_cost = sum(s.get("estimated_cost_usd", 0) for s in steps)
    models = [s["model"] for s in steps]
    violations_count = sum(len(s.get("contract_violations", [])) for s in steps)
    return {
        "plan_id": "deadbeef" * 8,
        "base": "base-sha",
        "target": "target-sha",
        "summary": {
            "total_steps": len(steps),
            "estimated_cost_usd": total_cost,
            "models_changed": models,
            "cosmetic_changes_skipped": cosmetic_skipped or [],
            "contract_violations_count": violations_count,
            "breaking_contract_violations": breaking_count,
        },
        "steps": steps,
    }


BASE_SHA = "abc123def456"
HEAD_SHA = "789012fed345"


# ---------------------------------------------------------------------------
# format_empty
# ---------------------------------------------------------------------------


class TestFormatEmpty:
    def test_contains_no_changes_message(self) -> None:
        md = format_empty(BASE_SHA, HEAD_SHA)
        assert "No model changes detected" in md
        assert "Nothing to execute" in md

    def test_contains_sha_refs(self) -> None:
        md = format_empty(BASE_SHA, HEAD_SHA)
        assert BASE_SHA[:12] in md
        assert HEAD_SHA[:12] in md

    def test_contains_footer(self) -> None:
        md = format_empty(BASE_SHA, HEAD_SHA)
        assert "IronLayer" in md


# ---------------------------------------------------------------------------
# format_failed
# ---------------------------------------------------------------------------


class TestFormatFailed:
    def test_shows_failure_message(self) -> None:
        md = format_failed("something broke", BASE_SHA, HEAD_SHA)
        assert "Plan generation failed" in md
        assert "something broke" in md

    def test_empty_error_no_details(self) -> None:
        md = format_failed("", BASE_SHA, HEAD_SHA)
        assert "Plan generation failed" in md
        assert "<details>" not in md

    def test_error_in_collapsible(self) -> None:
        md = format_failed("ValueError: bad input", BASE_SHA, HEAD_SHA)
        assert "<details>" in md
        assert "ValueError: bad input" in md


# ---------------------------------------------------------------------------
# format_success - basic (no diff_detail)
# ---------------------------------------------------------------------------


class TestFormatSuccessBasic:
    def test_basic_steps_table(self) -> None:
        plan = _make_plan(steps=[_make_step()])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "Execution Steps" in md
        assert "`staging.stg_orders`" in md
        assert "FULL_REFRESH" in md
        assert "$0.21" in md

    def test_header_contains_step_count(self) -> None:
        plan = _make_plan(steps=[_make_step(), _make_step(model="analytics.orders_daily", step_id="def456")])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "2 steps" in md

    def test_singular_step(self) -> None:
        plan = _make_plan(steps=[_make_step()])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "1 step" in md

    def test_plan_id_in_footer(self) -> None:
        plan = _make_plan(steps=[_make_step()])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "Plan ID:" in md
        assert "deadbeef" in md

    def test_full_plan_json_collapsible(self) -> None:
        plan = _make_plan(steps=[_make_step()])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "Full plan JSON" in md
        assert "```json" in md


# ---------------------------------------------------------------------------
# format_success - with diff_detail
# ---------------------------------------------------------------------------


class TestFormatSuccessWithDiffDetail:
    def test_column_changes_section_rendered(self) -> None:
        step = _make_step(diff_detail={
            "change_type": "MODIFIED",
            "columns_added": ["customer_segment", "order_priority"],
            "columns_removed": [],
            "columns_modified": ["total_amount"],
        })
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "Column Changes" in md
        assert "`customer_segment`" in md
        assert "`order_priority`" in md
        assert "`total_amount`" in md
        assert "expression changed" in md

    def test_removed_columns_shown(self) -> None:
        step = _make_step(diff_detail={
            "change_type": "MODIFIED",
            "columns_added": [],
            "columns_removed": ["legacy_flag"],
            "columns_modified": [],
        })
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "`legacy_flag`" in md

    def test_impact_summary_column_counts(self) -> None:
        step1 = _make_step(diff_detail={
            "change_type": "MODIFIED",
            "columns_added": ["a", "b"],
            "columns_removed": ["c"],
            "columns_modified": ["d"],
        })
        step2 = _make_step(
            model="analytics.orders_daily",
            step_id="def456",
            diff_detail={
                "change_type": "MODIFIED",
                "columns_added": ["e"],
                "columns_removed": [],
                "columns_modified": [],
            },
        )
        plan = _make_plan(steps=[step1, step2])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "+3 added" in md
        assert "-1 removed" in md
        assert "~1 modified" in md

    def test_column_summary_in_step_table(self) -> None:
        step = _make_step(diff_detail={
            "change_type": "MODIFIED",
            "columns_added": ["a", "b"],
            "columns_removed": [],
            "columns_modified": ["c"],
        })
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "+2 ~1" in md

    def test_no_column_changes_section_without_diff_detail(self) -> None:
        step = _make_step()  # no diff_detail
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "Column Changes" not in md


# ---------------------------------------------------------------------------
# format_success - with advisory
# ---------------------------------------------------------------------------


class TestFormatSuccessWithAdvisory:
    def test_advisory_section_rendered(self) -> None:
        step = _make_step()
        plan = _make_plan(steps=[step])
        advisory = {
            "risk_score": 3,
            "risk_label": "low",
            "category": "schema_evolution",
            "review_notes": ["Column change is safe."],
            "estimated_cost_usd": 0.21,
        }
        md = format_success(plan, BASE_SHA, HEAD_SHA, advisory=advisory)
        assert "AI Advisory" in md
        assert "3/10" in md
        assert "Schema Evolution" in md
        assert "Column change is safe." in md

    def test_no_advisory_section_without_data(self) -> None:
        step = _make_step()
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA, advisory=None)
        assert "AI Advisory" not in md

    def test_empty_advisory_dict_no_section(self) -> None:
        step = _make_step()
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA, advisory={})
        assert "AI Advisory" not in md


# ---------------------------------------------------------------------------
# Risk badge
# ---------------------------------------------------------------------------


class TestRiskBadge:
    def test_breaking_violations_high_risk(self) -> None:
        step = _make_step(contract_violations=[
            {"column_name": "id", "violation_type": "TYPE_CHANGE", "severity": "BREAKING", "message": "bad"},
        ])
        plan = _make_plan(steps=[step], breaking_count=1)
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "high risk" in md
        assert ":red_circle:" in md

    def test_removed_columns_review(self) -> None:
        step = _make_step(diff_detail={
            "change_type": "MODIFIED",
            "columns_added": [],
            "columns_removed": ["old_col"],
            "columns_modified": [],
        })
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "review" in md
        assert ":yellow_circle:" in md

    def test_advisory_high_risk_review(self) -> None:
        step = _make_step()
        plan = _make_plan(steps=[step])
        advisory = {"risk_score": 8}
        md = format_success(plan, BASE_SHA, HEAD_SHA, advisory=advisory)
        assert "review" in md

    def test_low_risk_default(self) -> None:
        step = _make_step()
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "low risk" in md
        assert ":green_circle:" in md


# ---------------------------------------------------------------------------
# Impact graph
# ---------------------------------------------------------------------------


class TestImpactGraph:
    def test_graph_rendered_for_multi_step(self) -> None:
        step1 = _make_step(step_id="s1", model="staging.stg_orders")
        step2 = _make_step(
            step_id="s2",
            model="analytics.orders_daily",
            reason="downstream of staging.stg_orders",
            depends_on=["s1"],
        )
        plan = _make_plan(steps=[step1, step2])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "Impact Graph" in md
        assert "staging.stg_orders" in md
        assert "analytics.orders_daily" in md

    def test_no_graph_for_single_step(self) -> None:
        step = _make_step()
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "Impact Graph" not in md

    def test_graph_labels(self) -> None:
        step1 = _make_step(step_id="s1", reason="SQL logic changed")
        step2 = _make_step(
            step_id="s2",
            model="analytics.orders_daily",
            reason="downstream of staging.stg_orders",
            depends_on=["s1"],
        )
        lines = _build_impact_graph([step1, step2])
        graph_text = "\n".join(lines)
        assert "CHANGED" in graph_text
        assert "DOWNSTREAM" in graph_text


# ---------------------------------------------------------------------------
# Contract violations
# ---------------------------------------------------------------------------


class TestContractViolations:
    def test_violations_collapsible(self) -> None:
        step = _make_step(contract_violations=[
            {
                "column_name": "amount",
                "violation_type": "NOT_NULL",
                "severity": "WARNING",
                "message": "Column may contain nulls",
            },
        ])
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "Contract Violations (1)" in md
        assert "`amount`" in md
        assert "NOT_NULL" in md

    def test_no_violations_no_section(self) -> None:
        step = _make_step()
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "Contract Violations" not in md


# ---------------------------------------------------------------------------
# Cosmetic changes
# ---------------------------------------------------------------------------


class TestCosmeticChanges:
    def test_cosmetic_skipped_collapsible(self) -> None:
        step = _make_step()
        plan = _make_plan(steps=[step], cosmetic_skipped=["raw.events"])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "Cosmetic changes skipped" in md
        assert "`raw.events`" in md

    def test_no_cosmetic_no_section(self) -> None:
        step = _make_step()
        plan = _make_plan(steps=[step])
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "Cosmetic changes skipped" not in md


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_plan_without_diff_detail_field(self) -> None:
        """Plans generated before this feature should still render without errors."""
        plan = {
            "plan_id": "abc123",
            "base": "a",
            "target": "b",
            "summary": {
                "total_steps": 1,
                "estimated_cost_usd": 0.21,
                "models_changed": ["staging.stg_orders"],
                "cosmetic_changes_skipped": [],
                "contract_violations_count": 0,
                "breaking_contract_violations": 0,
            },
            "steps": [
                {
                    "step_id": "x",
                    "model": "staging.stg_orders",
                    "run_type": "FULL_REFRESH",
                    "reason": "SQL logic changed",
                    "estimated_cost_usd": 0.21,
                    "depends_on": [],
                    "parallel_group": 0,
                    "contract_violations": [],
                    # No diff_detail field at all.
                },
            ],
        }
        md = format_success(plan, BASE_SHA, HEAD_SHA)
        assert "IronLayer Plan" in md
        assert "`staging.stg_orders`" in md
        # Should NOT crash and should NOT show column changes section.
        assert "Column Changes" not in md


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_aggregate_column_counts(self) -> None:
        steps = [
            _make_step(diff_detail={"columns_added": ["a", "b"], "columns_removed": [], "columns_modified": ["c"]}),
            _make_step(diff_detail={"columns_added": ["d"], "columns_removed": ["e"], "columns_modified": []}),
            _make_step(),  # no diff_detail
        ]
        added, removed, modified = _aggregate_column_counts(steps)
        assert added == 3
        assert removed == 1
        assert modified == 1

    def test_column_summary_cell_empty(self) -> None:
        assert _column_summary_cell({}) == ""
        assert _column_summary_cell({"diff_detail": None}) == ""

    def test_column_summary_cell_values(self) -> None:
        step = _make_step(diff_detail={
            "columns_added": ["a", "b"],
            "columns_removed": ["c"],
            "columns_modified": [],
        })
        assert _column_summary_cell(step) == "+2 -1"

    def test_compute_risk_low(self) -> None:
        plan = _make_plan(steps=[_make_step()])
        level, emoji = _compute_risk(plan, None)
        assert level == "low risk"

    def test_compute_risk_high(self) -> None:
        plan = _make_plan(steps=[_make_step()], breaking_count=1)
        level, emoji = _compute_risk(plan, None)
        assert level == "high risk"

    def test_compute_risk_review_removed(self) -> None:
        step = _make_step(diff_detail={
            "change_type": "MODIFIED",
            "columns_added": [],
            "columns_removed": ["x"],
            "columns_modified": [],
        })
        plan = _make_plan(steps=[step])
        level, emoji = _compute_risk(plan, None)
        assert level == "review"
