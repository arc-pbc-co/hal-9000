"""Google Sheets sync jobs for firm-wide HAL project views."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

import httpx
from sqlalchemy import desc

from hal9000.db.models import ResearchAuditEvent, ResearchOutput, ResearchProject
from hal9000.db.store import ResearchStore
from hal9000.research.authz import ResearchAuthorizer
from hal9000.research.collaboration import CollaborationService
from hal9000.research.review import ResearchReviewService

SheetSyncTarget = Literal["runs", "review_queue", "outputs", "audit"]


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


def sync_result_payload(result: SheetSyncResult) -> dict[str, Any]:
    """Return a JSON-friendly sync result."""
    return result.to_dict()


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
