"""Approval primitives for HAL agent tool execution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from hal9000.agent.events import utc_now
from hal9000.agent.model import AgentToolCall
from hal9000.agent.tools import AgentToolSpec


@dataclass(frozen=True)
class AgentToolApprovalRequest:
    """A pending approval request for a model-requested tool call."""

    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    approval_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reason: str = "Tool requires approval before execution."
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def from_tool_call(
        cls,
        tool_call: AgentToolCall,
        tool: AgentToolSpec,
    ) -> AgentToolApprovalRequest:
        """Create an approval request from a tool call and registered spec."""
        return cls(
            tool_call_id=tool_call.id,
            tool_name=tool_call.name,
            arguments=dict(tool_call.arguments),
            reason=f"Tool requires approval before execution: {tool.name}",
        )

    def to_event_data(self) -> dict[str, Any]:
        """Return a UI/API event payload for this approval request."""
        return {
            "approval_id": self.approval_id,
            "tool_call_id": self.tool_call_id,
            "tool": self.tool_name,
            "arguments": self.arguments,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class AgentToolApprovalDecision:
    """A decision resolving a pending tool approval."""

    approval_id: str
    approved: bool
    actor: str = "human"
    reason: str | None = None
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def from_operation_data(
        cls,
        data: dict[str, Any],
    ) -> AgentToolApprovalDecision:
        """Create a decision from an AgentOperation payload."""
        status = str(data.get("status") or "").strip().lower()
        if status:
            approved = status in {"approved", "approve", "accepted", "accept", "yes"}
        else:
            approved = _bool_value(data.get("approved"))
        return cls(
            approval_id=str(data.get("approval_id") or data.get("id") or ""),
            approved=approved,
            actor=str(data.get("actor") or "human"),
            reason=data.get("reason"),
        )

    @classmethod
    def timeout(cls, approval_id: str) -> AgentToolApprovalDecision:
        """Create a rejection decision caused by an approval timeout."""
        return cls(
            approval_id=approval_id,
            approved=False,
            actor="hal-agent",
            reason="Approval timed out.",
        )

    def to_event_data(self) -> dict[str, Any]:
        """Return a UI/API event payload for this decision."""
        return {
            "approval_id": self.approval_id,
            "approved": self.approved,
            "actor": self.actor,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "approve"}
    return bool(value)
