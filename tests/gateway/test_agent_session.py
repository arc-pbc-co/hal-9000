"""Tests for gateway-owned HAL agent sessions."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest
import websockets
from sqlalchemy.exc import OperationalError

from hal9000.agent import (
    AgentEventType,
    AgentModelResponse,
    AgentToolCall,
    AgentToolContext,
    AgentToolResult,
    AgentToolRouter,
    AgentToolSpec,
)
from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.gateway import (
    AgentGatewaySessionManager,
    AgentRunLedger,
    GatewayMessage,
    HALGateway,
    MessageType,
    Session,
    create_router_with_defaults,
)
from hal9000.gateway.agent_ledger import AGENT_GATEWAY_EVENT_TYPE


class ScriptedModelClient:
    """Small fake model client for gateway agent tests."""

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


def _empty_router(_payload) -> AgentToolRouter:
    return AgentToolRouter()


class LockedLedger:
    """Ledger double that behaves like a temporarily locked SQLite database."""

    def __init__(self) -> None:
        self.record_calls = 0

    def record_event(self, _session, _event) -> bool:
        self.record_calls += 1
        raise OperationalError("INSERT", {}, RuntimeError("database is locked"))

    def replay_events(self, **_kwargs) -> list[dict[str, Any]]:
        raise OperationalError("SELECT", {}, RuntimeError("database is locked"))

    def latest_history(self, **_kwargs) -> list[dict[str, Any]]:
        raise OperationalError("SELECT", {}, RuntimeError("database is locked"))


@pytest.mark.asyncio
async def test_agent_gateway_default_context_attaches_store_and_project_run(temp_directory) -> None:
    """Default gateway sessions should give HAL tools a store and run context."""
    db_url = f"sqlite:///{temp_directory / 'agent_context.db'}"
    _, session_factory = init_db(db_url)
    db_session = session_factory()
    try:
        store = ResearchStore(db_session)
        project = store.create_project("Agent Project", "agent-project")
        db_session.commit()
        project_id = project.id
    finally:
        db_session.close()

    manager = AgentGatewaySessionManager(
        settings=SimpleNamespace(database=SimpleNamespace(url=db_url)),
        model_client_factory=lambda _payload: ScriptedModelClient([]),
        tool_router_factory=_empty_router,
    )

    try:
        session = await manager.create_session(
            session_id="context-store",
            user_id="agent@example.com",
            metadata={"project_slug": "agent-project", "objective": "Research through gateway."},
        )

        context = session.runtime.tool_context
        assert context.store is not None
        assert context.run is not None
        assert session.run_id == context.run.id
        assert context.run.project_id == project_id
        assert context.run.objective == "Research through gateway."
        assert context.metadata["settings"] is manager.settings
    finally:
        await manager.close_all()


@pytest.mark.asyncio
async def test_agent_gateway_session_submit_replay_history_and_compact() -> None:
    """Gateway sessions should expose submit, replay, history, and compaction APIs."""
    model = ScriptedModelClient([AgentModelResponse(content="HAL is online.")])
    manager = AgentGatewaySessionManager(
        model_client_factory=lambda _payload: model,
        tool_router_factory=_empty_router,
    )

    try:
        session = await manager.create_session(
            session_id="agent-direct",
            gateway_session_id="gateway-direct",
        )

        assert session.replay()[0]["type"] == "ready"

        operation = await session.submit("Status?")
        turn_complete = await session.wait_for_event(AgentEventType.TURN_COMPLETE)
        history = session.history(include_system=False)

        assert operation.type.value == "user_input"
        assert turn_complete.data["final_response"] == "HAL is online."
        assert [message["role"] for message in history] == ["user", "assistant"]
        assert history[-1]["content"] == "HAL is online."

        await session.compact("Short gateway summary.")
        compacted = await session.wait_for_event(AgentEventType.COMPACTED)

        replayed = session.replay(after_sequence=1)
        assert compacted.data["summary"] == "Short gateway summary."
        assert [event["type"] for event in replayed][-1] == "compacted"
        assert model.calls[0]["messages"][1]["content"] == "Status?"
    finally:
        await manager.close_all()


@pytest.mark.asyncio
async def test_live_agent_replay_uses_memory_when_run_ledger_is_locked() -> None:
    """Live cockpit replay/history should not fail on transient SQLite ledger locks."""
    ledger = LockedLedger()
    model = ScriptedModelClient([AgentModelResponse(content="Live memory is available.")])
    manager = AgentGatewaySessionManager(
        model_client_factory=lambda _payload: model,
        tool_router_factory=_empty_router,
        tool_context_factory=lambda _payload: AgentToolContext(),
        run_ledger=ledger,
    )

    try:
        session = await manager.create_session(
            session_id="agent-locked-ledger",
            run_id="run-locked-ledger",
        )
        await session.submit("Replay while the ledger is locked.")
        await session.wait_for_event(AgentEventType.TURN_COMPLETE)

        replayed = await session.durable_replay()
        history = await session.durable_history(include_system=False)

        assert [event["type"] for event in replayed][-1] == "turn_complete"
        assert [message["role"] for message in history] == ["user", "assistant"]
        assert history[-1]["content"] == "Live memory is available."
        assert session._ledger_event_index == 0
    finally:
        await manager.close_all()


@pytest.mark.asyncio
async def test_agent_gateway_session_approve_resumes_gated_tool() -> None:
    """Approval operations should resume a paused tool call through the runtime queue."""
    handler_calls = []

    async def handler(arguments, context):
        handler_calls.append(arguments)
        return AgentToolResult.ok("approved tool result", payload={"approved": True})

    tool_call = AgentToolCall(
        id="gateway-tool-call",
        name="hal_test_tool",
        arguments={"topic": "phase stability"},
    )
    model = ScriptedModelClient(
        [
            AgentModelResponse(tool_calls=[tool_call]),
            AgentModelResponse(content="Tool approved and complete."),
        ]
    )
    manager = AgentGatewaySessionManager(
        model_client_factory=lambda _payload: model,
        tool_router_factory=lambda _payload: AgentToolRouter(
            [
                AgentToolSpec(
                    name="hal_test_tool",
                    description="Test approval-gated HAL tool.",
                    parameters={"type": "object"},
                    handler=handler,
                    requires_approval=True,
                )
            ]
        ),
    )

    try:
        session = await manager.create_session(session_id="agent-approval")
        await session.submit("Use the gated tool.")
        approval = await session.wait_for_event(AgentEventType.APPROVAL_REQUIRED)

        await session.approve(
            approval.data["approval_id"],
            actor="reviewer@example.com",
            reason="Within policy.",
        )
        complete = await session.wait_for_event(AgentEventType.TURN_COMPLETE)

        event_types = [event["type"] for event in session.replay()]
        assert handler_calls == [{"topic": "phase stability"}]
        assert complete.data["final_response"] == "Tool approved and complete."
        assert "tool_state_change" in event_types
        assert "tool_output" in event_types
    finally:
        await manager.close_all()


@pytest.mark.asyncio
async def test_agent_gateway_session_interrupt_cancels_active_turn() -> None:
    """Interrupt should cancel the active model request through the runtime."""
    model = WaitingModelClient()
    manager = AgentGatewaySessionManager(
        model_client_factory=lambda _payload: model,
        tool_router_factory=_empty_router,
    )

    try:
        session = await manager.create_session(session_id="agent-interrupt")
        await session.submit("Keep working.")
        await asyncio.wait_for(model.called.wait(), timeout=1.0)

        await session.interrupt(actor="reviewer@example.com", reason="Stop.")
        interrupted = await session.wait_for_event(AgentEventType.INTERRUPTED)

        assert model.cancelled is True
        assert interrupted.type == AgentEventType.INTERRUPTED
        assert session.runtime.is_processing is False
    finally:
        await manager.close_all()


@pytest.mark.asyncio
async def test_agent_session_command_handler_exposes_create_submit_replay_and_history() -> None:
    """The default gateway router should expose agent sessions via command messages."""
    model = ScriptedModelClient([AgentModelResponse(content="Command path complete.")])
    manager = AgentGatewaySessionManager(
        model_client_factory=lambda _payload: model,
        tool_router_factory=_empty_router,
    )
    router = create_router_with_defaults(agent_session_manager=manager)
    gateway_session = Session(id="gateway-command", user_id="user@example.com")

    try:
        create_responses = await _route(
            router,
            gateway_session,
            {
                "action": "agent.create",
                "agent_session_id": "agent-command",
            },
        )
        assert create_responses[0].payload["agent_session"]["id"] == "agent-command"
        assert create_responses[0].payload["events"][0]["type"] == "ready"

        submit_responses = await _route(
            router,
            gateway_session,
            {
                "action": "agent.submit",
                "agent_session_id": "agent-command",
                "text": "Finish through command handler.",
            },
        )
        assert submit_responses[0].payload["accepted"] is True

        agent_session = manager.get_session("agent-command")
        assert agent_session is not None
        await agent_session.wait_for_event(AgentEventType.TURN_COMPLETE)

        replay_responses = await _route(
            router,
            gateway_session,
            {
                "action": "agent.replay",
                "agent_session_id": "agent-command",
                "after_sequence": 1,
            },
        )
        history_responses = await _route(
            router,
            gateway_session,
            {
                "action": "agent.history",
                "agent_session_id": "agent-command",
                "include_system": False,
            },
        )

        assert [event["type"] for event in replay_responses[0].payload["events"]] == [
            "processing",
            "assistant_message",
            "turn_complete",
        ]
        assert history_responses[0].payload["messages"][-1]["content"] == (
            "Command path complete."
        )
    finally:
        await manager.close_all()


@pytest.mark.asyncio
async def test_hal_gateway_websocket_exposes_agent_session_commands() -> None:
    """The running WebSocket gateway should route agent session commands by default."""
    model = ScriptedModelClient([AgentModelResponse(content="WebSocket path complete.")])
    manager = AgentGatewaySessionManager(
        model_client_factory=lambda _payload: model,
        tool_router_factory=_empty_router,
    )
    gateway = HALGateway(
        host="127.0.0.1",
        port=0,
        agent_session_manager=manager,
    )
    await gateway.start()
    port = gateway._server.sockets[0].getsockname()[1]  # type: ignore

    try:
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            await ws.send(
                GatewayMessage(
                    type=MessageType.COMMAND,
                    session_id="placeholder",
                    payload={
                        "action": "agent.create",
                        "agent_session_id": "agent-ws",
                    },
                ).to_json()
            )
            create_response = GatewayMessage.from_json(await ws.recv())
            assert create_response.payload["events"][0]["type"] == "ready"

            await ws.send(
                GatewayMessage(
                    type=MessageType.COMMAND,
                    session_id="placeholder",
                    payload={
                        "action": "agent.submit",
                        "agent_session_id": "agent-ws",
                        "text": "Finish through WebSocket.",
                    },
                ).to_json()
            )
            submit_response = GatewayMessage.from_json(await ws.recv())
            assert submit_response.payload["accepted"] is True

            agent_session = manager.get_session("agent-ws")
            assert agent_session is not None
            await agent_session.wait_for_event(AgentEventType.TURN_COMPLETE)

            await ws.send(
                GatewayMessage(
                    type=MessageType.COMMAND,
                    session_id="placeholder",
                    payload={
                        "action": "agent.replay",
                        "agent_session_id": "agent-ws",
                        "after_sequence": 1,
                    },
                ).to_json()
            )
            replay_response = GatewayMessage.from_json(await ws.recv())

            assert replay_response.session_id == create_response.session_id
            assert replay_response.payload["events"][-1]["type"] == "turn_complete"
    finally:
        await gateway.stop()


@pytest.mark.asyncio
async def test_agent_gateway_replay_recovers_from_run_ledger_after_restart(
    temp_directory,
) -> None:
    """Replay/history should recover from run-ledger events without a live runtime."""
    db_url = f"sqlite:///{temp_directory / 'agent_gateway_ledger.db'}"
    _, session_factory = init_db(db_url)
    db = session_factory()
    try:
        store = ResearchStore(db)
        run = store.create_run("Durable gateway replay.")
        db.commit()
        run_id = run.id
    finally:
        db.close()

    model = ScriptedModelClient([AgentModelResponse(content="Durable response.")])
    manager = AgentGatewaySessionManager(
        settings=SimpleNamespace(database=SimpleNamespace(url=db_url)),
        model_client_factory=lambda _payload: model,
        tool_router_factory=_empty_router,
    )

    session = await manager.create_session(
        session_id="agent-durable",
        run_id=run_id,
        user_id="user@example.com",
    )
    await session.submit("Persist this turn.")
    await session.wait_for_event(AgentEventType.TURN_COMPLETE)
    await session.flush_ledger()
    await manager.close_all()

    db = session_factory()
    try:
        stored_run = ResearchStore(db).get_run(run_id)
        stored_events = ResearchStore(db).list_run_events(stored_run)
        agent_events = [
            event
            for event in stored_events
            if event.event_type == AGENT_GATEWAY_EVENT_TYPE
        ]
        payload = json.loads(agent_events[-1].payload_json)

        event_types = [json.loads(event.payload_json)["event"]["type"] for event in agent_events]
        assert event_types[:4] == [
            "ready",
            "processing",
            "assistant_message",
            "turn_complete",
        ]
        assert event_types[-1] == "shutdown"
        assert payload["history"][-1]["content"] == "Durable response."
        assert payload["agent_session_id"] == "agent-durable"
    finally:
        db.close()

    restarted = AgentGatewaySessionManager(
        settings=SimpleNamespace(database=SimpleNamespace(url=db_url)),
        model_client_factory=lambda _payload: model,
        tool_router_factory=_empty_router,
    )
    snapshot, replayed = await restarted.replay_events(
        session_id="agent-durable",
        run_id=run_id,
        after_sequence=1,
    )
    _history_snapshot, history = await restarted.history(
        session_id="agent-durable",
        run_id=run_id,
        include_system=False,
    )

    assert restarted.session_count() == 0
    assert snapshot["id"] == "agent-durable"
    assert snapshot["is_running"] is False
    assert [event["type"] for event in replayed] == [
        "processing",
        "assistant_message",
        "turn_complete",
        "shutdown",
    ]
    assert [message["role"] for message in history] == ["user", "assistant"]
    assert history[-1]["content"] == "Durable response."


@pytest.mark.asyncio
async def test_agent_command_replay_and_history_fall_back_to_run_ledger(
    temp_directory,
) -> None:
    """Gateway command replay/history should work after a process restart."""
    db_url = f"sqlite:///{temp_directory / 'agent_command_ledger.db'}"
    _, session_factory = init_db(db_url)
    db = session_factory()
    try:
        store = ResearchStore(db)
        run = store.create_run("Command durable replay.")
        db.commit()
        run_id = run.id
    finally:
        db.close()

    ledger = AgentRunLedger(database_url=db_url)
    live_model = ScriptedModelClient([AgentModelResponse(content="Persisted command path.")])
    live_manager = AgentGatewaySessionManager(
        model_client_factory=lambda _payload: live_model,
        tool_router_factory=_empty_router,
        run_ledger=ledger,
    )
    live_session = await live_manager.create_session(
        session_id="agent-command-durable",
        run_id=run_id,
    )
    await live_session.submit("Persist command history.")
    await live_session.wait_for_event(AgentEventType.TURN_COMPLETE)
    await live_session.flush_ledger()
    await live_manager.close_all()

    restarted_manager = AgentGatewaySessionManager(
        settings=SimpleNamespace(database=SimpleNamespace(url=db_url)),
        model_client_factory=lambda _payload: live_model,
        tool_router_factory=_empty_router,
    )
    router = create_router_with_defaults(agent_session_manager=restarted_manager)
    gateway_session = Session(id="gateway-after-restart")

    replay_responses = await _route(
        router,
        gateway_session,
        {
            "action": "agent.replay",
            "agent_session_id": "agent-command-durable",
            "run_id": run_id,
            "after_sequence": 1,
        },
    )
    history_responses = await _route(
        router,
        gateway_session,
        {
            "action": "agent.history",
            "agent_session_id": "agent-command-durable",
            "run_id": run_id,
            "include_system": False,
        },
    )

    assert replay_responses[0].type == "response"
    assert restarted_manager.session_count() == 0
    assert replay_responses[0].payload["agent_session"]["is_running"] is False
    assert "turn_complete" in [
        event["type"] for event in replay_responses[0].payload["events"]
    ]
    assert replay_responses[0].payload["events"][-1]["type"] == "shutdown"
    assert history_responses[0].payload["messages"][-1]["content"] == (
        "Persisted command path."
    )


async def _route(router, session: Session, payload: dict[str, Any]) -> list[GatewayMessage]:
    message = GatewayMessage(
        type=MessageType.COMMAND,
        session_id=session.id,
        payload=payload,
    )
    responses = []
    async for response in router.route(message, session):
        responses.append(response)
    return responses
