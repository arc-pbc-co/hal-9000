"""Operational observability summaries for research runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func

from hal9000.db.models import ResearchRun, ResearchRunEvent, ResearchToolCall, utc_now
from hal9000.db.store import ResearchStore

WORKER_OUTCOME_EVENTS = {
    "worker.completed",
    "worker.phase.retrying",
    "worker.phase.timeout",
    "worker.cancelled",
    "tool.acquisition.failed",
    "budget.runtime.exceeded",
    "budget.llm_calls.exceeded",
    "run.failed",
    "run.cancelled",
}


@dataclass(frozen=True)
class RunBrief:
    """Compact run row for dashboards and API responses."""

    id: str
    status: str
    objective: str
    project_slug: str | None = None
    program_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class QueueHealthSummary:
    """Queue-oriented operational health."""

    queued: int
    running: int
    cancel_requested: int
    oldest_queued_at: str | None
    next_queued_runs: list[RunBrief] = field(default_factory=list)
    running_runs: list[RunBrief] = field(default_factory=list)


@dataclass(frozen=True)
class ToolCallFailureSummary:
    """Recent failed tool-call row."""

    id: str
    run_id: str
    sequence: int
    tool_name: str
    actor: str | None
    error_message: str | None
    created_at: str | None


@dataclass(frozen=True)
class ToolCallObservabilitySummary:
    """Tool-call counts, cost, and recent failures."""

    total: int
    by_status: dict[str, int]
    by_tool: dict[str, int]
    total_cost_usd: float
    recent_failures: list[ToolCallFailureSummary] = field(default_factory=list)


@dataclass(frozen=True)
class EventSummary:
    """Recent operational event row."""

    id: str
    run_id: str
    sequence: int
    event_type: str
    message: str | None
    actor: str | None
    created_at: str | None


@dataclass(frozen=True)
class FailureSummary:
    """Recent failed run row."""

    run: RunBrief
    error_message: str | None = None


@dataclass(frozen=True)
class ResearchObservabilitySummary:
    """Compact operational summary for HAL research runs."""

    generated_at: str
    run_status_counts: dict[str, int]
    queue: QueueHealthSummary
    tool_calls: ToolCallObservabilitySummary
    recent_worker_outcomes: list[EventSummary]
    recent_failures: list[FailureSummary]
    recent_runs: list[RunBrief]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


class ResearchObservabilityService:
    """Build operational summaries from the shared research store."""

    def __init__(self, store: ResearchStore):
        """Initialize with the shared research store."""
        self.store = store
        self.session = store.session

    def summarize(self, limit: int = 10) -> ResearchObservabilitySummary:
        """Return a compact operations summary for runs, queue, tools, and failures."""
        bounded_limit = max(1, limit)
        run_status_counts = self._run_status_counts()
        return ResearchObservabilitySummary(
            generated_at=_format_datetime(utc_now()) or "",
            run_status_counts=run_status_counts,
            queue=self._queue_health(run_status_counts, bounded_limit),
            tool_calls=self._tool_call_summary(bounded_limit),
            recent_worker_outcomes=self._recent_worker_outcomes(bounded_limit),
            recent_failures=self._recent_failures(bounded_limit),
            recent_runs=[
                _run_brief(run)
                for run in (
                    self.session.query(ResearchRun)
                    .order_by(desc(ResearchRun.updated_at), desc(ResearchRun.created_at))
                    .limit(bounded_limit)
                    .all()
                )
            ],
        )

    def _run_status_counts(self) -> dict[str, int]:
        rows = (
            self.session.query(ResearchRun.status, func.count(ResearchRun.id))
            .group_by(ResearchRun.status)
            .all()
        )
        return {status: int(count) for status, count in rows}

    def _queue_health(
        self,
        run_status_counts: dict[str, int],
        limit: int,
    ) -> QueueHealthSummary:
        next_queued_runs = (
            self.session.query(ResearchRun)
            .filter_by(status="queued")
            .order_by(ResearchRun.created_at)
            .limit(limit)
            .all()
        )
        running_runs = (
            self.session.query(ResearchRun)
            .filter(ResearchRun.status.in_(["running", "cancel_requested"]))
            .order_by(ResearchRun.updated_at)
            .limit(limit)
            .all()
        )
        return QueueHealthSummary(
            queued=run_status_counts.get("queued", 0),
            running=run_status_counts.get("running", 0),
            cancel_requested=run_status_counts.get("cancel_requested", 0),
            oldest_queued_at=_format_datetime(next_queued_runs[0].created_at)
            if next_queued_runs
            else None,
            next_queued_runs=[_run_brief(run) for run in next_queued_runs],
            running_runs=[_run_brief(run) for run in running_runs],
        )

    def _tool_call_summary(self, limit: int) -> ToolCallObservabilitySummary:
        by_status = {
            status: int(count)
            for status, count in (
                self.session.query(ResearchToolCall.status, func.count(ResearchToolCall.id))
                .group_by(ResearchToolCall.status)
                .all()
            )
        }
        by_tool = {
            tool_name: int(count)
            for tool_name, count in (
                self.session.query(ResearchToolCall.tool_name, func.count(ResearchToolCall.id))
                .group_by(ResearchToolCall.tool_name)
                .all()
            )
        }
        total_cost = (
            self.session.query(func.coalesce(func.sum(ResearchToolCall.cost_usd), 0.0)).scalar()
            or 0.0
        )
        failures = (
            self.session.query(ResearchToolCall)
            .filter_by(status="failed")
            .order_by(desc(ResearchToolCall.created_at), desc(ResearchToolCall.sequence))
            .limit(limit)
            .all()
        )
        return ToolCallObservabilitySummary(
            total=sum(by_status.values()),
            by_status=by_status,
            by_tool=by_tool,
            total_cost_usd=float(total_cost),
            recent_failures=[
                ToolCallFailureSummary(
                    id=call.id,
                    run_id=call.run_id,
                    sequence=call.sequence,
                    tool_name=call.tool_name,
                    actor=call.actor,
                    error_message=call.error_message,
                    created_at=_format_datetime(call.created_at),
                )
                for call in failures
            ],
        )

    def _recent_worker_outcomes(self, limit: int) -> list[EventSummary]:
        events = (
            self.session.query(ResearchRunEvent)
            .filter(ResearchRunEvent.event_type.in_(WORKER_OUTCOME_EVENTS))
            .order_by(desc(ResearchRunEvent.created_at), desc(ResearchRunEvent.sequence))
            .limit(limit)
            .all()
        )
        return [_event_summary(event) for event in events]

    def _recent_failures(self, limit: int) -> list[FailureSummary]:
        failed_runs = (
            self.session.query(ResearchRun)
            .filter_by(status="failed")
            .order_by(desc(ResearchRun.updated_at), desc(ResearchRun.created_at))
            .limit(limit)
            .all()
        )
        return [
            FailureSummary(run=_run_brief(run), error_message=run.error_message)
            for run in failed_runs
        ]


def _run_brief(run: ResearchRun) -> RunBrief:
    return RunBrief(
        id=run.id,
        status=run.status,
        objective=run.objective,
        project_slug=run.project.slug if run.project else None,
        program_name=run.program.name if run.program else None,
        created_at=_format_datetime(run.created_at),
        updated_at=_format_datetime(run.updated_at),
    )


def _event_summary(event: ResearchRunEvent) -> EventSummary:
    return EventSummary(
        id=event.id,
        run_id=event.run_id,
        sequence=event.sequence,
        event_type=event.event_type,
        message=event.message,
        actor=event.actor,
        created_at=_format_datetime(event.created_at),
    )


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
