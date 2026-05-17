"""Queued research worker execution helpers."""

from __future__ import annotations

from dataclasses import dataclass
from time import sleep
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


@dataclass(frozen=True)
class QueueWorkerServiceConfig:
    """Runtime configuration for a packaged queue-worker service."""

    limit: int = 1
    poll_seconds: float = 30.0
    max_iterations: int | None = None


@dataclass(frozen=True)
class QueueWorkerServiceTick:
    """Summary of one queue-worker service iteration."""

    iteration: int
    results: list[QueuedRunResult]

    @property
    def processed(self) -> int:
        """Return the number of queued runs processed in this tick."""
        return len(self.results)

    @property
    def succeeded(self) -> int:
        """Return the number of successful runs."""
        return sum(1 for result in self.results if result.succeeded)

    @property
    def failed(self) -> int:
        """Return the number of failed runs."""
        return sum(1 for result in self.results if not result.succeeded)

    def to_dict(self) -> dict[str, object]:
        """Serialize the tick for CLI/API output."""
        return {
            "iteration": self.iteration,
            "processed": self.processed,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "results": [
                {
                    "run_id": result.run_id,
                    "status": result.status,
                    "succeeded": result.succeeded,
                    "error": result.error,
                }
                for result in self.results
            ],
        }


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


class QueueWorkerService:
    """Packaged queue-worker loop for scheduler/process-manager deployments."""

    def __init__(
        self,
        store: ResearchStore,
        worker_factory: Callable[[ResearchStore], BoundedResearchWorker],
        config: QueueWorkerServiceConfig | None = None,
        sleep_func: Callable[[float], None] = sleep,
    ):
        """Initialize the service with store, worker factory, and runtime config."""
        self.store = store
        self.worker_factory = worker_factory
        self.config = config or QueueWorkerServiceConfig()
        self.sleep_func = sleep_func

    def run_once(self, iteration: int = 1) -> QueueWorkerServiceTick:
        """Run one queue polling iteration."""
        results = ResearchQueueRunner(self.store, self.worker_factory).run_once(
            limit=self.config.limit
        )
        return QueueWorkerServiceTick(iteration=iteration, results=results)

    def run(self) -> list[QueueWorkerServiceTick]:
        """Run until max_iterations is reached, or forever when unset."""
        ticks: list[QueueWorkerServiceTick] = []
        iteration = 1
        while self.config.max_iterations is None or iteration <= self.config.max_iterations:
            tick = self.run_once(iteration=iteration)
            ticks.append(tick)
            if self.config.max_iterations is not None and iteration >= self.config.max_iterations:
                break
            self.sleep_func(max(0.0, self.config.poll_seconds))
            iteration += 1
        return ticks
