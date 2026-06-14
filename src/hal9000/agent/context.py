"""HAL-owned conversation context primitives for future agent sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentMessage:
    """Provider-neutral chat message stored by HAL."""

    role: str
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a dict compatible with common chat-completion APIs."""
        payload: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            payload["content"] = self.content
        if self.name is not None:
            payload["name"] = self.name
        if self.tool_call_id is not None:
            payload["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            payload["tool_calls"] = self.tool_calls
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AgentMessage:
        """Create a message from a stored or provider-style dict."""
        return cls(
            role=str(payload["role"]),
            content=payload.get("content"),
            name=payload.get("name"),
            tool_call_id=payload.get("tool_call_id"),
            tool_calls=list(payload.get("tool_calls") or []),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass(frozen=True)
class AgentCompactionResult:
    """Metadata returned when an agent context window is compacted."""

    old_token_count: int
    new_token_count: int
    max_token_count: int | None
    compacted_message_count: int
    preserved_message_count: int
    summary: str

    def to_event_data(self) -> dict[str, Any]:
        """Return a compact event payload."""
        return {
            "old_token_count": self.old_token_count,
            "new_token_count": self.new_token_count,
            "max_token_count": self.max_token_count,
            "compacted_message_count": self.compacted_message_count,
            "preserved_message_count": self.preserved_message_count,
            "summary": self.summary,
        }


class AgentContextWindow:
    """Small context window manager that preserves HAL-owned session history.

    HAL owns the persisted context shape. The compaction helpers use a
    deterministic token estimate so the runtime can keep long sessions inside a
    model budget without giving another system ownership of the research ledger.
    """

    def __init__(
        self,
        system_prompt: str,
        messages: list[AgentMessage] | None = None,
    ):
        """Initialize a context window with a system prompt and optional history."""
        self.system_prompt = system_prompt
        if messages is None:
            self.messages = [AgentMessage(role="system", content=system_prompt)]
        else:
            self.messages = list(messages)
            if not self.messages or self.messages[0].role != "system":
                self.messages.insert(0, AgentMessage(role="system", content=system_prompt))

    def add_message(self, message: AgentMessage) -> None:
        """Append a message to the context."""
        self.messages.append(message)

    def add_user_message(self, content: str, **metadata: Any) -> AgentMessage:
        """Append and return a user message."""
        message = AgentMessage(role="user", content=content, metadata=metadata)
        self.add_message(message)
        return message

    def add_assistant_message(self, content: str | None, **metadata: Any) -> AgentMessage:
        """Append and return an assistant message."""
        message = AgentMessage(role="assistant", content=content, metadata=metadata)
        self.add_message(message)
        return message

    def add_tool_result(
        self,
        tool_call_id: str,
        name: str,
        content: str,
        **metadata: Any,
    ) -> AgentMessage:
        """Append and return a tool-result message."""
        message = AgentMessage(
            role="tool",
            content=content,
            name=name,
            tool_call_id=tool_call_id,
            metadata=metadata,
        )
        self.add_message(message)
        return message

    def provider_messages(self) -> list[dict[str, Any]]:
        """Return messages in provider-neutral dictionary form."""
        return [message.to_dict() for message in self.messages]

    def estimated_token_count(self, messages: list[AgentMessage] | None = None) -> int:
        """Return a deterministic approximate token count for the context."""
        return sum(estimate_message_tokens(message) for message in messages or self.messages)

    def compact_to_token_budget(
        self,
        max_tokens: int,
        *,
        target_tokens: int | None = None,
        preserve_last: int = 8,
        summary: str | None = None,
    ) -> AgentCompactionResult | None:
        """Compact the context when its estimated token count exceeds a budget."""
        old_token_count = self.estimated_token_count()
        if old_token_count <= max_tokens:
            return None

        target = target_tokens or max(1, int(max_tokens * 0.8))
        max_preserve = min(max(0, preserve_last), max(0, len(self.messages) - 2))
        best_messages: list[AgentMessage] | None = None
        best_summary = ""
        best_compacted_count = 0
        best_token_count = old_token_count

        for summary_chars in (1600, 800, 400, 200):
            for keep_count in range(max_preserve, -1, -1):
                compacted, compacted_count, summary_text = self._compacted_messages(
                    summary=summary,
                    preserve_last=keep_count,
                    summary_max_chars=summary_chars,
                )
                token_count = self.estimated_token_count(compacted)
                if best_messages is None or token_count < best_token_count:
                    best_messages = compacted
                    best_summary = summary_text
                    best_compacted_count = compacted_count
                    best_token_count = token_count
                if token_count <= target:
                    self.messages = compacted
                    return AgentCompactionResult(
                        old_token_count=old_token_count,
                        new_token_count=token_count,
                        max_token_count=max_tokens,
                        compacted_message_count=compacted_count,
                        preserved_message_count=len(compacted),
                        summary=summary_text,
                    )

        if best_messages is None:
            return None
        self.messages = best_messages
        return AgentCompactionResult(
            old_token_count=old_token_count,
            new_token_count=best_token_count,
            max_token_count=max_tokens,
            compacted_message_count=best_compacted_count,
            preserved_message_count=len(best_messages),
            summary=best_summary,
        )

    def compact_with_summary(
        self,
        summary: str,
        preserve_last: int = 8,
    ) -> AgentCompactionResult | None:
        """Replace the middle of the context with a summary message.

        The first system message and first user task are preserved, matching the
        HAL requirement that run intent remains auditable.
        """
        if len(self.messages) <= preserve_last + 2:
            return None

        old_token_count = self.estimated_token_count()
        compacted, compacted_count, summary_text = self._compacted_messages(
            summary=summary,
            preserve_last=preserve_last,
        )
        self.messages = compacted
        return AgentCompactionResult(
            old_token_count=old_token_count,
            new_token_count=self.estimated_token_count(),
            max_token_count=None,
            compacted_message_count=compacted_count,
            preserved_message_count=len(compacted),
            summary=summary_text,
        )

    def _compacted_messages(
        self,
        *,
        summary: str | None,
        preserve_last: int,
        summary_max_chars: int = 1600,
    ) -> tuple[list[AgentMessage], int, str]:
        recent_start = self._recent_suffix_start(preserve_last)
        first_user_index = self._first_user_index()
        preserved_indices = {0}
        if first_user_index is not None and first_user_index < recent_start:
            preserved_indices.add(first_user_index)
        preserved_indices.update(range(recent_start, len(self.messages)))

        compacted_messages = [
            message for index, message in enumerate(self.messages) if index not in preserved_indices
        ]
        summary_text = summary or summarize_messages(compacted_messages)
        summary_text = _truncate_text(summary_text, summary_max_chars)

        head = [self.messages[0]]
        if first_user_index is not None and first_user_index < recent_start:
            head.append(self.messages[first_user_index])
        head.append(
            AgentMessage(
                role="assistant",
                content=summary_text,
                metadata={"kind": "context_summary"},
            )
        )
        return head + self.messages[recent_start:], len(compacted_messages), summary_text

    def _first_user_index(self) -> int | None:
        for index, message in enumerate(self.messages[1:], start=1):
            if message.role == "user":
                return index
        return None

    def _recent_suffix_start(self, preserve_last: int) -> int:
        if preserve_last <= 0:
            return len(self.messages)
        start = max(1, len(self.messages) - preserve_last)
        while start > 1 and self.messages[start].role == "tool":
            start -= 1
        return start


def estimate_message_tokens(message: AgentMessage) -> int:
    """Estimate model tokens for one provider-neutral message."""
    payload = message.to_dict()
    metadata = dict(payload.pop("metadata", {}) or {})
    estimated = 4
    for value in payload.values():
        estimated += estimate_text_tokens(value)
    if isinstance(metadata.get("token_count"), int):
        estimated = max(estimated, int(metadata["token_count"]))
    return estimated


def estimate_text_tokens(value: Any) -> int:
    """Estimate tokens from text or JSON-ish content using a stable heuristic."""
    if value is None:
        return 0
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, default=str)
    stripped = value.strip()
    if not stripped:
        return 0
    return max(1, (len(stripped) + 3) // 4)


def summarize_messages(messages: list[AgentMessage]) -> str:
    """Create a bounded deterministic summary for compacted context."""
    if not messages:
        return "No prior messages were compacted."

    role_counts: dict[str, int] = {}
    for message in messages:
        role_counts[message.role] = role_counts.get(message.role, 0) + 1
    role_summary = ", ".join(f"{role}={count}" for role, count in sorted(role_counts.items()))
    lines = [f"Compacted {len(messages)} prior messages ({role_summary})."]

    for message in messages[-6:]:
        snippet = _message_snippet(message)
        if snippet:
            lines.append(f"{message.role}: {snippet}")
    return "\n".join(lines)


def _message_snippet(message: AgentMessage) -> str:
    if message.content:
        return _truncate_text(message.content, 180)
    if message.tool_calls:
        names = []
        for tool_call in message.tool_calls[:4]:
            function = tool_call.get("function", {})
            names.append(str(function.get("name") or "unknown_tool"))
        return f"requested tools: {', '.join(names)}"
    return ""


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."
