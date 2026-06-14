"""HAL-native tool routing and accounting for agent sessions."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentToolResult:
    """Result returned by a HAL agent tool."""

    output: str
    success: bool = True
    payload: dict[str, Any] = field(default_factory=dict)
    cost_usd: float | None = None

    @classmethod
    def ok(
        cls,
        output: str,
        payload: dict[str, Any] | None = None,
        cost_usd: float | None = None,
    ) -> AgentToolResult:
        """Create a successful tool result."""
        return cls(output=output, success=True, payload=payload or {}, cost_usd=cost_usd)

    @classmethod
    def error(cls, output: str, payload: dict[str, Any] | None = None) -> AgentToolResult:
        """Create a failed tool result."""
        return cls(output=output, success=False, payload=payload or {})


@dataclass
class AgentToolContext:
    """Execution context passed to HAL agent tools."""

    store: Any | None = None
    run: Any | None = None
    actor: str = "hal-agent"
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def require_tool_policy(self, policy_name: str) -> None:
        """Enforce a research run's tool policy when a run is attached."""
        if self.run is None:
            return
        from hal9000.research.budget import RunBudgetTracker

        RunBudgetTracker(self.run).require_tool(policy_name)


ToolHandler = Callable[
    [dict[str, Any], AgentToolContext],
    AgentToolResult | Awaitable[AgentToolResult] | tuple[str, bool] | str,
]


@dataclass
class AgentToolSpec:
    """A tool exposed to the HAL agent runtime."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    policy_name: str | None = None
    requires_approval: bool = False
    source: str = "hal"

    def policy_key(self) -> str:
        """Return the run-policy key used to authorize this tool."""
        if self.policy_name:
            return self.policy_name
        return self.name.split(".", 1)[0]

    def as_llm_tool(self) -> dict[str, Any]:
        """Return an OpenAI-compatible function tool spec."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class AgentToolRouter:
    """Routes agent tool calls through HAL policy and durable accounting."""

    def __init__(self, tools: list[AgentToolSpec] | None = None):
        """Initialize a router with optional tools."""
        self._tools: dict[str, AgentToolSpec] = {}
        for tool in tools or []:
            self.register_tool(tool)

    def register_tool(self, tool: AgentToolSpec) -> None:
        """Register or replace a tool."""
        self._tools[tool.name] = tool

    def has_tool(self, name: str) -> bool:
        """Return whether a tool is registered."""
        return name in self._tools

    def get_tool(self, name: str) -> AgentToolSpec | None:
        """Return a registered tool by name."""
        return self._tools.get(name)

    def get_tool_specs_for_llm(self) -> list[dict[str, Any]]:
        """Return registered tool specs for LLM tool-calling APIs."""
        return [tool.as_llm_tool() for tool in self._tools.values()]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        context: AgentToolContext | None = None,
    ) -> AgentToolResult:
        """Execute a tool with HAL policy, telemetry, and durable tool-call records."""
        tool = self._tools.get(name)
        if tool is None:
            return AgentToolResult.error(f"Unknown HAL agent tool: {name}")

        context = context or AgentToolContext()
        arguments = arguments or {}
        call_record = None
        if context.store is not None and context.run is not None:
            call_record = context.store.start_tool_call(
                context.run,
                tool_name=tool.name,
                actor=context.actor,
                input=arguments,
            )
            context.store.append_run_event(
                context.run,
                event_type="agent.tool.started",
                message=f"Agent tool started: {tool.name}",
                actor=context.actor,
                payload={"tool_call_id": call_record.id, "tool_name": tool.name},
            )

        try:
            context.require_tool_policy(tool.policy_key())
            raw_result = tool.handler(arguments, context)
            if inspect.isawaitable(raw_result):
                raw_result = await raw_result
            result = _coerce_result(raw_result)
        except Exception as exc:
            result = AgentToolResult.error(
                str(exc),
                payload={"error_type": type(exc).__name__},
            )

        if call_record is not None:
            if result.success:
                context.store.finish_tool_call(
                    call_record,
                    status="completed",
                    output=_tool_output_payload(result),
                    cost_usd=result.cost_usd,
                )
                context.store.append_run_event(
                    context.run,
                    event_type="agent.tool.completed",
                    message=f"Agent tool completed: {tool.name}",
                    actor=context.actor,
                    payload={"tool_call_id": call_record.id, "tool_name": tool.name},
                )
            else:
                context.store.finish_tool_call(
                    call_record,
                    status="failed",
                    output=_tool_output_payload(result),
                    error_message=result.output,
                    cost_usd=result.cost_usd,
                )
                context.store.append_run_event(
                    context.run,
                    event_type="agent.tool.failed",
                    message=f"Agent tool failed: {tool.name}",
                    actor=context.actor,
                    payload={
                        "tool_call_id": call_record.id,
                        "tool_name": tool.name,
                        **result.payload,
                    },
                )
            persistence_error = _commit_context_store(context)
            if persistence_error is not None:
                result = persistence_error

        return result

    async def reject_tool_call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        context: AgentToolContext | None = None,
        reason: str | None = None,
        approval_id: str | None = None,
    ) -> AgentToolResult:
        """Record a rejected tool call without executing its handler."""
        tool = self._tools.get(name)
        if tool is None:
            return AgentToolResult.error(f"Unknown HAL agent tool: {name}")

        context = context or AgentToolContext()
        arguments = arguments or {}
        message = reason or "Tool call was rejected by approval policy."
        result = AgentToolResult.error(
            f"Tool call rejected: {message}",
            payload={
                "approval_id": approval_id,
                "rejected": True,
                "reason": message,
            },
        )

        if context.store is not None and context.run is not None:
            call_record = context.store.start_tool_call(
                context.run,
                tool_name=tool.name,
                actor=context.actor,
                input=arguments,
            )
            context.store.finish_tool_call(
                call_record,
                status="rejected",
                output=_tool_output_payload(result),
                error_message=result.output,
            )
            context.store.append_run_event(
                context.run,
                event_type="agent.tool.rejected",
                message=f"Agent tool rejected: {tool.name}",
                actor=context.actor,
                payload={
                    "tool_call_id": call_record.id,
                    "tool_name": tool.name,
                    "approval_id": approval_id,
                    "reason": message,
                },
            )
            persistence_error = _commit_context_store(context)
            if persistence_error is not None:
                return persistence_error

        return result


def _coerce_result(raw_result: AgentToolResult | tuple[str, bool] | str) -> AgentToolResult:
    """Normalize handler return values into AgentToolResult."""
    if isinstance(raw_result, AgentToolResult):
        return raw_result
    if isinstance(raw_result, tuple):
        output, success = raw_result
        return AgentToolResult(output=str(output), success=bool(success))
    return AgentToolResult.ok(str(raw_result))


def _tool_output_payload(result: AgentToolResult) -> dict[str, Any]:
    """Build a compact JSON payload for ResearchToolCall.output_json."""
    payload = dict(result.payload)
    payload.setdefault("output", result.output)
    payload.setdefault("success", result.success)
    return payload


def _commit_context_store(context: AgentToolContext) -> AgentToolResult | None:
    """Commit durable tool side effects when a context owns a store session."""
    store = context.store
    session = getattr(store, "session", None)
    commit = getattr(session, "commit", None)
    if not callable(commit):
        return None
    try:
        commit()
    except Exception as exc:
        rollback = getattr(session, "rollback", None)
        if callable(rollback):
            rollback()
        return AgentToolResult.error(
            f"Failed to persist HAL tool result: {exc}",
            payload={"error_type": type(exc).__name__},
        )
    return None
