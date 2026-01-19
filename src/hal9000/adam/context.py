"""Generate ADAM Platform compatible research contexts."""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from hal9000.rlm.processor import DocumentAnalysis, RLMProcessor
from hal9000.rlm.prompts import ADAM_CONTEXT_PROMPT, HYPOTHESIS_PROMPT, format_prompt

logger = logging.getLogger(__name__)


@dataclass
class ExperimentSuggestion:
    """A suggested experiment from literature analysis."""

    hypothesis: str
    methodology: str
    variables: dict = field(default_factory=dict)
    expected_outcomes: list[str] = field(default_factory=list)
    rationale: str = ""
    priority: str = "medium"
    confidence_score: float = 0.5

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "hypothesis": self.hypothesis,
            "methodology": self.methodology,
            "variables": self.variables,
            "expected_outcomes": self.expected_outcomes,
            "rationale": self.rationale,
            "priority": self.priority,
            "confidence_score": self.confidence_score,
        }


@dataclass
class LiteratureSummary:
    """Summary of analyzed literature."""

    papers_analyzed: int = 0
    key_findings: list[str] = field(default_factory=list)
    methodologies: list[str] = field(default_factory=list)
    gaps_identified: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "papers_analyzed": self.papers_analyzed,
            "key_findings": self.key_findings,
            "methodologies": self.methodologies,
            "gaps_identified": self.gaps_identified,
            "open_questions": self.open_questions,
        }


@dataclass
class KnowledgeGraphNode:
    """A node in the knowledge graph."""

    id: str
    label: str
    type: str  # paper, concept, material, method
    properties: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "type": self.type,
            "properties": self.properties,
        }


@dataclass
class KnowledgeGraphEdge:
    """An edge in the knowledge graph."""

    source: str
    target: str
    relationship: str
    weight: float = 1.0

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "weight": self.weight,
        }


