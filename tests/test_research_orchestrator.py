"""Tests for bounded research run execution."""

from pathlib import Path

import pytest

from hal9000.db.models import Document, ResearchOutput, init_db
from hal9000.db.store import ResearchStore
from hal9000.research import BoundedResearchWorker, load_program
from hal9000.research.pipeline import ResearchCorpusPipeline
from hal9000.vector import FakeEmbeddingProvider, VectorRepository


def test_bounded_worker_executes_queued_run(temp_directory: Path):
    """The worker should move queued runs to staged outputs."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'worker.db'}")
    session = session_factory()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        program = load_program(repo_root / "templates/research/programs/literature-review.md")

        store = ResearchStore(session)
        project = store.create_project(name="Worker Test", slug="worker-test")
        record = store.save_program(program, project=project)
        run = store.create_run(
            objective=record.objective,
            project=project,
            program=record,
            initiated_by="test",
        )
        store.append_run_event(run, "run.queued", actor="test")

        result = BoundedResearchWorker(store, actor="test-worker").execute_run(run.id)
        session.commit()

        assert result.run.status == "staged"
        assert len(result.output_ids) == 3
        assert result.run_report_id is not None
        assert session.query(ResearchOutput).count() == 4
        assert [event.event_type for event in run.events] == [
            "run.queued",
            "run.running",
            "outputs.staged",
            "run.staged",
            "output.run_report.staged",
            "worker.completed",
        ]
    finally:
        session.close()


def test_bounded_worker_rejects_completed_run(temp_directory: Path):
    """The worker should reject runs that are no longer executable."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'worker_reject.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        run = store.create_run(objective="Already done.")
        store.update_run_status(run, "completed", actor="test")

        with pytest.raises(ValueError, match="must be queued or running"):
            BoundedResearchWorker(store).execute_run(run.id)
    finally:
        session.close()


def test_bounded_worker_attaches_retrieval_context(temp_directory: Path):
    """The worker should retrieve embedded project chunks before staging outputs."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'worker_retrieval.db'}")
    session = session_factory()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        program = load_program(repo_root / "templates/research/programs/literature-review.md")

        store = ResearchStore(session)
        project = store.create_project(name="Retrieval Test", slug="retrieval-test")
        record = store.save_program(program, project=project)
        prior_run = store.create_run(
            objective="Prior corpus-building run.",
            project=project,
            program=record,
        )
        document = Document(
            source_path="/papers/retrieval.pdf",
            source_type="local",
            file_hash="r" * 64,
            title="Retrieval Source",
        )
        session.add(document)
        session.flush()
        chunk = store.add_document_chunk(
            document=document,
            run=prior_run,
            chunk_index=0,
            content="Single crystal samples showed superior creep resistance.",
        )
        provider = FakeEmbeddingProvider(dimension=8)
        VectorRepository(session).embed_and_store_chunk(chunk, provider)

        run = store.create_run(
            objective="Single crystal samples showed superior creep resistance.",
            project=project,
            program=record,
            initiated_by="test",
        )
        result = BoundedResearchWorker(
            store,
            actor="retrieval-worker",
            retrieval_provider=provider,
            retrieval_limit=3,
        ).execute_run(run.id)
        session.commit()

        assert len(result.retrieval_context) == 1
        assert result.retrieval_context[0]["chunk_id"] == chunk.id
        assert "retrieval.context.attached" in [event.event_type for event in run.events]

        brief = (
            session.query(ResearchOutput)
            .filter_by(run_id=run.id, output_type="research_brief")
            .one()
        )
        assert "Retrieved Context" in brief.content
        assert "Single crystal samples" in brief.content
    finally:
        session.close()


def test_bounded_worker_prepares_corpus_before_outputs(temp_directory: Path):
    """The worker should chunk, embed, extract claims, retrieve, and stage outputs."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'worker_pipeline.db'}")
    session = session_factory()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        program = load_program(repo_root / "templates/research/programs/literature-review.md")

        store = ResearchStore(session)
        project = store.create_project(name="Worker Pipeline", slug="worker-pipeline")
        record = store.save_program(program, project=project)
        document = Document(
            source_path="/papers/worker-pipeline.pdf",
            source_type="acquisition",
            file_hash="w" * 64,
            title="Worker Pipeline Source",
            findings='["Heat treatment improves creep resistance in nickel superalloys."]',
            full_text="Heat treatment improves creep resistance in nickel superalloys.",
            status="completed",
        )
        session.add(document)
        session.flush()

        run = store.create_run(
            objective="Find creep resistance findings.",
            project=project,
            program=record,
            initiated_by="test",
        )
        provider = FakeEmbeddingProvider(dimension=8)
        result = BoundedResearchWorker(
            store,
            actor="pipeline-worker",
            retrieval_provider=provider,
            retrieval_limit=3,
            corpus_pipeline=ResearchCorpusPipeline(
                store,
                embedding_provider=provider,
                chunk_size=100,
            ),
        ).execute_run(run.id)
        session.commit()

        assert result.corpus_document_ids == [document.id]
        assert len(result.corpus_chunk_ids) == 1
        assert len(result.corpus_claim_ids) == 1
        assert len(result.retrieval_context) == 1
        assert run.status == "staged"

        brief = (
            session.query(ResearchOutput)
            .filter_by(run_id=run.id, output_type="research_brief")
            .one()
        )
        assert "Heat treatment improves creep resistance" in brief.content
        assert "corpus.prepared" in [event.event_type for event in run.events]
    finally:
        session.close()
