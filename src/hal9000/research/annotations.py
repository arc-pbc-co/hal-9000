"""Reviewer comments and annotations for outputs and claims."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from hal9000.db.models import ExtractedClaim, ResearchOutput, ReviewAnnotation, utc_now
from hal9000.db.store import ResearchStore
from hal9000.research.authz import ResearchAuthorizer

AnnotationTarget = Literal["output", "claim"]


@dataclass(frozen=True)
class AnnotationPayload:
    """JSON-friendly review annotation payload."""

    id: str
    target_type: str
    target_id: str
    annotation_type: str
    body: str
    status: str
    author_email: str | None
    project_id: str | None
    run_id: str | None
    created_at: str | None
    resolved_by: str | None
    resolved_at: str | None

    def to_dict(self) -> dict:
        """Return a JSON-serializable representation."""
        return asdict(self)


class ReviewAnnotationService:
    """Authorized comments and annotations for review UI workflows."""

    def __init__(
        self,
        store: ResearchStore,
        authorizer: ResearchAuthorizer | None = None,
    ):
        """Initialize with the shared research store."""
        self.store = store
        self.session = store.session
        self.authorizer = authorizer or ResearchAuthorizer(store)

    def add_annotation(
        self,
        target_type: AnnotationTarget,
        target_id: str,
        body: str,
        author_email: str,
        annotation_type: str = "comment",
    ) -> ReviewAnnotation:
        """Add an annotation to an output or claim after contributor access checks."""
        target = self._resolve_target(target_type, target_id)
        run = getattr(target, "run", None)
        project = _target_project(target)
        actor = self.authorizer.require_project_role(project, author_email, "contributor")
        annotation = ReviewAnnotation(
            project=project,
            run=run,
            target_type=target_type,
            target_id=target_id,
            author=actor.user,
            author_email=actor.user.email,
            annotation_type=annotation_type,
            body=body,
            status="open",
        )
        self.session.add(annotation)
        self.session.flush()
        return annotation

    def list_annotations(
        self,
        target_type: AnnotationTarget,
        target_id: str,
        viewer_email: str,
        include_resolved: bool = False,
    ) -> list[ReviewAnnotation]:
        """List annotations for a target after viewer access checks."""
        target = self._resolve_target(target_type, target_id)
        project = _target_project(target)
        self.authorizer.require_project_role(project, viewer_email, "viewer")
        query = (
            self.session.query(ReviewAnnotation)
            .filter_by(target_type=target_type, target_id=target_id)
            .order_by(ReviewAnnotation.created_at, ReviewAnnotation.id)
        )
        if not include_resolved:
            query = query.filter_by(status="open")
        return query.all()

    def resolve_annotation(
        self,
        annotation_id: str,
        resolver_email: str,
    ) -> ReviewAnnotation:
        """Resolve an annotation after reviewer access checks."""
        annotation = self.session.get(ReviewAnnotation, annotation_id)
        if annotation is None:
            raise ValueError(f"Review annotation not found: {annotation_id}")
        self.authorizer.require_project_role(annotation.project, resolver_email, "reviewer")
        annotation.status = "resolved"
        annotation.resolved_by = resolver_email
        annotation.resolved_at = utc_now()
        self.session.flush()
        return annotation

    def _resolve_target(self, target_type: AnnotationTarget, target_id: str):
        if target_type == "output":
            target = self.session.get(ResearchOutput, target_id)
        elif target_type == "claim":
            target = self.session.get(ExtractedClaim, target_id)
        else:
            raise ValueError("Annotation target_type must be output or claim")
        if target is None:
            raise ValueError(f"Annotation target not found: {target_type}:{target_id}")
        return target


def annotation_payload(annotation: ReviewAnnotation) -> AnnotationPayload:
    """Return a JSON-friendly annotation payload."""
    return AnnotationPayload(
        id=annotation.id,
        target_type=annotation.target_type,
        target_id=annotation.target_id,
        annotation_type=annotation.annotation_type,
        body=annotation.body,
        status=annotation.status,
        author_email=annotation.author_email,
        project_id=annotation.project_id,
        run_id=annotation.run_id,
        created_at=_iso(annotation.created_at),
        resolved_by=annotation.resolved_by,
        resolved_at=_iso(annotation.resolved_at),
    )


def _target_project(target):
    project = getattr(target, "project", None)
    if project is not None:
        return project
    run = getattr(target, "run", None)
    return run.project if run is not None else None


def _iso(value) -> str | None:
    return value.isoformat() if value else None
