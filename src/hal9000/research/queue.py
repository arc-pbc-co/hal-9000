"""Queued research worker execution helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from hal9000.db.models import ResearchRun
from hal9000.db.store import ResearchStore
from hal9000.research.orchestrator import BoundedResearchWorker


@dataclass(frozen=True)
class QueuedRunResult:
    """Outcome for one queued worker execution."""

    run_id: str
    status: str
    succeeded: bool
    error: str | None = None


class ResearchQueueRunner:
    """Execute queued research runs through a worker factory."""

    def __init__(
        self,
        store: ResearchStore,
        worker_factory: Callable[[ResearchStore], BoundedResearchWorker],
    ):
        """Initialize with a store and worker factory."""
        self.store = store
        self.worker_factory = worker_factory

    def run_once(self, limit: int = 1) -> list[QueuedRunResult]:
        """Execute up to `limit` queued runs once."""
        runs = self.store.list_runs(status="queued", limit=max(0, limit))
        results: list[QueuedRunResult] = []
        for run in runs:
            results.append(self._execute_one(run))
        return results

    def _execute_one(self, run: ResearchRun) -> QueuedRunResult:
        worker = self.worker_factory(self.store)
        try:
            worker.execute_run(run.id)
        except Exception as exc:
            return QueuedRunResult(
                run_id=run.id,
                status=run.status,
                succeeded=False,
                error=str(exc),
            )
        return QueuedRunResult(run_id=run.id, status=run.status, succeeded=True)
