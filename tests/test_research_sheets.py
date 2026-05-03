"""Tests for Google Sheets project sync jobs."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.sheets import GoogleSheetsAPIClient, SheetsSyncService


class _FakeSheetsClient:
    def __init__(self):
        self.calls = []

    def update_values(self, spreadsheet_id, range_name, values):
        self.calls.append((spreadsheet_id, range_name, values))
        return {"updatedRange": range_name, "updatedRows": len(values)}


def test_sheets_sync_service_writes_review_queue_rows(temp_directory: Path):
    """Sheets sync should build authorized review queue rows and call client."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'sheets.db'}")
    session = session_factory()
    try:
        store = ResearchStore(session)
        project, _ = _seed_sheets_project(store)
        client = _FakeSheetsClient()

        result = SheetsSyncService(store, client).sync_project_view(
            project,
            target="review_queue",
            spreadsheet_id="sheet-123",
            range_name="Review!A1",
            actor_email="reviewer@example.com",
            reviewer_email="reviewer@example.com",
        )
        session.commit()

        assert result.status == "sent"
        assert result.row_count == 1
        assert client.calls[0][0] == "sheet-123"
        assert client.calls[0][2][0] == [
            "run_id",
            "project_slug",
            "program",
            "objective",
            "output_count",
            "updated_at",
        ]
        assert client.calls[0][2][1][1] == "sheets-project"
    finally:
        session.close()


def test_sheets_sync_cli_dry_run_records_result(temp_directory: Path):
    """CLI should support dry-run Sheets sync without Google credentials."""
    db_path = temp_directory / "sheets_cli.db"
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
        _seed_sheets_project(store)
        session.commit()
    finally:
        session.close()

    result = CliRunner().invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "sync-sheets",
            "sheets-project",
            "--target",
            "runs",
            "--spreadsheet-id",
            "sheet-123",
            "--range-name",
            "Runs!A1",
            "--actor",
            "reviewer@example.com",
            "--dry-run",
            "--json",
        ],
        obj={},
    )

    assert result.exit_code == 0, result.output
    assert '"status": "skipped"' in result.output
    assert '"target": "runs"' in result.output


def test_google_sheets_api_client_uses_values_update(monkeypatch):
    """Native client should call the Google Sheets Values API."""
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"updatedRange": "Runs!A1"}

    def fake_put(url, params, headers, json, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("hal9000.research.sheets.httpx.put", fake_put)

    result = GoogleSheetsAPIClient(
        access_token="token",
        base_url="https://sheets.example/v4/spreadsheets",
    ).update_values("sheet-123", "Runs!A1", [["run_id"], ["run-1"]])

    assert result["updatedRange"] == "Runs!A1"
    assert captured["url"] == "https://sheets.example/v4/spreadsheets/sheet-123/values/Runs!A1"
    assert captured["headers"]["Authorization"] == "Bearer token"
    assert captured["json"] == {"values": [["run_id"], ["run-1"]]}


def _seed_sheets_project(store: ResearchStore):
    project = store.create_project("Sheets Project", "sheets-project")
    reviewer = store.create_user("reviewer@example.com")
    store.grant_project_access(project, "user", reviewer.id, "reviewer")
    run = store.create_run("Sync review queue.", project=project, initiated_by="reviewer@example.com")
    store.update_run_status(run, "staged", actor="worker")
    store.stage_output(
        "Sheets Brief",
        "research_brief",
        project=project,
        run=run,
        content="# Brief",
    )
    return project, run
