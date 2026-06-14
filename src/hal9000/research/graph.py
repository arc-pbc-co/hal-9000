"""Knowledge graph relationship services for HAL research memory."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from hal9000.db.models import (
    Document,
    DocumentChunk,
    ExtractedClaim,
    ResearchGraphEdge,
    ResearchOutput,
    ResearchProject,
    ResearchRun,
)

if TYPE_CHECKING:
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
    source_key: str
    source_type: str
    source_id: str
    relationship_type: str
    target_key: str
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


@dataclass
class GraphNodePayload:
    """JSON-friendly graph node representation."""

    key: str
    entity_type: str
    entity_id: str
    label: str
    title: str | None = None
    project_id: str | None = None
    run_id: str | None = None
    metadata: dict[str, Any] | None = None
    incoming_count: int = 0
    outgoing_count: int = 0

    @property
    def degree(self) -> int:
        """Return total incoming and outgoing edge count."""
        return self.incoming_count + self.outgoing_count

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        payload = asdict(self)
        payload["degree"] = self.degree
        return payload


@dataclass(frozen=True)
class GraphPayload:
    """JSON-friendly graph payload for project and neighborhood views."""

    scope: str
    scope_id: str
    scope_label: str
    nodes: list[GraphNodePayload]
    edges: list[GraphEdgePayload]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return {
            "scope": self.scope,
            "scope_id": self.scope_id,
            "scope_label": self.scope_label,
            "summary": self.summary,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


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

    def project_graph(
        self,
        project: ResearchProject,
        status: str | None = "active",
        limit: int = 500,
    ) -> GraphPayload:
        """Return a project-scoped graph payload suitable for API/UI/export use."""
        edges = self.list_edges(project=project, status=status, limit=limit)
        return self._graph_from_edges(
            scope="project",
            scope_id=project.slug,
            scope_label=project.name,
            edges=edges,
        )

    def run_graph(
        self,
        run: ResearchRun,
        status: str | None = "active",
        limit: int = 500,
    ) -> GraphPayload:
        """Return a run-scoped graph payload suitable for API/UI/export use."""
        edges = self.list_edges(run=run, status=status, limit=limit)
        return self._graph_from_edges(
            scope="run",
            scope_id=run.id,
            scope_label=run.objective,
            edges=edges,
        )

    def edges_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        direction: str = "both",
        relationship_type: str | None = None,
        project: ResearchProject | None = None,
        run: ResearchRun | None = None,
        status: str | None = "active",
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
                project=project,
                run=run,
                status=status,
                limit=limit,
            )
        if direction == "incoming":
            return self.list_edges(
                target_type=entity_type,
                target_id=entity_id,
                relationship_type=relationship_type,
                project=project,
                run=run,
                status=status,
                limit=limit,
            )

        outgoing = self.edges_for_entity(
            entity_type,
            entity_id,
            direction="outgoing",
            relationship_type=relationship_type,
            project=project,
            run=run,
            status=status,
            limit=limit,
        )
        incoming = self.edges_for_entity(
            entity_type,
            entity_id,
            direction="incoming",
            relationship_type=relationship_type,
            project=project,
            run=run,
            status=status,
            limit=limit,
        )
        edges = outgoing + [edge for edge in incoming if edge.id not in {item.id for item in outgoing}]
        return edges[:limit]

    def neighborhood(
        self,
        entity_type: str,
        entity_id: str,
        direction: str = "both",
        depth: int = 1,
        relationship_type: str | None = None,
        project: ResearchProject | None = None,
        run: ResearchRun | None = None,
        status: str | None = "active",
        limit: int = 100,
    ) -> GraphPayload:
        """Return a bounded graph neighborhood around one entity."""
        entity_type = normalize_graph_entity_type(entity_type)
        if direction not in {"incoming", "outgoing", "both"}:
            raise ValueError("Graph edge direction must be incoming, outgoing, or both")
        if depth < 1:
            raise ValueError("Graph neighborhood depth must be at least 1")
        if limit <= 0:
            raise ValueError("Graph neighborhood limit must be positive")

        root_key = graph_node_key(entity_type, entity_id)
        frontier = {(entity_type, entity_id)}
        visited_nodes = {root_key}
        selected_edges: dict[str, ResearchGraphEdge] = {}

        for _ in range(depth):
            next_frontier: set[tuple[str, str]] = set()
            for current_type, current_id in frontier:
                remaining = max(1, limit - len(selected_edges))
                edges = self.edges_for_entity(
                    current_type,
                    current_id,
                    direction=direction,
                    relationship_type=relationship_type,
                    project=project,
                    run=run,
                    status=status,
                    limit=remaining,
                )
                for edge in edges:
                    selected_edges.setdefault(edge.id, edge)
                    for node_type, node_id in (
                        (edge.source_type, edge.source_id),
                        (edge.target_type, edge.target_id),
                    ):
                        key = graph_node_key(node_type, node_id)
                        if key not in visited_nodes:
                            visited_nodes.add(key)
                            next_frontier.add((node_type, node_id))
                    if len(selected_edges) >= limit:
                        break
                if len(selected_edges) >= limit:
                    break
            if not next_frontier or len(selected_edges) >= limit:
                break
            frontier = next_frontier

        return self._graph_from_edges(
            scope="neighborhood",
            scope_id=root_key,
            scope_label=root_key,
            edges=list(selected_edges.values()),
            root=(entity_type, entity_id),
        )

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

    def _graph_from_edges(
        self,
        scope: str,
        scope_id: str,
        scope_label: str,
        edges: list[ResearchGraphEdge],
        root: tuple[str, str] | None = None,
    ) -> GraphPayload:
        nodes: dict[str, GraphNodePayload] = {}
        if root is not None:
            root_type, root_id = root
            nodes[graph_node_key(root_type, root_id)] = self._node_payload(root_type, root_id)

        edge_payloads: list[GraphEdgePayload] = []
        for edge in edges:
            source_key = graph_node_key(edge.source_type, edge.source_id)
            target_key = graph_node_key(edge.target_type, edge.target_id)
            nodes.setdefault(source_key, self._node_payload(edge.source_type, edge.source_id))
            nodes.setdefault(target_key, self._node_payload(edge.target_type, edge.target_id))
            nodes[source_key].outgoing_count += 1
            nodes[target_key].incoming_count += 1
            edge_payloads.append(edge_payload(edge))

        ordered_nodes = sorted(
            nodes.values(),
            key=lambda node: (-node.degree, node.entity_type, node.label.lower(), node.entity_id),
        )
        return GraphPayload(
            scope=scope,
            scope_id=scope_id,
            scope_label=scope_label,
            nodes=ordered_nodes,
            edges=edge_payloads,
            summary=_graph_summary(ordered_nodes, edge_payloads),
        )

    def _node_payload(self, entity_type: str, entity_id: str) -> GraphNodePayload:
        entity_type = normalize_graph_entity_type(entity_type)
        entity = self._entity_or_none(entity_type, entity_id)
        label = _entity_label(entity_type, entity_id, entity)
        title = _entity_title(entity)
        project = _entity_project(entity)
        run = _entity_run(entity)
        return GraphNodePayload(
            key=graph_node_key(entity_type, entity_id),
            entity_type=entity_type,
            entity_id=entity_id,
            label=label,
            title=title,
            project_id=project.id if project else None,
            run_id=run.id if run else None,
            metadata=_entity_metadata(entity_type, entity),
        )

    def _entity_or_none(self, entity_type: str, entity_id: str):
        if entity_type not in DATABASE_ENTITY_TYPES:
            return None
        model = _database_entity_model(entity_type)
        return self.session.get(model, entity_id)


def edge_payload(edge: ResearchGraphEdge) -> GraphEdgePayload:
    """Return a JSON-friendly graph edge payload."""
    return GraphEdgePayload(
        id=edge.id,
        source_key=graph_node_key(edge.source_type, edge.source_id),
        source_type=edge.source_type,
        source_id=edge.source_id,
        relationship_type=edge.relationship_type,
        target_key=graph_node_key(edge.target_type, edge.target_id),
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


def graph_node_key(entity_type: str, entity_id: str) -> str:
    """Return the stable UI/export key for a graph node."""
    return f"{normalize_graph_entity_type(entity_type)}:{entity_id}"


def render_mermaid_graph(graph: GraphPayload) -> str:
    """Render a graph payload as a Mermaid flowchart."""
    if not graph.nodes:
        return "flowchart LR\n  empty[\"No graph nodes\"]"

    node_ids = {node.key: f"n{index}" for index, node in enumerate(graph.nodes)}
    lines = ["flowchart LR"]
    for node in graph.nodes:
        label = _escape_mermaid_label(f"{node.entity_type}: {_truncate(node.label, 64)}")
        lines.append(f"  {node_ids[node.key]}[\"{label}\"]")
    for edge in graph.edges:
        if edge.source_key not in node_ids or edge.target_key not in node_ids:
            continue
        label = _escape_mermaid_label(f"{edge.relationship_type} {edge.confidence:.2f}")
        lines.append(f"  {node_ids[edge.source_key]} -- \"{label}\" --> {node_ids[edge.target_key]}")
    return "\n".join(lines)


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


def _database_entity_model(entity_type: str):
    return {
        "document": Document,
        "chunk": DocumentChunk,
        "claim": ExtractedClaim,
        "output": ResearchOutput,
        "run": ResearchRun,
        "project": ResearchProject,
    }[entity_type]


def _entity_label(entity_type: str, entity_id: str, entity) -> str:
    if entity is None:
        return entity_id
    if isinstance(entity, Document):
        return entity.title or entity.source_path
    if isinstance(entity, DocumentChunk):
        return f"Chunk {entity.chunk_index}: {_truncate(entity.content, 72)}"
    if isinstance(entity, ExtractedClaim):
        return _truncate(entity.claim_text, 96)
    if isinstance(entity, ResearchOutput):
        return entity.title
    if isinstance(entity, ResearchRun):
        return _truncate(entity.objective, 96)
    if isinstance(entity, ResearchProject):
        return entity.name
    return entity_id


def _entity_title(entity) -> str | None:
    if entity is None:
        return None
    return getattr(entity, "title", None) or getattr(entity, "name", None)


def _entity_metadata(entity_type: str, entity) -> dict[str, Any]:
    if entity is None:
        return {"literal": entity_type not in DATABASE_ENTITY_TYPES}
    if isinstance(entity, Document):
        return {
            "source_type": entity.source_type,
            "source_path": entity.source_path,
            "doi": entity.doi,
            "year": entity.year,
            "status": entity.status,
        }
    if isinstance(entity, DocumentChunk):
        return {
            "document_id": entity.document_id,
            "chunk_index": entity.chunk_index,
            "token_count": entity.token_count,
        }
    if isinstance(entity, ExtractedClaim):
        return {
            "claim_type": entity.claim_type,
            "confidence": entity.confidence,
            "document_id": entity.document_id,
        }
    if isinstance(entity, ResearchOutput):
        return {
            "output_type": entity.output_type,
            "status": entity.status,
            "format": entity.format,
        }
    if isinstance(entity, ResearchRun):
        return {"status": entity.status, "program_id": entity.program_id}
    if isinstance(entity, ResearchProject):
        return {"slug": entity.slug, "visibility": entity.visibility, "status": entity.status}
    return {}


def _graph_summary(
    nodes: list[GraphNodePayload],
    edges: list[GraphEdgePayload],
) -> dict[str, Any]:
    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes_by_type": _counts(node.entity_type for node in nodes),
        "edges_by_relationship": _counts(edge.relationship_type for edge in edges),
        "top_nodes": [
            {
                "key": node.key,
                "label": node.label,
                "entity_type": node.entity_type,
                "degree": node.degree,
            }
            for node in nodes[:10]
        ],
    }


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _truncate(value: str, max_chars: int) -> str:
    normalized = " ".join(str(value).split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _escape_mermaid_label(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', "'").replace("[", "(").replace("]", ")")
