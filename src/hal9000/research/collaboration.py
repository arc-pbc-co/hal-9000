"""Collaboration views for shared HAL research projects."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from hal9000.db.models import (
    ResearchAuditEvent,
    ResearchCollection,
    ResearchCollectionItem,
    ResearchNotification,
    ResearchProject,
    ResearchRun,
    SavedSearch,
    SharedProjectView,
    utc_now,
)
from hal9000.db.store import ResearchStore


@dataclass(frozen=True)
class CollaborationPayload:
    """JSON-friendly wrapper for collaboration records."""

    id: str
    kind: str
    fields: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


class CollaborationService:
    """Service API for collections, saved searches, views, notifications, and audit."""

    def __init__(self, store: ResearchStore):
        """Initialize with the shared research store."""
        self.store = store
        self.session = store.session

    def create_collection(
        self,
        project: ResearchProject,
        name: str,
        slug: str | None = None,
        description: str | None = None,
        owner_email: str | None = None,
        visibility: str = "project",
    ) -> ResearchCollection:
        """Create a project collection."""
        collection = ResearchCollection(
            project=project,
            name=name,
            slug=slug or _slug(name),
            description=description,
            owner_email=_normalize_email_or_none(owner_email),
            visibility=_normalize_visibility(visibility),
        )
        self.session.add(collection)
        self.session.flush()
        self.store.record_audit_event(
            "collection.created",
            "collection",
            collection.id,
            project=project,
            actor_email=collection.owner_email,
            payload={"name": collection.name, "slug": collection.slug},
        )
        return collection

    def add_collection_item(
        self,
        collection: ResearchCollection,
        target_type: str,
        target_id: str,
        note: str | None = None,
        added_by: str | None = None,
    ) -> ResearchCollectionItem:
        """Add or update an item in a collection."""
        target_type = _normalize_target_type(target_type)
        item = (
            self.session.query(ResearchCollectionItem)
            .filter_by(
                collection_id=collection.id,
                target_type=target_type,
                target_id=target_id,
            )
            .one_or_none()
        )
        if item is None:
            item = ResearchCollectionItem(
                collection=collection,
                target_type=target_type,
                target_id=target_id,
            )
            self.session.add(item)
        item.note = note
        item.added_by = _normalize_email_or_none(added_by)
        self.session.flush()
        self.store.record_audit_event(
            "collection.item_added",
            target_type,
            target_id,
            project=collection.project,
            actor_email=item.added_by,
            payload={"collection_id": collection.id, "collection_slug": collection.slug},
        )
        return item

    def list_collections(
        self,
        project: ResearchProject,
        status: str = "active",
        limit: int = 50,
    ) -> list[ResearchCollection]:
        """List project collections."""
        return (
            self.session.query(ResearchCollection)
            .filter_by(project_id=project.id, status=status)
            .order_by(ResearchCollection.updated_at.desc(), ResearchCollection.name)
            .limit(max(1, limit))
            .all()
        )

    def get_collection(self, project: ResearchProject, slug: str) -> ResearchCollection | None:
        """Fetch a collection by project and slug."""
        return (
            self.session.query(ResearchCollection)
            .filter_by(project_id=project.id, slug=_slug(slug))
            .one_or_none()
        )

    def save_search(
        self,
        project: ResearchProject,
        name: str,
        query_text: str,
        target: str = "memory",
        filters: dict[str, Any] | None = None,
        owner_email: str | None = None,
        visibility: str = "project",
    ) -> SavedSearch:
        """Create or update a saved search."""
        search = (
            self.session.query(SavedSearch)
            .filter_by(project_id=project.id, name=name)
            .one_or_none()
        )
        if search is None:
            search = SavedSearch(project=project, name=name)
            self.session.add(search)
        search.query_text = query_text
        search.target = _normalize_search_target(target)
        search.filters_json = json.dumps(filters, sort_keys=True) if filters else None
        search.owner_email = _normalize_email_or_none(owner_email)
        search.visibility = _normalize_visibility(visibility)
        search.status = "active"
        self.session.flush()
        self.store.record_audit_event(
            "saved_search.saved",
            "saved_search",
            search.id,
            project=project,
            actor_email=search.owner_email,
            payload={"name": search.name, "target": search.target},
        )
        return search

    def list_saved_searches(
        self,
        project: ResearchProject,
        status: str = "active",
        limit: int = 50,
    ) -> list[SavedSearch]:
        """List saved searches for a project."""
        return (
            self.session.query(SavedSearch)
            .filter_by(project_id=project.id, status=status)
            .order_by(SavedSearch.updated_at.desc(), SavedSearch.name)
            .limit(max(1, limit))
            .all()
        )

    def create_shared_view(
        self,
        project: ResearchProject,
        name: str,
        slug: str | None = None,
        view_type: str = "dashboard",
        config: dict[str, Any] | None = None,
        owner_email: str | None = None,
        visibility: str = "project",
    ) -> SharedProjectView:
        """Create or update a shared project view."""
        normalized_slug = _slug(slug or name)
        view = (
            self.session.query(SharedProjectView)
            .filter_by(project_id=project.id, slug=normalized_slug)
            .one_or_none()
        )
        if view is None:
            view = SharedProjectView(project=project, slug=normalized_slug)
            self.session.add(view)
        view.name = name
        view.view_type = _normalize_view_type(view_type)
        view.config_json = json.dumps(config or {}, sort_keys=True)
        view.owner_email = _normalize_email_or_none(owner_email)
        view.visibility = _normalize_visibility(visibility)
        view.status = "active"
        self.session.flush()
        self.store.record_audit_event(
            "shared_view.saved",
            "shared_view",
            view.id,
            project=project,
            actor_email=view.owner_email,
            payload={"name": view.name, "slug": view.slug, "view_type": view.view_type},
        )
        return view

    def list_shared_views(
        self,
        project: ResearchProject,
        status: str = "active",
        limit: int = 50,
    ) -> list[SharedProjectView]:
        """List shared project views."""
        return (
            self.session.query(SharedProjectView)
            .filter_by(project_id=project.id, status=status)
            .order_by(SharedProjectView.updated_at.desc(), SharedProjectView.name)
            .limit(max(1, limit))
            .all()
        )

    def create_notification(
        self,
        notification_type: str,
        title: str,
        body: str | None = None,
        project: ResearchProject | None = None,
        run: ResearchRun | None = None,
        recipient_email: str | None = None,
        channel: str = "in_app",
        payload: dict[str, Any] | None = None,
    ) -> ResearchNotification:
        """Create a pending collaboration notification."""
        notification = ResearchNotification(
            project=project,
            run=run,
            recipient_email=_normalize_email_or_none(recipient_email),
            channel=_normalize_channel(channel),
            notification_type=notification_type.strip(),
            title=title,
            body=body,
            payload_json=json.dumps(payload, sort_keys=True) if payload else None,
        )
        self.session.add(notification)
        self.session.flush()
        self.store.record_audit_event(
            "notification.created",
            "notification",
            notification.id,
            project=project,
            run=run,
            actor_email=notification.recipient_email,
            payload={"notification_type": notification.notification_type, "channel": notification.channel},
        )
        return notification

    def create_review_ready_notifications(
        self,
        run: ResearchRun,
        recipients: list[str],
        channel: str = "in_app",
    ) -> list[ResearchNotification]:
        """Queue review-ready notifications for a staged run."""
        return [
            self.create_notification(
                notification_type="review_ready",
                title=f"Run ready for review: {run.objective[:120]}",
                body=f"Research run {run.id} is staged with {len(run.outputs)} output(s).",
                project=run.project,
                run=run,
                recipient_email=recipient,
                channel=channel,
                payload={"run_id": run.id, "output_ids": [output.id for output in run.outputs]},
            )
            for recipient in recipients
        ]

    def list_notifications(
        self,
        recipient_email: str | None = None,
        status: str | None = None,
        project: ResearchProject | None = None,
        limit: int = 50,
    ) -> list[ResearchNotification]:
        """List notifications by recipient, status, and project."""
        query = self.session.query(ResearchNotification).order_by(
            ResearchNotification.created_at.desc()
        )
        if recipient_email:
            query = query.filter_by(recipient_email=_normalize_email_or_none(recipient_email))
        if status:
            query = query.filter_by(status=status)
        if project:
            query = query.filter_by(project_id=project.id)
        return query.limit(max(1, limit)).all()

    def mark_notification(
        self,
        notification: ResearchNotification,
        status: str,
    ) -> ResearchNotification:
        """Mark notification delivery/read state."""
        normalized_status = _normalize_notification_status(status)
        notification.status = normalized_status
        now = utc_now()
        if normalized_status == "sent":
            notification.delivered_at = now
        if normalized_status == "read":
            notification.read_at = now
        self.session.flush()
        return notification

    def list_audit_events(
        self,
        project: ResearchProject | None = None,
        run: ResearchRun | None = None,
        action: str | None = None,
        target_type: str | None = None,
        limit: int = 50,
    ) -> list[ResearchAuditEvent]:
        """List audit events for dashboards and review trails."""
        query = self.session.query(ResearchAuditEvent).order_by(
            ResearchAuditEvent.created_at.desc()
        )
        if project:
            query = query.filter_by(project_id=project.id)
        if run:
            query = query.filter_by(run_id=run.id)
        if action:
            query = query.filter_by(action=action)
        if target_type:
            query = query.filter_by(target_type=target_type)
        return query.limit(max(1, limit)).all()


def collection_payload(collection: ResearchCollection) -> dict[str, Any]:
    """Return a JSON-friendly collection payload."""
    return {
        "id": collection.id,
        "project_id": collection.project_id,
        "name": collection.name,
        "slug": collection.slug,
        "description": collection.description,
        "owner_email": collection.owner_email,
        "visibility": collection.visibility,
        "status": collection.status,
        "item_count": len(collection.items),
        "items": [collection_item_payload(item) for item in collection.items],
    }


def collection_item_payload(item: ResearchCollectionItem) -> dict[str, Any]:
    """Return a JSON-friendly collection item payload."""
    return {
        "id": item.id,
        "collection_id": item.collection_id,
        "target_type": item.target_type,
        "target_id": item.target_id,
        "note": item.note,
        "added_by": item.added_by,
        "created_at": _iso(item.created_at),
    }


def saved_search_payload(search: SavedSearch) -> dict[str, Any]:
    """Return a JSON-friendly saved search payload."""
    return {
        "id": search.id,
        "project_id": search.project_id,
        "name": search.name,
        "query_text": search.query_text,
        "target": search.target,
        "filters": json.loads(search.filters_json) if search.filters_json else None,
        "owner_email": search.owner_email,
        "visibility": search.visibility,
        "status": search.status,
        "created_at": _iso(search.created_at),
        "updated_at": _iso(search.updated_at),
    }


def shared_view_payload(view: SharedProjectView) -> dict[str, Any]:
    """Return a JSON-friendly shared view payload."""
    return {
        "id": view.id,
        "project_id": view.project_id,
        "name": view.name,
        "slug": view.slug,
        "view_type": view.view_type,
        "config": json.loads(view.config_json),
        "owner_email": view.owner_email,
        "visibility": view.visibility,
        "status": view.status,
        "created_at": _iso(view.created_at),
        "updated_at": _iso(view.updated_at),
    }


def notification_payload(notification: ResearchNotification) -> dict[str, Any]:
    """Return a JSON-friendly notification payload."""
    return {
        "id": notification.id,
        "project_id": notification.project_id,
        "run_id": notification.run_id,
        "recipient_email": notification.recipient_email,
        "channel": notification.channel,
        "notification_type": notification.notification_type,
        "title": notification.title,
        "body": notification.body,
        "status": notification.status,
        "payload": json.loads(notification.payload_json) if notification.payload_json else None,
        "created_at": _iso(notification.created_at),
        "delivered_at": _iso(notification.delivered_at),
        "read_at": _iso(notification.read_at),
    }


def audit_event_payload(event: ResearchAuditEvent) -> dict[str, Any]:
    """Return a JSON-friendly audit event payload."""
    return {
        "id": event.id,
        "project_id": event.project_id,
        "run_id": event.run_id,
        "actor_email": event.actor_email,
        "action": event.action,
        "target_type": event.target_type,
        "target_id": event.target_id,
        "payload": json.loads(event.payload_json) if event.payload_json else None,
        "created_at": _iso(event.created_at),
    }


def _slug(value: str) -> str:
    slug = "-".join(re.findall(r"[a-z0-9]+", value.lower()))
    if not slug:
        raise ValueError("Slug must not be empty")
    return slug


def _normalize_email_or_none(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if not normalized or "@" not in normalized:
        raise ValueError(f"Invalid email: {value}")
    return normalized


def _normalize_visibility(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"private", "project", "firm"}:
        raise ValueError("Visibility must be private, project, or firm")
    return normalized


def _normalize_target_type(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    supported = {
        "document",
        "chunk",
        "claim",
        "output",
        "run",
        "project",
        "collection",
        "saved_search",
        "shared_view",
        "material",
        "method",
        "property",
        "concept",
    }
    if normalized not in supported:
        raise ValueError(f"Unsupported collaboration target type: {value}")
    return normalized


def _normalize_search_target(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"chunks", "claims", "outputs", "memory", "graph"}:
        raise ValueError("Saved search target must be chunks, claims, outputs, memory, or graph")
    return normalized


def _normalize_view_type(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"dashboard", "review_queue", "collection", "search", "audit"}:
        raise ValueError("View type must be dashboard, review_queue, collection, search, or audit")
    return normalized


def _normalize_channel(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"in_app", "slack", "email", "sheets"}:
        raise ValueError("Notification channel must be in_app, slack, email, or sheets")
    return normalized


def _normalize_notification_status(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"pending", "sent", "read", "failed"}:
        raise ValueError("Notification status must be pending, sent, read, or failed")
    return normalized


def _iso(value) -> str | None:
    return value.isoformat() if value else None
