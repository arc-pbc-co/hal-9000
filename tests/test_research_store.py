"""Tests for shared research store repository helpers."""

import json
from pathlib import Path

import pytest

from hal9000.db.models import Document, ReviewDecision, init_db
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


def test_store_manages_users_teams_and_project_access(temp_directory: Path):
    """The store should manage basic firm access grants."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'governance.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project(name="Governance", slug="governance")
        user = store.create_user(
            email="Researcher@Example.com",
            display_name="Researcher",
        )
        team = store.create_team(slug="materials", name="Materials")
        membership = store.add_team_member(team, user, role="manager")
        permission = store.grant_project_access(
            project,
            principal_type="team",
            principal_id=team.id,
            role="reviewer",
            granted_by="admin@example.com",
        )
        session.commit()

        assert user.email == "researcher@example.com"
        assert store.get_user_by_email("RESEARCHER@example.com").id == user.id
        assert store.get_team_by_slug("materials").id == team.id
        assert membership.role == "manager"
        assert permission.role == "reviewer"
        assert store.can_access_project(project, user, "viewer") is True
        assert store.can_access_project(project, user, "reviewer") is True
        assert store.can_access_project(project, user, "admin") is False
        assert store.list_project_permissions(project)[0].principal_type == "team"
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


def test_store_records_tool_calls(temp_directory: Path):
    """Tool calls should be durable accounting records attached to runs."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'tool_calls.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        run = store.create_run(objective="Acquire papers.")

        call = store.start_tool_call(
            run,
            tool_name="acquisition.acquire",
            actor="worker",
            input={"topic": "superalloys", "max_papers": 2},
        )
        store.finish_tool_call(
            call,
            output={"papers_downloaded": 1, "papers_processed": 1},
        )
        session.commit()

        calls = store.list_tool_calls(run)

        assert len(calls) == 1
        assert calls[0].sequence == 1
        assert calls[0].status == "completed"
        assert json.loads(calls[0].input_json)["max_papers"] == 2
        assert json.loads(calls[0].output_json)["papers_processed"] == 1
        assert calls[0].completed_at is not None
    finally:
        session.close()


@pytest.mark.parametrize(
    ("input_decision", "stored_decision"),
    [
        ("promote", "promoted"),
        ("reject", "rejected"),
        ("request-changes", "changes_requested"),
    ],
)
def test_store_reviews_all_staged_run_outputs(
    temp_directory: Path,
    input_decision: str,
    stored_decision: str,
):
    """Run review should record output decisions and advance run lifecycle."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / f'run_review_{stored_decision}.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project(name="Review", slug="review")
        run = store.create_run(objective="Review staged outputs.", project=project)
        store.update_run_status(run, "staged", actor="worker")
        first = store.stage_output(
            title="Brief",
            output_type="research_brief",
            project=project,
            run=run,
            content="# Brief",
        )
        second = store.stage_output(
            title="Questions",
            output_type="open_questions",
            project=project,
            run=run,
            content="# Questions",
        )

        result = store.review_run_outputs(
            run,
            decision=input_decision,
            reviewer="reviewer@example.com",
            rationale="Add stronger source coverage.",
        )
        session.commit()

        assert result.run.status == stored_decision
        assert result.event.event_type == f"run.{stored_decision}"
        assert first.status == stored_decision
        assert second.status == stored_decision
        assert len(result.decisions) == 2
        assert session.query(ReviewDecision).count() == 2
        payload = json.loads(result.event.payload_json)
        assert payload["decision"] == stored_decision
        assert payload["reviewer"] == "reviewer@example.com"
        assert payload["output_ids"] == [first.id, second.id]
    finally:
        session.close()
