"""Output generators for staged research artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hal9000.db.models import ResearchOutput, ResearchRun

if TYPE_CHECKING:
    from hal9000.db.store import ResearchStore


@dataclass
class StagedOutputs:
    """Outputs staged for a research run."""

    outputs: list[ResearchOutput]

    @property
    def output_ids(self) -> list[str]:
        """Return staged output ids."""
        return [output.id for output in self.outputs]


@dataclass(frozen=True)
class SourceCitation:
    """A stable citation marker used in rendered outputs."""

    marker: str
    document_id: str | None
    title: str
    citation: str
    source_url: str | None = None
    locator: str | None = None


class ResearchOutputGenerator:
    """Generate first-pass staged outputs from a research run contract."""

    def __init__(self, store: ResearchStore):
        """Initialize with the shared research store."""
        self.store = store

    def stage_contract_outputs(
        self,
        run: ResearchRun,
        created_by: str | None = "hal",
        mark_run_staged: bool = True,
        retrieval_context: list[dict[str, Any]] | None = None,
    ) -> StagedOutputs:
        """Stage outputs required by the run's program contract."""
        if run.program is None:
            raise ValueError("Run must be attached to a research program to stage contract outputs")

        spec = json.loads(run.program.spec_json)
        output_contract = spec.get("output_contract", {})
        required_outputs = output_contract.get("required_outputs", [])
        output_format = output_contract.get("format", "markdown")
        citation_policy = output_contract.get("citation_policy")
        retrieval_context = retrieval_context or []

        staged = []
        for output_type in required_outputs:
            content, rendered_format = self._render_output_content(
                run=run,
                output_type=output_type,
                output_format=output_format,
                citation_policy=citation_policy,
                retrieval_context=retrieval_context,
            )
            staged.append(
                self.store.stage_output(
                    title=self._title_for_output(run, output_type),
                    output_type=output_type,
                    project=run.project,
                    run=run,
                    content=content,
                    source={
                        "run_id": run.id,
                        "program_id": run.program.id,
                        "program_name": run.program.name,
                        "generator": "ResearchOutputGenerator.stage_contract_outputs",
                        "retrieval_context": retrieval_context,
                    },
                    created_by=created_by,
                    format=rendered_format,
                )
            )

        self.store.append_run_event(
            run,
            event_type="outputs.staged",
            message=f"Staged {len(staged)} output(s) from program contract.",
            actor=created_by,
            payload={
                "output_ids": [output.id for output in staged],
                "output_types": [output.output_type for output in staged],
            },
        )
        if mark_run_staged:
            self.store.update_run_status(
                run,
                status="staged",
                message="Program contract outputs staged for review.",
                actor=created_by,
                payload={"output_count": len(staged)},
            )
        return StagedOutputs(outputs=staged)

    def stage_run_report(
        self,
        run: ResearchRun,
        created_by: str | None = "hal",
    ) -> ResearchOutput:
        """Stage a Markdown run report from current run metadata and event log."""
        events = self.store.list_run_events(run)
        lines = [
            f"# Run Report: {run.objective}",
            "",
            f"- Run ID: `{run.id}`",
            f"- Status: `{run.status}`",
            f"- Project: `{run.project.slug if run.project else 'none'}`",
            f"- Program: `{run.program.name if run.program else 'none'}`",
            "",
            "## Event Log",
            "",
        ]
        if not events:
            lines.append("No events recorded.")
        else:
            lines.extend(["| # | Type | Actor | Message |", "|---:|------|-------|---------|"])
            for event in events:
                lines.append(
                    f"| {event.sequence} | `{event.event_type}` | "
                    f"{event.actor or ''} | {event.message or ''} |"
                )

        output = self.store.stage_output(
            title=f"Run Report: {run.objective[:80]}",
            output_type="run_report",
            project=run.project,
            run=run,
            content="\n".join(lines),
            source={"run_id": run.id, "generator": "ResearchOutputGenerator.stage_run_report"},
            created_by=created_by,
            format="markdown",
        )
        self.store.append_run_event(
            run,
            event_type="output.run_report.staged",
            message="Run report staged.",
            actor=created_by,
            payload={"output_id": output.id},
        )
        return output

    def _render_output_content(
        self,
        run: ResearchRun,
        output_type: str,
        output_format: str,
        citation_policy: str | None,
        retrieval_context: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Render concrete first-pass content for a required output."""
        if output_type == "research_brief":
            return self._render_research_brief(run, citation_policy, retrieval_context), "markdown"
        if output_type == "evidence_table":
            return self._render_evidence_table(run), "markdown"
        if output_type == "open_questions":
            return self._render_open_questions(run, citation_policy, retrieval_context), "markdown"
        if output_type == "adam_context":
            return self._render_adam_context(run, citation_policy, retrieval_context), "json"
        if output_type == "hypothesis_cards":
            return self._render_hypothesis_cards(run, citation_policy, retrieval_context), "json"
        if output_type == "experiment_suggestions":
            return self._render_experiment_suggestions(
                run,
                citation_policy,
                retrieval_context,
            ), "json"

        return self._render_output_scaffold(run, output_type, output_format, citation_policy)

    def _render_output_scaffold(
        self,
        run: ResearchRun,
        output_type: str,
        output_format: str,
        citation_policy: str | None,
    ) -> tuple[str, str]:
        """Render a fallback scaffold for an unknown required output."""
        payload: dict[str, Any] = {
            "output_type": output_type,
            "run_id": run.id,
            "program_id": run.program.id if run.program else None,
            "status": "staged",
            "citation_policy": citation_policy,
            "notes": "Generated scaffold pending full worker execution.",
        }
        if output_format == "json":
            return json.dumps(payload, indent=2, sort_keys=True), "json"

        title = output_type.replace("_", " ").title()
        return (
            f"# {title}\n\n"
            f"- Run ID: `{run.id}`\n"
            f"- Program: `{run.program.name if run.program else 'none'}`\n"
            f"- Status: `staged`\n\n"
            "## Notes\n\n"
            "Generated scaffold pending full worker execution.\n\n"
            "## Citation Policy\n\n"
            f"{citation_policy or 'No citation policy configured.'}\n"
        ), "markdown"

    def _title_for_output(self, run: ResearchRun, output_type: str) -> str:
        """Create a readable output title."""
        return f"{output_type.replace('_', ' ').title()}: {run.objective[:80]}"

    def _render_research_brief(
        self,
        run: ResearchRun,
        citation_policy: str | None,
        retrieval_context: list[dict[str, Any]],
    ) -> str:
        """Render a source-backed literature brief from run claims."""
        claims = list(run.claims)
        citations = self._citation_map(claims)
        figures_tables = self._figure_table_items(claims)
        lines = [
            f"# Research Brief: {run.objective}",
            "",
            "## Summary",
            "",
            self._summary_sentence(run, claims),
            "",
            "## Source-Backed Findings",
            "",
        ]
        if not claims:
            lines.append("No source-backed claims have been attached to this run yet.")
        else:
            for index, claim in enumerate(claims, start=1):
                citation = citations.get(claim.id)
                marker = citation.marker if citation else "[S?]"
                locator = citation.locator if citation and citation.locator else "no locator"
                lines.append(
                    f"{index}. {claim.claim_text} {marker} "
                    f"(locator: {locator}; confidence: {claim.confidence:.2f})"
                )
        if figures_tables:
            lines.extend(["", "## Figures and Tables", ""])
            for item in figures_tables:
                lines.append(
                    f"- {item['kind'].title()}: {item['label']} "
                    f"{item['citation_marker']} - {item['description']}"
                )
        if retrieval_context:
            lines.extend(
                [
                    "",
                    "## Retrieved Context",
                    "",
                ]
            )
            for index, item in enumerate(retrieval_context, start=1):
                source = item.get("document_title") or item.get("document_id") or "source document"
                score = item.get("score", 0)
                content = str(item.get("content") or "").replace("\n", " ").strip()
                lines.append(f"{index}. {content} (source: {source}; score: {score})")
        lines.extend(self._source_notes_section(citations.values()))
        lines.extend(
            [
                "",
                "## Citation Policy",
                "",
                citation_policy or "No citation policy configured.",
                "",
                "## Reviewer Notes",
                "",
                "Review source coverage, confidence, and missing evidence before promotion.",
            ]
        )
        return "\n".join(lines)

    def _render_evidence_table(self, run: ResearchRun) -> str:
        """Render an evidence table from run claims."""
        citations = self._citation_map(run.claims)
        lines = [
            f"# Evidence Table: {run.objective}",
            "",
            "| Claim | Type | Confidence | Citation | Source | Locator | Evidence |",
            "|-------|------|------------|----------|--------|---------|----------|",
        ]
        if not run.claims:
            lines.append("| No claims attached yet | - | - | - | - | - | - |")
            return "\n".join(lines)

        for claim in run.claims:
            evidence = claim.evidence_links[0] if claim.evidence_links else None
            source = claim.document.title if claim.document and claim.document.title else "source document"
            quote = evidence.quote if evidence and evidence.quote else claim.evidence_text or ""
            citation = citations.get(claim.id)
            marker = citation.marker if citation else "[S?]"
            locator = citation.locator if citation and citation.locator else ""
            lines.append(
                "| "
                f"{self._md_cell(claim.claim_text)} | "
                f"{self._md_cell(claim.claim_type)} | "
                f"{claim.confidence:.2f} | "
                f"{self._md_cell(marker)} | "
                f"{self._md_cell(source)} | "
                f"{self._md_cell(locator)} | "
                f"{self._md_cell(quote)} |"
            )
        lines.extend(self._source_notes_section(citations.values()))
        return "\n".join(lines)

    def _render_open_questions(
        self,
        run: ResearchRun,
        citation_policy: str | None,
        retrieval_context: list[dict[str, Any]],
    ) -> str:
        """Render open questions from gaps in current evidence coverage."""
        low_confidence_claims = [claim for claim in run.claims if claim.confidence < 0.7]
        lines = [
            f"# Open Questions: {run.objective}",
            "",
            "## Questions",
            "",
        ]
        if not run.claims:
            lines.append("- What source-backed claims should be extracted for this topic?")
            if retrieval_context:
                lines.append("- Which retrieved chunks should be converted into explicit claims?")
        elif low_confidence_claims:
            for claim in low_confidence_claims:
                lines.append(f"- What additional evidence would strengthen this claim: {claim.claim_text}")
        else:
            lines.append("- Are there contradictory sources or missing experimental conditions?")
            lines.append("- Which findings are actionable enough to become hypotheses or experiments?")
        lines.extend(
            [
                "",
                "## Evidence Standard",
                "",
                citation_policy or "No citation policy configured.",
            ]
        )
        return "\n".join(lines)

    def _render_adam_context(
        self,
        run: ResearchRun,
        citation_policy: str | None,
        retrieval_context: list[dict[str, Any]],
    ) -> str:
        """Render an ADAM-ready context JSON document."""
        payload = {
            "output_type": "adam_context",
            "context_id": run.id,
            "name": run.program.name if run.program else run.objective,
            "description": run.objective,
            "research_domain": run.program.domain if run.program else "materials_science",
            "topic_focus": run.objective,
            "literature_summary": {
                "papers_analyzed": len({claim.document_id for claim in run.claims}),
                "key_findings": [claim.claim_text for claim in run.claims],
                "open_questions": self._open_question_items(run),
            },
            "retrieval_context": retrieval_context,
            "experiment_suggestions": self._experiment_suggestion_items(run, citation_policy),
            "source_claims": [self._claim_payload(claim) for claim in run.claims],
            "figures_tables": self._figure_table_items(run.claims),
            "citations": [
                citation.__dict__
                for citation in self._citation_map(run.claims).values()
            ],
            "metadata": {
                "run_id": run.id,
                "program_id": run.program.id if run.program else None,
                "citation_policy": citation_policy,
                "generator": "ResearchOutputGenerator",
            },
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    def _render_hypothesis_cards(
        self,
        run: ResearchRun,
        citation_policy: str | None,
        retrieval_context: list[dict[str, Any]],
    ) -> str:
        """Render hypothesis cards derived from current claims."""
        cards = []
        for claim in run.claims:
            cards.append(
                {
                    "hypothesis": f"If this finding is robust, it can guide an experiment: {claim.claim_text}",
                    "rationale": claim.evidence_text or claim.claim_text,
                    "confidence_score": claim.confidence,
                    "evidence": self._claim_payload(claim),
                    "citation_policy": citation_policy,
                    "status": "staged",
                }
            )
        if not cards:
            cards.append(
                {
                    "hypothesis": "No hypothesis generated yet.",
                    "rationale": self._retrieval_rationale(retrieval_context),
                    "confidence_score": 0.0,
                    "evidence": retrieval_context[0] if retrieval_context else None,
                    "citation_policy": citation_policy,
                    "status": "needs_evidence",
                }
            )
        return json.dumps({"hypothesis_cards": cards}, indent=2, sort_keys=True)

    def _render_experiment_suggestions(
        self,
        run: ResearchRun,
        citation_policy: str | None,
        retrieval_context: list[dict[str, Any]],
    ) -> str:
        """Render experiment suggestions derived from current claims."""
        suggestions = self._experiment_suggestion_items(run, citation_policy)
        if not run.claims and retrieval_context:
            suggestions[0]["methodology"] = (
                "Review retrieved context, convert supported statements into claims, "
                "then design a focused experiment around the strongest source-backed finding."
            )
            suggestions[0]["retrieval_context"] = retrieval_context
        return json.dumps(
            {"experiment_suggestions": suggestions},
            indent=2,
            sort_keys=True,
        )

    def _experiment_suggestion_items(
        self,
        run: ResearchRun,
        citation_policy: str | None,
    ) -> list[dict[str, Any]]:
        """Build experiment suggestion payloads from run claims."""
        if not run.claims:
            return [
                {
                    "hypothesis": "No experiment suggested yet.",
                    "methodology": "Attach source-backed claims before generating experiments.",
                    "expected_outcomes": [],
                    "confidence_score": 0.0,
                    "evidence": None,
                    "citation_policy": citation_policy,
                    "priority": "low",
                }
            ]

        suggestions = []
        for claim in run.claims:
            suggestions.append(
                {
                    "hypothesis": f"Test whether the reported finding generalizes: {claim.claim_text}",
                    "methodology": "Design a focused experiment around the source finding and capture variables, materials, and metrics before execution.",
                    "expected_outcomes": [claim.claim_text],
                    "confidence_score": claim.confidence,
                    "evidence": self._claim_payload(claim),
                    "citation_policy": citation_policy,
                    "priority": "medium" if claim.confidence >= 0.7 else "low",
                }
            )
        return suggestions

    def _open_question_items(self, run: ResearchRun) -> list[str]:
        """Return open question strings for JSON outputs."""
        if not run.claims:
            return ["What source-backed claims should be extracted for this topic?"]
        low_confidence = [claim.claim_text for claim in run.claims if claim.confidence < 0.7]
        if low_confidence:
            return [f"What additional evidence would strengthen this claim: {text}" for text in low_confidence]
        return [
            "Are there contradictory sources or missing experimental conditions?",
            "Which findings are actionable enough to become hypotheses or experiments?",
        ]

    def _summary_sentence(self, run: ResearchRun, claims: list) -> str:
        """Render a short summary sentence."""
        if not claims:
            return "No source-backed claims have been attached to this run yet."
        return (
            f"This run has {len(claims)} staged source-backed claim(s) "
            f"across {len({claim.document_id for claim in claims})} source document(s)."
        )

    def _claim_payload(self, claim) -> dict[str, Any]:
        """Render a claim and first evidence link as JSON-safe data."""
        evidence = claim.evidence_links[0] if claim.evidence_links else None
        citation = self._citation_for_claim(claim, marker="[S1]")
        return {
            "claim_id": claim.id,
            "document_id": claim.document_id,
            "chunk_id": claim.chunk_id,
            "claim_text": claim.claim_text,
            "claim_type": claim.claim_type,
            "confidence": claim.confidence,
            "source_title": claim.document.title if claim.document else None,
            "locator": evidence.locator if evidence else None,
            "quote": evidence.quote if evidence else claim.evidence_text,
            "source_url": evidence.source_url if evidence else None,
            "citation": citation.__dict__ if citation else None,
        }

    def _md_cell(self, value: str | None) -> str:
        """Escape a value for use in a Markdown table cell."""
        return (value or "").replace("|", "\\|").replace("\n", " ").strip()

    def _retrieval_rationale(self, retrieval_context: list[dict[str, Any]]) -> str:
        """Render a rationale from retrieved context when claims are unavailable."""
        if not retrieval_context:
            return "No source-backed claims are attached to this run."
        top = retrieval_context[0]
        return (
            "Retrieved context is available but has not yet been converted into "
            f"reviewable claims. Top chunk: {top.get('content')}"
        )

    def _citation_map(self, claims) -> dict[str, SourceCitation]:
        """Return one citation marker per claim while deduplicating source notes."""
        source_markers: dict[tuple[str | None, str | None, str | None], str] = {}
        citations: dict[str, SourceCitation] = {}
        for claim in claims:
            evidence = claim.evidence_links[0] if claim.evidence_links else None
            key = (
                claim.document_id,
                evidence.source_url if evidence else None,
                evidence.locator if evidence else None,
            )
            if key not in source_markers:
                source_markers[key] = f"[S{len(source_markers) + 1}]"
            citation = self._citation_for_claim(claim, source_markers[key])
            if citation is not None:
                citations[claim.id] = citation
        return citations

    def _citation_for_claim(self, claim, marker: str) -> SourceCitation | None:
        """Build a source citation for a claim."""
        evidence = claim.evidence_links[0] if claim.evidence_links else None
        document = claim.document
        if document is None and evidence is None:
            return None
        title = document.title if document and document.title else "source document"
        citation = (
            document.normalized_citation
            if document and document.normalized_citation
            else self._fallback_citation(document, title)
        )
        return SourceCitation(
            marker=marker,
            document_id=claim.document_id,
            title=title,
            citation=citation,
            source_url=evidence.source_url if evidence else None,
            locator=evidence.locator if evidence else None,
        )

    def _fallback_citation(self, document, title: str) -> str:
        """Render a citation when corpus hardening has not populated normalized fields."""
        if document is None:
            return title
        year = document.year or "n.d."
        doi = f" DOI: {document.doi}." if document.doi else ""
        return f"{title} ({year}).{doi}".strip()

    def _source_notes_section(self, citations) -> list[str]:
        """Render source notes from citation records."""
        citations = list(citations)
        if not citations:
            return []
        lines = ["", "## Sources", ""]
        seen = set()
        for citation in citations:
            key = (citation.marker, citation.citation, citation.locator)
            if key in seen:
                continue
            seen.add(key)
            locator = f" Locator: {citation.locator}." if citation.locator else ""
            url = f" URL: {citation.source_url}." if citation.source_url else ""
            lines.append(f"- {citation.marker} {citation.citation}.{locator}{url}")
        return lines

    def _figure_table_items(self, claims) -> list[dict[str, Any]]:
        """Extract figure/table references from claim provenance and chunk metadata."""
        items: list[dict[str, Any]] = []
        citations = self._citation_map(claims)
        for claim in claims:
            citation = citations.get(claim.id)
            marker = citation.marker if citation else "[S?]"
            for payload in (
                self._json_payload(claim.provenance_json),
                self._json_payload(claim.chunk.extraction_metadata if claim.chunk else None),
            ):
                for kind in ("figures", "tables"):
                    for raw in payload.get(kind, []) if isinstance(payload.get(kind), list) else []:
                        item = self._figure_table_payload(raw, kind[:-1], marker, claim.id)
                        if item:
                            items.append(item)
        return items

    def _figure_table_payload(
        self,
        raw: Any,
        kind: str,
        citation_marker: str,
        claim_id: str,
    ) -> dict[str, Any] | None:
        """Normalize a figure/table reference."""
        if isinstance(raw, str):
            return {
                "kind": kind,
                "label": raw,
                "description": raw,
                "citation_marker": citation_marker,
                "claim_id": claim_id,
            }
        if isinstance(raw, dict):
            label = str(raw.get("label") or raw.get("id") or raw.get("title") or kind)
            description = str(raw.get("description") or raw.get("caption") or label)
            return {
                "kind": kind,
                "label": label,
                "description": description,
                "citation_marker": citation_marker,
                "claim_id": claim_id,
            }
        return None

    def _json_payload(self, raw: str | None) -> dict[str, Any]:
        """Parse optional JSON object payloads."""
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
