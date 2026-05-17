"""HTTP app gateway routes for Slack and Sheets-facing integrations."""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy import text

from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.gateway.agent_session import AgentGatewayError, AgentGatewaySessionManager
from hal9000.gateway.frontend import (
    frontend_config_payload,
    frontend_evidence_payload,
    frontend_graph_payload,
    frontend_html,
    frontend_review_payload,
)
from hal9000.research.sheets import SheetsWritebackService
from hal9000.research.slack_app import SlackAppService, verify_slack_signature
from hal9000.security import create_secret_manager_from_settings, secret_value


class GatewayHTTPError(Exception):
    """HTTP-shaped error for app gateway requests."""

    def __init__(self, status: HTTPStatus, message: str):
        """Initialize with status and message."""
        self.status = status
        self.message = message
        super().__init__(message)


def create_gateway_http_handler(
    settings,
    slack_signing_secret: str | None = None,
    agent_session_manager: AgentGatewaySessionManager | None = None,
):
    """Create an app gateway HTTP handler bound to HAL settings."""
    secret_manager = create_secret_manager_from_settings(settings)
    signing_secret = (
        slack_signing_secret
        or secret_value("slack", secret_manager=secret_manager)
    )
    agent_manager = agent_session_manager or AgentGatewaySessionManager(settings=settings)
    agent_bridge = _AgentHTTPBridge(agent_manager)

    class GatewayHTTPRequestHandler(BaseHTTPRequestHandler):
        """HTTP handler for Slack and future app-webhook routes."""

        server_version = "HALAppGateway/0.1"

        def do_GET(self) -> None:
            """Handle read endpoints."""
            try:
                parsed = urlparse(self.path)
                if parsed.path in {"/", "/ui"}:
                    self._send_html(frontend_html())
                    return
                if parsed.path == "/health":
                    self._send_json({"status": "ok", "service": "hal-app-gateway"})
                    return
                if parsed.path == "/ready":
                    payload = self._readiness_payload()
                    status = (
                        HTTPStatus.OK
                        if payload["status"] == "ready"
                        else HTTPStatus.SERVICE_UNAVAILABLE
                    )
                    self._send_json(payload, status=status)
                    return
                if parsed.path == "/api/frontend/config":
                    self._send_json(frontend_config_payload(settings))
                    return
                if parsed.path == "/api/frontend/review":
                    params = parse_qs(parsed.query)
                    self._with_store(
                        lambda store: self._send_json(
                            frontend_review_payload(
                                store,
                                reviewer=_required_query(params, "reviewer"),
                                project_slug=_optional_query(params, "project_slug"),
                                run_id=_optional_query(params, "run_id"),
                                limit=_query_int(params, "limit", 20),
                            )
                        )
                    )
                    return
                if parsed.path == "/api/frontend/evidence":
                    params = parse_qs(parsed.query)
                    self._with_store(
                        lambda store: self._send_json(
                            frontend_evidence_payload(
                                store,
                                viewer=_required_query(params, "viewer"),
                                run_id=_required_query(params, "run_id"),
                            )
                        )
                    )
                    return
                if parsed.path == "/api/frontend/graph":
                    params = parse_qs(parsed.query)
                    self._with_store(
                        lambda store: self._send_json(
                            frontend_graph_payload(
                                store,
                                viewer=_required_query(params, "viewer"),
                                project_slug=_optional_query(params, "project_slug"),
                                run_id=_optional_query(params, "run_id"),
                                limit=_query_int(params, "limit", 250),
                            )
                        )
                    )
                    return
                if parsed.path == "/api/agent/sessions":
                    self._send_json(agent_bridge.run(_agent_sessions_payload(agent_manager)))
                    return
                if parsed.path == "/api/agent/replay":
                    params = parse_qs(parsed.query)
                    self._send_json(
                        agent_bridge.run(
                            _agent_replay_payload(
                                agent_manager,
                                session_id=_optional_query(params, "agent_session_id")
                                or _optional_query(params, "id"),
                                run_id=_optional_query(params, "run_id"),
                                after_sequence=_query_optional_int(params, "after_sequence"),
                                limit=_query_optional_int(params, "limit"),
                            )
                        )
                    )
                    return
                if parsed.path == "/api/agent/history":
                    params = parse_qs(parsed.query)
                    self._send_json(
                        agent_bridge.run(
                            _agent_history_payload(
                                agent_manager,
                                session_id=_optional_query(params, "agent_session_id")
                                or _optional_query(params, "id"),
                                run_id=_optional_query(params, "run_id"),
                                include_system=_query_bool(params, "include_system", True),
                            )
                        )
                    )
                    return
                raise GatewayHTTPError(HTTPStatus.NOT_FOUND, f"Unknown path: {parsed.path}")
            except Exception as exc:
                self._send_error(exc)

        def do_POST(self) -> None:
            """Handle Slack app webhooks."""
            try:
                parsed = urlparse(self.path)
                raw_body = self._read_body()
                if parsed.path == "/api/agent/session":
                    payload = _json_object(raw_body.decode("utf-8"))
                    self._send_json(
                        agent_bridge.run(_agent_create_payload(agent_manager, payload)),
                        status=HTTPStatus.CREATED,
                    )
                    return
                if parsed.path == "/api/agent/submit":
                    payload = _json_object(raw_body.decode("utf-8"))
                    self._send_json(agent_bridge.run(_agent_submit_payload(agent_manager, payload)))
                    return
                if parsed.path == "/api/agent/approve":
                    payload = _json_object(raw_body.decode("utf-8"))
                    self._send_json(agent_bridge.run(_agent_approve_payload(agent_manager, payload)))
                    return
                if parsed.path == "/api/agent/interrupt":
                    payload = _json_object(raw_body.decode("utf-8"))
                    self._send_json(
                        agent_bridge.run(_agent_interrupt_payload(agent_manager, payload))
                    )
                    return
                if parsed.path == "/api/agent/compact":
                    payload = _json_object(raw_body.decode("utf-8"))
                    self._send_json(agent_bridge.run(_agent_compact_payload(agent_manager, payload)))
                    return
                if parsed.path == "/slack/command":
                    self._verify_slack_request(raw_body)
                    params = _form_params(raw_body)
                    text = _required_form(params, "text")
                    user_email = _slack_user_email(params)
                    self._with_store(
                        lambda store: self._send_json(
                            SlackAppService(store).handle_command(text, user_email).to_dict()
                        )
                    )
                    return
                if parsed.path in {"/slack/action", "/slack/actions"}:
                    self._verify_slack_request(raw_body)
                    params = _form_params(raw_body)
                    payload_raw = _required_form(params, "payload")
                    payload = _json_object(payload_raw)
                    self._with_store(
                        lambda store: self._send_json(
                            SlackAppService(store).handle_action(payload).to_dict()
                        )
                    )
                    return
                if parsed.path == "/slack/event":
                    self._verify_slack_request(raw_body)
                    payload = _json_object(raw_body.decode("utf-8"))
                    if payload.get("type") == "url_verification":
                        self._send_json(
                            {
                                "status": "ok",
                                "event_type": "url_verification",
                                "challenge": str(payload.get("challenge") or ""),
                            }
                        )
                        return
                    self._with_store(
                        lambda store: self._send_json(
                            SlackAppService(store).handle_event(payload).to_dict()
                        )
                    )
                    return
                if parsed.path == "/sheets/writeback":
                    self._verify_sheets_request()
                    payload = _json_object(raw_body.decode("utf-8"))
                    self._with_store(
                        lambda store: self._send_json(
                            SheetsWritebackService(store).handle_writeback(payload).to_dict(),
                            status=HTTPStatus.ACCEPTED,
                        )
                    )
                    return
                raise GatewayHTTPError(HTTPStatus.NOT_FOUND, f"Unknown path: {parsed.path}")
            except Exception as exc:
                self._send_error(exc)

        def log_message(self, format: str, *args) -> None:
            """Keep the default server quiet for CLI use."""
            return

        def _with_store(self, callback):
            _, session_local = init_db(settings.database.url)
            session = session_local()
            try:
                store = ResearchStore(session)
                result = callback(store)
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                raise GatewayHTTPError(HTTPStatus.BAD_REQUEST, "Request body is required")
            return self.rfile.read(length)

        def _verify_slack_request(self, body: bytes) -> None:
            if not signing_secret:
                return
            timestamp = self.headers.get("X-Slack-Request-Timestamp") or ""
            signature = self.headers.get("X-Slack-Signature") or ""
            if not verify_slack_signature(signing_secret, timestamp, body, signature):
                raise GatewayHTTPError(HTTPStatus.UNAUTHORIZED, "Invalid Slack signature")

        def _verify_sheets_request(self) -> None:
            if not _setting_bool(settings, "app_gateway.sheets_writeback_enabled"):
                raise GatewayHTTPError(
                    HTTPStatus.NOT_IMPLEMENTED,
                    "Sheets writeback is disabled; enable app_gateway.sheets_writeback_enabled.",
                )
            expected_token = _sheets_writeback_token(settings)
            if not expected_token:
                raise GatewayHTTPError(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "Sheets writeback token is not configured.",
                )
            presented_token = _bearer_token(self.headers.get("Authorization") or "")
            if not presented_token:
                presented_token = self.headers.get("X-HAL-Sheets-Token") or ""
            if not hmac.compare_digest(str(expected_token), str(presented_token)):
                raise GatewayHTTPError(HTTPStatus.UNAUTHORIZED, "Invalid Sheets writeback token")

        def _readiness_payload(self) -> dict[str, Any]:
            checks: dict[str, dict[str, str]] = {}
            issues: list[str] = []

            try:
                _, session_local = init_db(settings.database.url)
                session = session_local()
                try:
                    session.execute(text("SELECT 1"))
                finally:
                    session.close()
                checks["database"] = {"status": "ok"}
            except Exception as exc:
                checks["database"] = {"status": "error", "message": str(exc)}
                issues.append("database")

            slack_required = _setting_bool(settings, "app_gateway.slack_required")
            if signing_secret:
                checks["slack_signing_secret"] = {
                    "status": "ok",
                    "required": str(slack_required).lower(),
                }
            elif slack_required:
                checks["slack_signing_secret"] = {"status": "missing", "required": "true"}
                issues.append("slack_signing_secret")
            else:
                checks["slack_signing_secret"] = {"status": "optional", "required": "false"}

            sheets_enabled = _setting_bool(settings, "app_gateway.sheets_writeback_enabled")
            if sheets_enabled and _sheets_writeback_token(settings):
                checks["sheets_writeback"] = {"status": "enabled"}
            elif sheets_enabled:
                checks["sheets_writeback"] = {"status": "missing_token"}
                issues.append("sheets_writeback_token")
            else:
                checks["sheets_writeback"] = {"status": "disabled"}

            return {
                "status": "ready" if not issues else "not_ready",
                "service": "hal-app-gateway",
                "checks": checks,
                "issues": issues,
            }

        def _send_json(
            self,
            payload: dict[str, Any] | list[dict[str, Any]],
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send_html(self, html: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = html.encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send_error(self, exc: Exception) -> None:
            if isinstance(exc, GatewayHTTPError):
                status = exc.status
                message = exc.message
                payload = {"error": message, "status": status.value}
            elif isinstance(exc, AgentGatewayError):
                status = HTTPStatus.BAD_REQUEST
                message = str(exc)
                payload = {"error": message, "status": status.value, "code": exc.code}
            else:
                status = HTTPStatus.BAD_REQUEST
                message = str(exc)
                payload = {"error": message, "status": status.value}
            self._send_json(payload, status=status)

    GatewayHTTPRequestHandler.agent_bridge = agent_bridge
    return GatewayHTTPRequestHandler


def run_gateway_http_server(
    settings,
    host: str,
    port: int,
    slack_signing_secret: str | None = None,
) -> None:
    """Run the app gateway HTTP server forever."""
    server = create_gateway_http_server(settings, host, port, slack_signing_secret)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def create_gateway_http_server(
    settings,
    host: str,
    port: int,
    slack_signing_secret: str | None = None,
    agent_session_manager: AgentGatewaySessionManager | None = None,
) -> ThreadingHTTPServer:
    """Create an app gateway HTTP server."""
    handler = create_gateway_http_handler(
        settings,
        slack_signing_secret,
        agent_session_manager=agent_session_manager,
    )
    server = _GatewayHTTPServer(
        (host, port),
        handler,
    )
    server.agent_bridge = getattr(handler, "agent_bridge", None)
    return server


class _GatewayHTTPServer(ThreadingHTTPServer):
    """Threading HTTP server that can stop the agent bridge cleanly."""

    agent_bridge: _AgentHTTPBridge | None = None

    def server_close(self) -> None:
        if self.agent_bridge is not None:
            self.agent_bridge.close()
        super().server_close()


class _AgentHTTPBridge:
    """Run async agent session operations from the synchronous HTTP gateway."""

    def __init__(self, manager: AgentGatewaySessionManager):
        self.manager = manager
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

    def run(self, coro):
        """Run a coroutine on the bridge loop and return its result."""
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)

    def close(self) -> None:
        """Close live agent sessions and stop the bridge loop."""
        loop = self._loop
        thread = self._thread
        if loop is None or thread is None:
            return
        future = asyncio.run_coroutine_threadsafe(self.manager.close_all(), loop)
        try:
            future.result(timeout=5)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5)
            self._loop = None
            self._thread = None
            self._ready.clear()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is not None and self._thread is not None and self._thread.is_alive():
                return self._loop
            self._ready.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        self._ready.wait(timeout=5)
        if self._loop is None:
            raise GatewayHTTPError(HTTPStatus.SERVICE_UNAVAILABLE, "Agent bridge failed to start")
        return self._loop

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        loop.run_forever()
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()


