"""Review workflow service API for staged research outputs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import desc

from hal9000.db.models import ResearchOutput, ResearchProject, ResearchRun
from hal9000.db.store import ResearchStore, RunReviewResult
from hal9000.research.authz import ResearchAuthorizer
from hal9000.research.telemetry import RunTelemetrySummarizer


@dataclass(frozen=True)
class ReviewQueueItem:
    """A staged run awaiting reviewer action."""

    run_id: str
    project_slug: str | None
    program_name: str | None
    objective: str
    output_count: int
    created_at: str | None
    updated_at: str | None


@dataclass(frozen=True)
class ReviewOutputDetail:
    """One output in a review detail payload."""

    id: str
    output_type: str
    title: str
    status: str
    format: str
    content: str | None
    artifact_uri: str | None


@dataclass(frozen=True)
class ReviewRunDetail:
    """Review API payload for one staged run."""

    run_id: str
    status: str
    project_slug: str | None
    objective: str
    telemetry: dict[str, Any]
    outputs: list[ReviewOutputDetail]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


class ResearchReviewService:
    """Authorized service API for review queues, run detail, and decisions."""

    def __init__(
        self,
        store: ResearchStore,
        authorizer: ResearchAuthorizer | None = None,
    ):
        """Initialize with the shared research store."""
        self.store = store
        self.authorizer = authorizer or ResearchAuthorizer(store)
        self.session = store.session

    def list_review_queue(
        self,
        reviewer_email: str,
        project: ResearchProject | None = None,
        limit: int = 20,
    ) -> list[ReviewQueueItem]:
        """List staged runs the reviewer can review."""
        reviewer = self.authorizer.resolve_user(reviewer_email)
        query = (
            self.session.query(ResearchRun)
            .filter_by(status="staged")
            .order_by(desc(ResearchRun.updated_at), desc(ResearchRun.created_at))
        )
        if project is not None:
            self.authorizer.require_project_role(project, reviewer.email, "reviewer")
            query = query.filter_by(project_id=project.id)

        runs = query.limit(max(1, limit * 3)).all()
        visible_runs = [
            run
            for run in runs
            if run.project is not None
            and self.store.can_access_project(run.project, reviewer, "reviewer")
        ][: max(1, limit)]
        return [_queue_item(run) for run in visible_runs]

    def get_review_detail(
        self,
        run: ResearchRun,
        reviewer_email: str,
    ) -> ReviewRunDetail:
        """Return review detail for a staged run after permission checks."""
        self.authorizer.require_run_role(run, reviewer_email, "reviewer")
        summary = RunTelemetrySummarizer(self.store).summarize(run)
        return ReviewRunDetail(
            run_id=run.id,
            status=run.status,
            project_slug=run.project.slug if run.project else None,
            objective=run.objective,
            telemetry=summary.to_dict(),
            outputs=[_output_detail(output) for output in run.outputs],
        )

    def review_run(
        self,
        run: ResearchRun,
        decision: str,
        reviewer_email: str,
        rationale: str | None = None,
    ) -> RunReviewResult:
        """Record a run review decision after permission checks."""
        self.authorizer.require_run_role(run, reviewer_email, "reviewer")
        return self.store.review_run_outputs(
            run,
            decision=decision,
            reviewer=reviewer_email,
            rationale=rationale,
        )


def _queue_item(run: ResearchRun) -> ReviewQueueItem:
    return ReviewQueueItem(
        run_id=run.id,
        project_slug=run.project.slug if run.project else None,
        program_name=run.program.name if run.program else None,
        objective=run.objective,
        output_count=len(run.outputs),
        created_at=_iso(run.created_at),
        updated_at=_iso(run.updated_at),
    )


def _output_detail(output: ResearchOutput) -> ReviewOutputDetail:
    return ReviewOutputDetail(
        id=output.id,
        output_type=output.output_type,
        title=output.title,
        status=output.status,
        format=output.format,
        content=output.content,
        artifact_uri=output.artifact_uri,
    )


def _iso(value) -> str | None:
    return value.isoformat() if value else None
