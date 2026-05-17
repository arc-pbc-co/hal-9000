"""Retention planning and opt-in cleanup for production HAL deployments."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from hal9000.config import RetentionConfig
from hal9000.db.models import (
    Document,
    GatewaySession,
    ResearchAuditEvent,
    ResearchNotification,
    ResearchOutput,
    ResearchOutputVersion,
    ResearchRunEvent,
    ResearchToolCall,
    utc_now,
)
from hal9000.storage import LocalObjectStore, ObjectStore, S3ObjectStore


@dataclass(frozen=True)
class RetentionRulePlan:
    """Dry-run plan for one retention rule."""

    name: str
    table: str
    retain_days: int
    cutoff: datetime
    candidates: int
    protected: int = 0
    missing: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the rule plan for CLI/API output."""
        return {
            "name": self.name,
            "table": self.table,
            "retain_days": self.retain_days,
            "cutoff": _iso(self.cutoff),
            "candidates": self.candidates,
            "protected": self.protected,
            "missing": self.missing,
        }


@dataclass(frozen=True)
class RetentionObjectPlan:
    """Dry-run plan for one object-store artifact deletion."""

    rule: str
    owner_table: str
    owner_id: str
    object_uri: str
    object_key: str
    observed_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize the object candidate for CLI/API output."""
        return {
            "rule": self.rule,
            "owner_table": self.owner_table,
            "owner_id": self.owner_id,
            "object_uri": self.object_uri,
            "object_key": self.object_key,
            "observed_at": _iso(self.observed_at),
        }


@dataclass(frozen=True)
class _ArtifactScan:
    """Internal scan result for one artifact retention rule."""

    rule: RetentionRulePlan
    objects: list[RetentionObjectPlan]


@dataclass(frozen=True)
class RetentionPlan:
    """Dry-run retention report across all governed stores."""

    generated_at: datetime
    enabled: bool
    rules: list[RetentionRulePlan]
    objects: list[RetentionObjectPlan] | None = None

    @property
    def total_candidates(self) -> int:
        """Return the total rows that would be deleted by the plan."""
        return sum(rule.candidates for rule in self.rules)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the plan for CLI/API output."""
        return {
            "generated_at": _iso(self.generated_at),
            "enabled": self.enabled,
            "total_candidates": self.total_candidates,
            "rules": [rule.to_dict() for rule in self.rules],
            "objects": [item.to_dict() for item in self.objects or []],
        }


