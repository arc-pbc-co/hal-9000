"""Tests for research output generation."""

import json
from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import Document, init_db
from hal9000.db.store import ClaimEvidence, ResearchStore
from hal9000.research import ResearchOutputGenerator, load_program


def test_output_generator_stages_program_contract_outputs(temp_directory: Path):
    """Required program outputs should be staged through ResearchStore."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'outputs.db'}")
    session = session_factory()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        program = load_program(repo_root / "templates/research/programs/literature-review.md")

        store = ResearchStore(session)
        project = store.create_project(name="Dogfood", slug="dogfood")
        record = store.save_program(program, project=project)
        run = store.create_run(
            objective=record.objective,
            project=project,
            program=record,
            initiated_by="test",
        )
        store.append_run_event(run, "run.queued", actor="test")
        store.update_run_status(run, "running", actor="worker")
        document = Document(
            source_path="/papers/source.pdf",
            source_type="local",
            file_hash="d" * 64,
            title="Source Paper",
            year=2024,
            normalized_citation="Smith et al. (2024). Source Paper.",
            citation_key="smith-2024-source-paper",
        )
        session.add(document)
        session.flush()
        chunk = store.add_document_chunk(
            document=document,
            run=run,
            chunk_index=0,
            content="Single crystal samples showed superior creep resistance.",
        )
        store.add_claim_with_evidence(
            document=document,
            chunk=chunk,
            run=run,
            claim_evidence=ClaimEvidence(
                claim_text="Single crystal samples showed superior creep resistance.",
                evidence_text="Single crystal samples showed superior creep resistance.",
                quote="Single crystal samples showed superior creep resistance.",
                locator="p. 4",
                confidence=0.88,
                provenance={
                    "figures": [
                        {
                            "label": "Figure 2",
                            "caption": "Creep rupture comparison.",
                        }
                    ]
                },
            ),
        )

        generator = ResearchOutputGenerator(store)
        staged = generator.stage_contract_outputs(run, created_by="worker")
        report = generator.stage_run_report(run, created_by="worker")
        session.commit()

        output_types = [output.output_type for output in staged.outputs]
        assert output_types == ["research_brief", "evidence_table", "open_questions"]
        assert all(output.status == "staged" for output in staged.outputs)
        assert "Single crystal samples" in staged.outputs[0].content
        assert "[S1]" in staged.outputs[0].content
        assert "## Sources" in staged.outputs[0].content
        assert "Figure 2" in staged.outputs[0].content
        assert "| Single crystal samples" in staged.outputs[1].content
        assert "| [S1] | Source Paper | p. 4 |" in staged.outputs[1].content
        assert "contradictory sources" in staged.outputs[2].content
        assert staged.outputs[0].versions[0].version_number == 1
        assert run.status == "staged"
        assert report.output_type == "run_report"
        assert "Run Report" in report.content
        assert [event.event_type for event in run.events] == [
            "run.queued",
            "run.running",
            "outputs.staged",
            "run.staged",
            "output.run_report.staged",
        ]
    finally:
        session.close()


def test_output_version_cli_lists_and_diffs_versions(temp_directory: Path):
    """CLI should list output versions and render diffs."""
    db_path = temp_directory / "output_cli.db"
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
        output = store.stage_output(
            title="CLI Brief",
            output_type="research_brief",
            content="# Brief\n\nInitial.",
            created_by="hal",
        )
        store.update_output_content(
            output,
            content="# Brief\n\nUpdated with citations.",
            change_summary="Added citations.",
            created_by="reviewer@example.com",
        )
        output_id = output.id
        session.commit()
    finally:
        session.close()

    runner = CliRunner()
    versions_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "output-versions",
            output_id,
            "--json",
        ],
        obj={},
    )
    assert versions_result.exit_code == 0, versions_result.output
    assert '"version_number": 2' in versions_result.output

    diff_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "diff-output",
            output_id,
            "--from-version",
            "1",
            "--to-version",
            "2",
        ],
        obj={},
    )
    assert diff_result.exit_code == 0, diff_result.output
    assert "-Initial." in diff_result.output
    assert "+Updated with citations." in diff_result.output


def test_output_generator_renders_json_contract_outputs(temp_directory: Path):
    """JSON output contracts should stage JSON content."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'json_outputs.db'}")
    session = session_factory()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        program = load_program(
            repo_root / "templates/research/programs/adam-experiment-context.md"
        )

        store = ResearchStore(session)
        project = store.create_project(name="ADAM Dogfood", slug="adam-dogfood")
        record = store.save_program(program, project=project)
        run = store.create_run(objective=record.objective, project=project, program=record)
        document = Document(
            source_path="/papers/adam.pdf",
            source_type="local",
            file_hash="e" * 64,
            title="ADAM Source Paper",
        )
        session.add(document)
        session.flush()
        chunk = store.add_document_chunk(
            document=document,
            run=run,
            chunk_index=0,
            content="Heat treatment improves creep resistance.",
        )
        store.add_claim_with_evidence(
            document=document,
            chunk=chunk,
            run=run,
            claim_evidence=ClaimEvidence(
                claim_text="Heat treatment improves creep resistance.",
                quote="Heat treatment improves creep resistance.",
                locator="section 3",
                confidence=0.75,
            ),
        )

        staged = ResearchOutputGenerator(store).stage_contract_outputs(run)
        session.commit()

        assert [output.output_type for output in staged.outputs] == [
            "adam_context",
            "hypothesis_cards",
            "experiment_suggestions",
        ]
        first_payload = json.loads(staged.outputs[0].content)
        assert first_payload["output_type"] == "adam_context"
        assert first_payload["metadata"]["program_id"] == record.id
        assert first_payload["source_claims"][0]["claim_text"] == "Heat treatment improves creep resistance."
        assert first_payload["source_claims"][0]["citation"]["marker"] == "[S1]"
        assert first_payload["citations"][0]["marker"] == "[S1]"
        assert staged.outputs[0].format == "json"

        hypothesis_payload = json.loads(staged.outputs[1].content)
        experiment_payload = json.loads(staged.outputs[2].content)
        assert hypothesis_payload["hypothesis_cards"][0]["confidence_score"] == 0.75
        assert experiment_payload["experiment_suggestions"][0]["priority"] == "medium"
    finally:
        session.close()
