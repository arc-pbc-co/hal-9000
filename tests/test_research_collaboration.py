"""Tests for collaboration views and audit services."""

from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.collaboration import (
    CollaborationService,
    audit_event_payload,
    collection_payload,
    notification_payload,
    saved_search_payload,
    shared_view_payload,
)


def test_collaboration_service_manages_project_views_notifications_and_audit(
    temp_directory: Path,
):
    """Collaboration service should create and list shared project objects."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'collaboration_service.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project("Collaboration", "collaboration")
        run = store.create_run("Review collaboration output.", project=project)
        output = store.stage_output(
            "Collaboration Brief",
            "research_brief",
            project=project,
            run=run,
            content="# Brief",
        )
        service = CollaborationService(store)

        collection = service.create_collection(
            project,
            name="Head of Engineering Demo",
            owner_email="owner@example.com",
        )
        item = service.add_collection_item(
            collection,
            target_type="output",
            target_id=output.id,
            note="Use in demo.",
            added_by="owner@example.com",
        )
        search = service.save_search(
            project,
            name="Creep Claims",
            query_text="single crystal creep",
            target="memory",
            filters={"target": ["claims", "outputs"]},
            owner_email="owner@example.com",
        )
        view = service.create_shared_view(
            project,
            name="Review Dashboard",
            view_type="review_queue",
            config={"sections": ["queue", "failures"]},
            owner_email="owner@example.com",
        )
        notifications = service.create_review_ready_notifications(
            run,
            recipients=["reviewer@example.com"],
            channel="slack",
        )
        service.mark_notification(notifications[0], "sent")
        session.commit()

        assert collection_payload(collection)["items"][0]["target_id"] == item.target_id
        assert saved_search_payload(search)["filters"]["target"] == ["claims", "outputs"]
        assert shared_view_payload(view)["config"]["sections"] == ["queue", "failures"]
        assert notification_payload(notifications[0])["status"] == "sent"
        assert service.list_collections(project)[0].slug == "head-of-engineering-demo"
        assert service.list_saved_searches(project)[0].name == "Creep Claims"
        assert service.list_shared_views(project)[0].slug == "review-dashboard"
        assert service.list_notifications(recipient_email="reviewer@example.com")[0].channel == "slack"
        assert any(
            audit_event_payload(event)["action"] == "collection.item_added"
            for event in service.list_audit_events(project=project, target_type="output")
        )
    finally:
        session.close()


def test_collaboration_cli_commands(temp_directory: Path):
    """CLI should expose collaboration surfaces for non-CLI app adapters."""
    db_path = temp_directory / "collaboration_cli.db"
    config_path = temp_directory / "config.yaml"
    config_path.write_text(
        f"""hal9000:
  database:
    url: sqlite:///{db_path}
"""
    )
    _, session_factory = init_db(f"sqlite:///{db_path}")
    session = session_factory()
    try:
        store = ResearchStore(session)
        project = store.create_project("Collab CLI", "collab-cli")
        run = store.create_run("Collaboration CLI run.", project=project)
        store.update_run_status(run, "staged", actor="worker")
        output = store.stage_output(
            "CLI Brief",
            "research_brief",
            project=project,
            run=run,
            content="# Brief",
        )
        run_id = run.id
        output_id = output.id
        session.commit()
    finally:
        session.close()

    runner = CliRunner()
    create_collection = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "create-collection",
            "collab-cli",
            "--name",
            "Demo Collection",
            "--owner",
            "owner@example.com",
        ],
        obj={},
    )
    assert create_collection.exit_code == 0, create_collection.output
    assert "Research collection created" in create_collection.output

    add_item = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "add-collection-item",
            "collab-cli",
            "demo-collection",
            "--target-type",
            "output",
            "--target-id",
            output_id,
            "--added-by",
            "owner@example.com",
        ],
        obj={},
    )
    assert add_item.exit_code == 0, add_item.output

    save_search = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "save-search",
            "collab-cli",
            "--name",
            "Demo Search",
            "--query",
            "creep resistance",
            "--filters-json",
            '{"target": ["outputs"]}',
        ],
        obj={},
    )
    assert save_search.exit_code == 0, save_search.output

    create_view = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "create-shared-view",
            "collab-cli",
            "--name",
            "Review View",
            "--view-type",
            "review_queue",
            "--config-json",
            '{"sections": ["queue"]}',
        ],
        obj={},
    )
    assert create_view.exit_code == 0, create_view.output

    notify = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "notify-review-ready",
            run_id,
            "--recipient",
            "reviewer@example.com",
            "--channel",
            "slack",
        ],
        obj={},
    )
    assert notify.exit_code == 0, notify.output

    for command, expected in [
        (["collections", "collab-cli", "--json"], '"slug": "demo-collection"'),
        (["saved-searches", "collab-cli", "--json"], '"query_text": "creep resistance"'),
        (["shared-views", "collab-cli", "--json"], '"view_type": "review_queue"'),
        (["notifications", "--recipient", "reviewer@example.com", "--json"], '"channel": "slack"'),
        (
            ["deliver-notifications", "--channel", "slack", "--dry-run", "--json"],
            '"Dry run: notification was not delivered."',
        ),
        (["audit-events", "--project-slug", "collab-cli", "--json"], '"collection.created"'),
    ]:
        result = runner.invoke(
            cli,
            ["--config", str(config_path), "research", *command],
            obj={},
        )
        assert result.exit_code == 0, result.output
        assert expected in result.output
