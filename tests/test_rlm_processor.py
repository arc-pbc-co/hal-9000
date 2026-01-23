"""Unit tests for RLM processor module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from hal9000.rlm.processor import (
    ChunkResult,
    DocumentAnalysis,
    RLMProcessor,
)


class TestChunkResult:
    """Tests for ChunkResult dataclass."""

    def test_default_values(self):
        """Test default values."""
        result = ChunkResult(chunk_index=0)

        assert result.chunk_index == 0
        assert result.topics == []
        assert result.keywords == []
        assert result.findings == []
        assert result.methodology == {}
        assert result.materials == []
        assert result.raw_response is None
        assert result.error is None

    def test_with_data(self):
        """Test with populated data."""
        result = ChunkResult(
            chunk_index=1,
            topics=["topic1", "topic2"],
            keywords=["key1"],
            findings=["finding1"],
            materials=[{"name": "Steel"}],
            error=None
        )

        assert len(result.topics) == 2
        assert len(result.keywords) == 1
        assert len(result.findings) == 1


class TestDocumentAnalysis:
    """Tests for DocumentAnalysis dataclass."""

    def test_default_values(self):
        """Test default values."""
        analysis = DocumentAnalysis()

        assert analysis.title is None
        assert analysis.primary_topics == []
        assert analysis.secondary_topics == []
        assert analysis.keywords == []
        assert analysis.summary is None
        assert analysis.chunks_processed == 0
        assert analysis.total_chunks == 0
        assert analysis.processing_errors == []

    def test_to_dict(self, mock_document_analysis):
        """Test conversion to dictionary."""
        result = mock_document_analysis.to_dict()

        assert result["title"] == "Test Paper on Superalloys"
        assert len(result["primary_topics"]) == 2
        assert result["research_domain"] == "materials_science"
        assert "processing" in result
        assert result["processing"]["chunks_processed"] == 3

    def test_with_errors(self):
        """Test analysis with processing errors."""
        analysis = DocumentAnalysis(
            processing_errors=["Chunk 1: API error", "Chunk 2: Timeout"]
        )

        result = analysis.to_dict()
        assert len(result["processing"]["errors"]) == 2


class TestRLMProcessor:
    """Tests for RLMProcessor class."""

    def test_init_default(self):
        """Test default initialization."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor()

            assert processor.model == "claude-sonnet-4-20250514"
            assert processor.chunk_size == 50000
            assert processor.chunk_overlap == 1000
            assert processor.max_concurrent_calls == 5

    def test_init_custom(self):
        """Test custom initialization."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor(
                api_key="test-key",
                model="claude-3-opus",
                chunk_size=30000,
                chunk_overlap=500,
                max_concurrent_calls=3
            )

            assert processor.model == "claude-3-opus"
            assert processor.chunk_size == 30000
            assert processor.chunk_overlap == 500

    def test_chunk_document_small(self):
        """Test chunking with small document."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor(chunk_size=1000)

            text = "Small document"
            chunks = processor._chunk_document(text)

            assert len(chunks) == 1
            assert chunks[0] == text

    def test_chunk_document_large(self):
        """Test chunking with large document."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor(chunk_size=100, chunk_overlap=10)

            text = "A" * 500
            chunks = processor._chunk_document(text)

            assert len(chunks) > 1

    def test_chunk_document_respects_boundaries(self, sample_document_text: str):
        """Test that chunking respects paragraph boundaries."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor(chunk_size=500, chunk_overlap=50)

            chunks = processor._chunk_document(sample_document_text)

            # Each chunk should be non-empty
            for chunk in chunks:
                assert len(chunk.strip()) > 0

    def test_find_break_point_paragraph(self):
        """Test finding break point at paragraph."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor()

            text = "First part.\n\nSecond part starts here."
            break_point = processor._find_break_point(text, 0, 30, window=50)

            # Should break at paragraph
            assert text[break_point:].startswith("Second")

    def test_find_break_point_sentence(self):
        """Test finding break point at sentence."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor()

            text = "First sentence. Second sentence starts here."
            break_point = processor._find_break_point(text, 0, 30, window=50)

            assert break_point == 16

    def test_parse_json_response_valid(self):
        """Test parsing valid JSON response."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor()

            response = '{"topics": ["topic1"], "keywords": ["key1"]}'
            result = processor._parse_json_response(response)

            assert result is not None
            assert result["topics"] == ["topic1"]

    def test_parse_json_response_with_text(self):
        """Test parsing JSON embedded in text."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor()

            response = 'Here is the analysis:\n{"topics": ["topic1"]}\n\nEnd of response.'
            result = processor._parse_json_response(response)

            assert result is not None
            assert "topics" in result

    def test_parse_json_response_invalid(self):
        """Test parsing invalid JSON."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor()

            response = "This is not JSON at all"
            result = processor._parse_json_response(response)

            assert result is None

    def test_rank_by_frequency(self):
        """Test ranking items by frequency."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor()

            items = ["apple", "banana", "Apple", "cherry", "APPLE", "banana"]
            ranked = processor._rank_by_frequency(items)

            # Apple appears 3 times (case insensitive), banana 2 times
            assert ranked[0].lower() == "apple"
            assert ranked[1].lower() == "banana"

    def test_rank_by_frequency_empty(self):
        """Test ranking empty list."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor()

            ranked = processor._rank_by_frequency([])
            assert ranked == []

    def test_deduplicate_list(self):
        """Test deduplicating list."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor()

            items = ["Item 1", "item 1", "Item 2", "ITEM 1", "Item 3"]
            result = processor._deduplicate_list(items)

            # Should have 3 unique items
            assert len(result) == 3
            # Order should be preserved (first occurrence)
            assert result[0] == "Item 1"

    def test_deduplicate_list_with_whitespace(self):
        """Test deduplication handles whitespace."""
        with patch('hal9000.rlm.processor.Anthropic'):
            processor = RLMProcessor()

            items = ["Item ", " Item", "  Item  "]
            result = processor._deduplicate_list(items)

            assert len(result) == 1

    @patch('hal9000.rlm.processor.Anthropic')
    def test_process_chunk_success(self, mock_anthropic, mock_llm_response: dict):
        """Test processing a single chunk successfully."""
        # Setup mock
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(mock_llm_response))]
        mock_client.messages.create.return_value = mock_response

        processor = RLMProcessor()
        result = processor._process_chunk(
            chunk="Test chunk content",
            chunk_index=0,
            domain="materials_science",
            include_materials=True
        )

        assert isinstance(result, ChunkResult)
        assert result.chunk_index == 0
        assert result.error is None

    @patch('hal9000.rlm.processor.Anthropic')
    def test_process_chunk_error(self, mock_anthropic):
        """Test handling error in chunk processing."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        # Simulate API error
        mock_client.messages.create.side_effect = Exception("API Error")

        processor = RLMProcessor()
        result = processor._process_chunk(
            chunk="Test chunk",
            chunk_index=0,
            domain="materials_science",
            include_materials=True
        )

        assert result.error is not None
        assert "API Error" in result.error

    @patch('hal9000.rlm.processor.Anthropic')
    def test_aggregate_results(self, mock_anthropic, mock_llm_response: dict):
        """Test aggregating chunk results."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        # Setup aggregation response
        agg_response = {
            "title": "Test Document",
            "primary_topics": ["topic1", "topic2"],
            "summary": "Test summary",
            "research_domain": "materials_science",
        }
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(agg_response))]
        mock_client.messages.create.return_value = mock_response

        processor = RLMProcessor()

        # Create mock chunk results
        chunk_results = [
            ChunkResult(
                chunk_index=0,
                topics=["topic1", "topic2"],
                keywords=["key1", "key2"],
                findings=["finding1"]
            ),
            ChunkResult(
                chunk_index=1,
                topics=["topic2", "topic3"],
                keywords=["key2", "key3"],
                findings=["finding2"]
            ),
        ]

        analysis = processor._aggregate_results(chunk_results, "materials_science")

        assert isinstance(analysis, DocumentAnalysis)

    @patch('hal9000.rlm.processor.Anthropic')
    def test_aggregate_results_with_errors(self, mock_anthropic):
        """Test aggregation handles chunk errors."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"title": "Test"}')]
        mock_client.messages.create.return_value = mock_response

        processor = RLMProcessor()

        chunk_results = [
            ChunkResult(chunk_index=0, topics=["topic1"], error=None),
            ChunkResult(chunk_index=1, error="Some error"),
        ]

        analysis = processor._aggregate_results(chunk_results, "materials_science")

        # Should include error in processing_errors
        assert len(analysis.processing_errors) == 1
        assert "Chunk 1" in analysis.processing_errors[0]

    @patch('hal9000.rlm.processor.Anthropic')
    def test_process_document_small(self, mock_anthropic, mock_llm_response: dict):
        """Test processing a small document (single chunk)."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        # Mock responses for different prompts
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(mock_llm_response))]
        mock_client.messages.create.return_value = mock_response

        processor = RLMProcessor(chunk_size=100000)

        text = "Short document text for testing."
        analysis = processor.process_document(text)

        assert isinstance(analysis, DocumentAnalysis)
        assert analysis.total_chunks >= 1

    @patch('hal9000.rlm.processor.Anthropic')
    def test_call_llm(self, mock_anthropic):
        """Test direct LLM call."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test response")]
        mock_client.messages.create.return_value = mock_response

        processor = RLMProcessor()
        result = processor._call_llm("Test prompt")

        assert result == "Test response"
        mock_client.messages.create.assert_called_once()

    @patch('hal9000.rlm.processor.Anthropic')
    def test_generate_summary_short_doc(self, mock_anthropic):
        """Test summary generation for short document."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Generated summary of the document.")]
        mock_client.messages.create.return_value = mock_response

        processor = RLMProcessor()
        summary = processor.generate_summary("Short document text")

        assert isinstance(summary, str)
        assert len(summary) > 0


