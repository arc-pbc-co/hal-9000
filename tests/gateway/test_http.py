"""Tests for the HTTP app gateway routes."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from urllib.parse import urlencode

import httpx

from hal9000.agent import (
    AgentModelResponse,
    AgentToolCall,
    AgentToolResult,
    AgentToolRouter,
    AgentToolSpec,
)
from hal9000.db.models import ResearchNotification, init_db
from hal9000.db.store import ResearchStore
from hal9000.gateway import AgentGatewaySessionManager
from hal9000.gateway.http import create_gateway_http_server
from hal9000.research.graph import ResearchGraphService


class _ScriptedModelClient:
    def __init__(self, responses):
        self.responses = list(responses)

    async def complete(self, messages, tools):
        if not self.responses:
            raise AssertionError("No scripted response left")
        return self.responses.pop(0)


def test_gateway_http_slack_command_route_verifies_signature(temp_directory: Path):
    """HTTP app gateway should dispatch signed Slack commands into HAL services."""
    db_url, _ = _seed_slack_http_project(temp_directory)
    server, thread = _start_gateway_http_server(db_url, signing_secret="secret")
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        body = urlencode(
            {
                "text": "review slack-http",
                "user_email": "reviewer@example.com",
            }
        ).encode("utf-8")
        headers = _slack_headers("secret", body)
        with httpx.Client(base_url=base_url) as client:
            health = client.get("/health")
            assert health.status_code == 200
            assert health.json()["service"] == "hal-app-gateway"

            ready = client.get("/ready")
            assert ready.status_code == 200
            assert ready.json()["checks"]["database"]["status"] == "ok"

            response = client.post(
                "/slack/command",
                content=body,
                headers=headers,
            )
            assert response.status_code == 200
            assert "waiting for review" in response.json()["text"]

            denied = client.post(
                "/slack/command",
                content=body,
                headers=headers | {"X-Slack-Signature": "v0=bad"},
            )
            assert denied.status_code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_gateway_http_ready_reports_missing_required_integrations(temp_directory: Path):
    """Readiness should fail when enabled integrations are missing required secrets."""
    db_url, _ = _seed_slack_http_project(temp_directory)
    app_gateway = SimpleNamespace(slack_required=True, sheets_writeback_enabled=True)
    server, thread = _start_gateway_http_server(
        db_url,
        signing_secret=None,
        app_gateway=app_gateway,
    )
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        with httpx.Client(base_url=base_url) as client:
            response = client.get("/ready")
            payload = response.json()

        assert response.status_code == 503
        assert payload["status"] == "not_ready"
        assert "slack_signing_secret" in payload["issues"]
        assert "sheets_writeback_token" in payload["issues"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_gateway_http_sheets_writeback_is_token_gated(temp_directory: Path):
    """Sheets writeback should be disabled by default and token-gated when enabled."""
    db_url, _ = _seed_slack_http_project(temp_directory)
    server, thread = _start_gateway_http_server(db_url, signing_secret=None)
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        with httpx.Client(base_url=base_url) as client:
            disabled = client.post("/sheets/writeback", json={"action": "approve"})
            assert disabled.status_code == 501
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    app_gateway = SimpleNamespace(
        sheets_writeback_enabled=True,
        sheets_writeback_token="sheet-token",
    )
    server, thread = _start_gateway_http_server(
        db_url,
        signing_secret=None,
        app_gateway=app_gateway,
    )
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        body = {
            "action": "queue_run",
            "project_slug": "slack-http",
            "objective": "Queued from Sheets over HTTP.",
            "actor_email": "reviewer@example.com",
        }
        with httpx.Client(base_url=base_url) as client:
            denied = client.post("/sheets/writeback", json=body)
            assert denied.status_code == 401

            accepted = client.post(
                "/sheets/writeback",
                json=body,
                headers={"Authorization": "Bearer sheet-token"},
            )
            payload = accepted.json()

        assert accepted.status_code == 202
        assert payload["status"] == "accepted"
        assert payload["action"] == "queue_run"
        assert payload["queued_run_id"]

        _, session_factory = init_db(db_url)
        session = session_factory()
        try:
            run = ResearchStore(session).get_run(payload["queued_run_id"])
            assert run is not None
            assert run.objective == "Queued from Sheets over HTTP."
            assert run.initiated_by == "reviewer@example.com"
        finally:
            session.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_gateway_http_slack_command_maps_user_id(monkeypatch, temp_directory: Path):
    """Slack slash-command payloads can map user_id into HAL email identity."""
    db_url, _ = _seed_slack_http_project(temp_directory)
    monkeypatch.setenv("HAL9000_SLACK_USER_MAP_JSON", '{"U123": "reviewer@example.com"}')
    server, thread = _start_gateway_http_server(db_url, signing_secret=None)
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        body = urlencode({"text": "review slack-http", "user_id": "U123"}).encode("utf-8")
        with httpx.Client(base_url=base_url) as client:
            response = client.post("/slack/command", content=body)
            assert response.status_code == 200
            assert "waiting for review" in response.json()["text"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_gateway_http_slack_action_route_records_decision(temp_directory: Path):
    """Slack action route should execute review decisions through app service."""
    db_url, run_id = _seed_slack_http_project(temp_directory)
    server, thread = _start_gateway_http_server(db_url, signing_secret=None)
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        payload = {
            "user": {"profile": {"email": "reviewer@example.com"}},
            "actions": [
                {
                    "action_id": "hal_promote",
                    "value": json.dumps({"run_id": run_id, "rationale": "HTTP action"}),
                }
            ],
        }
        body = urlencode({"payload": json.dumps(payload)}).encode("utf-8")
        with httpx.Client(base_url=base_url) as client:
            response = client.post("/slack/action", content=body)
            assert response.status_code == 200
            assert "promoted" in response.json()["text"]

        _, session_factory = init_db(db_url)
        session = session_factory()
        try:
            assert ResearchStore(session).get_run(run_id).status == "promoted"
        finally:
            session.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_gateway_http_slack_action_maps_user_id(monkeypatch, temp_directory: Path):
    """Real Slack action payloads can map user.id into HAL email identity."""
    db_url, run_id = _seed_slack_http_project(temp_directory)
    monkeypatch.setenv("HAL9000_SLACK_USER_MAP_JSON", '{"U123": "reviewer@example.com"}')
    server, thread = _start_gateway_http_server(db_url, signing_secret=None)
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        payload = {
            "user": {"id": "U123", "username": "reviewer"},
            "actions": [{"action_id": "hal_promote", "value": json.dumps({"run_id": run_id})}],
        }
        body = urlencode({"payload": json.dumps(payload)}).encode("utf-8")
        with httpx.Client(base_url=base_url) as client:
            response = client.post("/slack/action", content=body)
            assert response.status_code == 200
            assert "promoted" in response.json()["text"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_gateway_http_slack_event_callback_queues_channel_response(monkeypatch, temp_directory: Path):
    """Slack Events API route should verify and dispatch channel callbacks."""
    db_url, run_id = _seed_slack_http_project(temp_directory)
    monkeypatch.setenv("HAL9000_SLACK_USER_MAP_JSON", '{"U123": "reviewer@example.com"}')
    server, thread = _start_gateway_http_server(db_url, signing_secret="secret")
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        url_verification = json.dumps(
            {"type": "url_verification", "challenge": "challenge-token"}
        ).encode("utf-8")
        event_payload = json.dumps(
            {
                "type": "event_callback",
                "event": {
                    "type": "app_mention",
                    "user": "U123",
                    "channel": "CDEV",
                    "ts": "1710000000.000100",
                    "text": f"<@UHAL> summary {run_id}",
                },
            }
        ).encode("utf-8")
        with httpx.Client(base_url=base_url) as client:
            challenge = client.post(
                "/slack/event",
                content=url_verification,
                headers=_slack_headers("secret", url_verification)
                | {"Content-Type": "application/json"},
            )
            response = client.post(
                "/slack/event",
                content=event_payload,
                headers=_slack_headers("secret", event_payload)
                | {"Content-Type": "application/json"},
            )
            payload = response.json()

        assert challenge.status_code == 200
        assert challenge.json()["challenge"] == "challenge-token"
        assert response.status_code == 200
        assert payload["status"] == "accepted"
        assert payload["run_id"] == run_id
        assert payload["channel_id"] == "CDEV"

        _, session_factory = init_db(db_url)
        session = session_factory()
        try:
            notification = session.get(ResearchNotification, payload["notification_id"])
            assert notification is not None
            assert notification.channel == "slack"
            assert notification.run_id == run_id
        finally:
            session.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_gateway_http_frontend_serves_cockpit_and_hal_panels(temp_directory: Path):
    """App gateway should serve the HAL cockpit and research panel payloads."""
    db_url, run_id = _seed_slack_http_project(temp_directory)
    _, session_factory = init_db(db_url)
    session = session_factory()
    try:
        store = ResearchStore(session)
        run = store.get_run(run_id)
        ResearchGraphService(store).add_edge(
            "run",
            run.id,
            "supports",
            "output",
            run.outputs[0].id,
            project=run.project,
            run=run,
            created_by="test",
        )
        session.commit()
    finally:
        session.close()

    server, thread = _start_gateway_http_server(db_url, signing_secret=None)
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        with httpx.Client(base_url=base_url) as client:
            ui = client.get("/")
            config = client.get("/api/frontend/config")
            review = client.get(
                "/api/frontend/review",
                params={"reviewer": "reviewer@example.com", "project_slug": "slack-http"},
            )
            evidence = client.get(
                "/api/frontend/evidence",
                params={"viewer": "reviewer@example.com", "run_id": run_id},
            )
            graph = client.get(
                "/api/frontend/graph",
                params={"viewer": "reviewer@example.com", "run_id": run_id},
            )
            logo = client.get("/assets/arc-logo-metal.png")

        assert ui.status_code == 200
        assert "HAL-9000 Research Console" in ui.text
        assert "/api/agent/session" in ui.text
        assert logo.status_code == 200
        assert logo.headers["content-type"] == "image/png"
        assert logo.content.startswith(b"\x89PNG")
        frontend_config = config.json()
        assert frontend_config["default_model"] == "anthropic/claude-opus-4-8"
        assert "anthropic/claude-opus-4-8" in frontend_config["models"]
        assert "anthropic/claude-sonnet-4-6" in frontend_config["models"]
        assert "openai/gpt-5.5" in frontend_config["models"]
        assert "openai/gpt-5.4-mini" in frontend_config["models"]
        assert "gemini/gemini-3.5-flash" in frontend_config["models"]
        assert "gemini/gemini-3.1-pro-preview" in frontend_config["models"]
        assert not any("fable" in model for model in frontend_config["models"])
        assert review.json()["queue"][0]["run_id"] == run_id
        assert evidence.json()["outputs"][0]["title"] == "HTTP Slack Brief"
        assert graph.json()["summary"]["edge_count"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_gateway_http_agent_frontend_session_submit_and_approval(temp_directory: Path):
    """Frontend REST endpoints should drive sessions, replay, history, and approvals."""
    db_url, _ = _seed_slack_http_project(temp_directory)
    handler_calls = []

    async def handler(arguments, context):
        handler_calls.append(arguments)
        return AgentToolResult.ok("approved", payload={"ok": True})

    tool_call = AgentToolCall(
        id="frontend-tool-call",
        name="hal_frontend_tool",
        arguments={"topic": "evidence"},
    )
    model = _ScriptedModelClient(
        [
            AgentModelResponse(tool_calls=[tool_call]),
            AgentModelResponse(content="Approved through the frontend."),
        ]
    )
    model_payloads = []
    manager = AgentGatewaySessionManager(
        model_client_factory=lambda payload: model_payloads.append(payload) or model,
        tool_router_factory=lambda _payload: AgentToolRouter(
            [
                AgentToolSpec(
                    name="hal_frontend_tool",
                    description="Frontend approval test tool.",
                    parameters={"type": "object"},
                    handler=handler,
                    requires_approval=True,
                )
            ]
        ),
    )
    server, thread = _start_gateway_http_server(
        db_url,
        signing_secret=None,
        agent_session_manager=manager,
    )
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            created = client.post(
                "/api/agent/session",
                json={
                    "agent_session_id": "frontend-agent",
                    "user_id": "reviewer@example.com",
                    "metadata": {
                        "model_name": "openai/gpt-5.5",
                        "reasoning_effort": "high",
                    },
                },
            )
            submitted = client.post(
                "/api/agent/submit",
                json={"agent_session_id": "frontend-agent", "text": "Use the gated tool."},
            )
            approval_replay = _poll_until(
                lambda: client.get(
                    "/api/agent/replay",
                    params={"agent_session_id": "frontend-agent"},
                ).json(),
                lambda payload: any(
                    event["type"] == "approval_required" for event in payload["events"]
                ),
            )
            approval_event = [
                event
                for event in approval_replay["events"]
                if event["type"] == "approval_required"
            ][-1]
            approved = client.post(
                "/api/agent/approve",
                json={
                    "agent_session_id": "frontend-agent",
                    "approval_id": approval_event["data"]["approval_id"],
                    "approved": True,
                    "actor": "reviewer@example.com",
                },
            )
            complete_replay = _poll_until(
                lambda: client.get(
                    "/api/agent/replay",
                    params={"agent_session_id": "frontend-agent"},
                ).json(),
                lambda payload: any(event["type"] == "turn_complete" for event in payload["events"]),
            )
            history = client.get(
                "/api/agent/history",
                params={"agent_session_id": "frontend-agent", "include_system": "false"},
            )

        assert created.status_code == 201
        assert created.json()["agent_session"]["id"] == "frontend-agent"
        assert submitted.json()["accepted"] is True
        assert approved.json()["accepted"] is True
        assert handler_calls == [{"topic": "evidence"}]
        assert complete_replay["events"][-1]["type"] == "turn_complete"
        assert history.json()["messages"][-1]["content"] == "Approved through the frontend."
        assert model_payloads[0]["metadata"]["model_name"] == "openai/gpt-5.5"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _seed_slack_http_project(temp_directory: Path) -> tuple[str, str]:
    db_url = f"sqlite:///{temp_directory / 'gateway_http.db'}"
    _, session_factory = init_db(db_url)
    session = session_factory()
    try:
        store = ResearchStore(session)
        project = store.create_project("Slack HTTP", "slack-http")
        reviewer = store.create_user("reviewer@example.com")
        store.grant_project_access(project, "user", reviewer.id, "reviewer")
        run = store.create_run("Review over HTTP.", project=project)
        store.update_run_status(run, "staged", actor="worker")
        store.stage_output(
            "HTTP Slack Brief",
            "research_brief",
            project=project,
            run=run,
            content="# Brief",
        )
        session.commit()
        return db_url, run.id
    finally:
        session.close()


def _start_gateway_http_server(
    db_url: str,
    signing_secret: str | None,
    app_gateway=None,
    agent_session_manager=None,
):
    settings = SimpleNamespace(
        database=SimpleNamespace(url=db_url),
        app_gateway=app_gateway or SimpleNamespace(),
    )
    server = create_gateway_http_server(
        settings,
        "127.0.0.1",
        0,
        signing_secret,
        agent_session_manager=agent_session_manager,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _slack_headers(secret: str, body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    base = b"v0:" + timestamp.encode("utf-8") + b":" + body
    signature = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
    }


def _poll_until(factory, predicate, attempts: int = 20):
    last_payload = None
    for _ in range(attempts):
        last_payload = factory()
        if predicate(last_payload):
            return last_payload
        time.sleep(0.05)
    raise AssertionError(f"condition was not met; last payload: {last_payload}")
