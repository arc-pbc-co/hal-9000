"""Async HAL agent runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from hal9000.agent.approvals import (
    AgentToolApprovalDecision,
    AgentToolApprovalRequest,
)
from hal9000.agent.context import AgentContextWindow, AgentMessage
from hal9000.agent.events import (
    AgentEvent,
    AgentEventType,
    AgentOperation,
    AgentOperationType,
)
from hal9000.agent.model import AgentModelClient, AgentModelResponse
from hal9000.agent.tools import AgentToolContext, AgentToolRouter


@dataclass(frozen=True)
class AgentLoopConfig:
    """Controls for one HAL agent loop."""

    max_iterations: int = 8
    approval_timeout_seconds: float | None = None
    max_context_tokens: int | None = None
    compact_target_tokens: int | None = None
    compact_preserve_last: int = 8

    @classmethod
    def from_settings(cls, settings) -> AgentLoopConfig:
        """Create loop controls from HAL Settings or a settings-like object."""
        agent = settings.agent
        return cls(
            approval_timeout_seconds=agent.approval_timeout_seconds,
            max_context_tokens=agent.max_context_tokens,
            compact_target_tokens=agent.compact_target_tokens,
            compact_preserve_last=agent.compact_preserve_last,
        )


@dataclass
class AgentTurnResult:
    """Result of one agent turn."""

    final_response: str | None = None
    interrupted: bool = False
    errored: bool = False
    iterations: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentSessionRuntime:
    """Queue-driven async agent runtime backed by HAL context and tools."""

    def __init__(
        self,
        *,
        context: AgentContextWindow,
        model_client: AgentModelClient,
        tool_router: AgentToolRouter | None = None,
        tool_context: AgentToolContext | None = None,
        event_queue: asyncio.Queue[AgentEvent] | None = None,
        config: AgentLoopConfig | None = None,
    ):
        """Initialize a HAL agent runtime."""
        self.context = context
        self.model_client = model_client
        self.tool_router = tool_router or AgentToolRouter()
        self.tool_context = tool_context or AgentToolContext()
        self.event_queue = event_queue or asyncio.Queue()
        self.config = config or AgentLoopConfig()
        self.is_running = True
        self.is_processing = False
        self._cancel_requested = asyncio.Event()
        self._active_turn_task: asyncio.Task[AgentTurnResult] | None = None
        self._pending_tool_approval_futures: dict[
            str,
            asyncio.Future[AgentToolApprovalDecision],
        ] = {}
        self.pending_tool_approvals: dict[str, AgentToolApprovalRequest] = {}
        self._event_sequence = 0
        self.emitted_events: list[AgentEvent] = []

    async def run(self, submission_queue: asyncio.Queue[AgentOperation]) -> None:
        """Run the submission loop until shutdown."""
        await self.send_event(
            AgentEvent(
                type=AgentEventType.READY,
                data={"tool_count": len(self.tool_router.get_tool_specs_for_llm())},
            )
        )
        get_task: asyncio.Task[AgentOperation] = asyncio.create_task(submission_queue.get())

        try:
            while self.is_running:
                wait_for: set[asyncio.Task[Any]] = {get_task}
                if self._active_turn_task is not None:
                    wait_for.add(self._active_turn_task)

                done, _pending = await asyncio.wait(
                    wait_for,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if get_task in done:
                    operation = get_task.result()
                    get_task = asyncio.create_task(submission_queue.get())
                    await self._handle_operation_from_loop(operation)

                if self._active_turn_task is not None and self._active_turn_task in done:
                    try:
                        await self._active_turn_task
                    finally:
                        self._active_turn_task = None
                        self.is_processing = False
        finally:
            get_task.cancel()
            if self._active_turn_task is not None and not self._active_turn_task.done():
                self._active_turn_task.cancel()

    async def _handle_operation_from_loop(self, operation: AgentOperation) -> None:
        """Handle one queued operation without blocking interrupts."""
        if operation.type == AgentOperationType.USER_INPUT:
            if self._active_turn_task is not None and not self._active_turn_task.done():
                await self.send_event(
                    AgentEvent(
                        type=AgentEventType.ERROR,
                        data={
                            "error": "Agent is already processing a turn.",
                            "code": "AGENT_BUSY",
                        },
                    )
                )
                return
            self._active_turn_task = asyncio.create_task(
                self.run_turn(str(operation.data.get("text") or ""))
            )
            return

        if operation.type == AgentOperationType.TOOL_APPROVAL:
            decision = AgentToolApprovalDecision.from_operation_data(operation.data)
            if not decision.approval_id:
                await self.send_event(
                    AgentEvent(
                        type=AgentEventType.ERROR,
                        data={
                            "error": "Tool approval operation is missing approval_id.",
                            "code": "MISSING_APPROVAL_ID",
                        },
                    )
                )
                return
            if not self.resolve_tool_approval(decision):
                await self.send_event(
                    AgentEvent(
                        type=AgentEventType.ERROR,
                        data={
                            "error": f"Unknown or resolved approval: {decision.approval_id}",
                            "code": "UNKNOWN_APPROVAL",
                            **decision.to_event_data(),
                        },
                    )
                )
            return

        if operation.type == AgentOperationType.INTERRUPT:
            self.request_interrupt()
            return

        if operation.type == AgentOperationType.COMPACT:
            summary = str(operation.data.get("summary") or "Prior turns summarized.")
            result = self.context.compact_with_summary(summary)
            data = result.to_event_data() if result else {"summary": summary}
            await self.send_event(AgentEvent(type=AgentEventType.COMPACTED, data=data))
            self._append_run_event(
                "agent.context.compacted",
                "Agent context compacted by request.",
                data,
            )
            return

        if operation.type == AgentOperationType.SHUTDOWN:
            self.is_running = False
            self.request_interrupt()
            await self.send_event(AgentEvent(type=AgentEventType.SHUTDOWN))
            return

        await self.send_event(
            AgentEvent(
                type=AgentEventType.ERROR,
                data={
                    "error": f"Unsupported agent operation: {operation.type.value}",
                    "code": "UNSUPPORTED_OPERATION",
                },
            )
        )

    async def run_turn(self, text: str) -> AgentTurnResult:
        """Run one user turn through model calls and HAL tool execution."""
        self.is_processing = True
        self._cancel_requested.clear()
        result = AgentTurnResult()
        if text:
            self.context.add_user_message(text)

        await self.send_event(
            AgentEvent(
                type=AgentEventType.PROCESSING,
                data={"message": "Processing user input"},
            )
        )

        try:
            for iteration in range(1, self.config.max_iterations + 1):
                result.iterations = iteration
                self._raise_if_cancelled()
                await self._maybe_compact_context()
                response = await self.model_client.complete(
                    self.context.provider_messages(),
                    self.tool_router.get_tool_specs_for_llm(),
                )
                self._raise_if_cancelled()

                if response.content:
                    await self.send_event(
                        AgentEvent(
                            type=AgentEventType.ASSISTANT_MESSAGE,
                            data={"content": response.content},
                        )
                    )

                if not response.tool_calls:
                    if response.content:
                        self.context.add_assistant_message(
                            response.content,
                            finish_reason=response.finish_reason,
                            token_count=response.token_count,
                            **response.metadata,
                        )
                    result.final_response = response.content
                    await self.send_event(
                        AgentEvent(
                            type=AgentEventType.TURN_COMPLETE,
                            data={
                                "final_response": result.final_response,
                                "iterations": iteration,
                                "history_size": len(self.context.messages),
                            },
                        )
                    )
                    return result

                self._add_assistant_tool_call_message(response)
                await self._execute_tool_calls(response)

            result.errored = True
            await self.send_event(
                AgentEvent(
                    type=AgentEventType.ERROR,
                    data={
                        "error": "Agent reached the maximum iteration limit.",
                        "code": "MAX_ITERATIONS",
                        "max_iterations": self.config.max_iterations,
                    },
                )
            )
            return result
        except asyncio.CancelledError:
            result.interrupted = True
            await self.send_event(AgentEvent(type=AgentEventType.INTERRUPTED))
            return result
        except Exception as exc:
            result.errored = True
            await self.send_event(
                AgentEvent(
                    type=AgentEventType.ERROR,
                    data={"error": str(exc), "error_type": type(exc).__name__},
                )
            )
            return result
        finally:
            self.is_processing = False

    def request_interrupt(self) -> None:
        """Request interruption of the active turn."""
        self._cancel_requested.set()
        if self._active_turn_task is not None and not self._active_turn_task.done():
            self._active_turn_task.cancel()

    def resolve_tool_approval(self, decision: AgentToolApprovalDecision) -> bool:
        """Resolve a pending tool approval, returning whether it was accepted."""
        future = self._pending_tool_approval_futures.get(decision.approval_id)
        if future is None or future.done():
            return False
        future.set_result(decision)
        return True

    async def send_event(self, event: AgentEvent) -> AgentEvent:
        """Emit an event with a local sequence number."""
        self._event_sequence += 1
        sequenced = AgentEvent(
            type=event.type,
            data=event.data,
            id=event.id,
            sequence=self._event_sequence,
            created_at=event.created_at,
        )
        self.emitted_events.append(sequenced)
        await self.event_queue.put(sequenced)
        return sequenced

    def _add_assistant_tool_call_message(self, response: AgentModelResponse) -> None:
        """Add a provider-style assistant tool-call message to the context."""
        self.context.add_message(
            AgentMessage(
                role="assistant",
                content=response.content,
                tool_calls=[tool_call.to_message_tool_call() for tool_call in response.tool_calls],
                metadata={
                    "finish_reason": response.finish_reason,
                    "token_count": response.token_count,
                    **response.metadata,
                },
            )
        )

    async def _execute_tool_calls(self, response: AgentModelResponse) -> None:
        """Execute model-requested tools sequentially and append tool results."""
        for tool_call in response.tool_calls:
            self._raise_if_cancelled()
            tool = self.tool_router.get_tool(tool_call.name)
            await self.send_event(
                AgentEvent(
                    type=AgentEventType.TOOL_CALL,
                    data={
                        "tool": tool_call.name,
                        "arguments": tool_call.arguments,
                        "tool_call_id": tool_call.id,
                    },
                )
            )
            if tool is not None and tool.requires_approval:
                decision = await self._request_tool_approval(tool_call, tool)
                self._raise_if_cancelled()
                if not decision.approved:
                    tool_result = await self.tool_router.reject_tool_call(
                        tool_call.name,
                        tool_call.arguments,
                        context=self.tool_context,
                        reason=decision.reason,
                        approval_id=decision.approval_id,
                    )
                    self.context.add_tool_result(
                        tool_call.id,
                        tool_call.name,
                        tool_result.output,
                        success=tool_result.success,
                        **tool_result.payload,
                    )
                    await self.send_event(
                        AgentEvent(
                            type=AgentEventType.TOOL_OUTPUT,
                            data={
                                "tool": tool_call.name,
                                "tool_call_id": tool_call.id,
                                "output": tool_result.output,
                                "success": tool_result.success,
                                "payload": tool_result.payload,
                            },
                        )
                    )
                    continue

            tool_result = await self.tool_router.call_tool(
                tool_call.name,
                tool_call.arguments,
                context=self.tool_context,
            )
            self.context.add_tool_result(
                tool_call.id,
                tool_call.name,
                tool_result.output,
                success=tool_result.success,
                **tool_result.payload,
            )
            await self.send_event(
                AgentEvent(
                    type=AgentEventType.TOOL_OUTPUT,
                    data={
                        "tool": tool_call.name,
                        "tool_call_id": tool_call.id,
                        "output": tool_result.output,
                        "success": tool_result.success,
                        "payload": tool_result.payload,
                    },
                )
            )

    async def _request_tool_approval(
        self,
        tool_call,
        tool,
    ) -> AgentToolApprovalDecision:
        request = AgentToolApprovalRequest.from_tool_call(tool_call, tool)
        future: asyncio.Future[AgentToolApprovalDecision] = (
            asyncio.get_running_loop().create_future()
        )
        self.pending_tool_approvals[request.approval_id] = request
        self._pending_tool_approval_futures[request.approval_id] = future
        event_data = request.to_event_data()

        self._append_run_event(
            "agent.tool.approval_required",
            f"Agent tool approval required: {request.tool_name}",
            event_data,
        )
        await self.send_event(AgentEvent(type=AgentEventType.APPROVAL_REQUIRED, data=event_data))

        try:
            if self.config.approval_timeout_seconds is None:
                decision = await future
            else:
                decision = await asyncio.wait_for(
                    future,
                    timeout=self.config.approval_timeout_seconds,
                )
        except asyncio.TimeoutError:
            decision = AgentToolApprovalDecision.timeout(request.approval_id)
        finally:
            self.pending_tool_approvals.pop(request.approval_id, None)
            self._pending_tool_approval_futures.pop(request.approval_id, None)

        event_type = (
            "agent.tool.approval_approved" if decision.approved else "agent.tool.approval_rejected"
        )
        state = "approved" if decision.approved else "rejected"
        decision_data = {
            **decision.to_event_data(),
            "tool_call_id": request.tool_call_id,
            "tool": request.tool_name,
        }
        self._append_run_event(
            event_type,
            f"Agent tool {state}: {request.tool_name}",
            decision_data,
            actor=decision.actor,
        )
        await self.send_event(
            AgentEvent(
                type=AgentEventType.TOOL_STATE_CHANGE,
                data={"state": state, **decision_data},
            )
        )
        return decision

    async def _maybe_compact_context(self) -> None:
        if self.config.max_context_tokens is None:
            return
        result = self.context.compact_to_token_budget(
            self.config.max_context_tokens,
            target_tokens=self.config.compact_target_tokens,
            preserve_last=self.config.compact_preserve_last,
        )
        if result is None:
            return
        data = result.to_event_data()
        await self.send_event(AgentEvent(type=AgentEventType.COMPACTED, data=data))
        self._append_run_event(
            "agent.context.compacted",
            "Agent context compacted before model call.",
            data,
        )

    def _append_run_event(
        self,
        event_type: str,
        message: str,
        payload: dict[str, Any],
        actor: str | None = None,
    ) -> None:
        if self.tool_context.store is None or self.tool_context.run is None:
            return
        self.tool_context.store.append_run_event(
            self.tool_context.run,
            event_type=event_type,
            message=message,
            actor=actor or self.tool_context.actor,
            payload=payload,
        )

    def _raise_if_cancelled(self) -> None:
        """Raise when the active turn has been interrupted."""
        if self._cancel_requested.is_set():
            raise asyncio.CancelledError
