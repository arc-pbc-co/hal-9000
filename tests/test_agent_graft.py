"""Tests for the HAL-native agent graft boundary."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from hal9000.agent import (
    AgentContextWindow,
    AgentEvent,
    AgentEventType,
    AgentLoopConfig,
    AgentMessage,
    AgentModelResponse,
    AgentOperation,
    AgentOperationType,
    AgentSessionRuntime,
    AgentToolCall,
    AgentToolContext,
    AgentToolResult,
    AgentToolRouter,
    AgentToolSpec,
)
from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore


def _search_tool(requires_approval: bool = False) -> AgentToolSpec:
    async def handler(arguments, context):
        query = arguments["query"]
        return AgentToolResult.ok(
            f"searched memory for {query}",
            payload={"query": query, "result_count": 1},
        )

    return AgentToolSpec(
        name="hal_search_memory",
        description="Search HAL's canonical research memory.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        handler=handler,
        policy_name="search",
        requires_approval=requires_approval,
    )


class ScriptedModelClient:
    """Small fake model client for runtime tests."""

    def __init__(self, responses: list[AgentModelResponse]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def complete(self, messages, tools):
        self.calls.append({"messages": messages, "tools": tools})
        if not self.responses:
            raise AssertionError("No scripted response left")
        return self.responses.pop(0)


class WaitingModelClient:
    """Model client that waits until cancelled."""

    def __init__(self):
        self.called = asyncio.Event()
        self.cancelled = False

    async def complete(self, messages, tools):
        self.called.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return AgentModelResponse(content="unreachable")


async def _collect_until(
    event_queue: asyncio.Queue[AgentEvent],
    event_type: AgentEventType,
    timeout: float = 1.0,
) -> list[AgentEvent]:
    events = []
    while True:
        event = await asyncio.wait_for(event_queue.get(), timeout=timeout)
        events.append(event)
        if event.type == event_type:
            return events


@pytest.mark.asyncio
async def test_agent_tool_router_records_allowed_hal_tool_call(temp_directory: Path):
    """Allowed agent tools should run through HAL's durable accounting."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'agent_allowed.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        run = store.create_run(
            objective="Search memory.",
            tool_policy={"allowed_tools": ["search"]},
        )
        router = AgentToolRouter([_search_tool()])

        result = await router.call_tool(
            "hal_search_memory",
            {"query": "nickel superalloy creep"},
            context=AgentToolContext(store=store, run=run, actor="hal-agent-test"),
        )
        session.commit()

        calls = store.list_tool_calls(run)
        events = store.list_run_events(run)

        assert result.success is True
        assert result.payload["result_count"] == 1
        assert len(calls) == 1
        assert calls[0].tool_name == "hal_search_memory"
        assert calls[0].status == "completed"
        assert json.loads(calls[0].output_json)["query"] == "nickel superalloy creep"
        assert [event.event_type for event in events] == [
            "agent.tool.started",
            "agent.tool.completed",
        ]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_agent_tool_router_enforces_hal_run_tool_policy(temp_directory: Path):
    """Disallowed tools should fail before handler execution but still leave an audit trail."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'agent_policy.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        run = store.create_run(
            objective="Search memory.",
            tool_policy={"allowed_tools": ["rlm"]},
        )
        router = AgentToolRouter([_search_tool()])

        result = await router.call_tool(
            "hal_search_memory",
            {"query": "nickel superalloy creep"},
            context=AgentToolContext(store=store, run=run, actor="hal-agent-test"),
        )
        session.commit()

        calls = store.list_tool_calls(run)
        events = store.list_run_events(run)

        assert result.success is False
        assert "not allowed" in result.output
        assert calls[0].status == "failed"
        assert calls[0].error_message == result.output
        assert [event.event_type for event in events] == [
            "agent.tool.started",
            "agent.tool.failed",
        ]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_agent_runtime_processes_user_input_to_final_response():
    """The async runtime should call the model and emit a complete turn."""
    event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
    submission_queue: asyncio.Queue[AgentOperation] = asyncio.Queue()
    model = ScriptedModelClient([AgentModelResponse(content="Ready for review.")])
    runtime = AgentSessionRuntime(
        context=AgentContextWindow("You are HAL."),
        model_client=model,
        event_queue=event_queue,
    )
    loop_task = asyncio.create_task(runtime.run(submission_queue))

    await submission_queue.put(AgentOperation.user_input("Summarize this run."))
    events = await _collect_until(event_queue, AgentEventType.TURN_COMPLETE)
    await submission_queue.put(AgentOperation(type=AgentOperationType.SHUTDOWN))
    await loop_task

    event_types = [event.type for event in events]
    assert event_types == [
        AgentEventType.READY,
        AgentEventType.PROCESSING,
        AgentEventType.ASSISTANT_MESSAGE,
        AgentEventType.TURN_COMPLETE,
    ]
    assert events[-1].data["final_response"] == "Ready for review."
    assert model.calls[0]["messages"][1]["content"] == "Summarize this run."
    assert runtime.context.messages[-1].content == "Ready for review."
    assert [event.sequence for event in runtime.emitted_events] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_agent_runtime_executes_tool_then_continues_to_final_response(
    temp_directory: Path,
):
    """Tool calls should flow through HAL accounting before the next model call."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'agent_runtime.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        run = store.create_run(
            objective="Search memory.",
            tool_policy={"allowed_tools": ["search"]},
        )
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        tool_call = AgentToolCall(
            id="tool-call-1",
            name="hal_search_memory",
            arguments={"query": "creep resistance"},
        )
        model = ScriptedModelClient(
            [
                AgentModelResponse(tool_calls=[tool_call]),
                AgentModelResponse(content="The memory search found one source."),
            ]
        )
        runtime = AgentSessionRuntime(
            context=AgentContextWindow("You are HAL."),
            model_client=model,
            tool_router=AgentToolRouter([_search_tool()]),
            tool_context=AgentToolContext(
                store=store,
                run=run,
                actor="hal-agent-runtime-test",
            ),
            event_queue=event_queue,
            config=AgentLoopConfig(max_iterations=4),
        )

        result = await runtime.run_turn("Find prior work.")
        session.commit()

        calls = store.list_tool_calls(run)
        event_types = [event.type for event in runtime.emitted_events]

        assert result.final_response == "The memory search found one source."
        assert len(model.calls) == 2
        assert model.calls[1]["messages"][-1]["role"] == "tool"
        assert model.calls[1]["messages"][-1]["tool_call_id"] == "tool-call-1"
        assert calls[0].tool_name == "hal_search_memory"
        assert calls[0].status == "completed"
        assert event_types == [
            AgentEventType.PROCESSING,
            AgentEventType.TOOL_CALL,
            AgentEventType.TOOL_OUTPUT,
            AgentEventType.ASSISTANT_MESSAGE,
            AgentEventType.TURN_COMPLETE,
        ]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_agent_runtime_waits_for_required_tool_approval(temp_directory: Path):
    """Approval-gated tools should pause the turn until an approval operation arrives."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'agent_approval.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        run = store.create_run(
            objective="Search memory.",
            tool_policy={"allowed_tools": ["search"]},
        )
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        submission_queue: asyncio.Queue[AgentOperation] = asyncio.Queue()
        tool_call = AgentToolCall(
            id="tool-call-approval-1",
            name="hal_search_memory",
            arguments={"query": "fatigue crack growth"},
        )
        model = ScriptedModelClient(
            [
                AgentModelResponse(tool_calls=[tool_call]),
                AgentModelResponse(content="Approved search completed."),
            ]
        )
        runtime = AgentSessionRuntime(
            context=AgentContextWindow("You are HAL."),
            model_client=model,
            tool_router=AgentToolRouter([_search_tool(requires_approval=True)]),
            tool_context=AgentToolContext(
                store=store,
                run=run,
                actor="hal-agent-approval-test",
            ),
            event_queue=event_queue,
        )
        loop_task = asyncio.create_task(runtime.run(submission_queue))

        await submission_queue.put(AgentOperation.user_input("Search if approved."))
        approval_events = await _collect_until(event_queue, AgentEventType.APPROVAL_REQUIRED)
        approval_id = approval_events[-1].data["approval_id"]

        assert approval_id in runtime.pending_tool_approvals

        await submission_queue.put(
            AgentOperation(
                type=AgentOperationType.TOOL_APPROVAL,
                data={
                    "approval_id": approval_id,
                    "approved": True,
                    "actor": "reviewer@example.com",
                    "reason": "Search is within scope.",
                },
            )
        )
        events = approval_events + await _collect_until(event_queue, AgentEventType.TURN_COMPLETE)
        await submission_queue.put(AgentOperation(type=AgentOperationType.SHUTDOWN))
        await loop_task
        session.commit()

        calls = store.list_tool_calls(run)
        run_events = store.list_run_events(run)
        run_event_types = [event.event_type for event in run_events]
        event_types = [event.type for event in events]

        assert calls[0].status == "completed"
        assert AgentEventType.TOOL_STATE_CHANGE in event_types
        assert AgentEventType.TOOL_OUTPUT in event_types
        assert run_event_types == [
            "agent.tool.approval_required",
            "agent.tool.approval_approved",
            "agent.tool.started",
            "agent.tool.completed",
        ]
        assert run_events[1].actor == "reviewer@example.com"
    finally:
        session.close()


@pytest.mark.asyncio
async def test_agent_runtime_rejected_tool_approval_skips_side_effects(
    temp_directory: Path,
):
    """Rejected approvals should be recorded without executing the handler."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'agent_rejection.db'}")
    session = session_factory()
    handler_called = False

    async def handler(arguments, context):
        nonlocal handler_called
        handler_called = True
        return AgentToolResult.ok("should not run")

    try:
        store = ResearchStore(session)
        run = store.create_run(
            objective="Search memory.",
            tool_policy={"allowed_tools": ["search"]},
        )
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        submission_queue: asyncio.Queue[AgentOperation] = asyncio.Queue()
        tool_call = AgentToolCall(
            id="tool-call-rejected-1",
            name="hal_search_memory",
            arguments={"query": "export controlled material"},
        )
        model = ScriptedModelClient(
            [
                AgentModelResponse(tool_calls=[tool_call]),
                AgentModelResponse(content="I skipped the rejected tool."),
            ]
        )
        runtime = AgentSessionRuntime(
            context=AgentContextWindow("You are HAL."),
            model_client=model,
            tool_router=AgentToolRouter(
                [
                    AgentToolSpec(
                        name="hal_search_memory",
                        description="Search HAL's canonical research memory.",
                        parameters={"type": "object"},
                        handler=handler,
                        policy_name="search",
                        requires_approval=True,
                    )
                ]
            ),
            tool_context=AgentToolContext(
                store=store,
                run=run,
                actor="hal-agent-rejection-test",
            ),
            event_queue=event_queue,
        )
        loop_task = asyncio.create_task(runtime.run(submission_queue))

        await submission_queue.put(AgentOperation.user_input("Search if approved."))
        approval_events = await _collect_until(event_queue, AgentEventType.APPROVAL_REQUIRED)
        approval_id = approval_events[-1].data["approval_id"]
        await submission_queue.put(
            AgentOperation(
                type=AgentOperationType.TOOL_APPROVAL,
                data={
                    "approval_id": approval_id,
                    "approved": "false",
                    "actor": "reviewer@example.com",
                    "reason": "Needs project owner approval.",
                },
            )
        )
        await _collect_until(event_queue, AgentEventType.TURN_COMPLETE)
        await submission_queue.put(AgentOperation(type=AgentOperationType.SHUTDOWN))
        await loop_task
        session.commit()

        calls = store.list_tool_calls(run)
        run_events = store.list_run_events(run)
        run_event_types = [event.event_type for event in run_events]

        assert handler_called is False
        assert calls[0].status == "rejected"
        assert "Needs project owner approval" in calls[0].error_message
        assert runtime.context.messages[-2].role == "tool"
        assert runtime.context.messages[-2].metadata["rejected"] is True
        assert run_event_types == [
            "agent.tool.approval_required",
            "agent.tool.approval_rejected",
            "agent.tool.rejected",
        ]
        assert run_events[1].actor == "reviewer@example.com"
    finally:
        session.close()