async def _agent_sessions_payload(manager: AgentGatewaySessionManager) -> dict[str, Any]:
    return {
        "sessions": [session.snapshot() for session in manager.list_sessions()],
    }


async def _agent_create_payload(
    manager: AgentGatewaySessionManager,
    payload: dict[str, Any],
) -> dict[str, Any]:
    session = await manager.create_session(
        session_id=_optional_text(payload.get("agent_session_id") or payload.get("id")),
        user_id=_optional_text(payload.get("user_id")),
        run_id=_optional_text(payload.get("run_id")),
        system_prompt=_optional_text(payload.get("system_prompt")),
        messages=_optional_messages(payload.get("messages")),
        metadata=dict(payload.get("metadata") or {}),
    )
    return {
        "action": "agent.create",
        "agent_session": session.snapshot(),
        "events": session.replay(),
    }


async def _agent_submit_payload(
    manager: AgentGatewaySessionManager,
    payload: dict[str, Any],
) -> dict[str, Any]:
    session = _require_agent_session(manager, payload)
    operation = await session.submit(
        str(payload.get("text") or payload.get("content") or ""),
        metadata=dict(payload.get("metadata") or {}),
    )
    return _operation_payload("agent.submit", session, operation)


async def _agent_approve_payload(
    manager: AgentGatewaySessionManager,
    payload: dict[str, Any],
) -> dict[str, Any]:
    session = _require_agent_session(manager, payload)
    operation = await session.approve(
        str(payload.get("approval_id") or payload.get("id") or ""),
        approved=payload.get("approved", payload.get("status", True)),
        actor=str(payload.get("actor") or "human"),
        reason=_optional_text(payload.get("reason")),
    )
    return _operation_payload("agent.approve", session, operation)


