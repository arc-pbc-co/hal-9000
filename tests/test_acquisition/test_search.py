"""Tests for the search engine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hal9000.acquisition.providers.arxiv import ArxivProvider
from hal9000.acquisition.providers.base import SearchResult
from hal9000.acquisition.providers.semantic_scholar import SemanticScholarProvider
from hal9000.acquisition.search import SearchEngine


class TestSearchEngine:
    """Tests for SearchEngine."""

    @pytest.fixture
    def mock_providers(self):
        """Create mock providers."""
        ss_provider = MagicMock(spec=SemanticScholarProvider)
        ss_provider.name = "semantic_scholar"
        ss_provider.search = AsyncMock(return_value=[
            SearchResult(
                title="Paper from Semantic Scholar",
                authors=["Author A"],
                doi="10.1234/test1",
                source="semantic_scholar",
            )
        ])

        arxiv_provider = MagicMock(spec=ArxivProvider)
        arxiv_provider.name = "arxiv"
        arxiv_provider.search = AsyncMock(return_value=[
            SearchResult(
                title="Paper from arXiv",
                authors=["Author B"],
                arxiv_id="2301.00001",
                source="arxiv",
            )
        ])

        return [ss_provider, arxiv_provider]

    @pytest.fixture
    def engine(self, mock_providers):
        """Create a SearchEngine with mock providers."""
        return SearchEngine(providers=mock_providers, anthropic_api_key=None)

    def test_deduplicate_results(self, engine):
        """Test result deduplication."""
        results = [
            SearchResult(
                title="Paper A",
                authors=[],
                doi="10.1234/test",
                source="semantic_scholar",
            ),
            SearchResult(
                title="Paper A",  # Same title
                authors=[],
                doi="10.1234/test",  # Same DOI
                source="arxiv",
            ),
            SearchResult(
                title="Paper B",
                authors=[],
                doi="10.1234/other",
                source="semantic_scholar",
            ),
        ]

        unique = engine._deduplicate_results(results)
        assert len(unique) == 2

    def test_deduplicate_by_arxiv_id(self, engine):
        """Test deduplication by arXiv ID."""
        results = [
            SearchResult(
                title="Paper A",
                authors=[],
                arxiv_id="2301.00001",
                source="arxiv",
            ),
            SearchResult(
                title="Paper A (different title)",
                authors=[],
                arxiv_id="2301.00001",  # Same arXiv ID
                source="semantic_scholar",
            ),
        ]

        unique = engine._deduplicate_results(results)
        assert len(unique) == 1

    @pytest.mark.asyncio
    async def test_search_combines_providers(self, engine, mock_providers):
        """Test that search combines results from all providers."""
        results = await engine.search("test query", expand_query=False)

        # Should have results from both providers
        assert len(results) == 2
        sources = {r.source for r in results}
        assert "semantic_scholar" in sources
        assert "arxiv" in sources

    @pytest.mark.asyncio
    async def test_search_filters_by_sources(self, engine, mock_providers):
        """Test that search honors selected sources."""
        results = await engine.search(
            "test query",
            expand_query=False,
            sources=["arxiv"],
        )

        assert len(results) == 1
        assert results[0].source == "arxiv"
        mock_providers[0].search.assert_not_called()
        mock_providers[1].search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_unknown_source_returns_empty(self, engine):
        """Test search handles unknown source filters safely."""
        results = await engine.search(
            "test query",
            expand_query=False,
            sources=["nonexistent_source"],
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_expand_query_without_anthropic(self, engine):
        """Test query expansion falls back when no API key."""
        expansion = await engine.expand_query("machine learning")

        # Should return the original query
        assert "machine learning" in expansion["queries"]

    @pytest.mark.asyncio
    async def test_search_provider_error_handling(self, engine, mock_providers):
        """Test that search continues if one provider fails."""
        # Make one provider fail
        mock_providers[0].search = AsyncMock(side_effect=Exception("API Error"))

        results = await engine.search("test query", expand_query=False)

        # Should still get results from the working provider
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_search_respects_provider_rate_limit_between_queries(self):
        """Test provider pacing is applied when query expansion yields multiple queries."""
        provider = MagicMock(spec=SemanticScholarProvider)
        provider.name = "semantic_scholar"
        provider.search = AsyncMock(return_value=[])
        provider.get_rate_limit_delay = AsyncMock(return_value=0.5)

        engine = SearchEngine(providers=[provider], anthropic_api_key=None)
        engine.expand_query = AsyncMock(return_value={"queries": ["q1", "q2"]})

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await engine.search("test topic", expand_query=True)

        assert provider.search.await_count == 3
        assert mock_sleep.await_count >= 1

    @pytest.mark.asyncio
    async def test_search_always_includes_original_topic_query(self):
        """Test expanded search keeps the original topic query."""
        provider = MagicMock(spec=SemanticScholarProvider)
        provider.name = "semantic_scholar"
        provider.search = AsyncMock(return_value=[])
        provider.get_rate_limit_delay = AsyncMock(return_value=0.0)

        engine = SearchEngine(providers=[provider], anthropic_api_key=None)
        engine.expand_query = AsyncMock(
            return_value={"queries": ["expanded query 1", "expanded query 2"]}
        )

        await engine.search("original topic", expand_query=True)

        searched_queries = [call.args[0] for call in provider.search.await_args_list]
        assert searched_queries[0] == "original topic"
        assert "expanded query 1" in searched_queries


class TestSearchEngineWithClaude:
    """Tests for SearchEngine with Claude integration."""

    @pytest.fixture
    def mock_anthropic(self):
        """Create a mock Anthropic client."""
        mock = MagicMock()
        mock.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"queries": ["query1", "query2"], "suggested_keywords": ["kw1"], "reasoning": "test"}')]
        )
        return mock

    @pytest.fixture
    def engine_with_claude(self, mock_anthropic):
        """Create a SearchEngine with mocked Claude."""
        engine = SearchEngine(providers=[], anthropic_api_key=None)
        engine._anthropic = mock_anthropic
        return engine

    @pytest.mark.asyncio
    async def test_expand_query_with_claude(self, engine_with_claude):
        """Test query expansion with Claude."""
        expansion = await engine_with_claude.expand_query("battery materials")

        assert "queries" in expansion
        assert len(expansion["queries"]) >= 1

    @pytest.mark.asyncio
    async def test_score_relevance(self, engine_with_claude, mock_anthropic):
        """Test relevance scoring with Claude."""
        mock_anthropic.messages.create.return_value = MagicMock(
            content=[MagicMock(text='{"scores": [{"paper_index": 0, "score": 0.8, "reasoning": "relevant"}]}')]
        )

        results = [
            SearchResult(
                title="Relevant Paper",
                authors=[],
                abstract="About batteries",
                source="test",
            )
        ]

        scored = await engine_with_claude.score_relevance(results, "battery research")

        assert len(scored) == 1
        assert scored[0].relevance_score == 0.8


class TestSearchEngineFiltering:
    """Tests for relevance filtering."""

    @pytest.fixture
    def engine(self):
        """Create a SearchEngine without providers."""
        return SearchEngine(providers=[], anthropic_api_key=None)

    @pytest.mark.asyncio
    async def test_filter_by_relevance_no_claude(self, engine):
        """Test filtering without Claude (returns as-is)."""
        results = [
            SearchResult(
                title="Paper A",
                authors=[],
                relevance_score=0.3,
                source="test",
            ),
            SearchResult(
                title="Paper B",
                authors=[],
                relevance_score=0.7,
                source="test",
            ),
        ]

        # Without Claude, should return results sorted by existing score
        filtered = await engine.filter_by_relevance(
            results, "test topic", threshold=0.5, max_results=10
        )

        # Without Claude scoring, original scores are preserved
        assert len(filtered) >= 1
