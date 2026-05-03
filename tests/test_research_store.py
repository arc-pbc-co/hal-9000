"""Tests for shared research store repository helpers."""

import json
from pathlib import Path

from hal9000.db.models import Document, init_db
from hal9000.db.store import ClaimEvidence, ResearchStore
from hal9000.research import load_program, render_program_template


def test_store_persists_program_run_output_and_review(temp_directory: Path):
    """The store should persist the main project/program/run/output workflow."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'store.db'}")
    session = session_factory()

    try:
        program_path = temp_directory / "program.md"
        program_path.write_text(
            render_program_template(
                name="Creep Review",
                objective="Find source-backed creep findings.",
                owner="research@example.com",
            )
        )
        program = load_program(program_path)

        store = ResearchStore(session)
        project = store.create_project(
            name="Superalloys",
            slug="superalloys",
            owner="research@example.com",
        )
        record = store.save_program(program, project=project)
        run = store.create_run(
            objective=record.objective,
            project=project,
            program=record,
            initiated_by="research@example.com",
            budget={"max_papers": 25},
            tool_policy={"allowed_tools": ["search", "rlm"]},
        )
        output = store.stage_output(
            title="Creep Review Brief",
            output_type="research_brief",
            project=project,
            run=run,
            content="# Brief",
            source={"program_id": record.id, "run_id": run.id},
            created_by="hal",
        )
        decision = store.record_review_decision(
            output,
            decision="promoted",
            reviewer="head-of-engineering@example.com",
        )
        session.commit()

        saved_project = store.get_project_by_slug("superalloys")

        assert saved_project is not None
        assert saved_project.programs[0].name == "Creep Review"
        assert json.loads(saved_project.runs[0].budget_json)["max_papers"] == 25
        assert saved_project.outputs[0].status == "promoted"
        assert decision.output.status == "promoted"
        assert json.loads(record.tags) == ["literature-review"]
    finally:
        session.close()


def test_store_persists_chunk_claim_and_evidence(temp_directory: Path):
    """The store should hide relationship boilerplate for claim extraction."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'claims.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        run = store.create_run(objective="Extract claims.")
        document = Document(
            source_path="/papers/source.pdf",
            source_type="local",
            file_hash="c" * 64,
            title="Source Paper",
        )
        session.add(document)
        session.flush()

        chunk = store.add_document_chunk(
            document=document,
            run=run,
            chunk_index=0,
            content="Single crystal samples showed superior creep resistance.",
            char_start=0,
            char_end=60,
            extraction_metadata={"processor": "test"},
        )
        claim = store.add_claim_with_evidence(
            document=document,
            chunk=chunk,
            run=run,
            claim_evidence=ClaimEvidence(
                claim_text="Single crystal samples showed superior creep resistance.",
                evidence_text="Single crystal samples showed superior creep resistance.",
                quote="Single crystal samples showed superior creep resistance.",
                locator="p. 4",
                confidence=0.82,
                provenance={"model": "test-model"},
            ),
        )
        session.commit()

        assert len(chunk.text_hash) == 64
        assert json.loads(chunk.extraction_metadata)["processor"] == "test"
        assert claim.status == "staged"
        assert claim.evidence_links[0].locator == "p. 4"
        assert json.loads(claim.provenance_json)["model"] == "test-model"
        assert run.claims[0].confidence == 0.82
    finally:
        session.close()


def test_store_appends_ordered_run_events_and_updates_status(temp_directory: Path):
    """Run lifecycle events should be ordered and update run status timestamps."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'run_events.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        run = store.create_run(objective="Run lifecycle test.")

        first = store.append_run_event(
            run,
            event_type="run.queued",
            message="Run entered the queue.",
            actor="tester@example.com",
            payload={"priority": "normal"},
        )
        second = store.update_run_status(
            run,
            status="running",
            message="Worker started the run.",
            actor="worker",
            payload={"worker_id": "worker-1"},
        )
        third = store.update_run_status(
            run,
            status="staged",
            message="Outputs are ready for review.",
            actor="worker",
        )
        session.commit()

        events = store.list_run_events(run)

        assert [event.sequence for event in events] == [1, 2, 3]
        assert [event.event_type for event in events] == [
            "run.queued",
            "run.running",
            "run.staged",
        ]
        assert first.payload_json == '{"priority": "normal"}'
        assert json.loads(second.payload_json)["worker_id"] == "worker-1"
        assert third.message == "Outputs are ready for review."
        assert run.status == "staged"
        assert run.started_at is not None
        assert run.completed_at is not None
    finally:
        session.close()
