"""Bounded research run execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hal9000.db.models import ResearchRun
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


class BoundedResearchWorker:
    """Minimal worker that executes queued runs through staged outputs."""

    def __init__(
        self,
        store: ResearchStore,
        actor: str = "hal-worker",
        retrieval_provider: EmbeddingProvider | None = None,
        retrieval_limit: int = 5,
        corpus_pipeline: ResearchCorpusPipeline | None = None,
    ):
        """Initialize the worker with a shared store."""
        self.store = store
        self.actor = actor
        self.output_generator = ResearchOutputGenerator(store)
        self.retrieval_provider = retrieval_provider
        self.retrieval_limit = retrieval_limit
        self.corpus_pipeline = corpus_pipeline

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

            corpus_result = self._prepare_corpus(run)
            retrieval_context = self._build_retrieval_context(run)
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
