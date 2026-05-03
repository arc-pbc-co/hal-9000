"""Reviewer-facing telemetry summaries for research runs."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from hal9000.db.models import ResearchRun
from hal9000.db.store import ResearchStore
from hal9000.research.budget import RunBudgetTracker, run_started_at


@dataclass(frozen=True)
class BudgetUsageSummary:
    """Observed run usage next to configured budget limits."""

    max_papers: int
    max_downloads: int
    max_llm_calls: int
    max_runtime_minutes: int
    papers_found: int
    papers_downloaded: int
    papers_processed: int
    llm_calls_used: int
    runtime_seconds: int
    runtime_exceeded: bool = False
    llm_calls_exceeded: bool = False


@dataclass(frozen=True)
class AcquisitionPaperSummary:
    """One paper-level acquisition event from a run."""

    status: str
    stage: str | None = None
    title: str | None = None
    identifier: str | None = None
    source: str | None = None
    reason: str | None = None
    document_id: str | None = None
    relevance_score: float | None = None


@dataclass(frozen=True)
class AcquisitionTelemetrySummary:
    """Aggregated paper acquisition telemetry."""

    papers_found: int = 0
    papers_downloaded: int = 0
    papers_processed: int = 0
    papers_skipped: int = 0
    papers_failed: int = 0
    duplicates_skipped: int = 0
    download_failures: int = 0
    processing_failures: int = 0
    paper_events: list[AcquisitionPaperSummary] = field(default_factory=list)


@dataclass(frozen=True)
class ToolCallSummary:
    """Compact tool-call accounting row."""

    sequence: int
    tool_name: str
    status: str
    actor: str | None = None
    error_message: str | None = None
    cost_usd: float | None = None
    started_at: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class OutputSummary:
    """Compact staged output row."""

    id: str
    output_type: str
    title: str
    status: str
    format: str
    artifact_uri: str | None = None
    created_by: str | None = None


@dataclass(frozen=True)
class RunTelemetrySummary:
    """Reviewer-facing summary of what happened during a run."""

    run_id: str
    status: str
    objective: str
    project_slug: str | None
    program_name: str | None
    initiated_by: str | None
    event_count: int
    tool_call_count: int
    claim_count: int
    chunk_count: int
    budget: BudgetUsageSummary
    acquisition: AcquisitionTelemetrySummary
    tool_calls: list[ToolCallSummary]
    outputs: list[OutputSummary]
    warnings: list[str]
    reviewer_notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


class RunTelemetrySummarizer:
    """Build reviewer-facing summaries from durable run records."""

    def __init__(self, store: ResearchStore):
        """Initialize with the shared research store."""
        self.store = store

    def summarize(self, run: ResearchRun) -> RunTelemetrySummary:
        """Summarize a run for review and handoff."""
        events = self.store.list_run_events(run)
        tool_calls = self.store.list_tool_calls(run)
        acquisition = self._summarize_acquisition(events, tool_calls)
        budget = self._summarize_budget(run, events, tool_calls, acquisition)
        warnings = self._build_warnings(run, events, tool_calls, acquisition, budget)
        outputs = [
            OutputSummary(
                id=output.id,
                output_type=output.output_type,
                title=output.title,
                status=output.status,
                format=output.format,
                artifact_uri=output.artifact_uri,
                created_by=output.created_by,
            )
            for output in run.outputs
        ]
        reviewer_notes = self._build_reviewer_notes(run, outputs, warnings, acquisition, budget)

        return RunTelemetrySummary(
            run_id=run.id,
            status=run.status,
            objective=run.objective,
            project_slug=run.project.slug if run.project else None,
            program_name=run.program.name if run.program else None,
            initiated_by=run.initiated_by,
            event_count=len(events),
            tool_call_count=len(tool_calls),
            claim_count=len(run.claims),
            chunk_count=len(run.chunks),
            budget=budget,
            acquisition=acquisition,
            tool_calls=[
                ToolCallSummary(
                    sequence=call.sequence,
                    tool_name=call.tool_name,
                    status=call.status,
                    actor=call.actor,
                    error_message=call.error_message,
                    cost_usd=call.cost_usd,
                    started_at=_format_datetime(call.started_at),
                    completed_at=_format_datetime(call.completed_at),
                )
                for call in tool_calls
            ],
            outputs=outputs,
            warnings=warnings,
            reviewer_notes=reviewer_notes,
        )

    def _summarize_acquisition(self, events, tool_calls) -> AcquisitionTelemetrySummary:
        paper_payloads = [
            _safe_json_loads(event.payload_json)
            for event in events
            if event.event_type.startswith("acquisition.paper.")
        ]
        paper_payloads = [payload for payload in paper_payloads if isinstance(payload, dict)]

        if not paper_payloads:
            paper_payloads = self._paper_events_from_tool_calls(tool_calls)

        paper_events = [
            AcquisitionPaperSummary(
                status=str(payload.get("status") or "unknown"),
                stage=_optional_str(payload.get("stage")),
                title=_optional_str(payload.get("title")),
                identifier=_paper_identifier(payload),
                source=_optional_str(payload.get("source")),
                reason=_optional_str(payload.get("reason")),
                document_id=_optional_str(payload.get("document_id")),
                relevance_score=_optional_float(payload.get("relevance_score")),
            )
            for payload in paper_payloads
        ]
        event_counts = _count_paper_statuses(paper_events)
        tool_totals = self._acquisition_totals_from_tool_calls(tool_calls)

        return AcquisitionTelemetrySummary(
            papers_found=max(event_counts["found"], tool_totals.get("papers_found", 0)),
            papers_downloaded=max(
                event_counts["downloaded"], tool_totals.get("papers_downloaded", 0)
            ),
            papers_processed=max(
                event_counts["processed"], tool_totals.get("papers_processed", 0)
            ),
            papers_skipped=max(event_counts["skipped"], tool_totals.get("duplicates_skipped", 0)),
            papers_failed=max(
                event_counts["failed"],
                tool_totals.get("download_failures", 0)
                + tool_totals.get("processing_failures", 0),
            ),
            duplicates_skipped=tool_totals.get("duplicates_skipped", 0),
            download_failures=tool_totals.get("download_failures", 0),
            processing_failures=tool_totals.get("processing_failures", 0),
            paper_events=paper_events,
        )

    def _summarize_budget(
        self,
        run: ResearchRun,
        events,
        tool_calls,
        acquisition: AcquisitionTelemetrySummary,
    ) -> BudgetUsageSummary:
        budget = RunBudgetTracker(run).budget
        event_types = {event.event_type for event in events}
        llm_calls_used = sum(1 for call in tool_calls if call.tool_name == "llm.call")

        return BudgetUsageSummary(
            max_papers=budget.max_papers,
            max_downloads=budget.max_downloads,
            max_llm_calls=budget.max_llm_calls,
            max_runtime_minutes=budget.max_runtime_minutes,
            papers_found=acquisition.papers_found,
            papers_downloaded=acquisition.papers_downloaded,
            papers_processed=acquisition.papers_processed,
            llm_calls_used=llm_calls_used,
            runtime_seconds=_runtime_seconds(run),
            runtime_exceeded="budget.runtime.exceeded" in event_types,
            llm_calls_exceeded="budget.llm_calls.exceeded" in event_types,
        )

    def _build_warnings(
        self,
        run: ResearchRun,
        events,
        tool_calls,
        acquisition: AcquisitionTelemetrySummary,
        budget: BudgetUsageSummary,
    ) -> list[str]:
        warnings: list[str] = []
        if run.status == "failed":
            warnings.append(run.error_message or "Run ended with failed status.")
        if budget.runtime_exceeded:
            warnings.append("Runtime budget was exceeded.")
        if budget.llm_calls_exceeded:
            warnings.append("LLM-call budget was exceeded.")
        if acquisition.papers_failed:
            warnings.append(f"{acquisition.papers_failed} acquisition paper event(s) failed.")
        if acquisition.papers_skipped:
            warnings.append(f"{acquisition.papers_skipped} acquisition paper event(s) skipped.")

        for call in tool_calls:
            if call.status == "failed":
                warnings.append(
                    f"Tool call {call.sequence} ({call.tool_name}) failed: "
                    f"{call.error_message or 'no error message recorded'}"
                )

        for event in events:
            event_text = f"{event.event_type} {event.message or ''}".lower()
            if "error" in event_text or "failed" in event_text or "exceeded" in event_text:
                message = event.message or event.event_type
                if message not in warnings:
                    warnings.append(message)

        return _dedupe_preserving_order(warnings)

    def _build_reviewer_notes(
        self,
        run: ResearchRun,
        outputs: list[OutputSummary],
        warnings: list[str],
        acquisition: AcquisitionTelemetrySummary,
        budget: BudgetUsageSummary,
    ) -> list[str]:
        notes: list[str] = []
        if warnings:
            notes.append("Review warnings before promoting any staged outputs.")
        if outputs:
            notes.append("Inspect staged outputs for source coverage and citation quality.")
        else:
            notes.append("No staged outputs are available for review yet.")
        if run.status == "staged":
            notes.append("Run is staged and ready for human review.")
        if run.status == "promoted":
            notes.append("Run outputs have been promoted.")
        if run.status == "rejected":
            notes.append("Run outputs have been rejected.")
        if run.status == "changes_requested":
            notes.append("A reviewer requested changes before promotion.")
        if run.status == "cancel_requested":
            notes.append("Run cancellation has been requested and is awaiting worker acknowledgement.")
        if run.status == "cancelled":
            notes.append("Run was cancelled before completion.")
        if acquisition.papers_downloaded >= budget.max_downloads and budget.max_downloads > 0:
            notes.append("Download budget was fully used; consider a larger budget for broader coverage.")
        if run.claims:
            notes.append(f"{len(run.claims)} source-backed claim(s) are attached to this run.")
        else:
            notes.append("No source-backed claims are attached to this run.")
        return notes

    def _paper_events_from_tool_calls(self, tool_calls) -> list[dict[str, Any]]:
        paper_events: list[dict[str, Any]] = []
        for call in tool_calls:
            output = _safe_json_loads(call.output_json)
            if isinstance(output, dict):
                raw_events = output.get("paper_events") or []
                paper_events.extend(event for event in raw_events if isinstance(event, dict))
        return paper_events

    def _acquisition_totals_from_tool_calls(self, tool_calls) -> dict[str, int]:
        totals = {
            "papers_found": 0,
            "papers_downloaded": 0,
            "papers_processed": 0,
            "duplicates_skipped": 0,
            "download_failures": 0,
            "processing_failures": 0,
        }
        for call in tool_calls:
            output = _safe_json_loads(call.output_json)
            if not isinstance(output, dict):
                continue
            for key in totals:
                totals[key] += _optional_int(output.get(key))
        return totals


def _safe_json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _count_paper_statuses(paper_events: list[AcquisitionPaperSummary]) -> dict[str, int]:
    counts = {"found": 0, "downloaded": 0, "processed": 0, "skipped": 0, "failed": 0}
    for event in paper_events:
        if event.status in counts:
            counts[event.status] += 1
    return counts


def _runtime_seconds(run: ResearchRun) -> int:
    ended_at = run.completed_at or datetime.now(timezone.utc)
    if ended_at.tzinfo is None:
        ended_at = ended_at.replace(tzinfo=timezone.utc)
    started_at = run_started_at(run)
    return max(0, int((ended_at - started_at).total_seconds()))


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _paper_identifier(payload: dict[str, Any]) -> str | None:
    return _optional_str(
        payload.get("identifier")
        or payload.get("doi")
        or payload.get("arxiv_id")
        or payload.get("pdf_url")
    )


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
