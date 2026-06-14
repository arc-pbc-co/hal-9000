"""Operation and event contracts for HAL agent sessions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class AgentOperationType(str, Enum):
    """Inputs accepted by a HAL agent session."""

    USER_INPUT = "user_input"
    TOOL_APPROVAL = "tool_approval"
    INTERRUPT = "interrupt"
    COMPACT = "compact"
    UNDO = "undo"
    RESUME = "resume"
    SHUTDOWN = "shutdown"


class AgentEventType(str, Enum):
    """Events emitted by a HAL agent session."""

    READY = "ready"
    PROCESSING = "processing"
    ASSISTANT_CHUNK = "assistant_chunk"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL = "tool_call"
    TOOL_OUTPUT = "tool_output"
    TOOL_STATE_CHANGE = "tool_state_change"
    APPROVAL_REQUIRED = "approval_required"
    COMPACTED = "compacted"
    TURN_COMPLETE = "turn_complete"
    ERROR = "error"
    INTERRUPTED = "interrupted"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class AgentOperation:
    """A queued operation for a HAL agent session.

    The shape deliberately mirrors ml-intern's queue operations while staying
    independent of its concrete session implementation.
    """

    type: AgentOperationType
    data: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def user_input(cls, text: str) -> AgentOperation:
        """Create a user-input operation."""
        return cls(type=AgentOperationType.USER_INPUT, data={"text": text})


@dataclass(frozen=True)
class AgentEvent:
    """A UI/API event emitted by a HAL agent session."""

    type: AgentEventType | str
    data: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sequence: int | None = None
    created_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable event payload."""
        event_type = self.type.value if isinstance(self.type, AgentEventType) else self.type
        return {
            "id": self.id,
            "type": event_type,
            "sequence": self.sequence,
            "created_at": self.created_at.isoformat(),
            "data": self.data,
        }
