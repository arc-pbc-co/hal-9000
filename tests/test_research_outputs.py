"""Tests for research output generation."""

import json
from pathlib import Path

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
        assert "| Single crystal samples" in staged.outputs[1].content
        assert "contradictory sources" in staged.outputs[2].content
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
        assert staged.outputs[0].format == "json"

        hypothesis_payload = json.loads(staged.outputs[1].content)
        experiment_payload = json.loads(staged.outputs[2].content)
        assert hypothesis_payload["hypothesis_cards"][0]["confidence_score"] == 0.75
        assert experiment_payload["experiment_suggestions"][0]["priority"] == "medium"
    finally:
        session.close()
