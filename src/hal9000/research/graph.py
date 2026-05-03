"""Knowledge graph relationship services for HAL research memory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from hal9000.db.models import (
    Document,
    DocumentChunk,
    ExtractedClaim,
    ResearchGraphEdge,
    ResearchOutput,
    ResearchProject,
    ResearchRun,
)
from hal9000.db.store import ResearchStore

GRAPH_RELATIONSHIPS = {
    "cites",
    "supports",
    "contradicts",
    "uses_method",
    "studies_material",
    "reports_property",
}

GRAPH_ENTITY_TYPES = {
    "document",
    "chunk",
    "claim",
    "output",
    "run",
    "project",
    "method",
    "material",
    "property",
    "concept",
}

DATABASE_ENTITY_TYPES = {
    "document",
    "chunk",
    "claim",
    "output",
    "run",
    "project",
}


@dataclass(frozen=True)
class GraphEdgePayload:
    """JSON-friendly graph edge representation."""

    id: str
    source_type: str
    source_id: str
    relationship_type: str
    target_type: str
    target_id: str
    confidence: float
    project_id: str | None
    run_id: str | None
    evidence: dict[str, Any] | None
    created_by: str | None
    status: str
    created_at: str | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


class ResearchGraphService:
    """Create and query typed research graph relationships."""

    def __init__(self, store: ResearchStore):
        """Initialize with the shared research store."""
        self.store = store
        self.session = store.session

    def add_edge(
        self,
        source_type: str,
        source_id: str,
        relationship_type: str,
        target_type: str,
        target_id: str,
        confidence: float = 1.0,
        project: ResearchProject | None = None,
        run: ResearchRun | None = None,
        evidence: dict[str, Any] | None = None,
        created_by: str | None = None,
        status: str = "active",
    ) -> ResearchGraphEdge:
        """Persist a typed graph edge after relationship and entity validation."""
        source_type = normalize_graph_entity_type(source_type)
        target_type = normalize_graph_entity_type(target_type)
        relationship_type = normalize_graph_relationship(relationship_type)
        if not 0 <= confidence <= 1:
            raise ValueError("Graph edge confidence must be between 0 and 1")

        source = self._resolve_entity(source_type, source_id)
        target = self._resolve_entity(target_type, target_id)
        inferred_run = run or _entity_run(source) or _entity_run(target)
        inferred_project = project or _entity_project(source) or _entity_project(target)
        if inferred_project is None and inferred_run is not None:
            inferred_project = inferred_run.project

        edge = ResearchGraphEdge(
            project=inferred_project,
            run=inferred_run,
            source_type=source_type,
            source_id=source_id,
            relationship_type=relationship_type,
            target_type=target_type,
            target_id=target_id,
            confidence=confidence,
            evidence_json=json.dumps(evidence, sort_keys=True) if evidence is not None else None,
            created_by=created_by,
            status=normalize_graph_status(status),
        )
        self.session.add(edge)
        self.session.flush()
        return edge

    def list_edges(
        self,
        source_type: str | None = None,
        source_id: str | None = None,
        relationship_type: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        project: ResearchProject | None = None,
        run: ResearchRun | None = None,
        status: str | None = "active",
        limit: int = 50,
    ) -> list[ResearchGraphEdge]:
        """List graph edges by optional source, target, project, run, and relation filters."""
        query = self.session.query(ResearchGraphEdge).order_by(
            ResearchGraphEdge.created_at.desc(),
            ResearchGraphEdge.id,
        )
        if source_type:
            query = query.filter_by(source_type=normalize_graph_entity_type(source_type))
        if source_id:
            query = query.filter_by(source_id=source_id)
        if relationship_type:
            query = query.filter_by(relationship_type=normalize_graph_relationship(relationship_type))
        if target_type:
            query = query.filter_by(target_type=normalize_graph_entity_type(target_type))
        if target_id:
            query = query.filter_by(target_id=target_id)
        if project:
            query = query.filter_by(project_id=project.id)
        if run:
            query = query.filter_by(run_id=run.id)
        if status:
            query = query.filter_by(status=normalize_graph_status(status))
        return query.limit(max(1, limit)).all()

    def edges_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        direction: str = "both",
        relationship_type: str | None = None,
        limit: int = 50,
    ) -> list[ResearchGraphEdge]:
        """Return incoming, outgoing, or all edges touching an entity."""
        entity_type = normalize_graph_entity_type(entity_type)
        if direction not in {"incoming", "outgoing", "both"}:
            raise ValueError("Graph edge direction must be incoming, outgoing, or both")

        if direction == "outgoing":
            return self.list_edges(
                source_type=entity_type,
                source_id=entity_id,
                relationship_type=relationship_type,
                limit=limit,
            )
        if direction == "incoming":
            return self.list_edges(
                target_type=entity_type,
                target_id=entity_id,
                relationship_type=relationship_type,
                limit=limit,
            )

        outgoing = self.edges_for_entity(
            entity_type,
            entity_id,
            direction="outgoing",
            relationship_type=relationship_type,
            limit=limit,
        )
        incoming = self.edges_for_entity(
            entity_type,
            entity_id,
            direction="incoming",
            relationship_type=relationship_type,
            limit=limit,
        )
        edges = outgoing + [edge for edge in incoming if edge.id not in {item.id for item in outgoing}]
        return edges[:limit]

    def _resolve_entity(self, entity_type: str, entity_id: str):
        if entity_type not in DATABASE_ENTITY_TYPES:
            if not entity_id.strip():
                raise ValueError(f"Graph {entity_type} id must not be empty")
            return None
        model = {
            "document": Document,
            "chunk": DocumentChunk,
            "claim": ExtractedClaim,
            "output": ResearchOutput,
            "run": ResearchRun,
            "project": ResearchProject,
        }[entity_type]
        entity = self.session.get(model, entity_id)
        if entity is None:
            raise ValueError(f"Graph {entity_type} not found: {entity_id}")
        return entity


def edge_payload(edge: ResearchGraphEdge) -> GraphEdgePayload:
    """Return a JSON-friendly graph edge payload."""
    return GraphEdgePayload(
        id=edge.id,
        source_type=edge.source_type,
        source_id=edge.source_id,
        relationship_type=edge.relationship_type,
        target_type=edge.target_type,
        target_id=edge.target_id,
        confidence=edge.confidence,
        project_id=edge.project_id,
        run_id=edge.run_id,
        evidence=json.loads(edge.evidence_json) if edge.evidence_json else None,
        created_by=edge.created_by,
        status=edge.status,
        created_at=edge.created_at.isoformat() if edge.created_at else None,
    )


def normalize_graph_relationship(value: str) -> str:
    """Normalize and validate supported graph relationship names."""
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in GRAPH_RELATIONSHIPS:
        supported = ", ".join(sorted(GRAPH_RELATIONSHIPS))
        raise ValueError(f"Unsupported graph relationship: {value}. Supported values: {supported}")
    return normalized


def normalize_graph_entity_type(value: str) -> str:
    """Normalize and validate supported graph entity types."""
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in GRAPH_ENTITY_TYPES:
        supported = ", ".join(sorted(GRAPH_ENTITY_TYPES))
        raise ValueError(f"Unsupported graph entity type: {value}. Supported values: {supported}")
    return normalized


def normalize_graph_status(value: str) -> str:
    """Normalize graph edge status."""
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"active", "retracted", "superseded"}:
        raise ValueError("Graph edge status must be active, retracted, or superseded")
    return normalized


def _entity_run(entity):
    if entity is None:
        return None
    if isinstance(entity, ResearchRun):
        return entity
    return getattr(entity, "run", None)


def _entity_project(entity):
    if entity is None:
        return None
    if isinstance(entity, ResearchProject):
        return entity
    project = getattr(entity, "project", None)
    if project is not None:
        return project
    run = getattr(entity, "run", None)
    return run.project if run is not None else None
