---
name: exodus-agent-create
description: >
  Scaffold a new Autopilot agent from scratch. Generates agent class, MCP tool wrapper,
  unit tests, and registration. Use when adding a new autonomous capability to the Autopilot
  fleet, expanding an existing agent, or creating a specialist for a new data domain.
triggers:
  - "create a new agent"
  - "add an agent"
  - "scaffold an agent"
  - "new autopilot agent"
  - "build an agent for"
outputs:
  - "autopilot/agents/{name}/agent.py"
  - "autopilot/agents/{name}/__init__.py"
  - "autopilot/mcp/tools/autopilot.py (updated)"
  - "tests/agents/test_{name}.py"
---

# Exodus Agent Create — Cursor Skill

> Scaffold a new Autopilot agent following PEVR loop contract.
> Read `autopilot/agents/base.py` and one existing agent before generating code.

---

## Step 1 — Read Existing Code First

```bash
# Base class — understand what you inherit
cat autopilot/agents/base.py | head -150

# Read the closest existing agent end-to-end
cat autopilot/agents/code_reviewer/agent.py
# or
cat autopilot/agents/backlog/agent.py

# Understand how MCP tools wrap agents
cat autopilot/mcp/tools/autopilot.py
```

**Never generate code before reading these. Pattern consistency matters.**

---

## Step 2 — Design Questionnaire

Answer these before writing code:

1. **What is the agent's single responsibility?** (One sentence. Not a list.)
2. **What is the PLAN phase doing?** (LLM constructs a plan. What format?)
3. **What is the EXECUTE phase doing?** (Deterministic. No LLM. What APIs?)
4. **What does VERIFY check?** (Pass/fail criteria. What evidence is required?)
5. **Which tier does it belong to?** (starter / professional / enterprise)
6. **Which MCP tool(s) expose it?** (One tool minimum)
7. **What model tier does it use?** (haiku for classification, sonnet for analysis, opus for architecture)

---

## Step 3 — Generate Agent Class

```python
# autopilot/agents/{name}/agent.py
"""
{AgentName} — {one-line description}.

Responsibility: {what this agent does and owns}
Tier: {starter | professional | enterprise}
PEVR contract:
  plan()    — {what the LLM plans}
  execute() — {what deterministic actions happen}
  verify()  — {what pass/fail criteria are checked}
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from autopilot.agents.base import AutopilotAgent, AgentPlan, AgentResult


@dataclass
class {AgentName}Plan(AgentPlan):
    """Structured plan produced by {AgentName}."""
    {plan_field_1}: str = ""
    {plan_field_2}: list[str] = field(default_factory=list)


@dataclass
class {AgentName}Result(AgentResult):
    """Results from {AgentName} execution."""
    {result_field_1}: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)


class {AgentName}Agent(AutopilotAgent):
    """{One-line description}."""

    AGENT_NAME = "{AgentName}"
    AGENT_DESCRIPTION = "{Brief description of what this agent does}"
    DEFAULT_MODEL = "claude-sonnet"  # tier alias — never hard-code model IDs
    MAX_TOKENS = 4096
    TIER = "starter"                 # "starter" | "professional" | "enterprise"

    def plan(self, task: str) -> {AgentName}Plan:
        """Generate a human-readable plan for the task.

        LLM call is here — produces structured plan for the approval gate.
        """
        prompt = f"""You are {self.AGENT_NAME}.
Task: {task}

Produce a plan with these fields:
- {plan_field_1}: ...
- {plan_field_2}: list of steps

Return JSON only."""

        response = self._call_claude(prompt)
        parsed = self._parse_json(response)
        return {AgentName}Plan(
            task=task,
            {plan_field_1}=parsed.get("{plan_field_1}", ""),
            {plan_field_2}=parsed.get("{plan_field_2}", []),
        )

    def execute(self, plan: {AgentName}Plan) -> {AgentName}Result:
        """Execute the plan deterministically. No LLM calls here.

        Uses: {list APIs/tools used — gh CLI, Databricks SDK, GitHub API, etc.}
        """
        results: dict[str, Any] = {}
        evidence: list[str] = []

        for step in plan.{plan_field_2}:
            # Deterministic execution
            result = self._run_step(step)
            results[step] = result
            if result.get("status") == "success":
                evidence.append(f"Step '{step}' succeeded: {result.get('summary')}")

        return {AgentName}Result(
            success=len(evidence) > 0,
            summary=f"Completed {len(evidence)}/{len(plan.{plan_field_2})} steps",
            {result_field_1}=results,
            evidence=evidence,
        )

    def verify(self, result: {AgentName}Result) -> bool:
        """Verify that execution met acceptance criteria.

        Returns True only if: {describe pass criteria precisely}
        """
        if not result.success:
            return False
        # Add specific verification logic
        return len(result.evidence) > 0

    def _run_step(self, step: str) -> dict[str, Any]:
        """Execute a single plan step."""
        # TODO: implement
        return {"status": "success", "summary": f"Ran: {step}"}
```

