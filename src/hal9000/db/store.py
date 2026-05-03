"""Repository helpers for HAL's shared research store."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from hal9000.db.models import (
    Document,
    DocumentChunk,
    EvidenceLink,
    ExtractedClaim,
    ProjectPermission,
    ResearchOutput,
    ResearchProgramRecord,
    ResearchProject,
    ResearchRun,
    ResearchRunEvent,
    ResearchToolCall,
    ReviewDecision,
    Team,
    TeamMembership,
    UserAccount,
    utc_now,
)
from hal9000.research.program import ResearchProgram


def _json_dumps(value: Any) -> str:
    """Serialize JSON payloads consistently for text columns."""
    return json.dumps(value, sort_keys=True)


@dataclass
class ClaimEvidence:
    """Input payload for a source-backed claim and its evidence."""

    claim_text: str
    evidence_text: Optional[str] = None
    quote: Optional[str] = None
    locator: Optional[str] = None
    source_url: Optional[str] = None
    claim_type: str = "finding"
    confidence: float = 0.5
    evidence_type: str = "source_excerpt"
    provenance: Optional[dict[str, Any]] = None


@dataclass
class RunReviewResult:
    """Review decisions and lifecycle event recorded for a run review."""

    run: ResearchRun
    decisions: list[ReviewDecision]
    event: ResearchRunEvent


PROJECT_ROLE_ORDER = {
    "viewer": 1,
    "contributor": 2,
    "reviewer": 3,
    "admin": 4,
}


class ResearchStore:
    """Small repository API over the shared research store models."""

    def __init__(self, session: Session):
        """Initialize the store with a SQLAlchemy session."""
        self.session = session

    def create_project(
        self,
        name: str,
        slug: str,
        owner: Optional[str] = None,
        description: Optional[str] = None,
        visibility: str = "firm",
    ) -> ResearchProject:
        """Create and persist a research project."""
        project = ResearchProject(
            name=name,
            slug=slug,
            owner=owner,
            description=description,
            visibility=visibility,
        )
        self.session.add(project)
        self.session.flush()
        return project

    def create_user(
        self,
        email: str,
        display_name: Optional[str] = None,
        external_subject: Optional[str] = None,
        global_role: str = "member",
        status: str = "active",
    ) -> UserAccount:
        """Create and persist a firm user account."""
        normalized_email = _normalize_email(email)
        user = UserAccount(
            email=normalized_email,
            display_name=display_name,
            external_subject=external_subject,
            global_role=global_role,
            status=status,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def get_user_by_email(self, email: str) -> Optional[UserAccount]:
        """Fetch a user account by normalized email."""
        return self.session.query(UserAccount).filter_by(email=_normalize_email(email)).one_or_none()

    def create_team(
        self,
        slug: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: str = "active",
    ) -> Team:
        """Create and persist a firm team."""
        normalized_slug = _normalize_slug(slug)
        team = Team(
            slug=normalized_slug,
            name=name or normalized_slug.replace("-", " ").title(),
            description=description,
            status=status,
        )
        self.session.add(team)
        self.session.flush()
        return team

    def get_team_by_slug(self, slug: str) -> Optional[Team]:
        """Fetch a team by normalized slug."""
        return self.session.query(Team).filter_by(slug=_normalize_slug(slug)).one_or_none()

    def add_team_member(
        self,
        team: Team,
        user: UserAccount,
        role: str = "member",
        status: str = "active",
    ) -> TeamMembership:
        """Add or update a user's team membership."""
        membership = (
            self.session.query(TeamMembership)
            .filter_by(team_id=team.id, user_id=user.id)
            .one_or_none()
        )
        if membership is None:
            membership = TeamMembership(team=team, user=user)
            self.session.add(membership)
        membership.role = role
        membership.status = status
        self.session.flush()
        return membership

    def grant_project_access(
        self,
        project: ResearchProject,
        principal_type: str,
        principal_id: str,
        role: str,
        granted_by: Optional[str] = None,
    ) -> ProjectPermission:
        """Grant or update a project permission for a user or team principal."""
        normalized_principal_type = _normalize_principal_type(principal_type)
        normalized_role = _normalize_project_role(role)
        permission = (
            self.session.query(ProjectPermission)
            .filter_by(
                project_id=project.id,
                principal_type=normalized_principal_type,
                principal_id=principal_id,
            )
            .one_or_none()
        )
        if permission is None:
            permission = ProjectPermission(
                project=project,
                principal_type=normalized_principal_type,
                principal_id=principal_id,
            )
            self.session.add(permission)
        permission.role = normalized_role
        permission.granted_by = granted_by
        self.session.flush()
        return permission

    def list_project_permissions(self, project: ResearchProject) -> list[ProjectPermission]:
        """Return permission grants for a project."""
        return (
            self.session.query(ProjectPermission)
            .filter_by(project_id=project.id)
            .order_by(ProjectPermission.principal_type, ProjectPermission.principal_id)
            .all()
        )

    def project_roles_for_user(
        self,
        project: ResearchProject,
        user: UserAccount,
    ) -> list[str]:
        """Return direct and team-derived project roles for a user."""
        roles = [
            permission.role
            for permission in self.session.query(ProjectPermission)
            .filter_by(project_id=project.id, principal_type="user", principal_id=user.id)
            .all()
        ]
        team_ids = [
            membership.team_id
            for membership in user.team_memberships
            if membership.status == "active" and membership.team.status == "active"
        ]
        if team_ids:
            roles.extend(
                permission.role
                for permission in self.session.query(ProjectPermission)
                .filter(
                    ProjectPermission.project_id == project.id,
                    ProjectPermission.principal_type == "team",
                    ProjectPermission.principal_id.in_(team_ids),
                )
                .all()
            )
        return roles

    def can_access_project(
        self,
        project: ResearchProject,
        user: UserAccount,
        required_role: str = "viewer",
    ) -> bool:
        """Return whether a user has the requested project role or stronger."""
        if user.status != "active":
            return False
        if user.global_role == "admin":
            return True
        required_rank = PROJECT_ROLE_ORDER[_normalize_project_role(required_role)]
        return any(
            PROJECT_ROLE_ORDER.get(role, 0) >= required_rank
            for role in self.project_roles_for_user(project, user)
        )

    def get_project_by_slug(self, slug: str) -> Optional[ResearchProject]:
        """Fetch a project by slug."""
        return self.session.query(ResearchProject).filter_by(slug=slug).one_or_none()

    def save_program(
        self,
        program: ResearchProgram,
        project: Optional[ResearchProject] = None,
        status: str = "active",
    ) -> ResearchProgramRecord:
        """Persist a validated research program."""
        spec = program.spec
        record = ResearchProgramRecord(
            project=project,
            name=spec.name,
            version=spec.version,
            objective=spec.objective,
            owner=spec.owner,
            domain=spec.domain,
            tags=_json_dumps(spec.tags),
            spec_json=spec.model_dump_json(),
            instructions=program.instructions,
            source_path=str(program.source_path) if program.source_path else None,
            status=status,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def create_run(
        self,
        objective: str,
        project: Optional[ResearchProject] = None,
        program: Optional[ResearchProgramRecord] = None,
        initiated_by: Optional[str] = None,
        budget: Optional[dict[str, Any]] = None,
        tool_policy: Optional[dict[str, Any]] = None,
    ) -> ResearchRun:
        """Create a queued research run."""
        run = ResearchRun(
            project=project,
            program=program,
            objective=objective,
            initiated_by=initiated_by,
            budget_json=_json_dumps(budget) if budget is not None else None,
            tool_policy_json=_json_dumps(tool_policy) if tool_policy is not None else None,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def get_run(self, run_id: str) -> Optional[ResearchRun]:
        """Fetch a research run by id."""
        return self.session.get(ResearchRun, run_id)

    def list_runs(
        self,
        status: Optional[str] = None,
        project: Optional[ResearchProject] = None,
        limit: int = 20,
    ) -> list[ResearchRun]:
        """List recent research runs."""
        query = self.session.query(ResearchRun).order_by(ResearchRun.created_at.desc())
        if status:
            query = query.filter_by(status=status)
        if project:
            query = query.filter_by(project_id=project.id)
        return query.limit(limit).all()

    def update_run_status(
        self,
        run: ResearchRun,
        status: str,
        message: Optional[str] = None,
        actor: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> ResearchRunEvent:
        """Update a run status and append a lifecycle event."""
        now = utc_now()
        run.status = status
        run.updated_at = now
        if status == "running" and run.started_at is None:
            run.started_at = now
        if status in {
            "staged",
            "completed",
            "failed",
            "promoted",
            "rejected",
            "changes_requested",
            "cancelled",
        }:
            run.completed_at = now

        return self.append_run_event(
            run,
            event_type=f"run.{status}",
            message=message,
            actor=actor,
            payload=payload,
        )

    def append_run_event(
        self,
        run: ResearchRun,
        event_type: str,
        message: Optional[str] = None,
        actor: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> ResearchRunEvent:
        """Append an ordered event to a research run log."""
        last_event = (
            self.session.query(ResearchRunEvent)
            .filter_by(run_id=run.id)
            .order_by(ResearchRunEvent.sequence.desc())
            .first()
        )
        next_sequence = 1 if last_event is None else last_event.sequence + 1
        event = ResearchRunEvent(
            run=run,
            sequence=next_sequence,
            event_type=event_type,
            message=message,
            actor=actor,
            payload_json=_json_dumps(payload) if payload is not None else None,
        )
        self.session.add(event)
        self.session.flush()
        return event

    def list_run_events(self, run: ResearchRun) -> list[ResearchRunEvent]:
        """Return run events in append order."""
        return (
            self.session.query(ResearchRunEvent)
            .filter_by(run_id=run.id)
            .order_by(ResearchRunEvent.sequence)
            .all()
        )

    def start_tool_call(
        self,
        run: ResearchRun,
        tool_name: str,
        actor: Optional[str] = None,
        input: Optional[dict[str, Any]] = None,
    ) -> ResearchToolCall:
        """Record the start of a worker tool call."""
        last_call = (
            self.session.query(ResearchToolCall)
            .filter_by(run_id=run.id)
            .order_by(ResearchToolCall.sequence.desc())
            .first()
        )
        next_sequence = 1 if last_call is None else last_call.sequence + 1
        call = ResearchToolCall(
            run=run,
            sequence=next_sequence,
            tool_name=tool_name,
            status="started",
            actor=actor,
            input_json=_json_dumps(input) if input is not None else None,
        )
        self.session.add(call)
        self.session.flush()
        return call

    def finish_tool_call(
        self,
        tool_call: ResearchToolCall,
        status: str = "completed",
        output: Optional[dict[str, Any]] = None,
        error_message: Optional[str] = None,
        cost_usd: Optional[float] = None,
    ) -> ResearchToolCall:
        """Record the outcome of a worker tool call."""
        tool_call.status = status
        tool_call.output_json = _json_dumps(output) if output is not None else None
        tool_call.error_message = error_message
        tool_call.cost_usd = cost_usd
        tool_call.completed_at = utc_now()
        self.session.flush()
        return tool_call

    def list_tool_calls(self, run: ResearchRun) -> list[ResearchToolCall]:
        """Return tool calls in execution order."""
        return (
            self.session.query(ResearchToolCall)
            .filter_by(run_id=run.id)
            .order_by(ResearchToolCall.sequence)
            .all()
        )

    def add_document_chunk(
        self,
        document: Document,
        content: str,
        chunk_index: int,
        run: Optional[ResearchRun] = None,
        char_start: Optional[int] = None,
        char_end: Optional[int] = None,
        token_count: Optional[int] = None,
        extraction_metadata: Optional[dict[str, Any]] = None,
    ) -> DocumentChunk:
        """Persist a canonical document chunk."""
        text_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk = DocumentChunk(
            document=document,
            run=run,
            chunk_index=chunk_index,
            text_hash=text_hash,
            char_start=char_start,
            char_end=char_end,
            token_count=token_count,
            content=content,
            extraction_metadata=(
                _json_dumps(extraction_metadata) if extraction_metadata is not None else None
            ),
        )
        self.session.add(chunk)
        self.session.flush()
        return chunk

    def add_claim_with_evidence(
        self,
        document: Document,
        claim_evidence: ClaimEvidence,
        chunk: Optional[DocumentChunk] = None,
        run: Optional[ResearchRun] = None,
    ) -> ExtractedClaim:
        """Persist a staged claim and its first evidence link."""
        claim = ExtractedClaim(
            document=document,
            chunk=chunk,
            run=run,
            claim_text=claim_evidence.claim_text,
            claim_type=claim_evidence.claim_type,
            confidence=claim_evidence.confidence,
            evidence_text=claim_evidence.evidence_text,
            provenance_json=(
                _json_dumps(claim_evidence.provenance)
                if claim_evidence.provenance is not None
                else None
            ),
        )
        self.session.add(claim)
        self.session.flush()

        evidence = EvidenceLink(
            claim=claim,
            document=document,
            chunk=chunk,
            source_url=claim_evidence.source_url,
            quote=claim_evidence.quote,
            locator=claim_evidence.locator,
            evidence_type=claim_evidence.evidence_type,
            confidence=claim_evidence.confidence,
        )
        self.session.add(evidence)
        self.session.flush()
        return claim

    def stage_output(
        self,
        title: str,
        output_type: str,
        project: Optional[ResearchProject] = None,
        run: Optional[ResearchRun] = None,
        content: Optional[str] = None,
        artifact_uri: Optional[str] = None,
        source: Optional[dict[str, Any]] = None,
        created_by: Optional[str] = None,
        format: str = "markdown",
    ) -> ResearchOutput:
        """Create a staged research output."""
        output = ResearchOutput(
            project=project,
            run=run,
            output_type=output_type,
            title=title,
            format=format,
            content=content,
            artifact_uri=artifact_uri,
            source_json=_json_dumps(source) if source is not None else None,
            created_by=created_by,
        )
        self.session.add(output)
        self.session.flush()
        return output

    def record_review_decision(
        self,
        output: ResearchOutput,
        decision: str,
        reviewer: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> ReviewDecision:
        """Record a review decision and mirror the decision on output status."""
        review = ReviewDecision(
            output=output,
            decision=decision,
            reviewer=reviewer,
            rationale=rationale,
        )
        output.status = decision
        self.session.add(review)
        self.session.flush()
        return review

    def review_run_outputs(
        self,
        run: ResearchRun,
        decision: str,
        reviewer: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> RunReviewResult:
        """Record a reviewer decision for every staged output on a run."""
        normalized_decision = _normalize_review_decision(decision)
        if run.status != "staged":
            raise ValueError(f"Only staged runs can be reviewed; current status is {run.status}")
        if not run.outputs:
            raise ValueError("Cannot review a run with no staged outputs")

        decisions = [
            self.record_review_decision(
                output,
                decision=normalized_decision,
                reviewer=reviewer,
                rationale=rationale,
            )
            for output in run.outputs
        ]
        event = self.update_run_status(
            run,
            status=normalized_decision,
            message=_review_message(normalized_decision),
            actor=reviewer,
            payload={
                "decision": normalized_decision,
                "reviewer": reviewer,
                "rationale": rationale,
                "output_ids": [output.id for output in run.outputs],
                "review_decision_ids": [decision.id for decision in decisions],
            },
        )
        return RunReviewResult(run=run, decisions=decisions, event=event)


def _normalize_review_decision(decision: str) -> str:
    normalized = decision.strip().lower().replace("-", "_")
    aliases = {
        "promote": "promoted",
        "promoted": "promoted",
        "reject": "rejected",
        "rejected": "rejected",
        "request_changes": "changes_requested",
        "changes_requested": "changes_requested",
    }
    if normalized not in aliases:
        supported = ", ".join(sorted({"promote", "reject", "request-changes"}))
        raise ValueError(f"Unsupported review decision: {decision}. Supported values: {supported}")
    return aliases[normalized]


def _review_message(decision: str) -> str:
    messages = {
        "promoted": "Run outputs promoted.",
        "rejected": "Run outputs rejected.",
        "changes_requested": "Run output changes requested.",
    }
    return messages[decision]


def _normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError(f"Invalid user email: {email}")
    return normalized


def _normalize_slug(slug: str) -> str:
    normalized = slug.strip().lower()
    if not normalized:
        raise ValueError("Slug must not be empty")
    return normalized


def _normalize_principal_type(principal_type: str) -> str:
    normalized = principal_type.strip().lower()
    if normalized not in {"user", "team"}:
        raise ValueError("Project permission principal_type must be 'user' or 'team'")
    return normalized


def _normalize_project_role(role: str) -> str:
    normalized = role.strip().lower().replace("-", "_")
    aliases = {
        "view": "viewer",
        "viewer": "viewer",
        "contribute": "contributor",
        "contributor": "contributor",
        "review": "reviewer",
        "reviewer": "reviewer",
        "admin": "admin",
    }
    if normalized not in aliases:
        supported = ", ".join(PROJECT_ROLE_ORDER)
        raise ValueError(f"Unsupported project role: {role}. Supported values: {supported}")
    return aliases[normalized]