@dataclass(frozen=True)
class RetentionApplyResult:
    """Result of applying or dry-running a retention plan."""

    plan: RetentionPlan
    applied: bool
    deleted_counts: dict[str, int]
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the apply result for CLI/API output."""
        return {
            "applied": self.applied,
            "deleted_counts": dict(self.deleted_counts),
            "message": self.message,
            "plan": self.plan.to_dict(),
        }


class ResearchRetentionService:
    """Plan and apply conservative retention over HAL operational records and artifacts."""

    def __init__(
        self,
        session: Session,
        config: RetentionConfig | None = None,
        object_store: ObjectStore | None = None,
    ):
        """Initialize the retention service with a database session and policy."""
        self.session = session
        self.config = config or RetentionConfig()
        self.object_store = object_store

    def plan(self, now: datetime | None = None) -> RetentionPlan:
        """Return a dry-run plan without mutating any records."""
        generated_at = _as_utc(now or utc_now())
        artifact_scans = self._artifact_scans(generated_at)
        return RetentionPlan(
            generated_at=generated_at,
            enabled=self.config.enabled,
            rules=[
                self._rule_plan(
                    "run_events",
                    ResearchRunEvent,
                    ResearchRunEvent.created_at,
                    self.config.run_event_days,
                    generated_at,
                ),
                self._rule_plan(
                    "tool_calls",
                    ResearchToolCall,
                    ResearchToolCall.created_at,
                    self.config.tool_call_days,
                    generated_at,
                ),
                self._rule_plan(
                    "notifications",
                    ResearchNotification,
                    ResearchNotification.created_at,
                    self.config.notification_days,
                    generated_at,
                ),
                self._rule_plan(
                    "audit_events",
                    ResearchAuditEvent,
                    ResearchAuditEvent.created_at,
                    self.config.audit_event_days,
                    generated_at,
                ),
                self._rule_plan(
                    "gateway_sessions",
                    GatewaySession,
                    GatewaySession.last_active,
                    self.config.gateway_session_days,
                    generated_at,
                ),
                *[scan.rule for scan in artifact_scans],
            ],
            objects=[item for scan in artifact_scans for item in scan.objects],
        )

    def apply(self, confirm: bool = False, now: datetime | None = None) -> RetentionApplyResult:
        """Apply a retention plan only when policy is enabled and explicitly confirmed."""
        plan = self.plan(now=now)
        if not confirm:
            return RetentionApplyResult(
                plan=plan,
                applied=False,
                deleted_counts={},
                message="dry run only; pass confirm=True to apply retention",
            )
        if not self.config.enabled:
            return RetentionApplyResult(
                plan=plan,
                applied=False,
                deleted_counts={},
                message="retention is disabled in configuration",
            )

        deleted_counts: dict[str, int] = {}
        for rule in plan.rules:
            if rule.name not in _RULE_TARGETS:
                continue
            model, column = _RULE_TARGETS[rule.name]
            deleted_counts[rule.name] = (
                self.session.query(model)
                .filter(column < rule.cutoff)
                .delete(synchronize_session=False)
            )
        if self.object_store is not None:
            for item in plan.objects or []:
                self.object_store.delete(item.object_key)
                deleted_counts[item.rule] = deleted_counts.get(item.rule, 0) + 1
        self.session.flush()
        return RetentionApplyResult(
            plan=plan,
            applied=True,
            deleted_counts=deleted_counts,
            message="retention applied",
        )

    def _rule_plan(
        self,
        name: str,
        model: Any,
        column: Any,
        retain_days: int,
        generated_at: datetime,
    ) -> RetentionRulePlan:
        cutoff = generated_at - timedelta(days=retain_days)
        candidates = self.session.query(model).filter(column < cutoff).count()
        table = getattr(model, "__tablename__", name)
        return RetentionRulePlan(
            name=name,
            table=table,
            retain_days=retain_days,
            cutoff=cutoff,
            candidates=candidates,
        )

    def _artifact_scans(self, generated_at: datetime) -> list[_ArtifactScan]:
        if self.object_store is None:
            return []
        return [
            self._pdf_artifact_scan(generated_at),
            self._output_artifact_scan(generated_at),
        ]

    def _pdf_artifact_scan(self, generated_at: datetime) -> _ArtifactScan:
        object_store = self.object_store
        if object_store is None:
            raise RuntimeError("artifact scan requires an object store")
        cutoff = generated_at - timedelta(days=self.config.pdf_artifact_days)
        objects: list[RetentionObjectPlan] = []
        protected = 0
        missing = 0
        seen: set[str] = set()
        for document in self.session.query(Document).filter(Document.updated_at < cutoff).all():
            if _has_legal_hold(_json_or_none(document.source_quality_json), generated_at):
                protected += 1
                continue
            object_key = _object_key_for_uri(object_store, document.source_path)
            if object_key is None:
                continue
            if object_key in seen:
                continue
            seen.add(object_key)
            if not object_store.exists(object_key):
                missing += 1
                continue
            objects.append(
                RetentionObjectPlan(
                    rule="pdf_artifacts",
                    owner_table=Document.__tablename__,
                    owner_id=document.id,
                    object_uri=document.source_path,
                    object_key=object_key,
                    observed_at=_as_utc(document.updated_at),
                )
            )
        return _ArtifactScan(
            rule=RetentionRulePlan(
                name="pdf_artifacts",
                table="object_store",
                retain_days=self.config.pdf_artifact_days,
                cutoff=cutoff,
                candidates=len(objects),
                protected=protected,
                missing=missing,
            ),
            objects=objects,
        )

    def _output_artifact_scan(self, generated_at: datetime) -> _ArtifactScan:
        cutoff = generated_at - timedelta(days=self.config.output_artifact_days)
        objects: list[RetentionObjectPlan] = []
        protected = 0
        missing = 0
        seen: set[str] = set()

        for output in self.session.query(ResearchOutput).filter(ResearchOutput.updated_at < cutoff).all():
            if _has_legal_hold(_json_or_none(output.source_json), generated_at):
                protected += 1
                continue
            missing += self._append_artifact_candidate(
                objects,
                seen,
                rule="output_artifacts",
                owner_table=ResearchOutput.__tablename__,
                owner_id=output.id,
                object_uri=output.artifact_uri,
                observed_at=_as_utc(output.updated_at),
            )

        for version in (
            self.session.query(ResearchOutputVersion)
            .filter(ResearchOutputVersion.created_at < cutoff)
            .all()
        ):
            if _has_legal_hold(_json_or_none(version.source_json), generated_at):
                protected += 1
                continue
            missing += self._append_artifact_candidate(
                objects,
                seen,
                rule="output_artifacts",
                owner_table=ResearchOutputVersion.__tablename__,
                owner_id=version.id,
                object_uri=version.artifact_uri,
                observed_at=_as_utc(version.created_at),
            )

        return _ArtifactScan(
            rule=RetentionRulePlan(
                name="output_artifacts",
                table="object_store",
                retain_days=self.config.output_artifact_days,
                cutoff=cutoff,
                candidates=len(objects),
                protected=protected,
                missing=missing,
            ),
            objects=objects,
        )

    def _append_artifact_candidate(
        self,
        objects: list[RetentionObjectPlan],
        seen: set[str],
        *,
        rule: str,
        owner_table: str,
        owner_id: str,
        object_uri: str | None,
        observed_at: datetime,
    ) -> int:
        object_key = _object_key_for_uri(self.object_store, object_uri)
        if object_key is None or object_key in seen:
            return 0
        seen.add(object_key)
        if not self.object_store or not self.object_store.exists(object_key):
            return 1
        objects.append(
            RetentionObjectPlan(
                rule=rule,
                owner_table=owner_table,
                owner_id=owner_id,
                object_uri=object_uri or object_key,
                object_key=object_key,
                observed_at=observed_at,
            )
        )
        return 0


_RULE_TARGETS = {
    "run_events": (ResearchRunEvent, ResearchRunEvent.created_at),
    "tool_calls": (ResearchToolCall, ResearchToolCall.created_at),
    "notifications": (ResearchNotification, ResearchNotification.created_at),
    "audit_events": (ResearchAuditEvent, ResearchAuditEvent.created_at),
    "gateway_sessions": (GatewaySession, GatewaySession.last_active),
}


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _json_or_none(raw_value: str | None) -> Any:
    if not raw_value:
        return None
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return None


def _has_legal_hold(payload: Any, now: datetime) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in ("legal_hold", "retention_hold", "copyright_hold", "hold"):
        if payload.get(key) is True:
            return True
    policy = str(payload.get("retention_policy") or payload.get("policy") or "").lower()
    if policy in {"hold", "legal_hold", "retention_hold", "preserve"}:
        return True
    tags = payload.get("tags")
    if isinstance(tags, list) and any(str(tag).lower() in {"legal_hold", "retention_hold"} for tag in tags):
        return True
    for key in ("legal_hold_until", "retention_hold_until", "hold_until"):
        if _datetime_is_future(payload.get(key), now):
            return True
    return False


def _datetime_is_future(raw_value: Any, now: datetime) -> bool:
    if not isinstance(raw_value, str) or not raw_value.strip():
        return False
    normalized = raw_value.strip().replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return _as_utc(value) >= _as_utc(now)


def _object_key_for_uri(object_store: ObjectStore | None, uri: str | None) -> str | None:
    if object_store is None or not uri:
        return None
    raw_value = uri.strip()
    if not raw_value:
        return None
    parsed = urlparse(raw_value)
    if isinstance(object_store, LocalObjectStore):
        if parsed.scheme and parsed.scheme != object_store.uri_scheme:
            return None
        if parsed.scheme:
            key = f"{parsed.netloc}{parsed.path}".strip("/")
        else:
            key = raw_value
        return key or None
    if isinstance(object_store, S3ObjectStore):
        if parsed.scheme != "s3" or parsed.netloc != object_store.bucket:
            return None
        key = parsed.path.strip("/")
        prefix = object_store.prefix
        if prefix and key.startswith(prefix):
            key = key[len(prefix) :]
        elif prefix:
            return None
        return key or None
    if parsed.scheme:
        return None
    return raw_value
