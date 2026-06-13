"""Gateway-facing API for HAL agent sessions."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from hal9000.agent import (
    AgentContextWindow,
    AgentEvent,
    AgentEventType,
    AgentLoopConfig,
    AgentMessage,
    AgentModelClient,
    AgentOperation,
    AgentOperationType,
    AgentSessionRuntime,
    AgentToolContext,
    AgentToolRouter,
    LiteLLMAgentModelClient,
    LiteLLMModelConfig,
    create_hal_service_tool_router,
)
from hal9000.agent.events import utc_now
from hal9000.config import get_settings
from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.gateway.agent_ledger import AgentRunLedger, is_sqlite_database_locked
from hal9000.gateway.protocol import GatewayMessage
from hal9000.gateway.session import Session
from hal9000.security import create_secret_manager_from_settings

DEFAULT_AGENT_SYSTEM_PROMPT = (
    "You are HAL-9000, a careful research OS agent. Preserve provenance, respect "
    "HAL tool policy, and keep research outputs reviewable."
)

AgentModelClientFactory = Callable[[dict[str, Any]], AgentModelClient]
AgentToolRouterFactory = Callable[[dict[str, Any]], AgentToolRouter]
AgentToolContextFactory = Callable[[dict[str, Any]], AgentToolContext]
AgentLoopConfigFactory = Callable[[dict[str, Any]], AgentLoopConfig]


class AgentGatewayError(ValueError):
    """Gateway-shaped error for agent session operations."""

    def __init__(self, message: str, code: str = "AGENT_SESSION_ERROR"):
        """Initialize with a stable error code."""
        self.code = code
        super().__init__(message)


@dataclass
class AgentGatewaySession:
    """Owns one running HAL agent runtime for gateway clients."""

    id: str
    runtime: AgentSessionRuntime
    submission_queue: asyncio.Queue[AgentOperation]
    event_queue: asyncio.Queue[AgentEvent]
    gateway_session_id: str | None = None
    user_id: str | None = None
    run_id: str | None = None
    run_ledger: AgentRunLedger | None = None
    created_at: datetime = field(default_factory=utc_now)
    _runtime_task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _ledger_task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)
    _ledger_event_index: int = field(default=0, init=False, repr=False)
    _ledger_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)
    _ledger_errors: list[Exception] = field(default_factory=list, init=False, repr=False)

    def start(self) -> None:
        """Start the runtime submission loop."""
        if self._runtime_task is not None and not self._runtime_task.done():
            return
        self._runtime_task = asyncio.create_task(self.runtime.run(self.submission_queue))
        if self.run_ledger is not None and self.run_id:
            self._ledger_task = asyncio.create_task(self._mirror_events_to_ledger())

    @property
    def is_active(self) -> bool:
        """Return whether the runtime loop can accept operations."""
        return (
            self._runtime_task is not None
            and not self._runtime_task.done()
            and self.runtime.is_running
        )

    async def submit(self, text: str, metadata: dict[str, Any] | None = None) -> AgentOperation:
        """Submit user input to the agent runtime."""
        if not str(text or "").strip():
            raise AgentGatewayError("Agent submit requires non-empty text.", "EMPTY_SUBMISSION")
        return await self._put_operation(
            AgentOperation(
                type=AgentOperationType.USER_INPUT,
                data={"text": text, "metadata": metadata or {}},
            )
        )

    async def approve(
        self,
        approval_id: str,
        *,
        approved: bool | str = True,
        actor: str = "human",
        reason: str | None = None,
    ) -> AgentOperation:
        """Resolve a pending tool approval through the runtime operation queue."""
        if approval_id not in self.runtime.pending_tool_approvals:
            raise AgentGatewayError(
                f"Unknown or resolved approval: {approval_id}",
                "UNKNOWN_APPROVAL",
            )
        return await self._put_operation(
            AgentOperation(
                type=AgentOperationType.TOOL_APPROVAL,
                data={
                    "approval_id": approval_id,
                    "approved": _bool_value(approved),
                    "actor": actor,
                    "reason": reason,
                },
            )
        )

    async def interrupt(
        self,
        *,
        actor: str | None = None,
        reason: str | None = None,
    ) -> AgentOperation:
        """Request cancellation of the active turn."""
        return await self._put_operation(
            AgentOperation(
                type=AgentOperationType.INTERRUPT,
                data={"actor": actor, "reason": reason},
            )
        )

    async def compact(self, summary: str | None = None) -> AgentOperation:
        """Request context compaction using the supplied summary."""
        return await self._put_operation(
            AgentOperation(
                type=AgentOperationType.COMPACT,
                data={"summary": summary or "Prior turns summarized by gateway request."},
            )
        )

    async def shutdown(self, timeout: float = 2.0) -> None:
        """Stop the runtime loop."""
        if self._runtime_task is None:
            return
        if self._runtime_task.done():
            await self._runtime_task
            await self.flush_ledger()
            if self._ledger_task is not None and not self._ledger_task.done():
                self._ledger_task.cancel()
                await asyncio.gather(self._ledger_task, return_exceptions=True)
            self._close_tool_context()
            return

        await self.submission_queue.put(AgentOperation(type=AgentOperationType.SHUTDOWN))
        try:
            await asyncio.wait_for(self._runtime_task, timeout=timeout)
        except asyncio.TimeoutError:
            self._runtime_task.cancel()
            await asyncio.gather(self._runtime_task, return_exceptions=True)
        finally:
            await self.flush_ledger()
            if self._ledger_task is not None and not self._ledger_task.done():
                self._ledger_task.cancel()
                await asyncio.gather(self._ledger_task, return_exceptions=True)
            self._close_tool_context()

    def _close_tool_context(self) -> None:
        store = getattr(self.runtime.tool_context, "store", None)
        session = getattr(store, "session", None)
        close = getattr(session, "close", None)
        if callable(close):
            close()

    def replay(
        self,
        *,
        after_sequence: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Replay emitted agent events in sequence order."""
        events = self.runtime.emitted_events
        if after_sequence is not None:
            events = [
                event
                for event in events
                if event.sequence is not None and event.sequence > after_sequence
            ]
        if limit is not None:
            events = events[: max(0, limit)]
        return [event.to_dict() for event in events]

    async def durable_replay(
        self,
        *,
        after_sequence: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Replay live events first, falling back to the run ledger after shutdown."""
        if self.run_ledger is None or not self.run_id:
            return self.replay(after_sequence=after_sequence, limit=limit)

        if self._runtime_task is not None and not self._runtime_task.done():
            return self.replay(after_sequence=after_sequence, limit=limit)

        await self.flush_ledger()
        try:
            events = self.run_ledger.replay_events(
                run_id=self.run_id,
                agent_session_id=self.id,
                after_sequence=after_sequence,
                limit=limit,
            )
        except Exception as exc:
            self._ledger_errors.append(exc)
            if is_sqlite_database_locked(exc):
                return self.replay(after_sequence=after_sequence, limit=limit)
            raise
        return events or self.replay(after_sequence=after_sequence, limit=limit)

    def history(self, *, include_system: bool = True) -> list[dict[str, Any]]:
        """Return the HAL-owned conversation history for this agent session."""
        messages = self.runtime.context.provider_messages()
        if include_system:
            return messages
        return [message for message in messages if message.get("role") != "system"]

    async def durable_history(self, *, include_system: bool = True) -> list[dict[str, Any]]:
        """Return live history first, falling back to the run ledger after shutdown."""
        if self.run_ledger is None or not self.run_id:
            return self.history(include_system=include_system)

        if self._runtime_task is not None and not self._runtime_task.done():
            return self.history(include_system=include_system)

        await self.flush_ledger()
        try:
            history = self.run_ledger.latest_history(
                run_id=self.run_id,
                agent_session_id=self.id,
                include_system=include_system,
            )
        except Exception as exc:
            self._ledger_errors.append(exc)
            if is_sqlite_database_locked(exc):
                return self.history(include_system=include_system)
            raise
        return history or self.history(include_system=include_system)

    async def next_event(self, timeout: float | None = None) -> AgentEvent:
        """Return the next queued event without changing replay history."""
        if timeout is None:
            return await self.event_queue.get()
        return await asyncio.wait_for(self.event_queue.get(), timeout=timeout)

    async def wait_for_event(
        self,
        event_type: AgentEventType | str,
        timeout: float = 1.0,
    ) -> AgentEvent:
        """Wait until a matching event appears on the live event queue."""
        expected = _event_type_value(event_type)
        while True:
            event = await self.next_event(timeout=timeout)
            if _event_type_value(event.type) == expected:
                return event

    def snapshot(self) -> dict[str, Any]:
        """Return a compact, JSON-serializable session snapshot."""
        last_sequence = self.runtime.emitted_events[-1].sequence if self.runtime.emitted_events else None
        return {
            "id": self.id,
            "gateway_session_id": self.gateway_session_id,
            "user_id": self.user_id,
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "is_running": self.runtime.is_running,
            "is_processing": self.runtime.is_processing,
            "event_count": len(self.runtime.emitted_events),
            "last_sequence": last_sequence,
            "history_size": len(self.runtime.context.messages),
            "pending_approvals": [
                request.to_event_data()
                for request in self.runtime.pending_tool_approvals.values()
            ],
        }

    async def _put_operation(self, operation: AgentOperation) -> AgentOperation:
        if not self.is_active:
            raise AgentGatewayError("Agent session is closed.", "SESSION_CLOSED")
        await self.submission_queue.put(operation)
        return operation

    async def flush_ledger(self) -> int:
        """Persist any live events not yet mirrored to the run ledger."""
        if self.run_ledger is None or not self.run_id:
            return 0

        async with self._ledger_lock:
            persisted = 0
            while self._ledger_event_index < len(self.runtime.emitted_events):
                event = self.runtime.emitted_events[self._ledger_event_index]
                try:
                    recorded = self.run_ledger.record_event(self, event)
                except Exception as exc:
                    self._ledger_errors.append(exc)
                    if is_sqlite_database_locked(exc):
                        break
                    raise
                if recorded:
                    persisted += 1
                self._ledger_event_index += 1
            return persisted

    async def _mirror_events_to_ledger(self) -> None:
        """Background mirror from live runtime memory into HAL's run ledger."""
        while True:
            try:
                await self.flush_ledger()
            except Exception as exc:
                self._ledger_errors.append(exc)
            if self._runtime_task is not None and self._runtime_task.done():
                break
            await asyncio.sleep(0.05)


class AgentGatewaySessionManager:
    """Creates and tracks gateway-accessible HAL agent sessions."""

    def __init__(
        self,
        *,
        settings: Any | None = None,
        model_client_factory: AgentModelClientFactory | None = None,
        tool_router_factory: AgentToolRouterFactory | None = None,
        tool_context_factory: AgentToolContextFactory | None = None,
        loop_config_factory: AgentLoopConfigFactory | None = None,
        run_ledger: AgentRunLedger | None = None,
        database_url: str | None = None,
        enable_run_ledger: bool = True,
        ready_timeout_seconds: float = 1.0,
    ):
        """Initialize the manager with injectable factories for tests and deployments."""
        self.settings = settings or get_settings()
        self.model_client_factory = model_client_factory or self._default_model_client
        self.tool_router_factory = tool_router_factory or self._default_tool_router
        self.tool_context_factory = tool_context_factory or self._default_tool_context
        self.loop_config_factory = loop_config_factory or self._default_loop_config
        self._run_ledger = run_ledger
        database_settings = getattr(self.settings, "database", None)
        settings_database_url = getattr(database_settings, "url", None)
        if database_url:
            self._database_url = database_url
            self._session_factory = init_db(database_url)[1]
        elif run_ledger is not None:
            self._database_url = None
            self._session_factory = getattr(run_ledger, "_session_factory", None)
        else:
            self._database_url = settings_database_url
            self._session_factory = init_db(settings_database_url)[1] if settings_database_url else None
        self._enable_run_ledger = enable_run_ledger
        self.ready_timeout_seconds = ready_timeout_seconds
        self._sessions: dict[str, AgentGatewaySession] = {}

    async def create_session(
        self,
        *,
        session_id: str | None = None,
        gateway_session_id: str | None = None,
        user_id: str | None = None,
        run_id: str | None = None,
        system_prompt: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentGatewaySession:
        """Create, start, and return one HAL agent session."""
        agent_session_id = session_id or str(uuid.uuid4())
        if agent_session_id in self._sessions:
            raise AgentGatewayError(
                f"Agent session already exists: {agent_session_id}",
                "SESSION_EXISTS",
            )

        create_payload = {
            "session_id": agent_session_id,
            "gateway_session_id": gateway_session_id,
            "user_id": user_id,
            "run_id": run_id,
            "system_prompt": system_prompt or DEFAULT_AGENT_SYSTEM_PROMPT,
            "metadata": metadata or {},
        }
        context = AgentContextWindow(
            create_payload["system_prompt"],
            messages=_agent_messages(messages),
        )
        event_queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        tool_context = self.tool_context_factory(create_payload)
        if tool_context.session_id is None:
            tool_context.session_id = agent_session_id
        if tool_context.run is not None and not create_payload.get("run_id"):
            create_payload["run_id"] = str(tool_context.run.id)
        runtime = AgentSessionRuntime(
            context=context,
            model_client=self.model_client_factory(create_payload),
            tool_router=self.tool_router_factory(create_payload),
            tool_context=tool_context,
            event_queue=event_queue,
            config=self.loop_config_factory(create_payload),
        )
        session = AgentGatewaySession(
            id=agent_session_id,
            runtime=runtime,
            submission_queue=asyncio.Queue(),
            event_queue=event_queue,
            gateway_session_id=gateway_session_id,
            user_id=user_id,
            run_id=create_payload.get("run_id"),
            run_ledger=self._resolve_run_ledger() if create_payload.get("run_id") else None,
        )
        self._sessions[agent_session_id] = session
        session.start()
        try:
            await session.wait_for_event(
                AgentEventType.READY,
                timeout=self.ready_timeout_seconds,
            )
        except Exception:
            self._sessions.pop(agent_session_id, None)
            await session.shutdown()
            raise
        return session

    def get_session(self, session_id: str) -> AgentGatewaySession | None:
        """Return an agent session by ID."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[AgentGatewaySession]:
        """Return all tracked agent sessions."""
        return list(self._sessions.values())

    def session_count(self) -> int:
        """Return the number of tracked agent sessions."""
        return len(self._sessions)

    async def replay_events(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        after_sequence: int | None = None,
        limit: int | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Replay live or durable events for an agent session."""
        if session_id:
            session = self.get_session(session_id)
            if session is not None:
                return (
                    session.snapshot(),
                    await session.durable_replay(
                        after_sequence=after_sequence,
                        limit=limit,
                    ),
                )

        if not run_id:
            raise AgentGatewayError(
                "run_id is required when replaying a non-live agent session.",
                "MISSING_RUN_ID",
            )
        ledger = self._require_run_ledger()
        snapshot = ledger.latest_session_snapshot(
            run_id=run_id,
            agent_session_id=session_id,
        )
        events = ledger.replay_events(
            run_id=run_id,
            agent_session_id=session_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        return snapshot, events

    async def history(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        include_system: bool = True,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Return live or durable history for an agent session."""
        if session_id:
            session = self.get_session(session_id)
            if session is not None:
                return (
                    session.snapshot(),
                    await session.durable_history(include_system=include_system),
                )

        if not run_id:
            raise AgentGatewayError(
                "run_id is required when reading a non-live agent session history.",
                "MISSING_RUN_ID",
            )
        ledger = self._require_run_ledger()
        snapshot = ledger.latest_session_snapshot(
            run_id=run_id,
            agent_session_id=session_id,
        )
        history = ledger.latest_history(
            run_id=run_id,
            agent_session_id=session_id,
            include_system=include_system,
        )
        return snapshot, history

    async def close_session(self, session_id: str) -> bool:
        """Close and remove one agent session."""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        await session.shutdown()
        return True

    async def close_gateway_sessions(self, gateway_session_id: str) -> int:
        """Close agent sessions associated with one gateway connection session."""
        session_ids = [
            session.id
            for session in self._sessions.values()
            if session.gateway_session_id == gateway_session_id
        ]
        for session_id in session_ids:
            await self.close_session(session_id)
        return len(session_ids)

    async def close_all(self) -> int:
        """Close all tracked agent sessions."""
        session_ids = list(self._sessions)
        for session_id in session_ids:
            await self.close_session(session_id)
        return len(session_ids)

    def _default_model_client(self, payload: dict[str, Any]) -> AgentModelClient:
        metadata = dict(payload.get("metadata") or {})
        model_name = _optional_str(metadata.get("model_name") or metadata.get("model"))
        reasoning_effort = _optional_str(
            metadata.get("reasoning_effort") or metadata.get("reasoning")
        )
        if not model_name and reasoning_effort is None:
            return LiteLLMAgentModelClient.from_settings(self.settings)

        agent = self.settings.agent
        return LiteLLMAgentModelClient(
            LiteLLMModelConfig(
                model_name=model_name or agent.model_name,
                reasoning_effort=reasoning_effort if reasoning_effort != "" else None,
                max_tokens=agent.max_tokens,
                timeout_seconds=agent.timeout_seconds,
                max_retries=agent.max_retries,
                hf_router_base_url=agent.hf_router_base_url,
                secret_manager=create_secret_manager_from_settings(self.settings),
            )
        )

    def _default_tool_router(self, _payload: dict[str, Any]) -> AgentToolRouter:
        return create_hal_service_tool_router()

    def _default_tool_context(self, payload: dict[str, Any]) -> AgentToolContext:
        metadata = dict(payload.get("metadata") or {})
        actor = str(payload.get("user_id") or "hal-agent")
        metadata.setdefault("secret_manager", create_secret_manager_from_settings(self.settings))
        metadata.setdefault("settings", self.settings)
        store = None
        run = None
        if self._session_factory is not None:
            db_session = self._session_factory()
            store = ResearchStore(db_session)
            run = self._resolve_tool_context_run(store, payload, metadata, actor=actor)
        return AgentToolContext(
            store=store,
            run=run,
            actor=actor,
            session_id=str(payload["session_id"]),
            metadata=metadata,
        )

    def _resolve_tool_context_run(
        self,
        store: ResearchStore,
        payload: dict[str, Any],
        metadata: dict[str, Any],
        *,
        actor: str,
    ):
        run_id = _optional_str(payload.get("run_id") or metadata.get("run_id"))
        if run_id:
            run = store.get_run(run_id)
            if run is None:
                raise AgentGatewayError(f"Research run not found: {run_id}", "RUN_NOT_FOUND")
            return run

        project_slug = _optional_str(metadata.get("project_slug") or payload.get("project_slug"))
        if not project_slug:
            return None
        project = store.get_project_by_slug(project_slug)
        if project is None:
            raise AgentGatewayError(
                f"Research project not found: {project_slug}",
                "PROJECT_NOT_FOUND",
            )
        objective = _optional_str(metadata.get("objective")) or f"Agent session {payload['session_id']}"
        run = store.create_run(objective=objective, project=project, initiated_by=actor)
        store.session.commit()
        return run

    def _default_loop_config(self, _payload: dict[str, Any]) -> AgentLoopConfig:
        if not hasattr(self.settings, "agent"):
            return AgentLoopConfig()
        return AgentLoopConfig.from_settings(self.settings)

    def _resolve_run_ledger(self) -> AgentRunLedger | None:
        if not self._enable_run_ledger:
            return None
        if self._run_ledger is None and self._database_url:
            self._run_ledger = AgentRunLedger(database_url=self._database_url)
        return self._run_ledger

    def _require_run_ledger(self) -> AgentRunLedger:
        ledger = self._resolve_run_ledger()
        if ledger is None:
            raise AgentGatewayError(
                "Agent run ledger is not configured.",
                "RUN_LEDGER_UNAVAILABLE",
            )
        return ledger


def create_agent_session_command_handler(
    manager: AgentGatewaySessionManager,
) -> Callable[[GatewayMessage, Session], AsyncGenerator[GatewayMessage, None]]:
    """Create a router handler for gateway agent-session commands."""

    async def handler(
        message: GatewayMessage,
        session: Session,
    ) -> AsyncGenerator[GatewayMessage, None]:
        action = _normalize_action(message.payload.get("action"))
        try:
            payload = await _dispatch_agent_command(manager, action, message.payload, session)
            yield GatewayMessage.create_response(
                session_id=session.id,
                payload=payload,
                metadata={"original_id": message.id, "action": action},
            )
        except AgentGatewayError as exc:
            yield GatewayMessage.create_error(
                session_id=session.id,
                error=str(exc),
                code=exc.code,
                metadata={"original_id": message.id, "action": action},
            )

    return handler


async def _dispatch_agent_command(
    manager: AgentGatewaySessionManager,
    action: str,
    payload: dict[str, Any],
    gateway_session: Session,
) -> dict[str, Any]:
    if action == "create":
        agent_session = await manager.create_session(
            session_id=_optional_str(payload.get("agent_session_id") or payload.get("id")),
            gateway_session_id=gateway_session.id,
            user_id=_optional_str(payload.get("user_id") or gateway_session.user_id),
            run_id=_optional_str(payload.get("run_id")),
            system_prompt=_optional_str(payload.get("system_prompt")),
            messages=_optional_messages(payload.get("messages")),
            metadata=dict(payload.get("metadata") or {}),
        )
        return {
            "action": "agent.create",
            "agent_session": agent_session.snapshot(),
            "events": agent_session.replay(),
        }

    if action == "submit":
        agent_session = _require_agent_session(manager, payload)
        operation = await agent_session.submit(
            str(payload.get("text") or payload.get("content") or ""),
            metadata=dict(payload.get("metadata") or {}),
        )
        return _operation_response("agent.submit", agent_session, operation)

    if action == "approve":
        agent_session = _require_agent_session(manager, payload)
        operation = await agent_session.approve(
            str(payload.get("approval_id") or payload.get("id") or ""),
            approved=payload.get("approved", payload.get("status", True)),
            actor=str(payload.get("actor") or gateway_session.user_id or "human"),
            reason=_optional_str(payload.get("reason")),
        )
        return _operation_response("agent.approve", agent_session, operation)

    if action == "interrupt":
        agent_session = _require_agent_session(manager, payload)
        operation = await agent_session.interrupt(
            actor=_optional_str(payload.get("actor") or gateway_session.user_id),
            reason=_optional_str(payload.get("reason")),
        )
        return _operation_response("agent.interrupt", agent_session, operation)

    if action == "compact":
        agent_session = _require_agent_session(manager, payload)
        operation = await agent_session.compact(_optional_str(payload.get("summary")))
        return _operation_response("agent.compact", agent_session, operation)

    if action == "replay":
        snapshot, events = await manager.replay_events(
            session_id=_optional_str(payload.get("agent_session_id") or payload.get("id")),
            run_id=_optional_str(payload.get("run_id")),
            after_sequence=_optional_int(payload.get("after_sequence"), "after_sequence"),
            limit=_optional_int(payload.get("limit"), "limit"),
        )
        return {
            "action": "agent.replay",
            "agent_session": snapshot,
            "events": events,
        }

    if action == "history":
        include_system = _bool_value(payload.get("include_system", True))
        snapshot, messages = await manager.history(
            session_id=_optional_str(payload.get("agent_session_id") or payload.get("id")),
            run_id=_optional_str(payload.get("run_id")),
            include_system=include_system,
        )
        return {
            "action": "agent.history",
            "agent_session": snapshot,
            "messages": messages,
        }

    raise AgentGatewayError(
        f"Unknown agent command action: {payload.get('action')}",
        "UNKNOWN_AGENT_ACTION",
    )


def _operation_response(
    action: str,
    session: AgentGatewaySession,
    operation: AgentOperation,
) -> dict[str, Any]:
    return {
        "action": action,
        "accepted": True,
        "operation": {
            "id": operation.id,
            "type": operation.type.value,
            "created_at": operation.created_at.isoformat(),
        },
        "agent_session": session.snapshot(),
    }


def _require_agent_session(
    manager: AgentGatewaySessionManager,
    payload: dict[str, Any],
) -> AgentGatewaySession:
    session_id = _optional_str(payload.get("agent_session_id") or payload.get("id"))
    if not session_id:
        raise AgentGatewayError("agent_session_id is required.", "MISSING_AGENT_SESSION_ID")
    session = manager.get_session(session_id)
    if session is None:
        raise AgentGatewayError(f"Unknown agent session: {session_id}", "UNKNOWN_AGENT_SESSION")
    return session


def _normalize_action(raw_action: Any) -> str:
    action = str(raw_action or "").strip().lower().replace("_", ".")
    aliases = {
        "agent.create": "create",
        "session.create": "create",
        "create": "create",
        "agent.submit": "submit",
        "session.submit": "submit",
        "submit": "submit",
        "agent.approve": "approve",
        "session.approve": "approve",
        "approve": "approve",
        "agent.interrupt": "interrupt",
        "session.interrupt": "interrupt",
        "interrupt": "interrupt",
        "agent.compact": "compact",
        "session.compact": "compact",
        "compact": "compact",
        "agent.replay": "replay",
        "session.replay": "replay",
        "replay": "replay",
        "agent.history": "history",
        "session.history": "history",
        "history": "history",
    }
    return aliases.get(action, action)


def _agent_messages(messages: list[dict[str, Any]] | None) -> list[AgentMessage] | None:
    if messages is None:
        return None
    return [AgentMessage.from_dict(message) for message in messages]


def _optional_messages(value: Any) -> list[dict[str, Any]] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise AgentGatewayError("messages must be a list.", "INVALID_MESSAGES")
    return [dict(item) for item in value]


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AgentGatewayError(
            f"{field_name} must be an integer.",
            "INVALID_AGENT_COMMAND",
        ) from exc


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "approve"}
    return bool(value)


def _event_type_value(event_type: AgentEventType | str) -> str:
    return event_type.value if isinstance(event_type, AgentEventType) else str(event_type)
