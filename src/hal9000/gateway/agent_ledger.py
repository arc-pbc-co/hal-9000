"""Durable run-ledger mirror for gateway agent events."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session as DBSession

from hal9000.agent import AgentEvent
from hal9000.db.models import ResearchRunEvent, init_db
from hal9000.db.store import ResearchStore

AGENT_GATEWAY_EVENT_TYPE = "agent.gateway.event"


class AgentRunLedger:
    """Persist and replay gateway agent events through `ResearchRunEvent`."""

    def __init__(
        self,
        *,
        database_url: str | None = None,
        session_factory: Callable[[], DBSession] | None = None,
    ):
        """Initialize a ledger backed by a database URL or SQLAlchemy session factory."""
        if session_factory is None:
            if database_url is None:
                raise ValueError("AgentRunLedger requires database_url or session_factory.")
            _, session_factory = init_db(database_url)
        self._session_factory = session_factory

    @classmethod
    def from_settings(cls, settings) -> AgentRunLedger:
        """Create a run ledger from HAL settings."""
        return cls(database_url=settings.database.url)

    def record_event(self, gateway_session, event: AgentEvent) -> bool:
        """Append one gateway agent event to the attached research run ledger."""
        if not gateway_session.run_id:
            return False

        event_payload = event.to_dict()
        db = self._session_factory()
        try:
            store = ResearchStore(db)
            run = store.get_run(gateway_session.run_id)
            if run is None:
                return False
            if self._event_exists(db, run.id, gateway_session.id, event_payload["id"]):
                return False

            payload = {
                "kind": "agent_event",
                "agent_session_id": gateway_session.id,
                "gateway_session_id": gateway_session.gateway_session_id,
                "user_id": gateway_session.user_id,
                "run_id": gateway_session.run_id,
                "event": event_payload,
                "session": gateway_session.snapshot(),
                "history": gateway_session.history(),
            }
            store.append_run_event(
                run,
                event_type=AGENT_GATEWAY_EVENT_TYPE,
                message=f"Agent event emitted: {event_payload['type']}",
                actor=gateway_session.user_id or "hal-agent",
                payload=payload,
            )
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def replay_events(
        self,
        *,
        run_id: str,
        agent_session_id: str | None = None,
        after_sequence: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Replay persisted `AgentEvent` payloads for a run/session."""
        events: list[dict[str, Any]] = []
        for payload in self._iter_agent_payloads(run_id, agent_session_id):
            event = payload.get("event")
            if not isinstance(event, dict):
                continue
            sequence = event.get("sequence")
            if after_sequence is not None and (
                not isinstance(sequence, int) or sequence <= after_sequence
            ):
                continue
            events.append(event)
            if limit is not None and len(events) >= max(0, limit):
                break
        return events

    def latest_history(
        self,
        *,
        run_id: str,
        agent_session_id: str | None = None,
        include_system: bool = True,
    ) -> list[dict[str, Any]]:
        """Return the latest persisted context history snapshot for a run/session."""
        latest: list[dict[str, Any]] = []
        for payload in self._iter_agent_payloads(run_id, agent_session_id):
            history = payload.get("history")
            if isinstance(history, list):
                latest = [dict(message) for message in history if isinstance(message, dict)]
        if include_system:
            return latest
        return [message for message in latest if message.get("role") != "system"]

    def latest_session_snapshot(
        self,
        *,
        run_id: str,
        agent_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the latest persisted gateway-agent session snapshot."""
        latest: dict[str, Any] = {}
        event_count = 0
        last_sequence = None
        for payload in self._iter_agent_payloads(run_id, agent_session_id):
            event_count += 1
            event = payload.get("event")
            if isinstance(event, dict):
                last_sequence = event.get("sequence")
            session = payload.get("session")
            if isinstance(session, dict):
                latest = dict(session)
        if latest:
            latest["is_running"] = False
            latest["is_processing"] = False
            return latest
        return {
            "id": agent_session_id,
            "run_id": run_id,
            "is_running": False,
            "is_processing": False,
            "event_count": event_count,
            "last_sequence": last_sequence,
            "pending_approvals": [],
        }

    def _iter_agent_payloads(
        self,
        run_id: str,
        agent_session_id: str | None,
    ) -> list[dict[str, Any]]:
        db = self._session_factory()
        try:
            records = (
                db.query(ResearchRunEvent)
                .filter_by(run_id=run_id, event_type=AGENT_GATEWAY_EVENT_TYPE)
                .order_by(ResearchRunEvent.sequence)
                .all()
            )
            payloads = []
            for record in records:
                payload = _json_object(record.payload_json)
                if payload.get("kind") != "agent_event":
                    continue
                if agent_session_id and payload.get("agent_session_id") != agent_session_id:
                    continue
                payloads.append(payload)
            return payloads
        finally:
            db.close()

    def _event_exists(
        self,
        db: DBSession,
        run_id: str,
        agent_session_id: str,
        event_id: str,
    ) -> bool:
        records = (
            db.query(ResearchRunEvent)
            .filter_by(run_id=run_id, event_type=AGENT_GATEWAY_EVENT_TYPE)
            .all()
        )
        for record in records:
            payload = _json_object(record.payload_json)
            event = payload.get("event")
            if (
                payload.get("agent_session_id") == agent_session_id
                and isinstance(event, dict)
                and event.get("id") == event_id
            ):
                return True
        return False


def is_sqlite_database_locked(exc: BaseException) -> bool:
    """Return whether an exception chain represents SQLite lock contention."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current).lower()
        if "database is locked" in message or "database table is locked" in message:
            return True
        current = (
            getattr(current, "orig", None)
            or getattr(current, "__cause__", None)
            or getattr(current, "__context__", None)
        )
    return False


def _json_object(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
