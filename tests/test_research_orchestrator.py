"""Tests for bounded research run execution."""

from datetime import timedelta
from pathlib import Path

import pytest

from hal9000.db.models import Document, ResearchOutput, init_db, utc_now
from hal9000.db.store import ResearchStore
from hal9000.research import BoundedResearchWorker, load_program
from hal9000.research.acquisition import WorkerAcquisitionResult
from hal9000.research.budget import BudgetExceededError
from hal9000.research.pipeline import ResearchCorpusPipeline
from hal9000.vector import FakeEmbeddingProvider, VectorRepository


class FakeAcquisitionRunner:
    """Deterministic acquisition runner for worker tests."""

    def __init__(self, result: WorkerAcquisitionResult | None = None):
        self.result = result or WorkerAcquisitionResult(
            papers_found=1,
            papers_downloaded=1,
            papers_processed=1,
            document_ids=["doc-1"],
            paper_events=[
                {
                    "status": "processed",
                    "stage": "process",
                    "title": "Fake Paper",
                    "identifier": "doi:10.1234/fake",
                    "document_id": "doc-1",
                }
            ],
        )
        self.calls: list[tuple[str, int]] = []

    def acquire(
        self,
        topic: str,
        max_papers: int,
        progress_callback=None,
        llm_call_callback=None,
    ) -> WorkerAcquisitionResult:
        """Record a fake acquisition call."""
        self.calls.append((topic, max_papers))
        if progress_callback:
            progress_callback("Searching", 0, 1)
            progress_callback("Searching", 1, 1)
        return self.result


class FakeLLMAcquisitionRunner(FakeAcquisitionRunner):
    """Fake acquisition runner that emits LLM call callbacks."""

    def __init__(self, llm_calls: int):
        super().__init__()
        self.llm_calls = llm_calls

    def acquire(
        self,
        topic: str,
        max_papers: int,
        progress_callback=None,
        llm_call_callback=None,
    ) -> WorkerAcquisitionResult:
        """Emit deterministic LLM call callbacks."""
        self.calls.append((topic, max_papers))
        if llm_call_callback:
            for index in range(self.llm_calls):
                llm_call_callback(
                    {
                        "model": "fake-model",
                        "prompt_chars": 100 + index,
                        "max_tokens": 1000,
                        "call_index": index + 1,
                    }
                )
        return self.result


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


def test_bounded_worker_runs_acquisition_with_tool_call_accounting(temp_directory: Path):
    """The worker should run allowed acquisition through durable tool calls."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'worker_acquisition.db'}")
    session = session_factory()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        program = load_program(repo_root / "templates/research/programs/literature-review.md")

        store = ResearchStore(session)
        project = store.create_project(name="Worker Acquisition", slug="worker-acquisition")
        record = store.save_program(program, project=project)
        run = store.create_run(
            objective="Acquire creep resistance papers.",
            project=project,
            program=record,
            budget={"max_papers": 4, "max_downloads": 2},
            tool_policy={"allowed_tools": ["search", "acquire", "ingest", "rlm"]},
        )
        acquisition_runner = FakeAcquisitionRunner()

        result = BoundedResearchWorker(
            store,
            actor="acquisition-worker",
            acquisition_runner=acquisition_runner,
        ).execute_run(run.id)
        session.commit()

        calls = store.list_tool_calls(run)

        assert acquisition_runner.calls == [("Acquire creep resistance papers.", 2)]
        assert result.acquisition is not None
        assert result.acquisition.papers_processed == 1
        assert len(calls) == 1
        assert calls[0].tool_name == "acquisition.acquire"
        assert calls[0].status == "completed"
        assert "paper_events" in calls[0].output_json
        assert "tool.acquisition.completed" in [event.event_type for event in run.events]
        assert "acquisition.progress" in [event.event_type for event in run.events]
        assert "acquisition.paper.processed" in [event.event_type for event in run.events]
    finally:
        session.close()


def test_bounded_worker_skips_acquisition_when_tool_policy_disallows_it(
    temp_directory: Path,
):
    """Tool policy should prevent live acquisition from running."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'worker_acquisition_skip.db'}")
    session = session_factory()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        program = load_program(repo_root / "templates/research/programs/literature-review.md")

        store = ResearchStore(session)
        record = store.save_program(program)
        run = store.create_run(
            objective="Do not acquire.",
            program=record,
            budget={"max_papers": 4, "max_downloads": 2},
            tool_policy={"allowed_tools": ["ingest"]},
        )
        acquisition_runner = FakeAcquisitionRunner()

        result = BoundedResearchWorker(
            store,
            actor="acquisition-worker",
            acquisition_runner=acquisition_runner,
        ).execute_run(run.id)
        session.commit()

        assert acquisition_runner.calls == []
        assert result.acquisition is None
        assert store.list_tool_calls(run) == []
        assert "acquisition.skipped" in [event.event_type for event in run.events]
    finally:
        session.close()


def test_bounded_worker_enforces_runtime_budget(temp_directory: Path):
    """The worker should fail a running job that has exceeded runtime budget."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'worker_runtime_budget.db'}")
    session = session_factory()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        program = load_program(repo_root / "templates/research/programs/literature-review.md")

        store = ResearchStore(session)
        record = store.save_program(program)
        run = store.create_run(
            objective="Expired run.",
            program=record,
            budget={"max_runtime_minutes": 1},
        )
        run.status = "running"
        run.started_at = utc_now() - timedelta(minutes=2)
        session.flush()

        with pytest.raises(BudgetExceededError, match="Runtime budget exceeded"):
            BoundedResearchWorker(store, actor="runtime-worker").execute_run(run.id)
        session.commit()

        assert run.status == "failed"
        assert "budget.runtime.exceeded" in [event.event_type for event in run.events]
    finally:
        session.close()


def test_bounded_worker_enforces_llm_call_budget(temp_directory: Path):
    """The worker should fail acquisition when LLM calls exceed budget."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'worker_llm_budget.db'}")
    session = session_factory()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        program = load_program(repo_root / "templates/research/programs/literature-review.md")

        store = ResearchStore(session)
        record = store.save_program(program)
        run = store.create_run(
            objective="LLM budgeted run.",
            program=record,
            budget={"max_papers": 2, "max_downloads": 2, "max_llm_calls": 1},
            tool_policy={"allowed_tools": ["acquire", "rlm"]},
        )

        with pytest.raises(BudgetExceededError, match="LLM call budget exceeded"):
            BoundedResearchWorker(
                store,
                actor="llm-budget-worker",
                acquisition_runner=FakeLLMAcquisitionRunner(llm_calls=2),
            ).execute_run(run.id)
        session.commit()

        calls = store.list_tool_calls(run)

        assert [call.tool_name for call in calls] == ["acquisition.acquire", "llm.call"]
        assert calls[0].status == "failed"
        assert run.status == "failed"
        assert "budget.llm_calls.exceeded" in [event.event_type for event in run.events]
    finally:
        session.close()
