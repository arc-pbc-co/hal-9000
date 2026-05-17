"""Firm-wide export targets for promoted research outputs."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from hal9000.db.models import ResearchOutput, ResearchProject, ResearchRun
from hal9000.research.graph import ResearchGraphService, render_mermaid_graph
from hal9000.research.media import (
    dedupe_media_references,
    extract_media_references_from_text,
    normalize_media_reference,
)
from hal9000.storage import ObjectStore

ExportTarget = Literal["adam", "obsidian", "markdown", "json", "dashboard", "graph"]

EXPORT_TARGETS: tuple[ExportTarget, ...] = (
    "adam",
    "obsidian",
    "markdown",
    "json",
    "dashboard",
    "graph",
)


@dataclass(frozen=True)
class ExportResult:
    """Result metadata for one export target."""

    target: ExportTarget
    artifact_uri: str
    artifact_count: int
    output_count: int
    manifest: dict[str, Any]


class ResearchOutputExporter:
    """Export canonical research outputs into firm-wide sharing formats."""

    def __init__(
        self,
        session: Session,
        object_store: ObjectStore,
        artifact_prefix: str = "exports",
    ):
        """Initialize the exporter."""
        self.session = session
        self.object_store = object_store
        self.artifact_prefix = _normalize_prefix(artifact_prefix)

    def export_run(
        self,
        run: ResearchRun,
        targets: Iterable[ExportTarget] = EXPORT_TARGETS,
        statuses: Iterable[str] = ("promoted",),
    ) -> list[ExportResult]:
        """Export outputs attached to a run."""
        outputs = self._outputs_for_run(run, statuses)
        return [
            self._export(
                target=target,
                scope="run",
                scope_id=run.id,
                scope_label=run.objective,
                project=run.project,
                run=run,
                outputs=outputs,
            )
            for target in targets
        ]

    def export_project(
        self,
        project: ResearchProject,
        targets: Iterable[ExportTarget] = EXPORT_TARGETS,
        statuses: Iterable[str] = ("promoted",),
    ) -> list[ExportResult]:
        """Export outputs attached to a project."""
        outputs = self._outputs_for_project(project, statuses)
        return [
            self._export(
                target=target,
                scope="project",
                scope_id=project.slug,
                scope_label=project.name,
                project=project,
                run=None,
                outputs=outputs,
            )
            for target in targets
        ]

    def _outputs_for_run(
        self,
        run: ResearchRun,
        statuses: Iterable[str],
    ) -> list[ResearchOutput]:
        query = (
            self.session.query(ResearchOutput)
            .filter(ResearchOutput.run_id == run.id)
            .order_by(ResearchOutput.created_at, ResearchOutput.id)
        )
        normalized_statuses = _normalize_statuses(statuses)
        if normalized_statuses:
            query = query.filter(ResearchOutput.status.in_(normalized_statuses))
        return query.all()

    def _outputs_for_project(
        self,
        project: ResearchProject,
        statuses: Iterable[str],
    ) -> list[ResearchOutput]:
        query = (
            self.session.query(ResearchOutput)
            .filter(ResearchOutput.project_id == project.id)
            .order_by(ResearchOutput.created_at, ResearchOutput.id)
        )
        normalized_statuses = _normalize_statuses(statuses)
        if normalized_statuses:
            query = query.filter(ResearchOutput.status.in_(normalized_statuses))
        return query.all()

    def _export(
        self,
        target: ExportTarget,
        scope: str,
        scope_id: str,
        scope_label: str,
        project: ResearchProject | None,
        run: ResearchRun | None,
        outputs: list[ResearchOutput],
    ) -> ExportResult:
        if target not in EXPORT_TARGETS:
            supported = ", ".join(EXPORT_TARGETS)
            raise ValueError(f"Unsupported export target: {target}. Supported targets: {supported}")

        key_prefix = self._key_prefix(scope, scope_id, target)
        manifest = self._base_manifest(
            target=target,
            scope=scope,
            scope_id=scope_id,
            scope_label=scope_label,
            project=project,
            run=run,
            outputs=outputs,
        )

        if target == "markdown":
            return self._export_markdown(key_prefix, manifest, outputs)
        if target == "json":
            return self._export_json(key_prefix, manifest, outputs)
        if target == "dashboard":
            return self._export_dashboard(key_prefix, manifest, outputs)
        if target == "graph":
            return self._export_graph(key_prefix, manifest, project=project, run=run)
        if target == "adam":
            return self._export_adam(key_prefix, manifest, outputs)
        return self._export_obsidian(key_prefix, manifest, outputs)

    def _export_markdown(
        self,
        key_prefix: str,
        manifest: dict[str, Any],
        outputs: list[ResearchOutput],
    ) -> ExportResult:
        lines = [
            f"# HAL Research Export: {manifest['scope_label']}",
            "",
            f"- Export target: `{manifest['target']}`",
            f"- Scope: `{manifest['scope']}`",
            f"- Scope ID: `{manifest['scope_id']}`",
            f"- Output count: `{len(outputs)}`",
            f"- Created at: `{manifest['created_at']}`",
            "",
        ]
        lines.extend(_media_register_markdown(manifest.get("figures_tables", [])))
        for output in outputs:
            lines.extend(self._markdown_section(output))

        stored = self.object_store.put_bytes(
            f"{key_prefix}/bundle.md",
            "\n".join(lines).encode("utf-8"),
            content_type="text/markdown",
        )
        manifest["artifacts"] = [{"kind": "markdown_bundle", "uri": stored.uri, "key": stored.key}]
        manifest_stored = self._write_manifest(key_prefix, manifest)
        return ExportResult(
            target="markdown",
            artifact_uri=manifest_stored.uri,
            artifact_count=2,
            output_count=len(outputs),
            manifest=manifest,
        )

    def _export_json(
        self,
        key_prefix: str,
        manifest: dict[str, Any],
        outputs: list[ResearchOutput],
    ) -> ExportResult:
        payload = {**manifest, "outputs": [self._output_payload(output) for output in outputs]}
        stored = self._write_json(f"{key_prefix}/outputs.json", payload)
        manifest["artifacts"] = [{"kind": "json_outputs", "uri": stored.uri, "key": stored.key}]
        manifest_stored = self._write_manifest(key_prefix, manifest)
        return ExportResult(
            target="json",
            artifact_uri=manifest_stored.uri,
            artifact_count=2,
            output_count=len(outputs),
            manifest=manifest,
        )

    def _export_dashboard(
        self,
        key_prefix: str,
        manifest: dict[str, Any],
        outputs: list[ResearchOutput],
    ) -> ExportResult:
        payload = {
            **manifest,
            "rows": [self._dashboard_row(output) for output in outputs],
            "summary": self._dashboard_summary(outputs),
        }
        stored = self._write_json(f"{key_prefix}/dashboard.json", payload)
        manifest["artifacts"] = [{"kind": "dashboard_json", "uri": stored.uri, "key": stored.key}]
        manifest_stored = self._write_manifest(key_prefix, manifest)
        return ExportResult(
            target="dashboard",
            artifact_uri=manifest_stored.uri,
            artifact_count=2,
            output_count=len(outputs),
            manifest=manifest,
        )

    def _export_adam(
        self,
        key_prefix: str,
        manifest: dict[str, Any],
        outputs: list[ResearchOutput],
    ) -> ExportResult:
        contexts = []
        for output in outputs:
            if output.output_type != "adam_context":
                continue
            payload = self._json_content(output)
            self._validate_adam_context(output, payload)
            contexts.append(
                {
                    "output_id": output.id,
                    "title": output.title,
                    "status": output.status,
                    "context": payload,
                }
            )

        payload = {**manifest, "adam_contexts": contexts}
        stored = self._write_json(f"{key_prefix}/adam-contexts.json", payload)
        manifest["artifacts"] = [{"kind": "adam_contexts", "uri": stored.uri, "key": stored.key}]
        manifest["adam_context_count"] = len(contexts)
        manifest_stored = self._write_manifest(key_prefix, manifest)
        return ExportResult(
            target="adam",
            artifact_uri=manifest_stored.uri,
            artifact_count=2,
            output_count=len(outputs),
            manifest=manifest,
        )

    def _export_graph(
        self,
        key_prefix: str,
        manifest: dict[str, Any],
        project: ResearchProject | None,
        run: ResearchRun | None,
    ) -> ExportResult:
        from hal9000.db.store import ResearchStore

        store = ResearchStore(self.session)
        service = ResearchGraphService(store)
        if run is not None:
            graph = service.run_graph(run)
        elif project is not None:
            graph = service.project_graph(project)
        else:
            graph = service._graph_from_edges(
                scope=manifest["scope"],
                scope_id=manifest["scope_id"],
                scope_label=manifest["scope_label"],
                edges=[],
            )

        graph_payload = graph.to_dict()
        graph_json = self._write_json(f"{key_prefix}/graph.json", graph_payload)
        graph_mermaid = self.object_store.put_bytes(
            f"{key_prefix}/graph.mmd",
            render_mermaid_graph(graph).encode("utf-8"),
            content_type="text/plain",
        )
        manifest["graph_summary"] = graph_payload["summary"]
        manifest["artifacts"] = [
            {"kind": "graph_json", "uri": graph_json.uri, "key": graph_json.key},
            {"kind": "graph_mermaid", "uri": graph_mermaid.uri, "key": graph_mermaid.key},
        ]
        manifest_stored = self._write_manifest(key_prefix, manifest)
        return ExportResult(
            target="graph",
            artifact_uri=manifest_stored.uri,
            artifact_count=3,
            output_count=manifest["output_count"],
            manifest=manifest,
        )

    def _export_obsidian(
        self,
        key_prefix: str,
        manifest: dict[str, Any],
        outputs: list[ResearchOutput],
    ) -> ExportResult:
        artifacts = []
        index_lines = [
            f"# {manifest['scope_label']}",
            "",
            f"- Scope: `{manifest['scope']}`",
            f"- Scope ID: `{manifest['scope_id']}`",
            f"- Exported outputs: `{len(outputs)}`",
            "",
            "## Outputs",
            "",
        ]
        for output in outputs:
            filename = f"{_slugify(output.title)}-{output.id[:8]}.md"
            note_key = f"{key_prefix}/notes/{filename}"
            note = self._obsidian_note(output, manifest)
            stored = self.object_store.put_bytes(
                note_key,
                note.encode("utf-8"),
                content_type="text/markdown",
            )
            artifacts.append({"kind": "obsidian_note", "uri": stored.uri, "key": stored.key})
            index_lines.append(f"- [[{filename.removesuffix('.md')}]] - {output.output_type}")

        index_stored = self.object_store.put_bytes(
            f"{key_prefix}/index.md",
            "\n".join(index_lines).encode("utf-8"),
            content_type="text/markdown",
        )
        artifacts.insert(0, {"kind": "obsidian_index", "uri": index_stored.uri, "key": index_stored.key})
        manifest["artifacts"] = artifacts
        manifest_stored = self._write_manifest(key_prefix, manifest)
        return ExportResult(
            target="obsidian",
            artifact_uri=manifest_stored.uri,
            artifact_count=len(artifacts) + 1,
            output_count=len(outputs),
            manifest=manifest,
        )

    def _base_manifest(
        self,
        target: ExportTarget,
        scope: str,
        scope_id: str,
        scope_label: str,
        project: ResearchProject | None,
        run: ResearchRun | None,
        outputs: list[ResearchOutput],
    ) -> dict[str, Any]:
        media_refs = self._figure_table_refs(outputs)
        return {
            "target": target,
            "schema_version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scope": scope,
            "scope_id": scope_id,
            "scope_label": scope_label,
            "project": self._project_payload(project),
            "run": self._run_payload(run),
            "output_count": len(outputs),
            "output_ids": [output.id for output in outputs],
            "output_statuses": sorted({output.status for output in outputs}),
            "output_types": sorted({output.output_type for output in outputs}),
            "figures_tables": media_refs,
            "figure_table_count": len(media_refs),
        }

    def _key_prefix(self, scope: str, scope_id: str, target: ExportTarget) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_scope_id = _slugify(scope_id)
        return f"{self.artifact_prefix}/{scope}s/{safe_scope_id}/{timestamp}/{target}"

    def _write_manifest(self, key_prefix: str, manifest: dict[str, Any]):
        return self._write_json(f"{key_prefix}/manifest.json", manifest)

    def _write_json(self, key: str, payload: dict[str, Any]):
        return self.object_store.put_bytes(
            key,
            json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )

    def _output_payload(self, output: ResearchOutput) -> dict[str, Any]:
        return {
            "id": output.id,
            "project_id": output.project_id,
            "run_id": output.run_id,
            "output_type": output.output_type,
            "title": output.title,
            "status": output.status,
            "format": output.format,
            "content": output.content,
            "artifact_uri": output.artifact_uri,
            "source": self._json_or_none(output.source_json),
            "figures_tables": self._figure_table_refs_for_output(output),
            "created_by": output.created_by,
            "created_at": _iso(output.created_at),
            "updated_at": _iso(output.updated_at),
        }

    def _dashboard_row(self, output: ResearchOutput) -> dict[str, Any]:
        return {
            "output_id": output.id,
            "project_id": output.project_id,
            "project_slug": output.project.slug if output.project else None,
            "run_id": output.run_id,
            "run_status": output.run.status if output.run else None,
            "output_type": output.output_type,
            "title": output.title,
            "status": output.status,
            "format": output.format,
            "artifact_uri": output.artifact_uri,
            "created_by": output.created_by,
            "created_at": _iso(output.created_at),
            "content_length": len(output.content or ""),
            "figure_table_count": len(self._figure_table_refs_for_output(output)),
        }

    def _dashboard_summary(self, outputs: list[ResearchOutput]) -> dict[str, Any]:
        return {
            "outputs_by_status": _counts(output.status for output in outputs),
            "outputs_by_type": _counts(output.output_type for output in outputs),
            "outputs_by_format": _counts(output.format for output in outputs),
            "figure_table_count": len(self._figure_table_refs(outputs)),
        }

    def _markdown_section(self, output: ResearchOutput) -> list[str]:
        lines = [
            f"## {output.title}",
            "",
            f"- Output ID: `{output.id}`",
            f"- Type: `{output.output_type}`",
            f"- Status: `{output.status}`",
            f"- Format: `{output.format}`",
            "",
        ]
        if output.format == "json":
            lines.extend(["```json", _pretty_json_text(output.content or "{}"), "```", ""])
        else:
            lines.extend([output.content or "", ""])
        lines.extend(_media_register_markdown(self._figure_table_refs_for_output(output), heading="Figures/Tables"))
        return lines

    def _obsidian_note(self, output: ResearchOutput, manifest: dict[str, Any]) -> str:
        media_refs = self._figure_table_refs_for_output(output)
        front_matter = {
            "hal_output_id": output.id,
            "hal_output_type": output.output_type,
            "hal_output_status": output.status,
            "hal_run_id": output.run_id,
            "hal_project_id": output.project_id,
            "hal_export_target": manifest["target"],
            "hal_exported_at": manifest["created_at"],
            "hal_figure_table_count": len(media_refs),
        }
        lines = ["---"]
        for key, value in front_matter.items():
            lines.append(f"{key}: {json.dumps(value)}")
        lines.extend(["---", "", f"# {output.title}", ""])
        lines.extend(_media_register_markdown(media_refs, heading="Figures/Tables"))
        lines.extend(self._markdown_section(output)[1:])
        return "\n".join(lines)

    def _figure_table_refs(self, outputs: list[ResearchOutput]) -> list[dict[str, Any]]:
        """Return deduplicated figure/table refs across outputs."""
        refs = []
        for output in outputs:
            refs.extend(self._figure_table_refs_for_output(output))
        return dedupe_media_references(refs)

    def _figure_table_refs_for_output(self, output: ResearchOutput) -> list[dict[str, Any]]:
        """Extract figure/table refs from output source metadata and content."""
        refs = []
        source = self._json_or_none(output.source_json) or {}
        refs.extend(_normalize_media_list(source.get("figures_tables"), output.id))
        if output.format == "json" and output.content:
            try:
                payload = json.loads(output.content)
            except json.JSONDecodeError:
                payload = {}
            if isinstance(payload, dict):
                refs.extend(_normalize_media_list(payload.get("figures_tables"), output.id))
        elif output.content:
            for item in extract_media_references_from_text(output.content):
                item["output_id"] = output.id
                refs.append(item)
        return dedupe_media_references(refs)

    def _json_content(self, output: ResearchOutput) -> dict[str, Any]:
        if output.content is None:
            raise ValueError(f"Output has no JSON content: {output.id}")
        try:
            payload = json.loads(output.content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Output {output.id} is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Output {output.id} JSON content must be an object")
        return payload

    def _validate_adam_context(self, output: ResearchOutput, payload: dict[str, Any]) -> None:
        required = {
            "output_type",
            "context_id",
            "name",
            "description",
            "literature_summary",
            "metadata",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(
                f"ADAM context output {output.id} is missing required key(s): {', '.join(missing)}"
            )
        if payload.get("output_type") != "adam_context":
            raise ValueError(f"ADAM context output {output.id} has unexpected output_type")

    def _project_payload(self, project: ResearchProject | None) -> dict[str, Any] | None:
        if project is None:
            return None
        return {
            "id": project.id,
            "slug": project.slug,
            "name": project.name,
            "owner": project.owner,
            "visibility": project.visibility,
        }

    def _run_payload(self, run: ResearchRun | None) -> dict[str, Any] | None:
        if run is None:
            return None
        return {
            "id": run.id,
            "status": run.status,
            "objective": run.objective,
            "program_id": run.program_id,
            "initiated_by": run.initiated_by,
            "created_at": _iso(run.created_at),
            "completed_at": _iso(run.completed_at),
        }

    def _json_or_none(self, raw: str | None) -> Any:
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def _normalize_statuses(statuses: Iterable[str]) -> list[str]:
    normalized = [status.strip().lower() for status in statuses if status.strip()]
    if any(status == "all" for status in normalized):
        return []
    return normalized


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.replace("\\", "/").strip("/")
    if not normalized:
        raise ValueError("Export artifact prefix must not be empty")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"Invalid export artifact prefix: {prefix}")
    return "/".join(parts)


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return normalized[:96] or "untitled"


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _pretty_json_text(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw), indent=2, sort_keys=True)
    except json.JSONDecodeError:
        return raw


def _normalize_media_list(raw: Any, output_id: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    refs = []
    for item in raw:
        normalized = normalize_media_reference(item)
        if normalized:
            normalized["output_id"] = output_id
            refs.append(normalized)
    return refs


def _media_register_markdown(
    refs: list[dict[str, Any]],
    *,
    heading: str = "Figure/Table Register",
) -> list[str]:
    if not refs:
        return []
    lines = [f"## {heading}", ""]
    for ref in refs:
        locator = ref.get("locator") or (f"p. {ref['page']}" if ref.get("page") else None)
        locator_text = f" ({locator})" if locator else ""
        marker = f" {ref['citation_marker']}" if ref.get("citation_marker") else ""
        lines.append(
            f"- {str(ref.get('kind', 'media')).title()}: {ref.get('label')}"
            f"{marker}{locator_text} - {ref.get('caption') or ref.get('description') or ''}"
        )
    lines.append("")
    return lines
