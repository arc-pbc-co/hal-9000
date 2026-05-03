"""Tests for firm-wide research output exports."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.exports import ResearchOutputExporter
from hal9000.storage import LocalObjectStore


def test_exporter_writes_all_firmwide_targets(temp_directory: Path):
    """Exporter should package promoted outputs for all firm-wide targets."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'exports.db'}")
    session = session_factory()
    object_store = LocalObjectStore(temp_directory / "objects")

    try:
        store = ResearchStore(session)
        project = store.create_project(name="Export Project", slug="export-project")
        run = store.create_run(objective="Package promoted outputs.", project=project)
        store.update_run_status(run, "staged", actor="worker")
        store.stage_output(
            title="Research Brief",
            output_type="research_brief",
            project=project,
            run=run,
            content="# Brief\n\nPromoted finding.",
            format="markdown",
        )
        store.stage_output(
            title="ADAM Context",
            output_type="adam_context",
            project=project,
            run=run,
            content=json.dumps(
                {
                    "output_type": "adam_context",
                    "context_id": run.id,
                    "name": "Export Project",
                    "description": run.objective,
                    "literature_summary": {"papers_analyzed": 0, "key_findings": []},
                    "metadata": {"run_id": run.id},
                }
            ),
            format="json",
        )
        store.review_run_outputs(run, decision="promote", reviewer="reviewer@example.com")
        session.commit()

        exporter = ResearchOutputExporter(session, object_store, artifact_prefix="firm-exports")
        results = exporter.export_run(run)

        assert {result.target for result in results} == {
            "adam",
            "obsidian",
            "markdown",
            "json",
            "dashboard",
        }
        assert all(result.output_count == 2 for result in results)
        for result in results:
            assert result.artifact_uri.startswith("hal-local://firm-exports/")
            manifest_key = result.artifact_uri.removeprefix("hal-local://")
            manifest = json.loads(object_store.get_bytes(manifest_key))
            assert manifest["scope"] == "run"
            assert manifest["output_count"] == 2

        adam_result = next(result for result in results if result.target == "adam")
        adam_key = adam_result.manifest["artifacts"][0]["key"]
        adam_payload = json.loads(object_store.get_bytes(adam_key))
        assert adam_payload["adam_contexts"][0]["context"]["output_type"] == "adam_context"

        dashboard_result = next(result for result in results if result.target == "dashboard")
        dashboard_key = dashboard_result.manifest["artifacts"][0]["key"]
        dashboard_payload = json.loads(object_store.get_bytes(dashboard_key))
        assert dashboard_payload["summary"]["outputs_by_status"] == {"promoted": 2}

        obsidian_result = next(result for result in results if result.target == "obsidian")
        assert obsidian_result.artifact_count == 4
        assert any(artifact["kind"] == "obsidian_note" for artifact in obsidian_result.manifest["artifacts"])
    finally:
        session.close()


def test_exporter_validates_adam_context_json(temp_directory: Path):
    """ADAM exports should reject malformed ADAM context outputs."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'bad_adam.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project(name="Bad ADAM", slug="bad-adam")
        run = store.create_run(objective="Validate ADAM output.", project=project)
        store.update_run_status(run, "staged", actor="worker")
        store.stage_output(
            title="Broken ADAM Context",
            output_type="adam_context",
            project=project,
            run=run,
            content=json.dumps({"output_type": "adam_context"}),
            format="json",
        )
        store.review_run_outputs(run, decision="promote", reviewer="reviewer@example.com")
        session.commit()

        exporter = ResearchOutputExporter(
            session,
            LocalObjectStore(temp_directory / "objects"),
        )

        with pytest.raises(ValueError, match="missing required key"):
            exporter.export_run(run, targets=("adam",))
    finally:
        session.close()


def test_research_export_run_cli_writes_configured_storage(temp_directory: Path):
    """CLI export should use configured object storage and emit machine-readable results."""
    db_path = temp_directory / "cli_exports.db"
    object_root = temp_directory / "objects"
    config_path = temp_directory / "config.yaml"
    config_path.write_text(
        f"""hal9000:
  database:
    url: sqlite:///{db_path}
  storage:
    backend: local
    root_path: {object_root}
"""
    )
    _, session_factory = init_db(f"sqlite:///{db_path}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project(name="CLI Export", slug="cli-export")
        run = store.create_run(objective="Export from CLI.", project=project)
        store.update_run_status(run, "staged", actor="worker")
        store.stage_output(
            title="CLI Brief",
            output_type="research_brief",
            project=project,
            run=run,
            content="# CLI Brief",
        )
        store.review_run_outputs(run, decision="promote", reviewer="reviewer@example.com")
        session.commit()
        run_id = run.id
    finally:
        session.close()

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "export-run",
            run_id,
            "--target",
            "json",
            "--json",
        ],
        obj={},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["scope"] == "run"
    assert payload["exports"][0]["target"] == "json"
    manifest_key = payload["exports"][0]["artifact_uri"].removeprefix("hal-local://")
    assert (object_root / manifest_key).exists()
