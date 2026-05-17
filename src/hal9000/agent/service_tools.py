"""HAL service tools exposed to the agent runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hal9000.agent.hf_tools import build_hal_hf_compute_tools, build_hal_hf_research_tools
from hal9000.agent.tools import AgentToolContext, AgentToolResult, AgentToolRouter, AgentToolSpec
from hal9000.db.models import Document, ResearchOutput, ResearchProject, ResearchRun, utc_now
from hal9000.research.acquisition import LiveAcquisitionRunner
from hal9000.research.exports import EXPORT_TARGETS, ResearchOutputExporter
from hal9000.research.graph import ResearchGraphService, edge_payload
from hal9000.research.outputs import ResearchOutputGenerator
from hal9000.research.pipeline import ResearchCorpusPipeline
from hal9000.storage import create_object_store_from_settings
from hal9000.vector import FakeEmbeddingProvider, VectorRepository, create_embedding_provider


def build_hal_service_tools() -> list[AgentToolSpec]:
    """Return HAL service tools for an agent session."""
    return [
        AgentToolSpec(
            name="hal_acquire",
            description="Search, download, and process papers for the current HAL research run.",
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "max_papers": {"type": "integer", "minimum": 1},
                },
            },
            handler=hal_acquire,
            policy_name="acquire",
            requires_approval=True,
        ),
        AgentToolSpec(
            name="hal_process_pdf",
            description="Extract or prepare one PDF/document for HAL retrieval and claims.",
            parameters={
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "pdf_path": {"type": "string"},
                    "run_id": {"type": "string"},
                    "chunk_size": {"type": "integer", "minimum": 1},
                    "chunk_overlap": {"type": "integer", "minimum": 0},
                },
            },
            handler=hal_process_pdf,
            policy_name="process",
            requires_approval=True,
        ),
        AgentToolSpec(
            name="hal_search_memory",
            description="Search HAL's canonical memory across chunks, claims, and outputs.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "targets": {
                        "type": "array",
                        "items": {"enum": ["chunks", "claims", "outputs"]},
                    },
                    "project_slug": {"type": "string"},
                    "run_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1},
                    "min_score": {"type": "number"},
                },
                "required": ["query"],
            },
            handler=hal_search_memory,
            policy_name="semantic_search",
            requires_approval=False,
        ),
        AgentToolSpec(
            name="hal_stage_outputs",
            description="Stage contract outputs and optional run reports for HAL review.",
            parameters={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "include_run_report": {"type": "boolean"},
                    "run_report_only": {"type": "boolean"},
                    "mark_run_staged": {"type": "boolean"},
                    "retrieval_context": {"type": "array", "items": {"type": "object"}},
                },
            },
            handler=hal_stage_outputs,
            policy_name="output",
            requires_approval=True,
        ),
        AgentToolSpec(
            name="hal_export_run",
            description="Export reviewed HAL run outputs to firm-wide artifact targets.",
            parameters={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "targets": {
                        "type": "array",
                        "items": {"enum": list(EXPORT_TARGETS)},
                    },
                    "statuses": {"type": "array", "items": {"type": "string"}},
                    "artifact_prefix": {"type": "string"},
                },
            },
            handler=hal_export_run,
            policy_name="export",
            requires_approval=True,
        ),
        AgentToolSpec(
            name="hal_build_adam_context",
            description="Stage an ADAM-compatible context JSON output from the current run.",
            parameters={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "name": {"type": "string"},
                    "topic_focus": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
            handler=hal_build_adam_context,
            policy_name="adam",
            requires_approval=True,
        ),
        AgentToolSpec(
            name="hal_review_output",
            description="Promote, reject, or request changes for a staged run or output.",
            parameters={
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "output_id": {"type": "string"},
                    "decision": {
                        "enum": ["promote", "promoted", "reject", "rejected", "request_changes", "changes_requested"]
                    },
                    "rationale": {"type": "string"},
                    "reviewer": {"type": "string"},
                },
                "required": ["decision"],
            },
            handler=hal_review_output,
            policy_name="review",
            requires_approval=True,
        ),
        AgentToolSpec(
            name="hal_graph_edge",
            description="Add a typed HAL research graph edge between research entities or concepts.",
            parameters={
                "type": "object",
                "properties": {
                    "source_type": {"type": "string"},
                    "source_id": {"type": "string"},
                    "relationship_type": {"type": "string"},
                    "target_type": {"type": "string"},
                    "target_id": {"type": "string"},
                    "project_slug": {"type": "string"},
                    "run_id": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "evidence": {"type": "object"},
                    "status": {"type": "string"},
                },
                "required": [
                    "source_type",
                    "source_id",
                    "relationship_type",
                    "target_type",
                    "target_id",
                ],
            },
            handler=hal_graph_edge,
            policy_name="graph",
            requires_approval=True,
        ),
        *build_hal_hf_research_tools(),
        *build_hal_hf_compute_tools(),
    ]


def create_hal_service_tool_router() -> AgentToolRouter:
    """Create an AgentToolRouter populated with HAL service tools."""
    return AgentToolRouter(build_hal_service_tools())


def hal_acquire(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Acquire papers for the current HAL research run."""
    store = _require_store(context)
    run = _resolve_run(context, arguments.get("run_id"))
    topic = str(arguments.get("topic") or run.objective).strip()
    if not topic:
        raise ValueError("hal_acquire requires a topic or run objective")

    from hal9000.research.budget import RunBudgetTracker

    budget_limit, _max_downloads = RunBudgetTracker(run).acquisition_limits()
    requested = arguments.get("max_papers")
    max_papers = min(int(requested or budget_limit or 1), budget_limit or int(requested or 1))
    if max_papers <= 0:
        raise ValueError("Acquisition budget is zero")

    runner = context.metadata.get("acquisition_runner")
    if runner is None:
        settings = _settings(context)
        if settings is None:
            raise ValueError("hal_acquire requires context.metadata['acquisition_runner'] or settings")
        runner = LiveAcquisitionRunner(settings=settings, db_session=store.session)

    result = runner.acquire(topic=topic, max_papers=max_papers)
    payload = _to_dict(result)
    store.append_run_event(
        run,
        event_type="agent.acquire.completed",
        message=f"Agent acquisition completed for topic: {topic}",
        actor=context.actor,
        payload=payload,
    )
    return AgentToolResult.ok(
        f"Acquired {payload.get('papers_processed', 0)} processed paper(s) for '{topic}'.",
        payload=payload,
    )


