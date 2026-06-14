"""Tests for production retention planning and cleanup."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.config import RetentionConfig
from hal9000.db.models import (
    Document,
    GatewaySession,
    ResearchAuditEvent,
    ResearchNotification,
    ResearchOutput,
    ResearchOutputVersion,
    ResearchRunEvent,
    ResearchToolCall,
    init_db,
)
from hal9000.db.store import ResearchStore
from hal9000.research.retention import ResearchRetentionService
from hal9000.storage import LocalObjectStore


def test_retention_plan_counts_expired_operational_rows(temp_directory: Path):
    """Retention plans should count only rows older than their configured cutoffs."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'retention.db'}")
    session = session_factory()
    now = datetime(2026, 5, 16, tzinfo=timezone.utc)

    try:
        _seed_retention_rows(session, now)
        config = RetentionConfig(
            run_event_days=90,
            tool_call_days=90,
            notification_days=30,
            audit_event_days=365,
            gateway_session_days=7,
        )

        plan = ResearchRetentionService(session, config).plan(now=now)
        candidates = {rule.name: rule.candidates for rule in plan.rules}

        assert candidates == {
            "run_events": 1,
            "tool_calls": 1,
            "notifications": 1,
            "audit_events": 1,
            "gateway_sessions": 1,
        }
        assert plan.total_candidates == 5
    finally:
        session.close()


def test_retention_apply_requires_enablement_and_confirm(temp_directory: Path):
    """Retention apply should be dry-run-first and require enabled config."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'retention_apply.db'}")
    session = session_factory()
    now = datetime(2026, 5, 16, tzinfo=timezone.utc)

    try:
        _seed_retention_rows(session, now)
        disabled = RetentionConfig(
            run_event_days=90,
            tool_call_days=90,
            notification_days=30,
            audit_event_days=365,
            gateway_session_days=7,
        )

        dry_run = ResearchRetentionService(session, disabled).apply(confirm=True, now=now)
        assert dry_run.applied is False
        assert session.query(ResearchRunEvent).count() == 2

        enabled = RetentionConfig(
            enabled=True,
            run_event_days=90,
            tool_call_days=90,
            notification_days=30,
            audit_event_days=365,
            gateway_session_days=7,
        )
        result = ResearchRetentionService(session, enabled).apply(confirm=True, now=now)
        session.commit()

        assert result.applied is True
        assert result.deleted_counts["run_events"] == 1
        assert session.query(ResearchRunEvent).count() == 1
        assert session.query(ResearchToolCall).count() == 1
        assert session.query(ResearchNotification).count() == 1
        assert session.query(ResearchAuditEvent).count() == 1
        assert session.query(GatewaySession).count() == 1
    finally:
        session.close()


def test_retention_applies_object_artifacts_with_legal_hold_safeguards(temp_directory: Path):
    """Artifact retention should delete only old HAL-owned objects without legal holds."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'retention_artifacts.db'}")
    object_store = LocalObjectStore(temp_directory / "objects")
    session = session_factory()
    now = datetime(2026, 5, 16, tzinfo=timezone.utc)
    old = now - timedelta(days=90)
    recent = now - timedelta(days=2)

    try:
        old_pdf = object_store.put_bytes("pdfs/old.pdf", b"old pdf")
        held_pdf = object_store.put_bytes("pdfs/held.pdf", b"held pdf")
        recent_pdf = object_store.put_bytes("pdfs/recent.pdf", b"recent pdf")
        old_output = object_store.put_bytes("outputs/old.md", b"old output")
        held_output = object_store.put_bytes("outputs/held.md", b"held output")
        recent_output = object_store.put_bytes("outputs/recent.md", b"recent output")

        project = ResearchStore(session).create_project("Retention Artifacts", "retention-artifacts")
        run = ResearchStore(session).create_run("Test artifact retention.", project=project)

        session.add_all(
            [
                _document("old", old_pdf.uri, old),
                _document(
                    "held",
                    held_pdf.uri,
                    old,
                    source_quality={"legal_hold": True},
                ),
                _document("recent", recent_pdf.uri, recent),
                _document("external", "/outside/hal/source.pdf", old),
            ]
        )
        store = ResearchStore(session)
        old_record = store.stage_output(
            "Old artifact",
            "brief",
            project=project,
            run=run,
            artifact_uri=old_output.uri,
            source={"generator": "test"},
        )
        held_record = store.stage_output(
            "Held artifact",
            "brief",
            project=project,
            run=run,
            artifact_uri=held_output.uri,
            source={"retention_policy": "legal_hold"},
        )
        recent_record = store.stage_output(
            "Recent artifact",
            "brief",
            project=project,
            run=run,
            artifact_uri=recent_output.uri,
        )
        for record in (old_record, held_record):
            record.created_at = old
            record.updated_at = old
        recent_record.created_at = recent
        recent_record.updated_at = recent
        session.flush()
        for version in session.query(ResearchOutputVersion).all():
            version.created_at = old if version.output_id in {old_record.id, held_record.id} else recent
        session.commit()

        config = RetentionConfig(
            enabled=True,
            pdf_artifact_days=30,
            output_artifact_days=30,
        )
        service = ResearchRetentionService(session, config, object_store=object_store)

        plan = service.plan(now=now)
        rules = {rule.name: rule for rule in plan.rules}

        assert rules["pdf_artifacts"].candidates == 1
        assert rules["pdf_artifacts"].protected == 1
        assert rules["output_artifacts"].candidates == 1
        assert rules["output_artifacts"].protected == 2
        assert {item.object_key for item in plan.objects or []} == {
            "pdfs/old.pdf",
            "outputs/old.md",
        }

        result = service.apply(confirm=True, now=now)
        session.commit()

        assert result.applied is True
        assert result.deleted_counts["pdf_artifacts"] == 1
        assert result.deleted_counts["output_artifacts"] == 1
        assert not object_store.exists("pdfs/old.pdf")
        assert not object_store.exists("outputs/old.md")
        assert object_store.exists("pdfs/held.pdf")
        assert object_store.exists("outputs/held.md")
        assert object_store.exists("pdfs/recent.pdf")
        assert object_store.exists("outputs/recent.md")
        assert session.query(Document).count() == 4
        assert session.query(ResearchOutput).count() == 3
    finally:
        session.close()


