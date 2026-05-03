"""Tests for Slack app command and action handlers."""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.slack_app import SlackAppService, verify_slack_signature


def test_slack_app_handles_review_queue_buttons_and_decision(temp_directory: Path):
    """Slack service should expose review queue buttons and execute decisions."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'slack_app.db'}")
    session = session_factory()
    try:
        store = ResearchStore(session)
        project, run = _seed_slack_project(store)

        queue = SlackAppService(store).handle_command("review slack-project", "reviewer@example.com")
        assert "waiting for review" in queue.text
        assert queue.blocks[2]["elements"][1]["action_id"] == "hal_promote"

        payload = {
            "user": {"profile": {"email": "reviewer@example.com"}},
            "actions": [
                {
                    "action_id": "hal_promote",
                    "value": json.dumps({"run_id": run.id, "rationale": "Looks good."}),
                }
            ],
        }
        decision = SlackAppService(store).handle_action(payload)
        session.commit()

        assert decision.text == f"Run `{run.id}` is now `promoted`."
        assert store.get_run(run.id).status == "promoted"
        assert store.list_runs(project=project)[0].id == run.id
    finally:
        session.close()


def test_slack_command_cli_queues_run(temp_directory: Path):
    """CLI adapter should process slash command text for gateway workers."""
    db_path = temp_directory / "slack_cli.db"
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
        project = store.create_project("Slack CLI", "slack-cli")
        user = store.create_user("slack@example.com")
        store.grant_project_access(project, "user", user.id, "contributor")
        session.commit()
    finally:
        session.close()

    result = CliRunner().invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "slack-command",
            "--user",
            "slack@example.com",
            "--text",
            "queue slack-cli Find alloy creep evidence",
            "--json",
        ],
        obj={},
    )

    assert result.exit_code == 0, result.output
    assert "Queued HAL research run" in result.output


def test_verify_slack_signature_accepts_current_signed_body():
    """Signature helper should validate Slack v0 HMAC requests."""
    secret = "test-secret"
    timestamp = "1700000000"
    body = b"token=x&team_id=T&text=status"
    base = b"v0:" + timestamp.encode("utf-8") + b":" + body
    signature = "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()

    assert verify_slack_signature(secret, timestamp, body, signature, now=1700000001)
    assert not verify_slack_signature(secret, timestamp, body, "v0=bad", now=1700000001)


def _seed_slack_project(store: ResearchStore):
    project = store.create_project("Slack Project", "slack-project")
    reviewer = store.create_user("reviewer@example.com")
    store.grant_project_access(project, "user", reviewer.id, "reviewer")
    run = store.create_run("Review from Slack.", project=project)
    store.update_run_status(run, "staged", actor="worker")
    store.stage_output(
        "Slack Brief",
        "research_brief",
        project=project,
        run=run,
        content="# Brief",
    )
    return project, run