---

## Step 4 — Register in `__init__.py`

```python
# autopilot/agents/{name}/__init__.py
from autopilot.agents.{name}.agent import {AgentName}Agent

__all__ = ["{AgentName}Agent"]
```

```python
# autopilot/agents/__init__.py — add to existing file
from autopilot.agents.{name} import {AgentName}Agent
```

---

## Step 5 — MCP Tool Wrapper

```python
# autopilot/mcp/tools/autopilot.py — add to existing router

@router.tool()
async def autopilot_{action}(
    task: str,
    {additional_param}: str | None = None,
) -> dict:
    """Run {AgentName} for a specific task.

    Args:
        task: Description of what the agent should do
        {additional_param}: Optional {description}

    Returns:
        Agent result with success status, summary, and evidence
    """
    try:
        from autopilot.agents.{name} import {AgentName}Agent
        agent = {AgentName}Agent()
        plan = agent.plan(task)
        result = agent.execute(plan)
        agent.verify(result)
        return {
            "status": "success" if result.success else "failure",
            "summary": result.summary,
            "evidence": result.evidence,
            "confidence": result.confidence,
        }
    except ImportError as e:
        return {"status": "error", "error": str(e)}
```

---

## Step 6 — Unit Tests

```python
# tests/agents/test_{name}.py
import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def mock_claude():
    with patch("autopilot.agents.base.Anthropic") as mock:
        client = Mock()
        client.messages.create.return_value = Mock(
            content=[Mock(text='{"plan_field_1": "test", "plan_field_2": ["step1"]}')],
            usage=Mock(input_tokens=100, output_tokens=50),
        )
        mock.return_value = client
        yield client


class TestPlan:
    def test_plan_returns_agent_plan(self, mock_claude):
        from autopilot.agents.{name}.agent import {AgentName}Agent
        agent = {AgentName}Agent()
        plan = agent.plan("test task")
        assert plan.task == "test task"
        assert mock_claude.messages.create.called

    def test_plan_has_required_fields(self, mock_claude):
        from autopilot.agents.{name}.agent import {AgentName}Agent
        agent = {AgentName}Agent()
        plan = agent.plan("test task")
        assert isinstance(plan.{plan_field_2}, list)


class TestExecute:
    def test_execute_returns_result(self, mock_claude):
        from autopilot.agents.{name}.agent import {AgentName}Agent, {AgentName}Plan
        agent = {AgentName}Agent()
        plan = {AgentName}Plan(task="test", {plan_field_2}=["step1"])
        result = agent.execute(plan)
        assert isinstance(result.success, bool)
        assert isinstance(result.summary, str)

    def test_no_llm_in_execute(self, mock_claude):
        """Execute must not call Claude — PEVR contract."""
        from autopilot.agents.{name}.agent import {AgentName}Agent, {AgentName}Plan
        agent = {AgentName}Agent()
        plan = {AgentName}Plan(task="test", {plan_field_2}=[])
        mock_claude.messages.create.reset_mock()
        agent.execute(plan)
        mock_claude.messages.create.assert_not_called()  # deterministic!


class TestVerify:
    def test_verify_passes_on_success(self, mock_claude):
        from autopilot.agents.{name}.agent import {AgentName}Agent, {AgentName}Result
        agent = {AgentName}Agent()
        result = {AgentName}Result(success=True, summary="done", evidence=["step1 ok"])
        assert agent.verify(result) is True

    def test_verify_fails_on_failure(self, mock_claude):
        from autopilot.agents.{name}.agent import {AgentName}Agent, {AgentName}Result
        agent = {AgentName}Agent()
        result = {AgentName}Result(success=False, summary="failed", evidence=[])
        assert agent.verify(result) is False
```

---

## Step 7 — Verify

```bash
# Tests pass
uv run pytest tests/agents/test_{name}.py -v

# Type checking
uv run mypy autopilot/agents/{name}/agent.py

# Linting
uv run ruff check autopilot/agents/{name}/

# MCP server loads without import error
uv run python -c "from autopilot.mcp.server import create_server; s = create_server(); print('OK')"

# New tool appears in tool list
uv run python -m autopilot.mcp.server --list-tools | grep autopilot_{action}
```

---

## Circuit Breaker Configuration

Agents auto-get a circuit breaker from `AutopilotAgent`. Configure in class:

```python
CIRCUIT_BREAKER_THRESHOLD = 3   # failures before OPEN
CIRCUIT_BREAKER_TIMEOUT = 300   # seconds in OPEN before HALF_OPEN probe
```

For high-risk agents (PR healing, auto-merge gating), set lower threshold.