class TestRLMProcessorIntegration:
    """Integration tests for RLM processor (with mocked API)."""

    @patch('hal9000.rlm.processor.Anthropic')
    def test_full_pipeline_mock(self, mock_anthropic, sample_document_text: str):
        """Test full processing pipeline with mocked API."""
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client

        # Create realistic mock responses
        topic_response = {
            "primary_topics": ["superalloys", "nickel", "creep"],
            "keywords": ["Mar-M 247", "turbine", "gamma-prime"],
            "research_domain": "materials_science"
        }
        materials_response = {
            "materials": [{"name": "Mar-M 247", "composition": "Ni-based"}],
            "characterization_techniques": ["SEM", "XRD"],
            "performance_metrics": []
        }
        findings_response = {
            "qualitative_findings": ["Single crystal samples showed superior creep resistance"]
        }
        agg_response = {
            "title": "Superalloy Creep Study",
            "primary_topics": ["superalloys", "creep"],
            "summary": "Study of nickel superalloys",
            "research_domain": "materials_science"
        }

        responses = [
            MagicMock(content=[MagicMock(text=json.dumps(topic_response))]),
            MagicMock(content=[MagicMock(text=json.dumps(materials_response))]),
            MagicMock(content=[MagicMock(text=json.dumps(findings_response))]),
            MagicMock(content=[MagicMock(text=json.dumps(agg_response))]),
        ]
        mock_client.messages.create.side_effect = responses

        processor = RLMProcessor(chunk_size=100000)  # Large enough for single chunk
        analysis = processor.process_document(sample_document_text)

        assert isinstance(analysis, DocumentAnalysis)
        assert analysis.total_chunks == 1
        assert analysis.chunks_processed == 1
