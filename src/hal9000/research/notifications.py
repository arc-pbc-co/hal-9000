"""Delivery workers for durable collaboration notifications."""

from __future__ import annotations

import csv
import json
import os
import smtplib
from dataclasses import asdict, dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Protocol

import httpx

from hal9000.db.models import ResearchNotification, utc_now
from hal9000.db.store import ResearchStore


@dataclass(frozen=True)
class DeliveryResult:
    """Result of one notification delivery attempt."""

    notification_id: str
    channel: str
    status: str
    destination: str | None
    message: str
    provider_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly result."""
        return asdict(self)


class NotificationDeliveryAdapter(Protocol):
    """Provider contract for delivering one notification channel."""

    channel: str

    def deliver(self, notification: ResearchNotification) -> DeliveryResult:
        """Deliver a single notification."""


class InAppDeliveryAdapter:
    """Mark in-app notifications available in the durable notification feed."""

    channel = "in_app"

    def deliver(self, notification: ResearchNotification) -> DeliveryResult:
        """Return a successful in-app delivery result."""
        return DeliveryResult(
            notification_id=notification.id,
            channel=self.channel,
            status="sent",
            destination=notification.recipient_email,
            message="Notification is available in the HAL in-app feed.",
        )


class SlackWebhookDeliveryAdapter:
    """Deliver Slack notifications through an incoming webhook."""

    channel = "slack"

    def __init__(
        self,
        webhook_url: str | None = None,
        timeout_seconds: float = 10.0,
    ):
        """Initialize with explicit URL or HAL9000_SLACK_WEBHOOK_URL."""
        self.webhook_url = webhook_url or os.getenv("HAL9000_SLACK_WEBHOOK_URL")
        self.timeout_seconds = timeout_seconds

    def deliver(self, notification: ResearchNotification) -> DeliveryResult:
        """Post a compact notification payload to Slack."""
        if not self.webhook_url:
            return DeliveryResult(
                notification_id=notification.id,
                channel=self.channel,
                status="skipped",
                destination=None,
                message="HAL9000_SLACK_WEBHOOK_URL is not configured.",
            )
        response = httpx.post(
            self.webhook_url,
            json=_slack_payload(notification),
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return DeliveryResult(
            notification_id=notification.id,
            channel=self.channel,
            status="sent",
            destination="slack:webhook",
            message="Slack webhook accepted the notification.",
            provider_response={"status_code": response.status_code},
        )


class EmailSMTPDeliveryAdapter:
    """Deliver email notifications through SMTP environment configuration."""

    channel = "email"

    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        sender: str | None = None,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool | None = None,
    ):
        """Initialize with explicit values or HAL9000_SMTP_* environment variables."""
        self.smtp_host = smtp_host or os.getenv("HAL9000_SMTP_HOST")
        self.smtp_port = smtp_port or int(os.getenv("HAL9000_SMTP_PORT") or "587")
        self.sender = sender or os.getenv("HAL9000_EMAIL_FROM") or "hal9000@localhost"
        self.username = username or os.getenv("HAL9000_SMTP_USERNAME")
        self.password = password or os.getenv("HAL9000_SMTP_PASSWORD")
        tls_env = os.getenv("HAL9000_SMTP_TLS")
        self.use_tls = use_tls if use_tls is not None else tls_env != "0"

    def deliver(self, notification: ResearchNotification) -> DeliveryResult:
        """Send a plain-text email notification."""
        if not self.smtp_host:
            return DeliveryResult(
                notification_id=notification.id,
                channel=self.channel,
                status="skipped",
                destination=notification.recipient_email,
                message="HAL9000_SMTP_HOST is not configured.",
            )
        if not notification.recipient_email:
            return DeliveryResult(
                notification_id=notification.id,
                channel=self.channel,
                status="failed",
                destination=None,
                message="Email notifications require recipient_email.",
            )

        message = EmailMessage()
        message["Subject"] = notification.title
        message["From"] = self.sender
        message["To"] = notification.recipient_email
        message.set_content(notification.body or notification.title)

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.username and self.password:
                smtp.login(self.username, self.password)
            smtp.send_message(message)

        return DeliveryResult(
            notification_id=notification.id,
            channel=self.channel,
            status="sent",
            destination=notification.recipient_email,
            message="SMTP accepted the notification email.",
        )


class SheetsCsvDeliveryAdapter:
    """Append notification rows to a Sheets-compatible CSV export sink."""

    channel = "sheets"

    def __init__(self, csv_path: str | Path | None = None):
        """Initialize with explicit path or HAL9000_SHEETS_CSV_PATH."""
        env_path = os.getenv("HAL9000_SHEETS_CSV_PATH")
        self.csv_path = Path(csv_path or env_path) if csv_path or env_path else None

    def deliver(self, notification: ResearchNotification) -> DeliveryResult:
        """Append one notification row to the configured CSV path."""
        if self.csv_path is None:
            return DeliveryResult(
                notification_id=notification.id,
                channel=self.channel,
                status="skipped",
                destination=None,
                message="HAL9000_SHEETS_CSV_PATH is not configured.",
            )
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        write_header = not self.csv_path.exists()
        with self.csv_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "notification_id",
                    "project_id",
                    "run_id",
                    "recipient_email",
                    "notification_type",
                    "title",
                    "body",
                    "created_at",
                    "payload_json",
                ],
            )
            if write_header:
                writer.writeheader()
            writer.writerow(
                {
                    "notification_id": notification.id,
                    "project_id": notification.project_id,
                    "run_id": notification.run_id,
                    "recipient_email": notification.recipient_email,
                    "notification_type": notification.notification_type,
                    "title": notification.title,
                    "body": notification.body,
                    "created_at": notification.created_at.isoformat()
                    if notification.created_at
                    else "",
                    "payload_json": notification.payload_json or "",
                }
            )
        return DeliveryResult(
            notification_id=notification.id,
            channel=self.channel,
            status="sent",
            destination=str(self.csv_path),
            message="Notification row appended to the Sheets CSV sink.",
        )


class DryRunDeliveryAdapter:
    """Adapter that records what would be delivered without changing queue state."""

    def __init__(self, channel: str):
        """Initialize for the requested channel."""
        self.channel = channel

    def deliver(self, notification: ResearchNotification) -> DeliveryResult:
        """Return a skipped dry-run result."""
        return DeliveryResult(
            notification_id=notification.id,
            channel=self.channel,
            status="skipped",
            destination=notification.recipient_email,
            message="Dry run: notification was not delivered.",
        )


class NotificationDeliveryService:
    """Deliver pending collaboration notifications through channel adapters."""

    def __init__(
        self,
        store: ResearchStore,
        adapters: list[NotificationDeliveryAdapter] | None = None,
    ):
        """Initialize with a store and optional adapter overrides."""
        self.store = store
        self.adapters = {
            adapter.channel: adapter
            for adapter in (
                adapters
                or [
                    InAppDeliveryAdapter(),
                    SlackWebhookDeliveryAdapter(),
                    EmailSMTPDeliveryAdapter(),
                    SheetsCsvDeliveryAdapter(),
                ]
            )
        }

    def deliver_pending(
        self,
        channel: str | None = None,
        limit: int = 20,
        dry_run: bool = False,
    ) -> list[DeliveryResult]:
        """Deliver pending notifications, preserving skipped dry-run rows."""
        notifications = self._pending_notifications(channel=channel, limit=limit)
        results = []
        for notification in notifications:
            adapter = DryRunDeliveryAdapter(notification.channel) if dry_run else self.adapters.get(
                notification.channel
            )
            if adapter is None:
                result = DeliveryResult(
                    notification_id=notification.id,
                    channel=notification.channel,
                    status="failed",
                    destination=notification.recipient_email,
                    message=f"No adapter registered for channel: {notification.channel}",
                )
            else:
                try:
                    result = adapter.deliver(notification)
                except Exception as exc:  # pragma: no cover - provider-specific failure shape
                    result = DeliveryResult(
                        notification_id=notification.id,
                        channel=notification.channel,
                        status="failed",
                        destination=notification.recipient_email,
                        message=str(exc),
                    )
            self._record_attempt(notification, result)
            results.append(result)
        return results

    def _pending_notifications(
        self,
        channel: str | None,
        limit: int,
    ) -> list[ResearchNotification]:
        query = self.store.session.query(ResearchNotification).filter_by(status="pending")
        if channel:
            query = query.filter_by(channel=channel.strip().lower().replace("-", "_"))
        return query.order_by(ResearchNotification.created_at.asc()).limit(max(1, limit)).all()

    def _record_attempt(
        self,
        notification: ResearchNotification,
        result: DeliveryResult,
    ) -> None:
        payload = json.loads(notification.payload_json) if notification.payload_json else {}
        attempts = payload.setdefault("delivery_attempts", [])
        attempts.append(result.to_dict() | {"attempted_at": utc_now().isoformat()})
        notification.payload_json = json.dumps(payload, sort_keys=True)
        if result.status == "sent":
            notification.status = "sent"
            notification.delivered_at = utc_now()
        elif result.status == "failed":
            notification.status = "failed"
        self.store.record_audit_event(
            action=f"notification.delivery_{result.status}",
            target_type="notification",
            target_id=notification.id,
            project=notification.project,
            run=notification.run,
            actor_email=notification.recipient_email,
            payload=result.to_dict(),
        )
        self.store.session.flush()


def delivery_results_payload(results: list[DeliveryResult]) -> list[dict[str, Any]]:
    """Return JSON-friendly delivery results."""
    return [result.to_dict() for result in results]


def _slack_payload(notification: ResearchNotification) -> dict[str, Any]:
    payload = json.loads(notification.payload_json) if notification.payload_json else {}
    if isinstance(payload.get("blocks"), list) and payload["blocks"]:
        message = {"text": notification.title, "blocks": payload["blocks"]}
        channel_id = payload.get("channel_id") or payload.get("channel")
        if channel_id:
            message["channel"] = str(channel_id)
        thread_ts = payload.get("thread_ts")
        if thread_ts:
            message["thread_ts"] = str(thread_ts)
        return message

    fields = [
        {"type": "mrkdwn", "text": f"*Type:*\n{notification.notification_type}"},
        {"type": "mrkdwn", "text": f"*Status:*\n{notification.status}"},
    ]
    if notification.run_id:
        fields.append({"type": "mrkdwn", "text": f"*Run:*\n{notification.run_id}"})
    if payload.get("output_ids"):
        fields.append({"type": "mrkdwn", "text": f"*Outputs:*\n{len(payload['output_ids'])}"})
    if payload.get("export_links"):
        export_lines = [
            f"- *{link.get('target', 'export')}*: {link.get('uri')}"
            for link in payload["export_links"]
            if isinstance(link, dict) and link.get("uri")
        ]
        if export_lines:
            fields.append({"type": "mrkdwn", "text": "*Exports:*\n" + "\n".join(export_lines[:5])})
    message = {
        "text": notification.title,
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{notification.title}*"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": notification.body or "HAL notification ready.",
                },
            },
            {"type": "section", "fields": fields},
        ],
    }
    channel_id = payload.get("channel_id") or payload.get("channel")
    if channel_id:
        message["channel"] = str(channel_id)
    thread_ts = payload.get("thread_ts")
    if thread_ts:
        message["thread_ts"] = str(thread_ts)
    return message