@dataclass
class ADAMResearchContext:
    """
    A complete research context for the ADAM Platform.

    This format is designed to provide comprehensive context for
    experimental design in materials discovery.
    """

    context_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    research_domain: str = "materials_science"
    topic_focus: str = ""

    literature_summary: LiteratureSummary = field(default_factory=LiteratureSummary)
    experiment_suggestions: list[ExperimentSuggestion] = field(default_factory=list)

    # Knowledge graph
    nodes: list[KnowledgeGraphNode] = field(default_factory=list)
    edges: list[KnowledgeGraphEdge] = field(default_factory=list)

    # Metadata
    materials_of_interest: list[str] = field(default_factory=list)
    recommended_characterization: list[str] = field(default_factory=list)
    source_documents: list[str] = field(default_factory=list)

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "context_id": self.context_id,
            "name": self.name,
            "description": self.description,
            "research_domain": self.research_domain,
            "topic_focus": self.topic_focus,
            "literature_summary": self.literature_summary.to_dict(),
            "experiment_suggestions": [e.to_dict() for e in self.experiment_suggestions],
            "knowledge_graph": {
                "nodes": [n.to_dict() for n in self.nodes],
                "edges": [e.to_dict() for e in self.edges],
            },
            "materials_of_interest": self.materials_of_interest,
            "recommended_characterization": self.recommended_characterization,
            "source_documents": self.source_documents,
            "metadata": {
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "version": "1.0",
                "generator": "HAL9000",
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: Path) -> None:
        """Save to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.to_json())
        logger.info(f"Saved ADAM context to: {path}")


class ContextBuilder:
    """
    Build ADAM research contexts from analyzed documents.

    Aggregates information from multiple document analyses into
    a comprehensive research context for experimental design.
    """

    def __init__(
        self,
        processor: Optional[RLMProcessor] = None,
        default_domain: str = "materials_science",
    ):
        """
        Initialize the context builder.

        Args:
            processor: RLMProcessor for generating suggestions (creates new if None)
            default_domain: Default research domain
        """
        self.processor = processor or RLMProcessor()
        self.default_domain = default_domain

    def build_context(
        self,
        analyses: list[DocumentAnalysis],
        name: str,
        topic_focus: Optional[str] = None,
        generate_experiments: bool = True,
    ) -> ADAMResearchContext:
        """
        Build a research context from document analyses.

        Args:
            analyses: List of DocumentAnalysis from processed documents
            name: Name for this context
            topic_focus: Specific topic to focus on
            generate_experiments: Whether to generate experiment suggestions

        Returns:
            ADAMResearchContext object
        """
        context = ADAMResearchContext(
            name=name,
            research_domain=self.default_domain,
            topic_focus=topic_focus or self._infer_topic_focus(analyses),
        )

        # Aggregate literature summary
        context.literature_summary = self._aggregate_literature(analyses)

        # Build knowledge graph
        context.nodes, context.edges = self._build_knowledge_graph(analyses)

        # Extract materials and methods
        context.materials_of_interest = self._extract_materials(analyses)
        context.recommended_characterization = self._extract_characterization(analyses)

        # Track source documents
        context.source_documents = [
            a.title for a in analyses if a.title
        ]

        # Generate experiment suggestions
        if generate_experiments:
            context.experiment_suggestions = self._generate_experiments(
                context.literature_summary, context.topic_focus
            )

        # Generate description
        context.description = self._generate_description(context)

        return context

    def _infer_topic_focus(self, analyses: list[DocumentAnalysis]) -> str:
        """Infer the main topic focus from analyses."""
        topic_counts: dict[str, int] = {}

        for analysis in analyses:
            for topic in analysis.primary_topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 2
            for topic in analysis.secondary_topics:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

        if topic_counts:
            return max(topic_counts, key=topic_counts.get)
        return "general materials science"

    def _aggregate_literature(
        self, analyses: list[DocumentAnalysis]
    ) -> LiteratureSummary:
        """Aggregate findings from all analyses."""
        summary = LiteratureSummary(papers_analyzed=len(analyses))

        # Collect all findings, methodologies, etc.
        all_findings = []
        all_methods = []
        all_keywords = []

        for analysis in analyses:
            all_findings.extend(analysis.key_findings)
            if analysis.methodology_summary:
                all_methods.append(analysis.methodology_summary)
            all_keywords.extend(analysis.keywords)

        # Deduplicate and rank
        summary.key_findings = self._deduplicate_and_rank(all_findings)[:20]
        summary.methodologies = self._deduplicate_and_rank(all_methods)[:10]

        # Gaps and questions (would be generated by LLM in full implementation)
        summary.gaps_identified = []
        summary.open_questions = []

        return summary

    def _build_knowledge_graph(
        self, analyses: list[DocumentAnalysis]
    ) -> tuple[list[KnowledgeGraphNode], list[KnowledgeGraphEdge]]:
        """Build a knowledge graph from analyses."""
        nodes = []
        edges = []
        node_ids: dict[str, str] = {}

        def get_or_create_node(label: str, node_type: str) -> str:
            """Get existing node ID or create new node."""
            key = f"{node_type}:{label.lower()}"
            if key not in node_ids:
                node_id = str(uuid.uuid4())[:8]
                node_ids[key] = node_id
                nodes.append(KnowledgeGraphNode(
                    id=node_id,
                    label=label,
                    type=node_type,
                ))
            return node_ids[key]

        for analysis in analyses:
            # Create paper node
            if analysis.title:
                paper_id = get_or_create_node(analysis.title, "paper")

                # Connect to topics
                for topic in analysis.primary_topics[:5]:
                    topic_id = get_or_create_node(topic, "concept")
                    edges.append(KnowledgeGraphEdge(
                        source=paper_id,
                        target=topic_id,
                        relationship="discusses",
                    ))

                # Connect to materials
                for material in analysis.materials[:5]:
                    if isinstance(material, dict):
                        mat_name = material.get("name", "")
                    else:
                        mat_name = str(material)
                    if mat_name:
                        mat_id = get_or_create_node(mat_name, "material")
                        edges.append(KnowledgeGraphEdge(
                            source=paper_id,
                            target=mat_id,
                            relationship="studies",
                        ))

        return nodes, edges

    def _extract_materials(self, analyses: list[DocumentAnalysis]) -> list[str]:
        """Extract unique materials from analyses."""
        materials = []
        seen = set()

        for analysis in analyses:
            for mat in analysis.materials:
                if isinstance(mat, dict):
                    name = mat.get("name", "")
                else:
                    name = str(mat)
                if name and name.lower() not in seen:
                    seen.add(name.lower())
                    materials.append(name)

        return materials[:30]

    def _extract_characterization(self, analyses: list[DocumentAnalysis]) -> list[str]:
        """Extract characterization techniques from analyses."""
        techniques = set()

        # Common characterization keywords
        char_keywords = {
            "xrd", "x-ray diffraction", "sem", "tem", "afm", "xps",
            "squid", "vsm", "eds", "eels", "ftir", "raman",
            "nmr", "dsc", "tga", "bh loop", "magnetic measurement"
        }

        for analysis in analyses:
            for keyword in analysis.keywords:
                if keyword.lower() in char_keywords:
                    techniques.add(keyword)

            # Also check methodology
            if analysis.methodology_summary:
                for char in char_keywords:
                    if char in analysis.methodology_summary.lower():
                        techniques.add(char.upper())

        return list(techniques)[:15]

    def _generate_experiments(
        self,
        literature: LiteratureSummary,
        topic_focus: str,
    ) -> list[ExperimentSuggestion]:
        """Generate experiment suggestions using LLM."""
        try:
            # Prepare analysis summary
            analysis_text = f"""
