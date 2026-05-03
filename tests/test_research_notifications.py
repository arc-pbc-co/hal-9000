"""Tests for collaboration notification delivery workers."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.collaboration import CollaborationService
from hal9000.research.notifications import (
    DeliveryResult,
    NotificationDeliveryService,
    SheetsCsvDeliveryAdapter,
    SlackWebhookDeliveryAdapter,
)


class _FakeAdapter:
    channel = "slack"

    def deliver(self, notification):
        return DeliveryResult(
            notification_id=notification.id,
            channel=self.channel,
            status="sent",
            destination="slack:test",
            message=f"delivered {notification.title}",
        )


def test_notification_delivery_service_marks_sent_and_records_audit(temp_directory: Path):
    """Delivery service should update queue state and persist attempt metadata."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'notifications.db'}")
    session = session_factory()
    try:
        store = ResearchStore(session)
        project = store.create_project("Notify", "notify")
        run = store.create_run("Notify reviewers.", project=project)
        notification = CollaborationService(store).create_notification(
            "review_ready",
            "Review ready",
            project=project,
            run=run,
            recipient_email="reviewer@example.com",
            channel="slack",
            payload={"run_id": run.id},
        )

        results = NotificationDeliveryService(store, adapters=[_FakeAdapter()]).deliver_pending()
        session.commit()

        assert results[0].status == "sent"
        assert notification.status == "sent"
        assert notification.delivered_at is not None
        payload = json.loads(notification.payload_json)
        assert payload["delivery_attempts"][0]["destination"] == "slack:test"
        events = CollaborationService(store).list_audit_events(
            project=project,
            action="notification.delivery_sent",
        )
        assert events[0].target_id == notification.id
    finally:
        session.close()


def test_sheets_csv_delivery_adapter_appends_notification_rows(temp_directory: Path):
    """Sheets adapter should write a stable CSV bridge for Google Sheets sync."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'sheets_notifications.db'}")
    session = session_factory()
    try:
        store = ResearchStore(session)
        notification = CollaborationService(store).create_notification(
            "run_summary",
            "Run summary",
            body="A run completed.",
            recipient_email="ops@example.com",
            channel="sheets",
        )
        csv_path = temp_directory / "sheets" / "notifications.csv"

        result = SheetsCsvDeliveryAdapter(csv_path).deliver(notification)

        assert result.status == "sent"
        with csv_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        assert rows[0]["notification_id"] == notification.id
        assert rows[0]["title"] == "Run summary"
    finally:
        session.close()


def test_slack_webhook_adapter_posts_compact_payload(monkeypatch, temp_directory: Path):
    """Slack adapter should post the durable notification payload to a webhook."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'slack_notifications.db'}")
    session = session_factory()
    posted = {}

    class _Response:
        status_code = 200

        def raise_for_status(self):
            return None

    def fake_post(url, json, timeout):
        posted["url"] = url
        posted["json"] = json
        posted["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("hal9000.research.notifications.httpx.post", fake_post)
    try:
        store = ResearchStore(session)
        notification = CollaborationService(store).create_notification(
            "review_ready",
            "Run ready",
            body="Review output.",
            recipient_email="reviewer@example.com",
            channel="slack",
            payload={"output_ids": ["out-1", "out-2"]},
        )

        result = SlackWebhookDeliveryAdapter("https://hooks.example/slack").deliver(notification)

        assert result.status == "sent"
        assert posted["url"] == "https://hooks.example/slack"
        assert posted["json"]["text"] == "Run ready"
        assert posted["json"]["blocks"][2]["fields"][2]["text"] == "*Outputs:*\n2"
    finally:
        session.close()