@pytest.mark.asyncio
async def test_agent_runtime_interrupt_operation_cancels_active_turn():
    """An interrupt operation should cancel an in-flight model call."""
    event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
    submission_queue: asyncio.Queue[AgentOperation] = asyncio.Queue()
    model = WaitingModelClient()
    runtime = AgentSessionRuntime(
        context=AgentContextWindow("You are HAL."),
        model_client=model,
        event_queue=event_queue,
    )
    loop_task = asyncio.create_task(runtime.run(submission_queue))

    await submission_queue.put(AgentOperation.user_input("Keep working."))
    await asyncio.wait_for(model.called.wait(), timeout=1.0)
    await submission_queue.put(AgentOperation(type=AgentOperationType.INTERRUPT))
    events = await _collect_until(event_queue, AgentEventType.INTERRUPTED)
    await submission_queue.put(AgentOperation(type=AgentOperationType.SHUTDOWN))
    await loop_task

    assert model.cancelled is True
    assert events[-1].type == AgentEventType.INTERRUPTED
    assert runtime.is_processing is False


def test_agent_context_compaction_preserves_system_and_first_user_message():
    """Context summaries should not erase the original research objective."""
    context = AgentContextWindow("You are HAL.")
    context.add_user_message("Research nickel superalloy creep resistance.")
    for index in range(12):
        context.add_assistant_message(f"assistant note {index}")
        context.add_user_message(f"user follow-up {index}")

    context.compact_with_summary("Middle turns summarized.", preserve_last=4)

    messages = context.provider_messages()
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "Research nickel superalloy creep resistance."
    assert messages[2]["metadata"]["kind"] == "context_summary"
    assert messages[2]["content"] == "Middle turns summarized."
    assert messages[-1]["content"] == "user follow-up 11"