Topic Focus: {topic_focus}
Papers Analyzed: {literature.papers_analyzed}

Key Findings:
{chr(10).join('- ' + f for f in literature.key_findings[:10])}

Methodologies Used:
{chr(10).join('- ' + m for m in literature.methodologies[:5])}
"""

            # Call LLM to generate suggestions
            response = self.processor._call_llm(
                format_prompt(
                    ADAM_CONTEXT_PROMPT,
                    documents_summary=analysis_text,
                ),
                max_tokens=4000,
            )

            data = self.processor._parse_json_response(response)

            if data and "experiment_suggestions" in data:
                suggestions = []
                for exp in data["experiment_suggestions"][:5]:
                    suggestions.append(ExperimentSuggestion(
                        hypothesis=exp.get("hypothesis", ""),
                        methodology=exp.get("methodology", ""),
                        variables=exp.get("variables", {}),
                        expected_outcomes=exp.get("expected_outcomes", []),
                        rationale=exp.get("rationale", ""),
                        priority=exp.get("priority", "medium"),
                        confidence_score=exp.get("confidence_score", 0.5),
                    ))
                return suggestions

        except Exception as e:
            logger.error(f"Failed to generate experiments: {e}")

        return []

    def _generate_description(self, context: ADAMResearchContext) -> str:
        """Generate a description for the context."""
        parts = [
            f"Research context for {context.topic_focus}.",
            f"Based on analysis of {context.literature_summary.papers_analyzed} papers.",
        ]

        if context.materials_of_interest:
            parts.append(
                f"Key materials: {', '.join(context.materials_of_interest[:5])}."
            )

        if context.experiment_suggestions:
            parts.append(
                f"Includes {len(context.experiment_suggestions)} experiment suggestions."
            )

        return " ".join(parts)

    def _deduplicate_and_rank(self, items: list[str]) -> list[str]:
        """Deduplicate and rank items by frequency."""
        from collections import Counter

        normalized = [item.lower().strip() for item in items if item]
        counts = Counter(normalized)

        # Return original casing for most common
        seen = set()
        ranked = []
        for item in items:
            key = item.lower().strip()
            if key and key not in seen:
                seen.add(key)
                ranked.append((item, counts[key]))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return [item for item, _ in ranked]

    def save_context(
        self,
        context: ADAMResearchContext,
        output_dir: Path,
    ) -> Path:
        """
        Save a context to the output directory.

        Args:
            context: The context to save
            output_dir: Directory to save to

        Returns:
            Path to the saved file
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"adam_context_{context.context_id[:8]}.json"
        output_path = output_dir / filename

        context.save(output_path)
        return output_path
