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

from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.gateway.http import create_gateway_http_server


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


def _start_gateway_http_server(db_url: str, signing_secret: str | None):
    settings = SimpleNamespace(database=SimpleNamespace(url=db_url))
    server = create_gateway_http_server(settings, "127.0.0.1", 0, signing_secret)
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
