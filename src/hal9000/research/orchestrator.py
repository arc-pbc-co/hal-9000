"""Bounded research run execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hal9000.db.models import ResearchRun
from hal9000.research.acquisition import AcquisitionRunner, WorkerAcquisitionResult
from hal9000.research.budget import BudgetExceededError, RunBudgetTracker
from hal9000.research.outputs import ResearchOutputGenerator
from hal9000.vector import EmbeddingProvider, VectorRepository

if TYPE_CHECKING:
    from hal9000.db.store import ResearchStore
    from hal9000.research.pipeline import ResearchCorpusPipeline


@dataclass
class RunExecutionResult:
    """Result of executing a bounded research run."""

    run: ResearchRun
    output_ids: list[str]
    run_report_id: str | None
    retrieval_context: list[dict[str, object]]
    corpus_document_ids: list[str]
    corpus_chunk_ids: list[str]
    corpus_claim_ids: list[str]
    acquisition: WorkerAcquisitionResult | None = None


class BoundedResearchWorker:
    """Minimal worker that executes queued runs through staged outputs."""

    def __init__(
        self,
        store: ResearchStore,
        actor: str = "hal-worker",
        retrieval_provider: EmbeddingProvider | None = None,
        retrieval_limit: int = 5,
        corpus_pipeline: ResearchCorpusPipeline | None = None,
        acquisition_runner: AcquisitionRunner | None = None,
    ):
        """Initialize the worker with a shared store."""
        self.store = store
        self.actor = actor
        self.output_generator = ResearchOutputGenerator(store)
        self.retrieval_provider = retrieval_provider
        self.retrieval_limit = retrieval_limit
        self.corpus_pipeline = corpus_pipeline
        self.acquisition_runner = acquisition_runner

    def execute_run(self, run_id: str) -> RunExecutionResult:
        """Execute a queued run and stage reviewable outputs."""
        run = self.store.get_run(run_id)
        if run is None:
            raise ValueError(f"Research run not found: {run_id}")
        if run.status not in {"queued", "running"}:
            raise ValueError(f"Research run must be queued or running, not {run.status}")

        try:
            if run.status == "queued":
                self.store.update_run_status(
                    run,
                    status="running",
                    message="Bounded worker started.",
                    actor=self.actor,
                )

            self._require_runtime_budget(run, "worker.start")
            acquisition_result = self._run_acquisition(run)
            self._require_runtime_budget(run, "corpus.prepare")
            corpus_result = self._prepare_corpus(run)
            self._require_runtime_budget(run, "retrieval.context")
            retrieval_context = self._build_retrieval_context(run)
            self._require_runtime_budget(run, "outputs.stage")
            staged = self.output_generator.stage_contract_outputs(
                run,
                created_by=self.actor,
                mark_run_staged=True,
                retrieval_context=retrieval_context,
            )
            report = self.output_generator.stage_run_report(run, created_by=self.actor)
            self.store.append_run_event(
                run,
                event_type="worker.completed",
                message="Bounded worker completed run execution.",
                actor=self.actor,
                payload={
                    "output_ids": staged.output_ids,
                    "run_report_id": report.id,
                    "corpus_document_ids": corpus_result.document_ids,
                    "corpus_chunk_ids": corpus_result.chunk_ids,
                    "corpus_claim_ids": corpus_result.claim_ids,
                    "acquisition": acquisition_result.to_dict()
                    if acquisition_result is not None
                    else None,
                },
            )
            return RunExecutionResult(
                run=run,
                output_ids=staged.output_ids,
                run_report_id=report.id,
                retrieval_context=retrieval_context,
                corpus_document_ids=corpus_result.document_ids,
                corpus_chunk_ids=corpus_result.chunk_ids,
                corpus_claim_ids=corpus_result.claim_ids,
                acquisition=acquisition_result,
            )
        except Exception as exc:
            self.store.update_run_status(
                run,
                status="failed",
                message=str(exc),
                actor=self.actor,
                payload={"error_type": type(exc).__name__},
            )
            raise

    def _run_acquisition(self, run: ResearchRun) -> WorkerAcquisitionResult | None:
        """Run live acquisition when configured and allowed by budget."""
        if self.acquisition_runner is None:
            return None

        tracker = RunBudgetTracker(run)
        try:
            max_papers = tracker.require_acquisition_budget()
        except BudgetExceededError as exc:
            self.store.append_run_event(
                run,
                event_type="acquisition.skipped",
                message=str(exc),
                actor=self.actor,
                payload={"reason": type(exc).__name__},
            )
            return None

        tool_call = self.store.start_tool_call(
            run,
            tool_name="acquisition.acquire",
            actor=self.actor,
            input={"topic": run.objective, "max_papers": max_papers},
        )
        self.store.append_run_event(
            run,
            event_type="tool.acquisition.started",
            message="Live acquisition started.",
            actor=self.actor,
            payload={"tool_call_id": tool_call.id, "max_papers": max_papers},
        )
        try:
            result = self.acquisition_runner.acquire(
                run.objective,
                max_papers=max_papers,
                progress_callback=self._progress_callback(run),
                llm_call_callback=self._llm_call_callback(run),
            )
        except Exception as exc:
            self.store.finish_tool_call(
                tool_call,
                status="failed",
                error_message=str(exc),
            )
            self.store.append_run_event(
                run,
                event_type="tool.acquisition.failed",
                message=str(exc),
                actor=self.actor,
                payload={"tool_call_id": tool_call.id, "error_type": type(exc).__name__},
            )
            raise

        self.store.finish_tool_call(
            tool_call,
            status="completed",
            output=result.to_dict(),
        )
        self.store.append_run_event(
            run,
            event_type="tool.acquisition.completed",
            message=(
                f"Live acquisition completed: {result.papers_downloaded} downloaded, "
                f"{result.papers_processed} processed."
            ),
            actor=self.actor,
            payload={"tool_call_id": tool_call.id, **result.to_dict()},
        )
        return result

    def _require_runtime_budget(self, run: ResearchRun, phase: str) -> None:
        """Ensure the run has runtime budget remaining."""
        try:
            RunBudgetTracker(run).require_runtime_budget()
        except BudgetExceededError as exc:
            self.store.append_run_event(
                run,
                event_type="budget.runtime.exceeded",
                message=str(exc),
                actor=self.actor,
                payload={"phase": phase},
            )
            raise

    def _progress_callback(self, run: ResearchRun):
        """Create a callback that records acquisition progress events."""
        def record_progress(stage: str, current: int, total: int) -> None:
            self._require_runtime_budget(run, f"acquisition.{stage}")
            self.store.append_run_event(
                run,
                event_type="acquisition.progress",
                message=f"{stage}: {current}/{total}",
                actor=self.actor,
                payload={"stage": stage, "current": current, "total": total},
            )

        return record_progress

    def _llm_call_callback(self, run: ResearchRun):
        """Create a callback that enforces and records LLM-call budget."""
        def record_llm_call(payload: dict[str, object]) -> None:
            self._require_runtime_budget(run, "llm.call")
            used_calls = len(
                [
                    call
                    for call in self.store.list_tool_calls(run)
                    if call.tool_name == "llm.call"
                ]
            )
            try:
                RunBudgetTracker(run).require_llm_call_budget(used_calls)
            except BudgetExceededError as exc:
                self.store.append_run_event(
                    run,
                    event_type="budget.llm_calls.exceeded",
                    message=str(exc),
                    actor=self.actor,
                    payload={"used_calls": used_calls, **payload},
                )
                raise

            call = self.store.start_tool_call(
                run,
                tool_name="llm.call",
                actor=self.actor,
                input=payload,
            )
            self.store.finish_tool_call(
                call,
                status="completed",
                output={"budget_reserved": True},
            )
            self.store.append_run_event(
                run,
                event_type="tool.llm_call.recorded",
                message=f"Recorded LLM call {used_calls + 1}.",
                actor=self.actor,
                payload={"tool_call_id": call.id, **payload},
            )

        return record_llm_call

    def _prepare_corpus(self, run: ResearchRun):
        """Prepare corpus records before retrieval/output generation."""
        if self.corpus_pipeline is None:
            from hal9000.research.pipeline import CorpusPipelineResult

            return CorpusPipelineResult()
        return self.corpus_pipeline.execute(run)

    def _build_retrieval_context(self, run: ResearchRun) -> list[dict[str, object]]:
        """Search prior chunk embeddings and append a retrieval event."""
        if self.retrieval_provider is None:
            return []
        if self.retrieval_limit <= 0:
            raise ValueError("Retrieval limit must be positive")

        repository = VectorRepository(self.store.session)
        results = repository.search_chunks(
            query_text=run.objective,
            provider=self.retrieval_provider,
            limit=self.retrieval_limit,
            project_id=run.project_id,
        )
        context = [result.as_context_item() for result in results]
        self.store.append_run_event(
            run,
            event_type="retrieval.context.attached",
            message=f"Retrieved {len(context)} chunk(s) for run context.",
            actor=self.actor,
            payload={
                "query": run.objective,
                "result_count": len(context),
                "chunk_ids": [item["chunk_id"] for item in context],
                "embedding_provider": self.retrieval_provider.name,
                "embedding_model": self.retrieval_provider.model,
            },
        )
        return context
