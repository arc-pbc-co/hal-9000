"""Unit tests for ADAM context module."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hal9000.adam.context import (
    ExperimentSuggestion,
    LiteratureSummary,
    KnowledgeGraphNode,
    KnowledgeGraphEdge,
    ADAMResearchContext,
    ContextBuilder,
)
from hal9000.rlm.processor import DocumentAnalysis


class TestExperimentSuggestion:
    """Tests for ExperimentSuggestion dataclass."""

    def test_default_values(self):
        """Test default values."""
        exp = ExperimentSuggestion(
            hypothesis="Test hypothesis",
            methodology="Test methodology"
        )

        assert exp.hypothesis == "Test hypothesis"
        assert exp.methodology == "Test methodology"
        assert exp.variables == {}
        assert exp.expected_outcomes == []
        assert exp.priority == "medium"
        assert exp.confidence_score == 0.5

    def test_to_dict(self):
        """Test conversion to dictionary."""
        exp = ExperimentSuggestion(
            hypothesis="Higher temperature increases diffusion",
            methodology="Anneal samples at various temperatures",
            variables={"independent": ["temperature"], "dependent": ["diffusion rate"]},
            expected_outcomes=["Exponential increase in diffusion"],
            rationale="Based on Arrhenius equation",
            priority="high",
            confidence_score=0.8
        )

        result = exp.to_dict()

        assert result["hypothesis"] == "Higher temperature increases diffusion"
        assert result["priority"] == "high"
        assert result["confidence_score"] == 0.8
        assert "temperature" in result["variables"]["independent"]


class TestLiteratureSummary:
    """Tests for LiteratureSummary dataclass."""

    def test_default_values(self):
        """Test default values."""
        summary = LiteratureSummary()

        assert summary.papers_analyzed == 0
        assert summary.key_findings == []
        assert summary.methodologies == []
        assert summary.gaps_identified == []
        assert summary.open_questions == []

    def test_to_dict(self):
        """Test conversion to dictionary."""
        summary = LiteratureSummary(
            papers_analyzed=5,
            key_findings=["Finding 1", "Finding 2"],
            methodologies=["SEM", "XRD"],
            gaps_identified=["No data on high pressure"]
        )

        result = summary.to_dict()

        assert result["papers_analyzed"] == 5
        assert len(result["key_findings"]) == 2
        assert len(result["methodologies"]) == 2


class TestKnowledgeGraphNode:
    """Tests for KnowledgeGraphNode dataclass."""

    def test_creation(self):
        """Test node creation."""
        node = KnowledgeGraphNode(
            id="node-1",
            label="Superalloys",
            type="concept"
        )

        assert node.id == "node-1"
        assert node.label == "Superalloys"
        assert node.type == "concept"
        assert node.properties == {}

    def test_to_dict(self):
        """Test conversion to dictionary."""
        node = KnowledgeGraphNode(
            id="node-1",
            label="Superalloys",
            type="concept",
            properties={"importance": "high"}
        )

        result = node.to_dict()

        assert result["id"] == "node-1"
        assert result["properties"]["importance"] == "high"


class TestKnowledgeGraphEdge:
    """Tests for KnowledgeGraphEdge dataclass."""

    def test_creation(self):
        """Test edge creation."""
        edge = KnowledgeGraphEdge(
            source="node-1",
            target="node-2",
            relationship="discusses"
        )

        assert edge.source == "node-1"
        assert edge.target == "node-2"
        assert edge.relationship == "discusses"
        assert edge.weight == 1.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        edge = KnowledgeGraphEdge(
            source="node-1",
            target="node-2",
            relationship="cites",
            weight=0.8
        )

        result = edge.to_dict()

        assert result["source"] == "node-1"
        assert result["weight"] == 0.8


class TestADAMResearchContext:
    """Tests for ADAMResearchContext dataclass."""

    def test_default_values(self):
        """Test default values."""
        context = ADAMResearchContext()

        assert context.context_id is not None
        assert len(context.context_id) == 36  # UUID length
        assert context.research_domain == "materials_science"
        assert context.created_at is not None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        context = ADAMResearchContext(
            name="Test Context",
            description="A test research context",
            topic_focus="superalloys"
        )

        result = context.to_dict()

        assert result["name"] == "Test Context"
        assert result["topic_focus"] == "superalloys"
        assert "context_id" in result
        assert "knowledge_graph" in result
        assert "metadata" in result
        assert result["metadata"]["generator"] == "HAL9000"

    def test_to_json(self):
        """Test JSON serialization."""
        context = ADAMResearchContext(name="Test")

        json_str = context.to_json()
        parsed = json.loads(json_str)

        assert parsed["name"] == "Test"

    def test_save(self, temp_directory: Path):
        """Test saving context to file."""
        context = ADAMResearchContext(
            name="Test Context",
            topic_focus="batteries"
        )

        output_path = temp_directory / "context.json"
        context.save(output_path)

        assert output_path.exists()

        with open(output_path) as f:
            data = json.load(f)

        assert data["name"] == "Test Context"

    def test_save_creates_parent_dirs(self, temp_directory: Path):
        """Test that save creates parent directories."""
        context = ADAMResearchContext(name="Test")

        output_path = temp_directory / "nested" / "dirs" / "context.json"
        context.save(output_path)

        assert output_path.exists()


class TestContextBuilder:
    """Tests for ContextBuilder class."""

    @patch('hal9000.adam.context.RLMProcessor')
    def test_init_default(self, mock_processor):
        """Test default initialization."""
        builder = ContextBuilder()

        assert builder.default_domain == "materials_science"

    @patch('hal9000.adam.context.RLMProcessor')
    def test_init_custom(self, mock_processor):
        """Test custom initialization."""
        mock_proc = MagicMock()
        builder = ContextBuilder(
            processor=mock_proc,
            default_domain="chemistry"
        )

        assert builder.processor == mock_proc
        assert builder.default_domain == "chemistry"

    @patch('hal9000.adam.context.RLMProcessor')
    def test_infer_topic_focus(self, mock_processor):
        """Test topic focus inference."""
        builder = ContextBuilder()

        analyses = [
            DocumentAnalysis(
                primary_topics=["superalloys", "nickel"],
                secondary_topics=["creep"]
            ),
            DocumentAnalysis(
                primary_topics=["superalloys", "turbines"],
                secondary_topics=["high temperature"]
            ),
        ]

        focus = builder._infer_topic_focus(analyses)

        # Superalloys appears most frequently
        assert focus == "superalloys"

    @patch('hal9000.adam.context.RLMProcessor')
    def test_infer_topic_focus_empty(self, mock_processor):
        """Test topic focus with empty analyses."""
        builder = ContextBuilder()

        focus = builder._infer_topic_focus([])

        assert focus == "general materials science"

    @patch('hal9000.adam.context.RLMProcessor')
    def test_aggregate_literature(self, mock_processor, mock_document_analysis):
        """Test literature aggregation."""
        builder = ContextBuilder()

        analyses = [mock_document_analysis, mock_document_analysis]
        summary = builder._aggregate_literature(analyses)

        assert isinstance(summary, LiteratureSummary)
        assert summary.papers_analyzed == 2
        assert len(summary.key_findings) > 0

    @patch('hal9000.adam.context.RLMProcessor')
    def test_build_knowledge_graph(self, mock_processor, mock_document_analysis):
        """Test knowledge graph building."""
        builder = ContextBuilder()

        nodes, edges = builder._build_knowledge_graph([mock_document_analysis])

        assert len(nodes) > 0
        assert len(edges) > 0

        # Should have paper node
        paper_nodes = [n for n in nodes if n.type == "paper"]
        assert len(paper_nodes) == 1

    @patch('hal9000.adam.context.RLMProcessor')
    def test_extract_materials(self, mock_processor, mock_document_analysis):
        """Test materials extraction."""
        builder = ContextBuilder()

        materials = builder._extract_materials([mock_document_analysis])

        assert len(materials) > 0
        assert "Mar-M 247" in materials

    @patch('hal9000.adam.context.RLMProcessor')
    def test_extract_characterization(self, mock_processor):
        """Test characterization technique extraction."""
        builder = ContextBuilder()

        analysis = DocumentAnalysis(
            keywords=["XRD", "SEM", "TEM", "unrelated"],
            methodology_summary="We used XRD and SQUID magnetometry"
        )

        techniques = builder._extract_characterization([analysis])

        assert len(techniques) > 0
        # Should find XRD (appears in both)

    @patch('hal9000.adam.context.RLMProcessor')
    def test_deduplicate_and_rank(self, mock_processor):
        """Test deduplication and ranking."""
        builder = ContextBuilder()

        items = ["item1", "Item1", "item2", "ITEM1", "item3"]
        result = builder._deduplicate_and_rank(items)

        assert len(result) == 3
        # item1 appears most frequently
        assert result[0].lower() == "item1"

    @patch('hal9000.adam.context.RLMProcessor')
    def test_generate_description(self, mock_processor):
        """Test description generation."""
        builder = ContextBuilder()

        context = ADAMResearchContext(
            topic_focus="superalloys",
            materials_of_interest=["Inconel", "Mar-M 247"],
        )
        context.literature_summary = LiteratureSummary(papers_analyzed=3)
        context.experiment_suggestions = [
            ExperimentSuggestion(hypothesis="h", methodology="m")
        ]

        desc = builder._generate_description(context)

        assert "superalloys" in desc
        assert "3 papers" in desc
        assert "Inconel" in desc
        assert "1 experiment" in desc

    @patch('hal9000.adam.context.RLMProcessor')
    def test_build_context_without_experiments(self, mock_processor, mock_document_analysis):
        """Test building context without experiment generation."""
        mock_proc = MagicMock()
        mock_processor.return_value = mock_proc

        builder = ContextBuilder(processor=mock_proc)

        context = builder.build_context(
            analyses=[mock_document_analysis],
            name="Test Context",
            generate_experiments=False
        )

        assert isinstance(context, ADAMResearchContext)
        assert context.name == "Test Context"
        assert len(context.experiment_suggestions) == 0

    @patch('hal9000.adam.context.RLMProcessor')
    def test_build_context_with_experiments(self, mock_processor, mock_document_analysis):
        """Test building context with experiment generation."""
        mock_proc = MagicMock()

        # Mock the LLM response for experiment generation
        exp_response = {
            "experiment_suggestions": [
                {
                    "hypothesis": "Test hypothesis",
                    "methodology": "Test method",
                    "variables": {"independent": ["var1"]},
                    "expected_outcomes": ["outcome1"],
                    "rationale": "Based on literature",
                    "priority": "high",
                    "confidence_score": 0.7
                }
            ]
        }
        mock_proc._call_llm.return_value = json.dumps(exp_response)
        mock_proc._parse_json_response.return_value = exp_response

        builder = ContextBuilder(processor=mock_proc)

        context = builder.build_context(
            analyses=[mock_document_analysis],
            name="Test Context",
            generate_experiments=True
        )

        assert len(context.experiment_suggestions) == 1
        assert context.experiment_suggestions[0].hypothesis == "Test hypothesis"

    @patch('hal9000.adam.context.RLMProcessor')
    def test_save_context(self, mock_processor, temp_directory: Path, mock_document_analysis):
        """Test saving context to directory."""
        mock_proc = MagicMock()
        builder = ContextBuilder(processor=mock_proc)

        context = builder.build_context(
            analyses=[mock_document_analysis],
            name="Test",
            generate_experiments=False
        )

        output_path = builder.save_context(context, temp_directory)

        assert output_path.exists()
        assert output_path.suffix == ".json"

        with open(output_path) as f:
            data = json.load(f)

        assert data["name"] == "Test"


class TestContextBuilderIntegration:
    """Integration tests for ContextBuilder."""

    @patch('hal9000.adam.context.RLMProcessor')
    def test_full_context_building(self, mock_processor, mock_document_analysis, temp_directory: Path):
        """Test complete context building workflow."""
        mock_proc = MagicMock()
        mock_proc._call_llm.return_value = "{}"
        mock_proc._parse_json_response.return_value = None

        builder = ContextBuilder(processor=mock_proc)

        # Build with multiple analyses
        analyses = [mock_document_analysis] * 3

        context = builder.build_context(
            analyses=analyses,
            name="Full Test",
            topic_focus="superalloys",
            generate_experiments=False
        )

        # Verify structure
        assert context.name == "Full Test"
        assert context.topic_focus == "superalloys"
        assert context.literature_summary.papers_analyzed == 3
        assert len(context.source_documents) == 3
        assert len(context.nodes) > 0
        assert len(context.edges) > 0

        # Save and reload
        output_path = builder.save_context(context, temp_directory)

        with open(output_path) as f:
            reloaded = json.load(f)

        assert reloaded["name"] == "Full Test"
        assert reloaded["literature_summary"]["papers_analyzed"] == 3
