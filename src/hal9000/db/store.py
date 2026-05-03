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
    ResearchOutput,
    ResearchProgramRecord,
    ResearchProject,
    ResearchRun,
    ResearchRunEvent,
    ResearchToolCall,
    ReviewDecision,
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
        if status in {"staged", "completed", "failed", "promoted", "rejected"}:
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
