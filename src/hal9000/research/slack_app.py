"""Slack app command and action handlers for HAL research workflows."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from hal9000.db.store import ResearchStore
from hal9000.research.annotations import ReviewAnnotationService
from hal9000.research.authz import ResearchAuthorizer
from hal9000.research.collaboration import CollaborationService
from hal9000.research.review import ResearchReviewService
from hal9000.research.telemetry import RunTelemetrySummarizer


@dataclass(frozen=True)
class SlackAppResponse:
    """Slack-compatible response payload."""

    text: str
    response_type: str = "ephemeral"
    blocks: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly Slack response."""
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class SlackEventResponse:
    """Gateway response for Slack Events API callbacks."""

    status: str
    event_type: str
    text: str | None = None
    channel_id: str | None = None
    run_id: str | None = None
    notification_id: str | None = None
    blocks: list[dict[str, Any]] | None = None
    challenge: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly Slack Events response."""
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


class SlackAppService:
    """Handle Slack slash commands and interactive review actions."""

    def __init__(self, store: ResearchStore):
        """Initialize with the shared research store."""
        self.store = store
        self.authorizer = ResearchAuthorizer(store)

    def handle_command(
        self,
        text: str,
        user_email: str,
    ) -> SlackAppResponse:
        """Handle `/hal ...` command text."""
        verb, rest = _split_command(text)
        if verb in {"", "help"}:
            return SlackAppResponse(_help_text())
        if verb == "queue":
            return self._queue_run(rest, user_email)
        if verb == "status":
            return self._run_status(rest, user_email)
        if verb == "summary":
            return self._run_summary(rest, user_email)
        if verb == "exports":
            return self._export_links(rest, user_email)
        if verb == "review":
            return self._review_queue(rest, user_email)
        if verb == "comment":
            return self._comment(rest, user_email)
        if verb in {"promote", "reject", "request-changes"}:
            return self._review_decision(verb, rest, user_email)
        return SlackAppResponse(f"Unknown HAL command `{verb}`.\n\n{_help_text()}")

    def handle_action(
        self,
        payload: dict[str, Any],
    ) -> SlackAppResponse:
        """Handle Slack interactive button payloads."""
        action = (payload.get("actions") or [{}])[0]
        action_id = str(action.get("action_id") or "")
        value = _json_value(action.get("value"))
        user_email = _payload_user_email(payload)
        if action_id == "hal_open_review":
            return self._run_status(value.get("run_id", ""), user_email)
        if action_id in {"hal_promote", "hal_reject", "hal_request_changes"}:
            decision = {
                "hal_promote": "promote",
                "hal_reject": "reject",
                "hal_request_changes": "request-changes",
            }[action_id]
            run_id = value.get("run_id", "")
            rationale = value.get("rationale", f"Slack action: {decision}")
            return self._review_decision(decision, f"{run_id} {rationale}", user_email)
        return SlackAppResponse(f"Unsupported HAL Slack action: {action_id}")

    def handle_event(self, payload: dict[str, Any]) -> SlackEventResponse:
        """Handle Slack Events API callbacks for channel workflows."""
        payload_type = str(payload.get("type") or "")
        if payload_type == "url_verification":
            return SlackEventResponse(
                status="ok",
                event_type=payload_type,
                challenge=str(payload.get("challenge") or ""),
            )
        if payload_type != "event_callback":
            return SlackEventResponse(status="ignored", event_type=payload_type or "unknown")

        event = payload.get("event")
        if not isinstance(event, dict):
            raise ValueError("Slack event callback must include an event object")
        event_type = str(event.get("type") or "unknown")
        if event.get("bot_id") or event.get("subtype") in {"bot_message", "message_deleted"}:
            return SlackEventResponse(status="ignored", event_type=event_type)
        if event_type not in {"app_mention", "message"}:
            return SlackEventResponse(status="ignored", event_type=event_type)

        user_email = _event_user_email(payload, event)
        command_text = _normalize_event_text(str(event.get("text") or ""))
        command = self.handle_command(command_text, user_email)
        channel_id = _optional_str(event.get("channel"))
        thread_ts = _optional_str(event.get("thread_ts") or event.get("ts"))
        run_id = _run_id_from_command(command_text)
        run = self.store.get_run(run_id) if run_id else None
        notification = CollaborationService(self.store).create_notification(
            notification_type="slack_channel_response",
            title=command.text,
            body=command.text,
            project=run.project if run else None,
            run=run,
            recipient_email=None,
            channel="slack",
            payload={
                "channel_id": channel_id,
                "thread_ts": thread_ts,
                "source_event_type": event_type,
                "source_event_ts": _optional_str(event.get("ts")),
                "command_text": command_text,
                "blocks": command.blocks or [],
            },
        )
        self.store.record_audit_event(
            "slack.event_callback",
            "notification",
            notification.id,
            project=run.project if run else None,
            run=run,
            actor_email=user_email,
            payload={
                "event_type": event_type,
                "channel_id": channel_id,
                "run_id": run_id,
                "command_text": command_text,
            },
        )
        return SlackEventResponse(
            status="accepted",
            event_type=event_type,
            text=command.text,
            channel_id=channel_id,
            run_id=run_id,
            notification_id=notification.id,
            blocks=command.blocks,
        )

    def _queue_run(self, text: str, user_email: str) -> SlackAppResponse:
        project_slug, objective = _split_first(text)
        if not project_slug or not objective:
            return SlackAppResponse("Usage: `/hal queue <project_slug> <objective>`")
        project = self.store.get_project_by_slug(project_slug)
        if project is None:
            return SlackAppResponse(f"Research project not found: `{project_slug}`")
        self.authorizer.require_project_role(project, user_email, "contributor")
        run = self.store.create_run(
            objective=objective,
            project=project,
            initiated_by=user_email,
        )
        self.store.append_run_event(
            run,
            event_type="run.queued",
            message="Research run queued from Slack.",
            actor=user_email,
            payload={"source": "slack"},
        )
        self.store.record_audit_event(
            "slack.run_queued",
            "run",
            run.id,
            project=project,
            run=run,
            actor_email=user_email,
            payload={"objective": objective},
        )
        return SlackAppResponse(
            text=f"Queued HAL research run `{run.id}` for `{project.slug}`.",
            blocks=[_section(f"*Queued HAL research run*\nProject: `{project.slug}`\nRun: `{run.id}`")],
        )

    def _run_status(self, text: str, user_email: str) -> SlackAppResponse:
        run_id = text.strip()
        if not run_id:
            return SlackAppResponse("Usage: `/hal status <run_id>`")
        run = self.store.get_run(run_id)
        if run is None:
            return SlackAppResponse(f"Research run not found: `{run_id}`")
        self.authorizer.require_run_role(run, user_email, "viewer")
        return SlackAppResponse(
            text=f"Run `{run.id}` is `{run.status}`.",
            blocks=[
                _section(
                    f"*HAL run status*\nRun: `{run.id}`\nStatus: `{run.status}`\nObjective: {run.objective}"
                )
            ],
        )

    def _run_summary(self, text: str, user_email: str) -> SlackAppResponse:
        run_id = text.strip()
        if not run_id:
            return SlackAppResponse("Usage: `/hal summary <run_id>`")
        run = self.store.get_run(run_id)
        if run is None:
            return SlackAppResponse(f"Research run not found: `{run_id}`")
        self.authorizer.require_run_role(run, user_email, "viewer")
        summary = RunTelemetrySummarizer(self.store).summarize(run)
        output_count = len(summary.outputs)
        blocks = [
            _section(
                "\n".join(
                    [
                        "*HAL run summary*",
                        f"Run: `{summary.run_id}`",
                        f"Project: `{summary.project_slug or '-'}`",
                        f"Status: `{summary.status}`",
                        f"Objective: {summary.objective}",
                    ]
                )
            ),
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Outputs:*\n{output_count}"},
                    {"type": "mrkdwn", "text": f"*Claims:*\n{summary.claim_count}"},
                    {"type": "mrkdwn", "text": f"*Tool calls:*\n{summary.tool_call_count}"},
                    {"type": "mrkdwn", "text": f"*Warnings:*\n{len(summary.warnings)}"},
                ],
            },
        ]
        if summary.outputs:
            output_lines = [
                f"- `{output.status}` {output.title}"
                for output in summary.outputs[:5]
            ]
            blocks.append(_section("*Outputs*\n" + "\n".join(output_lines)))
        if summary.warnings:
            blocks.append(_section("*Warnings*\n" + "\n".join(summary.warnings[:3])))
        return SlackAppResponse(
            text=f"Run `{run.id}` summary: `{run.status}` with {output_count} output(s).",
            response_type="in_channel",
            blocks=blocks,
        )

    def _export_links(self, text: str, user_email: str) -> SlackAppResponse:
        run_id = text.strip()
        if not run_id:
            return SlackAppResponse("Usage: `/hal exports <run_id>`")
        run = self.store.get_run(run_id)
        if run is None:
            return SlackAppResponse(f"Research run not found: `{run_id}`")
        self.authorizer.require_run_role(run, user_email, "viewer")
        links = _run_export_links(self.store, run)
        if not links:
            return SlackAppResponse(f"No export links recorded for run `{run.id}`.")
        blocks = [
            _section(f"*HAL export links*\nRun: `{run.id}`"),
            _section("\n".join(f"- *{link['target']}*: {link['uri']}" for link in links[:10])),
        ]
        return SlackAppResponse(
            text=f"{len(links)} export link(s) recorded for run `{run.id}`.",
            response_type="in_channel",
            blocks=blocks,
        )

    def _review_queue(self, text: str, user_email: str) -> SlackAppResponse:
        project = None
        project_slug = text.strip()
        if project_slug:
            project = self.store.get_project_by_slug(project_slug)
            if project is None:
                return SlackAppResponse(f"Research project not found: `{project_slug}`")
        items = ResearchReviewService(self.store).list_review_queue(
            reviewer_email=user_email,
            project=project,
            limit=5,
        )
        if not items:
            return SlackAppResponse("No HAL runs are waiting for your review.")
        blocks = [_section("*HAL review queue*")]
        for item in items:
            blocks.extend(
                [
                    _section(
                        f"*{item.project_slug or '-'}*\n{item.objective}\nRun: `{item.run_id}`"
                    ),
                    _actions(item.run_id),
                ]
            )
        return SlackAppResponse(
            text=f"{len(items)} HAL run(s) are waiting for review.",
            blocks=blocks,
        )

    def _comment(self, text: str, user_email: str) -> SlackAppResponse:
        output_id, body = _split_first(text)
        if not output_id or not body:
            return SlackAppResponse("Usage: `/hal comment <output_id> <comment>`")
        annotation = ReviewAnnotationService(self.store).add_annotation(
            "output",
            output_id,
            body=body,
            author_email=user_email,
        )
        self.store.record_audit_event(
            "slack.comment_added",
            "output",
            output_id,
            project=annotation.project,
            run=annotation.run,
            actor_email=user_email,
            payload={"annotation_id": annotation.id},
        )
        return SlackAppResponse(f"Added comment `{annotation.id}` to output `{output_id}`.")

    def _review_decision(self, decision: str, text: str, user_email: str) -> SlackAppResponse:
        run_id, rationale = _split_first(text)
        if not run_id:
            return SlackAppResponse(f"Usage: `/hal {decision} <run_id> [rationale]`")
        run = self.store.get_run(run_id)
        if run is None:
            return SlackAppResponse(f"Research run not found: `{run_id}`")
        result = ResearchReviewService(self.store).review_run(
            run,
            decision=decision,
            reviewer_email=user_email,
            rationale=rationale or f"Slack decision: {decision}",
        )
        return SlackAppResponse(
            text=f"Run `{run.id}` is now `{result.run.status}`.",
            blocks=[
                _section(
                    f"*HAL review decision recorded*\nRun: `{run.id}`\nStatus: `{result.run.status}`"
                )
            ],
        )


def verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
    now: int | None = None,
    tolerance_seconds: int = 300,
) -> bool:
    """Verify a Slack request signature."""
    try:
        request_time = int(timestamp)
    except ValueError:
        return False
    current_time = now if now is not None else int(time.time())
    if abs(current_time - request_time) > tolerance_seconds:
        return False
    base = b"v0:" + timestamp.encode("utf-8") + b":" + body
    expected = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        base,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _split_command(text: str) -> tuple[str, str]:
    verb, rest = _split_first(text.strip())
    return verb.lower(), rest


def _split_first(text: str) -> tuple[str, str]:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return "", ""
    return parts[0], parts[1] if len(parts) > 1 else ""


def _json_value(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        payload = json.loads(str(value))
    except json.JSONDecodeError:
        return {"run_id": str(value)}
    return payload if isinstance(payload, dict) else {}


def _run_export_links(store: ResearchStore, run) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for event in store.list_run_events(run):
        if event.event_type != "outputs.exported" or not event.payload_json:
            continue
        payload = _safe_json_object(event.payload_json)
        targets = payload.get("targets") if isinstance(payload.get("targets"), list) else []
        uris = (
            payload.get("manifest_uris")
            if isinstance(payload.get("manifest_uris"), list)
            else []
        )
        for index, uri in enumerate(uris):
            target = str(targets[index]) if index < len(targets) else "export"
            if uri:
                links.append({"target": target, "uri": str(uri)})
    if links:
        return links
    for output in run.outputs:
        if output.artifact_uri:
            links.append({"target": output.output_type, "uri": output.artifact_uri})
    return links


def _safe_json_object(raw_value: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_user_email(payload: dict[str, Any]) -> str:
    user = payload.get("user") or {}
    profile = user.get("profile") or {}
    email = profile.get("email") or user.get("email")
    if email:
        return str(email).strip().lower()
    user_id = user.get("id")
    if user_id:
        mapped = _mapped_slack_user_email(str(user_id))
        if mapped:
            return mapped
    raise ValueError(
        "Slack action payload must include user email or map user.id through "
        "HAL9000_SLACK_USER_MAP_JSON"
    )


def _event_user_email(payload: dict[str, Any], event: dict[str, Any]) -> str:
    for candidate in (
        event.get("user_email"),
        event.get("email"),
        payload.get("user_email"),
        payload.get("email"),
    ):
        if candidate:
            return str(candidate).strip().lower()
    user_id = event.get("user") or payload.get("user_id")
    if user_id:
        mapped = _mapped_slack_user_email(str(user_id))
        if mapped:
            return mapped
    raise ValueError(
        "Slack event payload must include user email or map event.user through "
        "HAL9000_SLACK_USER_MAP_JSON"
    )


def _mapped_slack_user_email(user_id: str) -> str | None:
    raw_map = os.getenv("HAL9000_SLACK_USER_MAP_JSON")
    if not raw_map:
        return None
    user_map = json.loads(raw_map)
    if not isinstance(user_map, dict):
        raise ValueError("HAL9000_SLACK_USER_MAP_JSON must be a JSON object")
    email = user_map.get(user_id)
    return str(email).strip().lower() if email else None


def _normalize_event_text(text: str) -> str:
    without_mentions = re.sub(r"<@[A-Z0-9]+>", " ", text)
    normalized = " ".join(without_mentions.strip().split())
    if normalized.lower().startswith("/hal "):
        return normalized[5:].strip()
    return normalized


def _run_id_from_command(text: str) -> str | None:
    verb, rest = _split_command(text)
    if verb in {"status", "summary", "exports", "promote", "reject", "request-changes"}:
        run_id, _ = _split_first(rest)
        return run_id or None
    return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _actions(run_id: str) -> dict[str, Any]:
    return {
        "type": "actions",
        "elements": [
            _button("Open", "hal_open_review", {"run_id": run_id}),
            _button("Promote", "hal_promote", {"run_id": run_id}),
            _button("Request changes", "hal_request_changes", {"run_id": run_id}),
            _button("Reject", "hal_reject", {"run_id": run_id}),
        ],
    }


def _button(text: str, action_id: str, value: dict[str, Any]) -> dict[str, Any]:
    style = "primary" if action_id == "hal_promote" else "danger" if action_id == "hal_reject" else None
    payload = {
        "type": "button",
        "text": {"type": "plain_text", "text": text},
        "action_id": action_id,
        "value": json.dumps(value, sort_keys=True),
    }
    if style:
        payload["style"] = style
    return payload


def _help_text() -> str:
    return (
        "HAL Slack commands:\n"
        "`/hal queue <project_slug> <objective>`\n"
        "`/hal status <run_id>`\n"
        "`/hal summary <run_id>`\n"
        "`/hal exports <run_id>`\n"
        "`/hal review [project_slug]`\n"
        "`/hal comment <output_id> <comment>`\n"
        "`/hal promote|request-changes|reject <run_id> [rationale]`"
    )