@pytest.mark.asyncio
async def test_agent_runtime_auto_compacts_when_context_exceeds_token_budget():
    """The runtime should compact oversized context before model calls."""
    context = AgentContextWindow("You are HAL.")
    context.add_user_message("Research nickel superalloy creep resistance.")
    for index in range(16):
        context.add_assistant_message(
            "assistant note "
            + str(index)
            + ": "
            + ("long context about alloys, creep, fatigue, and review evidence. " * 3)
        )
        context.add_user_message(f"user follow-up {index}: keep the audit trail intact.")

    model = ScriptedModelClient([AgentModelResponse(content="Compacted and ready.")])
    runtime = AgentSessionRuntime(
        context=context,
        model_client=model,
        config=AgentLoopConfig(
            max_context_tokens=180,
            compact_target_tokens=120,
            compact_preserve_last=4,
        ),
    )

    result = await runtime.run_turn("Continue the research.")

    compacted_event = next(
        event for event in runtime.emitted_events if event.type == AgentEventType.COMPACTED
    )
    messages = model.calls[0]["messages"]

    assert result.final_response == "Compacted and ready."
    assert compacted_event.data["old_token_count"] > compacted_event.data["new_token_count"]
    assert any(message.get("metadata", {}).get("kind") == "context_summary" for message in messages)
    assert messages[1]["content"] == "Research nickel superalloy creep resistance."


def test_agent_context_token_compaction_preserves_tool_call_pairs():
    """Compaction should not leave provider-invalid orphaned tool outputs."""
    context = AgentContextWindow("You are HAL.")
    context.add_user_message("Research objective.")
    for index in range(8):
        context.add_assistant_message("older assistant note " + str(index) + (" x" * 40))
    tool_call = AgentToolCall(
        id="tool-call-preserved",
        name="hal_search_memory",
        arguments={"query": "phase stability"},
    )
    context.add_message(
        AgentMessage(
            role="assistant",
            tool_calls=[tool_call.to_message_tool_call()],
        )
    )
    context.add_tool_result(
        "tool-call-preserved",
        "hal_search_memory",
        "search result",
    )

    context.compact_to_token_budget(
        300,
        target_tokens=300,
        preserve_last=1,
    )
    messages = context.provider_messages()
    tool_index = next(index for index, message in enumerate(messages) if message["role"] == "tool")

    assert messages[tool_index - 1]["role"] == "assistant"
    assert messages[tool_index - 1]["tool_calls"][0]["id"] == "tool-call-preserved"