async def _agent_interrupt_payload(
    manager: AgentGatewaySessionManager,
    payload: dict[str, Any],
) -> dict[str, Any]:
    session = _require_agent_session(manager, payload)
    operation = await session.interrupt(
        actor=_optional_text(payload.get("actor")),
        reason=_optional_text(payload.get("reason")),
    )
    return _operation_payload("agent.interrupt", session, operation)


async def _agent_compact_payload(
    manager: AgentGatewaySessionManager,
    payload: dict[str, Any],
) -> dict[str, Any]:
    session = _require_agent_session(manager, payload)
    operation = await session.compact(_optional_text(payload.get("summary")))
    return _operation_payload("agent.compact", session, operation)


async def _agent_replay_payload(
    manager: AgentGatewaySessionManager,
    *,
    session_id: str | None,
    run_id: str | None,
    after_sequence: int | None,
    limit: int | None,
) -> dict[str, Any]:
    snapshot, events = await manager.replay_events(
        session_id=session_id,
        run_id=run_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    return {
        "action": "agent.replay",
        "agent_session": snapshot,
        "events": events,
    }


async def _agent_history_payload(
    manager: AgentGatewaySessionManager,
    *,
    session_id: str | None,
    run_id: str | None,
    include_system: bool,
) -> dict[str, Any]:
    snapshot, messages = await manager.history(
        session_id=session_id,
        run_id=run_id,
        include_system=include_system,
    )
    return {
        "action": "agent.history",
        "agent_session": snapshot,
        "messages": messages,
    }


def _operation_payload(action: str, session, operation) -> dict[str, Any]:
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


def _require_agent_session(manager: AgentGatewaySessionManager, payload: dict[str, Any]):
    session_id = _optional_text(payload.get("agent_session_id") or payload.get("id"))
    if not session_id:
        raise AgentGatewayError("agent_session_id is required.", "MISSING_AGENT_SESSION_ID")
    session = manager.get_session(session_id)
    if session is None:
        raise AgentGatewayError(f"Unknown agent session: {session_id}", "UNKNOWN_AGENT_SESSION")
    return session


def _form_params(raw_body: bytes) -> dict[str, list[str]]:
    return parse_qs(raw_body.decode("utf-8"), keep_blank_values=True)


def _required_form(params: dict[str, list[str]], name: str) -> str:
    values = params.get(name) or []
    value = values[0].strip() if values else ""
    if not value:
        raise GatewayHTTPError(HTTPStatus.BAD_REQUEST, f"Missing required form field: {name}")
    return value


def _slack_user_email(params: dict[str, list[str]]) -> str:
    for key in ("user_email", "email"):
        values = params.get(key) or []
        if values and values[0].strip():
            return values[0].strip().lower()
    user_ids = params.get("user_id") or []
    if user_ids and user_ids[0].strip():
        mapped = _mapped_slack_user_email(user_ids[0].strip())
        if mapped:
            return mapped
    raise GatewayHTTPError(
        HTTPStatus.BAD_REQUEST,
        "Slack request must include user_email/email or map user_id through HAL9000_SLACK_USER_MAP_JSON.",
    )


def _mapped_slack_user_email(user_id: str) -> str | None:
    raw_map = os.getenv("HAL9000_SLACK_USER_MAP_JSON")
    if not raw_map:
        return None
    try:
        user_map = json.loads(raw_map)
    except json.JSONDecodeError as exc:
        raise GatewayHTTPError(
            HTTPStatus.BAD_REQUEST,
            f"Invalid HAL9000_SLACK_USER_MAP_JSON: {exc}",
        ) from exc
    if not isinstance(user_map, dict):
        raise GatewayHTTPError(
            HTTPStatus.BAD_REQUEST,
            "HAL9000_SLACK_USER_MAP_JSON must be a JSON object mapping Slack user IDs to emails.",
        )
    email = user_map.get(user_id)
    return str(email).strip().lower() if email else None


def _json_object(raw_value: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise GatewayHTTPError(HTTPStatus.BAD_REQUEST, f"Invalid JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise GatewayHTTPError(HTTPStatus.BAD_REQUEST, "Payload must be a JSON object")
    return payload


def _required_query(params: dict[str, list[str]], name: str) -> str:
    value = _optional_query(params, name)
    if not value:
        raise GatewayHTTPError(HTTPStatus.BAD_REQUEST, f"Missing required query parameter: {name}")
    return value


def _optional_query(params: dict[str, list[str]], name: str) -> str | None:
    values = params.get(name) or []
    value = values[0].strip() if values else ""
    return value or None


def _query_int(params: dict[str, list[str]], name: str, default: int) -> int:
    value = _optional_query(params, name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise GatewayHTTPError(
            HTTPStatus.BAD_REQUEST,
            f"{name} must be an integer",
        ) from exc


def _query_optional_int(params: dict[str, list[str]], name: str) -> int | None:
    value = _optional_query(params, name)
    if value is None:
        return None
    return _query_int(params, name, 0)


def _query_bool(params: dict[str, list[str]], name: str, default: bool) -> bool:
    value = _optional_query(params, name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_messages(value: Any) -> list[dict[str, Any]] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise AgentGatewayError("messages must be a list.", "INVALID_MESSAGES")
    return [dict(item) for item in value]


def _settings_value(settings, dotted_path: str, default: Any = None) -> Any:
    current = settings
    for part in dotted_path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return default
            current = current[part]
            continue
        if not hasattr(current, part):
            return default
        current = getattr(current, part)
    return current


def _setting_bool(settings, dotted_path: str, default: bool = False) -> bool:
    value = _settings_value(settings, dotted_path, None)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _sheets_writeback_token(settings) -> str | None:
    return secret_value(
        "google_sheets",
        secret_manager=create_secret_manager_from_settings(settings),
    )


def _bearer_token(header_value: str) -> str:
    scheme, _, token = header_value.strip().partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return token.strip()
