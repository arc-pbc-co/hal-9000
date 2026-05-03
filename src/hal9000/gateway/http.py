"""HTTP app gateway routes for Slack and Sheets-facing integrations."""

from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.slack_app import SlackAppService, verify_slack_signature


class GatewayHTTPError(Exception):
    """HTTP-shaped error for app gateway requests."""

    def __init__(self, status: HTTPStatus, message: str):
        """Initialize with status and message."""
        self.status = status
        self.message = message
        super().__init__(message)


def create_gateway_http_handler(settings, slack_signing_secret: str | None = None):
    """Create an app gateway HTTP handler bound to HAL settings."""
    signing_secret = slack_signing_secret or os.getenv("HAL9000_SLACK_SIGNING_SECRET")

    class GatewayHTTPRequestHandler(BaseHTTPRequestHandler):
        """HTTP handler for Slack and future app-webhook routes."""

        server_version = "HALAppGateway/0.1"

        def do_GET(self) -> None:
            """Handle read endpoints."""
            try:
                parsed = urlparse(self.path)
                if parsed.path == "/health":
                    self._send_json({"status": "ok", "service": "hal-app-gateway"})
                    return
                raise GatewayHTTPError(HTTPStatus.NOT_FOUND, f"Unknown path: {parsed.path}")
            except Exception as exc:
                self._send_error(exc)

        def do_POST(self) -> None:
            """Handle Slack app webhooks."""
            try:
                parsed = urlparse(self.path)
                raw_body = self._read_body()
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
                if parsed.path == "/sheets/writeback":
                    raise GatewayHTTPError(
                        HTTPStatus.NOT_IMPLEMENTED,
                        "Sheets writeback is planned; use hal research sync-sheets for read sync.",
                    )
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

        def _send_error(self, exc: Exception) -> None:
            if isinstance(exc, GatewayHTTPError):
                status = exc.status
                message = exc.message
            else:
                status = HTTPStatus.BAD_REQUEST
                message = str(exc)
            self._send_json({"error": message, "status": status.value}, status=status)

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
) -> ThreadingHTTPServer:
    """Create an app gateway HTTP server."""
    return ThreadingHTTPServer(
        (host, port),
        create_gateway_http_handler(settings, slack_signing_secret),
    )


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
