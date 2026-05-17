"""Google Sheets sync jobs for firm-wide HAL project views."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

import httpx
from sqlalchemy import desc

from hal9000.db.models import (
    ResearchAuditEvent,
    ResearchOutput,
    ResearchProgramRecord,
    ResearchProject,
)
from hal9000.db.store import ResearchStore
from hal9000.research.annotations import ReviewAnnotationService
from hal9000.research.authz import ResearchAuthorizer
from hal9000.research.collaboration import CollaborationService
from hal9000.research.review import ResearchReviewService

SheetSyncTarget = Literal["runs", "review_queue", "outputs", "audit"]
SheetWritebackAction = Literal["add_comment", "review_run", "queue_run"]


@dataclass(frozen=True)
class SheetSyncResult:
    """Result of syncing one HAL view into a sheet range."""

    target: SheetSyncTarget
    spreadsheet_id: str
    range_name: str
    row_count: int
    status: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly result."""
        return asdict(self)


@dataclass(frozen=True)
class SheetWritebackResult:
    """Result of applying one Sheets-originated action to HAL state."""

    action: SheetWritebackAction
    status: str
    message: str
    project_slug: str | None = None
    run_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    annotation_id: str | None = None
    decision: str | None = None
    queued_run_id: str | None = None
    audit_event_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly writeback result."""
        return asdict(self)


class SheetsClient(Protocol):
    """Minimal Google Sheets Values API client contract."""

    def update_values(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: list[list[Any]],
    ) -> dict[str, Any]:
        """Replace values in a sheet range."""


class GoogleSheetsAPIClient:
    """Native Google Sheets Values API client using a bearer token."""

    def __init__(
        self,
        access_token: str | None = None,
        timeout_seconds: float = 10.0,
        base_url: str = "https://sheets.googleapis.com/v4/spreadsheets",
    ):
        """Initialize with explicit token or HAL9000_GOOGLE_SHEETS_TOKEN."""
        self.access_token = access_token or os.getenv("HAL9000_GOOGLE_SHEETS_TOKEN")
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url.rstrip("/")

    def update_values(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: list[list[Any]],
    ) -> dict[str, Any]:
        """Replace values in a Google Sheets range."""
        if not self.access_token:
            raise ValueError("HAL9000_GOOGLE_SHEETS_TOKEN is not configured")
        url = f"{self.base_url}/{spreadsheet_id}/values/{range_name}"
        response = httpx.put(
            url,
            params={"valueInputOption": "RAW"},
            headers={"Authorization": f"Bearer {self.access_token}"},
            json={"values": values},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}


class SheetsSyncService:
    """Sync HAL project cockpit views to Google Sheets."""

    def __init__(
        self,
        store: ResearchStore,
        client: SheetsClient | None = None,
    ):
        """Initialize with store and optional Sheets API client."""
        self.store = store
        self.client = client or GoogleSheetsAPIClient()
        self.authorizer = ResearchAuthorizer(store)

    def sync_project_view(
        self,
        project: ResearchProject,
        target: SheetSyncTarget,
        spreadsheet_id: str,
        range_name: str,
        actor_email: str,
        reviewer_email: str | None = None,
        limit: int = 100,
        dry_run: bool = False,
    ) -> SheetSyncResult:
        """Sync one project view to a Google Sheets range."""
        self.authorizer.require_project_role(project, actor_email, "viewer")
        values = self.values_for_project_view(
            project,
            target=target,
            reviewer_email=reviewer_email or actor_email,
            limit=limit,
        )
        if dry_run:
            status = "skipped"
            message = "Dry run: Google Sheets was not updated."
        else:
            response = self.client.update_values(spreadsheet_id, range_name, values)
            status = "sent"
            message = f"Google Sheets updated: {response.get('updatedRange', range_name)}"
        self.store.record_audit_event(
            action=f"sheets.{target}_synced",
            target_type="project",
            target_id=project.id,
            project=project,
            actor_email=actor_email,
            payload={
                "spreadsheet_id": spreadsheet_id,
                "range_name": range_name,
                "row_count": max(0, len(values) - 1),
                "dry_run": dry_run,
            },
        )
        return SheetSyncResult(
            target=target,
            spreadsheet_id=spreadsheet_id,
            range_name=range_name,
            row_count=max(0, len(values) - 1),
            status=status,
            message=message,
        )

    def values_for_project_view(
        self,
        project: ResearchProject,
        target: SheetSyncTarget,
        reviewer_email: str,
        limit: int = 100,
    ) -> list[list[Any]]:
        """Build rows for a project view without writing to Google Sheets."""
        if target == "runs":
            return _runs_values(self.store, project, limit)
        if target == "review_queue":
            return _review_queue_values(self.store, project, reviewer_email, limit)
        if target == "outputs":
            return _outputs_values(self.store, project, limit)
        if target == "audit":
            return _audit_values(self.store, project, limit)
        raise ValueError("Sheets sync target must be runs, review_queue, outputs, or audit")


class SheetsWritebackService:
    """Apply token-gated Google Sheets writeback actions to HAL state."""

    def __init__(self, store: ResearchStore):
        """Initialize with the shared research store."""
        self.store = store
        self.authorizer = ResearchAuthorizer(store)

    def handle_writeback(self, payload: dict[str, Any]) -> SheetWritebackResult:
        """Apply a Sheets-originated action payload."""
        raw_action = _required_text(payload, "action")
        action = _normalize_writeback_action(raw_action)
        if action == "add_comment":
            return self._add_comment(payload)
        if action == "review_run":
            return self._review_run(payload, raw_action)
        if action == "queue_run":
            return self._queue_run(payload)
        raise ValueError(f"Unsupported Sheets writeback action: {raw_action}")

    def _add_comment(self, payload: dict[str, Any]) -> SheetWritebackResult:
        actor_email = _actor_email(payload)
        target_type = _normalize_annotation_target(
            _required_text(payload, "target_type", "targetType")
        )
        target_id = _required_text(payload, "target_id", "targetId", "output_id", "claim_id")
        body = _required_text(payload, "body", "comment", "comment_body", "text")
        annotation_type = (
            _optional_text(payload, "annotation_type", "annotationType", "type") or "comment"
        )

        annotation = ReviewAnnotationService(
            self.store,
            authorizer=self.authorizer,
        ).add_annotation(
            target_type,
            target_id,
            body=body,
            author_email=actor_email,
            annotation_type=annotation_type,
        )
        audit_event = self.store.record_audit_event(
            action="sheets.comment_added",
            target_type=annotation.target_type,
            target_id=annotation.target_id,
            project=annotation.project,
            run=annotation.run,
            actor_email=actor_email,
            payload={
                "annotation_id": annotation.id,
                "annotation_type": annotation.annotation_type,
                "body": annotation.body,
            },
        )
        return SheetWritebackResult(
            action="add_comment",
            status="accepted",
            message="Sheets comment recorded.",
            project_slug=annotation.project.slug if annotation.project else None,
            run_id=annotation.run_id,
            target_type=annotation.target_type,
            target_id=annotation.target_id,
            annotation_id=annotation.id,
            audit_event_id=audit_event.id,
        )

    def _review_run(
        self,
        payload: dict[str, Any],
        raw_action: str,
    ) -> SheetWritebackResult:
        reviewer_email = _actor_email(payload)
        run_id = _required_text(payload, "run_id", "runId")
        decision = _optional_text(payload, "decision") or _decision_from_action(raw_action)
        if not decision:
            raise ValueError("Sheets review_run writeback requires decision")
        rationale = _optional_text(payload, "rationale", "reason", "comment", "body")
        run = self.store.get_run(run_id)
        if run is None:
            raise ValueError(f"Research run not found: {run_id}")

        result = ResearchReviewService(
            self.store,
            authorizer=self.authorizer,
        ).review_run(
            run,
            decision=decision,
            reviewer_email=reviewer_email,
            rationale=rationale,
        )
        audit_event = self.store.record_audit_event(
            action="sheets.run_reviewed",
            target_type="run",
            target_id=result.run.id,
            project=result.run.project,
            run=result.run,
            actor_email=reviewer_email,
            payload={
                "decision": result.run.status,
                "rationale": rationale,
                "review_decision_ids": [decision.id for decision in result.decisions],
            },
        )
        return SheetWritebackResult(
            action="review_run",
            status="accepted",
            message=f"Sheets review decision recorded: {result.run.status}.",
            project_slug=result.run.project.slug if result.run.project else None,
            run_id=result.run.id,
            decision=result.run.status,
            audit_event_id=audit_event.id,
        )

    def _queue_run(self, payload: dict[str, Any]) -> SheetWritebackResult:
        actor_email = _actor_email(payload)
        program = self._optional_program(payload)
        project = self._resolve_queue_project(payload, program)
        self.authorizer.require_project_role(project, actor_email, "contributor")

        objective = _optional_text(payload, "objective", "prompt") or (
            program.objective if program else None
        )
        if not objective:
            raise ValueError("Sheets queue_run writeback requires objective or program_id")
        budget = _optional_mapping(payload, "budget")
        tool_policy = _optional_mapping(payload, "tool_policy", "toolPolicy")
        if program and (budget is None or tool_policy is None):
            spec = json.loads(program.spec_json)
            budget = budget if budget is not None else spec.get("budget")
            tool_policy = (
                tool_policy
                if tool_policy is not None
                else {"allowed_tools": spec.get("allowed_tools", [])}
            )

        run = self.store.create_run(
            objective=objective,
            project=project,
            program=program,
            initiated_by=actor_email,
            budget=budget,
            tool_policy=tool_policy,
        )
        self.store.append_run_event(
            run,
            event_type="run.queued",
            message="Research run queued from Sheets.",
            actor=actor_email,
            payload={"source": "sheets", "program_id": program.id if program else None},
        )
        audit_event = self.store.record_audit_event(
            action="sheets.run_queued",
            target_type="run",
            target_id=run.id,
            project=project,
            run=run,
            actor_email=actor_email,
            payload={
                "objective": objective,
                "program_id": program.id if program else None,
            },
        )
        return SheetWritebackResult(
            action="queue_run",
            status="accepted",
            message=f"Sheets queued HAL research run {run.id}.",
            project_slug=project.slug if project else None,
            run_id=run.id,
            queued_run_id=run.id,
            audit_event_id=audit_event.id,
        )

    def _optional_program(self, payload: dict[str, Any]) -> ResearchProgramRecord | None:
        program_id = _optional_text(payload, "program_id", "programId")
        if not program_id:
            return None
        program = self.store.session.get(ResearchProgramRecord, program_id)
        if program is None:
            raise ValueError(f"Research program not found: {program_id}")
        return program

    def _resolve_queue_project(
        self,
        payload: dict[str, Any],
        program: ResearchProgramRecord | None,
    ) -> ResearchProject:
        project_slug = _optional_text(payload, "project_slug", "projectSlug", "project")
        if project_slug:
            project = self.store.get_project_by_slug(project_slug)
            if project is None:
                raise ValueError(f"Research project not found: {project_slug}")
            if program is not None and program.project_id not in {None, project.id}:
                raise ValueError(
                    f"Research program {program.id} is not attached to project {project.slug}"
                )
            return project
        if program is not None and program.project is not None:
            return program.project
        raise ValueError("Sheets queue_run writeback requires project_slug")


def sync_result_payload(result: SheetSyncResult) -> dict[str, Any]:
    """Return a JSON-friendly sync result."""
    return result.to_dict()


def writeback_result_payload(result: SheetWritebackResult) -> dict[str, Any]:
    """Return a JSON-friendly writeback result."""
    return result.to_dict()


def _normalize_writeback_action(action: str) -> SheetWritebackAction:
    normalized = action.strip().lower().replace("-", "_").replace(".", "_")
    aliases: dict[str, SheetWritebackAction] = {
        "add_comment": "add_comment",
        "comment": "add_comment",
        "sheet_add_comment": "add_comment",
        "sheets_add_comment": "add_comment",
        "writeback_comment": "add_comment",
        "review_run": "review_run",
        "review": "review_run",
        "review_decision": "review_run",
        "decision": "review_run",
        "approve": "review_run",
        "promote": "review_run",
        "reject": "review_run",
        "request_changes": "review_run",
        "sheet_review_run": "review_run",
        "sheets_review_run": "review_run",
        "queue_run": "queue_run",
        "queue": "queue_run",
        "enqueue": "queue_run",
        "sheet_queue_run": "queue_run",
        "sheets_queue_run": "queue_run",
    }
    if normalized not in aliases:
        supported = ", ".join(sorted({"add_comment", "review_run", "queue_run"}))
        raise ValueError(f"Unsupported Sheets writeback action: {action}. Supported: {supported}")
    return aliases[normalized]


def _decision_from_action(action: str) -> str | None:
    normalized = action.strip().lower().replace("-", "_").replace(".", "_")
    return {
        "approve": "promote",
        "promote": "promote",
        "reject": "reject",
        "request_changes": "request-changes",
    }.get(normalized)


def _normalize_annotation_target(value: str) -> Literal["output", "claim"]:
    normalized = value.strip().lower().replace("-", "_")
    if normalized in {"output", "outputs", "research_output"}:
        return "output"
    if normalized in {"claim", "claims", "extracted_claim"}:
        return "claim"
    raise ValueError("Sheets comment target_type must be output or claim")


def _actor_email(payload: dict[str, Any]) -> str:
    return _required_text(
        payload,
        "actor_email",
        "actorEmail",
        "reviewer_email",
        "reviewerEmail",
        "author_email",
        "authorEmail",
        "user_email",
        "userEmail",
        "initiated_by",
        "initiatedBy",
        "email",
        "actor",
    ).lower()


def _required_text(payload: dict[str, Any], *keys: str) -> str:
    value = _optional_text(payload, *keys)
    if value is None:
        joined = "/".join(keys)
        raise ValueError(f"Sheets writeback payload requires {joined}")
    return value


def _optional_text(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        if key not in payload:
            continue
        value = payload[key]
        if value is None:
            continue
        if isinstance(value, str):
            normalized = value.strip()
        else:
            normalized = str(value).strip()
        if normalized:
            return normalized
    return None


def _optional_mapping(payload: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    for key in keys:
        if key not in payload:
            continue
        value = payload[key]
        if value is None or value == "":
            continue
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            decoded = json.loads(value)
            if not isinstance(decoded, dict):
                raise ValueError(f"Sheets writeback field {key} must be a JSON object")
            return decoded
        raise ValueError(f"Sheets writeback field {key} must be an object")
    return None


def _runs_values(
    store: ResearchStore,
    project: ResearchProject,
    limit: int,
) -> list[list[Any]]:
    rows = [
        [
            "run_id",
            "status",
            "objective",
            "initiated_by",
            "program",
            "created_at",
            "updated_at",
        ]
    ]
    runs = store.list_runs(project=project, limit=max(1, limit))
    rows.extend(
        [
            run.id,
            run.status,
            run.objective,
            run.initiated_by or "",
            run.program.name if run.program else "",
            _iso(run.created_at),
            _iso(run.updated_at),
        ]
        for run in runs
    )
    return rows


def _review_queue_values(
    store: ResearchStore,
    project: ResearchProject,
    reviewer_email: str,
    limit: int,
) -> list[list[Any]]:
    rows = [["run_id", "project_slug", "program", "objective", "output_count", "updated_at"]]
    items = ResearchReviewService(store).list_review_queue(
        reviewer_email=reviewer_email,
        project=project,
        limit=max(1, limit),
    )
    rows.extend(
        [
            item.run_id,
            item.project_slug or "",
            item.program_name or "",
            item.objective,
            item.output_count,
            item.updated_at or "",
        ]
        for item in items
    )
    return rows


def _outputs_values(
    store: ResearchStore,
    project: ResearchProject,
    limit: int,
) -> list[list[Any]]:
    rows = [["output_id", "run_id", "status", "type", "title", "artifact_uri", "created_at"]]
    outputs = (
        store.session.query(ResearchOutput)
        .filter_by(project_id=project.id)
        .order_by(desc(ResearchOutput.created_at), desc(ResearchOutput.id))
        .limit(max(1, limit))
        .all()
    )
    rows.extend(
        [
            output.id,
            output.run_id or "",
            output.status,
            output.output_type,
            output.title,
            output.artifact_uri or "",
            _iso(output.created_at),
        ]
        for output in outputs
    )
    return rows


def _audit_values(
    store: ResearchStore,
    project: ResearchProject,
    limit: int,
) -> list[list[Any]]:
    rows = [["event_id", "action", "actor", "target_type", "target_id", "run_id", "created_at"]]
    events = CollaborationService(store).list_audit_events(project=project, limit=max(1, limit))
    rows.extend(
        [
            event.id,
            event.action,
            event.actor_email or "",
            event.target_type,
            event.target_id,
            event.run_id or "",
            _iso(event.created_at),
        ]
        for event in events
        if isinstance(event, ResearchAuditEvent)
    )
    return rows


def _iso(value) -> str:
    return value.isoformat() if value else ""