def test_retention_cli_plan_and_apply(temp_directory: Path):
    """The CLI should expose retention dry-runs and confirmed apply."""
    db_path = temp_directory / "retention_cli.db"
    config_path = temp_directory / "config.yaml"
    _, session_factory = init_db(f"sqlite:///{db_path}")
    session = session_factory()

    try:
        _seed_retention_rows(session, datetime.now(timezone.utc))
    finally:
        session.close()

    config_path.write_text(
        "\n".join(
            [
                "hal9000:",
                "  database:",
                f"    url: sqlite:///{db_path}",
                "  retention:",
                "    enabled: true",
                "    run_event_days: 0",
                "    tool_call_days: 0",
                "    notification_days: 0",
                "    audit_event_days: 0",
                "    gateway_session_days: 0",
            ]
        )
    )
    runner = CliRunner()

    plan = runner.invoke(
        cli,
        ["--config", str(config_path), "research", "retention-plan", "--json"],
    )
    assert plan.exit_code == 0, plan.output
    assert json.loads(plan.output)["total_candidates"] >= 5

    apply = runner.invoke(
        cli,
        ["--config", str(config_path), "research", "retention-apply", "--confirm", "--json"],
    )
    assert apply.exit_code == 0, apply.output
    payload = json.loads(apply.output)
    assert payload["applied"] is True
    assert payload["deleted_counts"]["run_events"] >= 1


def _seed_retention_rows(session, now: datetime) -> None:
    store = ResearchStore(session)
    project = store.create_project("Retention", "retention")
    run = store.create_run("Test retention.", project=project)

    old = now - timedelta(days=800)
    recent = now - timedelta(days=1)

    old_event = store.append_run_event(run, "run.old")
    old_event.created_at = old
    recent_event = store.append_run_event(run, "run.recent")
    recent_event.created_at = recent

    old_call = store.start_tool_call(run, "old.tool")
    old_call.created_at = old
    recent_call = store.start_tool_call(run, "recent.tool")
    recent_call.created_at = recent

    session.add(
        ResearchNotification(
            project_id=project.id,
            run_id=run.id,
            recipient_email="reviewer@example.com",
            notification_type="review_ready",
            title="Old notification",
            created_at=old,
        )
    )
    session.add(
        ResearchNotification(
            project_id=project.id,
            run_id=run.id,
            recipient_email="reviewer@example.com",
            notification_type="review_ready",
            title="Recent notification",
            created_at=recent,
        )
    )
    session.add(
        ResearchAuditEvent(
            project_id=project.id,
            run_id=run.id,
            actor_email="reviewer@example.com",
            action="old",
            target_type="run",
            target_id=run.id,
            created_at=old,
        )
    )
    session.add(
        ResearchAuditEvent(
            project_id=project.id,
            run_id=run.id,
            actor_email="reviewer@example.com",
            action="recent",
            target_type="run",
            target_id=run.id,
            created_at=recent,
        )
    )
    session.add(
        GatewaySession(
            id="old-session",
            channel="websocket",
            user_id="reviewer@example.com",
            created_at=old,
            last_active=old,
        )
    )
    session.add(
        GatewaySession(
            id="recent-session",
            channel="websocket",
            user_id="reviewer@example.com",
            created_at=recent,
            last_active=recent,
        )
    )
    session.commit()


def _document(
    name: str,
    source_path: str,
    updated_at: datetime,
    source_quality: dict[str, object] | None = None,
) -> Document:
    digest = f"{name:0<64}"[:64]
    return Document(
        source_path=source_path,
        source_type="object_store",
        file_hash=digest,
        title=f"{name} document",
        status="completed",
        source_quality_json=json.dumps(source_quality) if source_quality is not None else None,
        created_at=updated_at,
        updated_at=updated_at,
        processed_at=updated_at,
    )