def hal_process_pdf(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Process an existing HAL document or local PDF path into run corpus records."""
    store = _require_store(context)
    run = _resolve_run(context, arguments.get("run_id"))
    document = _resolve_document(context, arguments)
    chunk_size = int(arguments.get("chunk_size") or _settings_value(context, "processing.chunk_size", 50000))
    chunk_overlap = int(arguments.get("chunk_overlap") or 1000)

    pipeline = ResearchCorpusPipeline(
        store,
        embedding_provider=_embedding_provider(context),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    result = pipeline.process_document(run, document)
    payload = {
        "document_ids": result.document_ids,
        "chunk_ids": result.chunk_ids,
        "embedding_ids": result.embedding_ids,
        "claim_ids": result.claim_ids,
        "document_id": document.id,
    }
    return AgentToolResult.ok(
        (
            f"Processed document {document.id}: "
            f"{len(result.chunk_ids)} chunk(s), {len(result.embedding_ids)} embedding(s), "
            f"{len(result.claim_ids)} claim(s)."
        ),
        payload=payload,
    )


def hal_search_memory(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Search HAL memory across chunks, claims, and outputs."""
    store = _require_store(context)
    query = str(arguments.get("query") or "").strip()
    if not query:
        raise ValueError("hal_search_memory requires query")

    targets = set(arguments.get("targets") or ["claims", "outputs"])
    limit = int(arguments.get("limit") or _settings_value(context, "vector.retrieval_limit", 5))
    min_score = arguments.get("min_score")
    project = _resolve_project(context, arguments.get("project_slug"))
    run = _resolve_optional_run(context, arguments.get("run_id"))
    if project is None and run is not None:
        project = run.project
    if project is None and context.run is not None:
        project = context.run.project

    repository = VectorRepository(store.session)
    provider = _embedding_provider(context)
    results: list[dict[str, Any]] = []
    if "chunks" in targets:
        results.extend(
            result.as_context_item()
            for result in repository.search_chunks(
                query,
                provider,
                limit=limit,
                project_id=project.id if project else None,
                run_id=run.id if run else None,
                min_score=min_score,
            )
        )
    semantic_targets = targets & {"claims", "outputs"}
    if semantic_targets:
        results.extend(
            result.as_context_item()
            for result in repository.search_memory(
                query,
                provider,
                targets=semantic_targets,
                limit=limit,
                project_id=project.id if project else None,
                run_id=run.id if run else None,
                min_score=min_score,
            )
        )
    results.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    results = results[:limit]
    return AgentToolResult.ok(
        f"Found {len(results)} HAL memory result(s) for '{query}'.",
        payload={"query": query, "result_count": len(results), "results": results},
    )


def hal_stage_outputs(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Stage outputs for a HAL research run."""
    store = _require_store(context)
    run = _resolve_run(context, arguments.get("run_id"))
    generator = ResearchOutputGenerator(store)
    outputs = []
    if not arguments.get("run_report_only"):
        if run.program is None:
            raise ValueError("Run must have a program to stage contract outputs")
        staged = generator.stage_contract_outputs(
            run,
            created_by=context.actor,
            mark_run_staged=bool(arguments.get("mark_run_staged", True)),
            retrieval_context=list(arguments.get("retrieval_context") or []),
        )
        outputs.extend(staged.outputs)
    if arguments.get("include_run_report") or arguments.get("run_report_only"):
        outputs.append(generator.stage_run_report(run, created_by=context.actor))
    return AgentToolResult.ok(
        f"Staged {len(outputs)} output(s) for run {run.id}.",
        payload={
            "run_id": run.id,
            "output_ids": [output.id for output in outputs],
            "output_types": [output.output_type for output in outputs],
        },
    )


def hal_export_run(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Export a HAL run to object-store artifacts."""
    store = _require_store(context)
    run = _resolve_run(context, arguments.get("run_id"))
    exporter = ResearchOutputExporter(
        session=store.session,
        object_store=_object_store(context),
        artifact_prefix=str(arguments.get("artifact_prefix") or "exports"),
    )
    results = exporter.export_run(
        run,
        targets=arguments.get("targets") or EXPORT_TARGETS,
        statuses=arguments.get("statuses") or ("promoted",),
    )
    payload = {
        "run_id": run.id,
        "exports": [
            {
                "target": result.target,
                "artifact_uri": result.artifact_uri,
                "artifact_count": result.artifact_count,
                "output_count": result.output_count,
            }
            for result in results
        ],
    }
    store.append_run_event(
        run,
        event_type="outputs.exported",
        message=f"Agent exported run outputs to {len(results)} target(s).",
        actor=context.actor,
        payload=payload,
    )
    return AgentToolResult.ok(
        f"Exported run {run.id} to {len(results)} target(s).",
        payload=payload,
    )


def hal_build_adam_context(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Stage an ADAM context output for a run."""
    store = _require_store(context)
    run = _resolve_run(context, arguments.get("run_id"))
    payload = _adam_context_payload(run, arguments, context)
    output = store.stage_output(
        title=str(arguments.get("name") or f"ADAM Context: {run.objective[:80]}"),
        output_type="adam_context",
        project=run.project,
        run=run,
        content=json.dumps(payload, indent=2, sort_keys=True),
        source={"run_id": run.id, "generator": "hal_build_adam_context"},
        created_by=context.actor,
        format="json",
    )
    store.append_run_event(
        run,
        event_type="adam.context.staged",
        message="ADAM context staged by agent.",
        actor=context.actor,
        payload={"output_id": output.id, "context_id": payload["context_id"]},
    )
    return AgentToolResult.ok(
        f"Staged ADAM context output {output.id}.",
        payload={"output_id": output.id, "context": payload},
    )


def hal_review_output(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Review a staged run or individual output."""
    store = _require_store(context)
    decision = _normalize_review_decision(str(arguments.get("decision") or ""))
    reviewer = str(arguments.get("reviewer") or context.actor)
    rationale = arguments.get("rationale")

    if output_id := arguments.get("output_id"):
        output = store.session.get(ResearchOutput, str(output_id))
        if output is None:
            raise ValueError(f"Research output not found: {output_id}")
        review = store.record_review_decision(
            output,
            decision=decision,
            reviewer=reviewer,
            rationale=rationale,
        )
        if output.run is not None:
            store.append_run_event(
                output.run,
                event_type="output.reviewed",
                message=f"Output reviewed: {decision}",
                actor=reviewer,
                payload={
                    "output_id": output.id,
                    "decision": decision,
                    "review_decision_id": review.id,
                    "rationale": rationale,
                },
            )
        return AgentToolResult.ok(
            f"Reviewed output {output.id}: {decision}.",
            payload={"output_id": output.id, "decision": decision, "review_decision_id": review.id},
        )

    run = _resolve_run(context, arguments.get("run_id"))
    result = store.review_run_outputs(
        run,
        decision=decision,
        reviewer=reviewer,
        rationale=rationale,
    )
    return AgentToolResult.ok(
        f"Reviewed run {run.id}: {decision}.",
        payload={
            "run_id": run.id,
            "decision": decision,
            "review_decision_ids": [review.id for review in result.decisions],
            "event_id": result.event.id,
        },
    )


def hal_graph_edge(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Add a typed graph edge."""
    store = _require_store(context)
    run = _resolve_optional_run(context, arguments.get("run_id"))
    project = _resolve_project(context, arguments.get("project_slug"))
    if run is None:
        run = context.run
    edge = ResearchGraphService(store).add_edge(
        source_type=str(arguments["source_type"]),
        source_id=str(arguments["source_id"]),
        relationship_type=str(arguments["relationship_type"]),
        target_type=str(arguments["target_type"]),
        target_id=str(arguments["target_id"]),
        project=project,
        run=run,
        confidence=float(arguments.get("confidence", 1.0)),
        evidence=arguments.get("evidence"),
        created_by=context.actor,
        status=str(arguments.get("status") or "active"),
    )
    payload = edge_payload(edge).to_dict()
    return AgentToolResult.ok(
        f"Added graph edge {edge.id}.",
        payload=payload,
    )


def _require_store(context: AgentToolContext):
    if context.store is None:
        raise ValueError("HAL service tools require AgentToolContext.store")
    return context.store


def _resolve_run(context: AgentToolContext, run_id: Any | None = None) -> ResearchRun:
    run = _resolve_optional_run(context, run_id)
    if run is None:
        raise ValueError("HAL service tool requires a research run")
    return run


def _resolve_optional_run(context: AgentToolContext, run_id: Any | None = None) -> ResearchRun | None:
    if run_id:
        run = _require_store(context).get_run(str(run_id))
        if run is None:
            raise ValueError(f"Research run not found: {run_id}")
        return run
    return context.run


def _resolve_project(context: AgentToolContext, project_slug: Any | None) -> ResearchProject | None:
    if not project_slug:
        return None
    project = _require_store(context).get_project_by_slug(str(project_slug))
    if project is None:
        raise ValueError(f"Research project not found: {project_slug}")
    return project


def _resolve_document(context: AgentToolContext, arguments: dict[str, Any]) -> Document:
    store = _require_store(context)
    if document_id := arguments.get("document_id"):
        document = store.session.get(Document, str(document_id))
        if document is None:
            raise ValueError(f"Document not found: {document_id}")
        return document
    if not arguments.get("pdf_path"):
        raise ValueError("hal_process_pdf requires document_id or pdf_path")

    from hal9000.ingest import PDFProcessor

    content = PDFProcessor().extract_text(Path(str(arguments["pdf_path"])))
    existing = store.session.query(Document).filter_by(file_hash=content.file_hash).one_or_none()
    if existing is not None:
        return existing
    document = Document(
        source_path=str(content.file_path),
        source_type="local",
        file_hash=content.file_hash,
        title=str(content.metadata.get("Title") or content.file_path.stem),
        full_text=content.full_text,
        page_count=content.page_count,
        status="completed",
        processed_at=utc_now(),
    )
    store.session.add(document)
    store.session.flush()
    return document


def _settings(context: AgentToolContext):
    return context.metadata.get("settings")


def _settings_value(context: AgentToolContext, dotted_key: str, default: Any) -> Any:
    current = _settings(context)
    if current is None:
        return default
    for part in dotted_key.split("."):
        current = getattr(current, part, None)
        if current is None:
            return default
    return current


def _embedding_provider(context: AgentToolContext):
    if provider := context.metadata.get("embedding_provider"):
        return provider
    settings = _settings(context)
    if settings is None:
        return FakeEmbeddingProvider(dimension=8)
    return create_embedding_provider(
        settings.vector.embedding_provider,
        dimension=settings.vector.embedding_dimension,
        model=settings.vector.embedding_model,
    )


def _object_store(context: AgentToolContext):
    if object_store := context.metadata.get("object_store"):
        return object_store
    settings = _settings(context)
    if settings is None:
        raise ValueError("hal_export_run requires context.metadata['object_store'] or settings")
    return create_object_store_from_settings(settings)


def _adam_context_payload(
    run: ResearchRun,
    arguments: dict[str, Any],
    context: AgentToolContext,
) -> dict[str, Any]:
    claims = list(run.claims)
    documents = {claim.document for claim in claims if claim.document is not None}
    key_findings = [claim.claim_text for claim in claims[:20]]
    methodologies = [
        claim.evidence_text
        for claim in claims
        if claim.claim_type == "method" and claim.evidence_text
    ][:10]
    return {
        "output_type": "adam_context",
        "context_id": str(arguments.get("context_id") or run.id),
        "name": str(arguments.get("name") or f"ADAM Context: {run.objective[:80]}"),
        "description": str(
            arguments.get("description")
            or f"HAL research context for {arguments.get('topic_focus') or run.objective}."
        ),
        "research_domain": _settings_value(context, "adam.default_domain", "materials_science"),
        "topic_focus": str(arguments.get("topic_focus") or run.objective),
        "literature_summary": {
            "papers_analyzed": len(documents),
            "key_findings": key_findings,
            "methodologies": methodologies,
            "gaps_identified": [],
            "open_questions": [],
        },
        "experiment_suggestions": [],
        "knowledge_graph": {"nodes": [], "edges": []},
        "materials_of_interest": [],
        "recommended_characterization": [],
        "source_documents": [document.title or document.id for document in documents],
        "metadata": {
            "run_id": run.id,
            "project_id": run.project_id,
            "created_by": context.actor,
            "generator": "hal_build_adam_context",
            "version": "1.0",
        },
    }


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
        raise ValueError("decision must be promote, reject, or request_changes")
    return aliases[normalized]


def _to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return dict(value.to_dict())
    if isinstance(value, dict):
        return value
    raise TypeError(f"Cannot convert result to dict: {type(value).__name__}")
