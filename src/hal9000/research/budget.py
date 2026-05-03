"""Budget and tool-policy helpers for bounded research runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from hal9000.db.models import ResearchRun


@dataclass(frozen=True)
class RunBudget:
    """Parsed run budget limits."""

    max_papers: int = 10
    max_downloads: int = 5
    max_llm_calls: int = 50
    max_runtime_minutes: int = 60


@dataclass(frozen=True)
class RunToolPolicy:
    """Parsed worker tool allow-list."""

    allowed_tools: set[str] = field(default_factory=set)

    def allows(self, tool_name: str) -> bool:
        """Return whether a tool or tool family is allowed."""
        if not self.allowed_tools:
            return True
        parts = tool_name.split(".")
        candidates = {tool_name, parts[0]}
        return bool(candidates & self.allowed_tools)


class BudgetExceededError(ValueError):
    """Raised when a worker step would exceed the run budget."""


class RunBudgetTracker:
    """Small budget facade over a research run."""

    def __init__(self, run: ResearchRun):
        """Initialize from a research run."""
        self.run = run
        self.budget = _parse_budget(run)
        self.tool_policy = _parse_tool_policy(run)

    def acquisition_limits(self) -> tuple[int, int]:
        """Return max papers and max downloads for acquisition."""
        max_papers = max(0, self.budget.max_papers)
        max_downloads = max(0, self.budget.max_downloads)
        return min(max_papers, max_downloads), max_downloads

    def require_tool(self, tool_name: str) -> None:
        """Ensure a tool is allowed by the run policy."""
        if not self.tool_policy.allows(tool_name):
            raise BudgetExceededError(f"Tool is not allowed by run policy: {tool_name}")

    def require_acquisition_budget(self) -> int:
        """Ensure acquisition can run and return the paper/download limit."""
        self.require_tool("acquire")
        max_papers, max_downloads = self.acquisition_limits()
        if max_papers <= 0 or max_downloads <= 0:
            raise BudgetExceededError("Acquisition budget is zero")
        return max_papers


def _parse_budget(run: ResearchRun) -> RunBudget:
    if not run.budget_json:
        return RunBudget()
    try:
        raw = json.loads(run.budget_json)
    except json.JSONDecodeError:
        return RunBudget()
    return RunBudget(
        max_papers=int(raw.get("max_papers") or 10),
        max_downloads=int(raw.get("max_downloads") or 5),
        max_llm_calls=int(raw.get("max_llm_calls") or 50),
        max_runtime_minutes=int(raw.get("max_runtime_minutes") or 60),
    )


def _parse_tool_policy(run: ResearchRun) -> RunToolPolicy:
    if not run.tool_policy_json:
        return RunToolPolicy()
    try:
        raw = json.loads(run.tool_policy_json)
    except json.JSONDecodeError:
        return RunToolPolicy()
    return RunToolPolicy(allowed_tools=set(raw.get("allowed_tools") or []))
