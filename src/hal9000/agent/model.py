"""Model-client contracts for HAL agent sessions."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentToolCall:
    """A model-requested tool invocation."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_message_tool_call(self) -> dict[str, Any]:
        """Return a provider-style tool call payload for context replay."""
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": json.dumps(self.arguments, sort_keys=True),
            },
        }


@dataclass(frozen=True)
class AgentModelResponse:
    """Response from an agent model client."""

    content: str | None = None
    tool_calls: list[AgentToolCall] = field(default_factory=list)
    token_count: int | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentModelClient(Protocol):
    """Protocol implemented by concrete model providers.

    The next graft slice can implement this with LiteLLM without changing the
    HAL-owned agent loop or tool accounting.
    """

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> AgentModelResponse:
        """Return the next model response for the current context."""
        ...
