"""Tests for search providers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hal9000.acquisition.providers.arxiv import API_BASE as ARXIV_API_BASE
from hal9000.acquisition.providers.arxiv import ArxivProvider
from hal9000.acquisition.providers.base import SearchResult
from hal9000.acquisition.providers.semantic_scholar import SemanticScholarProvider
from hal9000.acquisition.providers.unpaywall import UnpaywallProvider


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_creation(self):
        """Test basic SearchResult creation."""
        result = SearchResult(
            title="Test Paper",
            authors=["John Doe", "Jane Smith"],
            abstract="This is a test abstract.",
            year=2024,
            doi="10.1234/test",
            source="test",
        )
        assert result.title == "Test Paper"
        assert len(result.authors) == 2
        assert result.year == 2024

    def test_doi_normalization(self):
        """Test DOI URL prefix is removed."""
        result = SearchResult(
            title="Test",
            authors=[],
            doi="https://doi.org/10.1234/test",
            source="test",
        )
        assert result.doi == "10.1234/test"

    def test_has_pdf(self):
        """Test has_pdf property."""
        result_with_pdf = SearchResult(
            title="Test",
            authors=[],
            pdf_url="https://example.com/paper.pdf",
            source="test",
        )
        result_without_pdf = SearchResult(
            title="Test",
            authors=[],
            source="test",
        )
        assert result_with_pdf.has_pdf is True
        assert result_without_pdf.has_pdf is False

    def test_identifier(self):
        """Test identifier property returns best available ID."""
        # DOI preferred
        result = SearchResult(
            title="Test",
            authors=[],
            doi="10.1234/test",
            arxiv_id="2301.00001",
            source="test",
        )
        assert result.identifier == "doi:10.1234/test"

        # arXiv if no DOI
        result2 = SearchResult(
            title="Test",
            authors=[],
            arxiv_id="2301.00001",
            source="test",
        )
        assert result2.identifier == "arxiv:2301.00001"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = SearchResult(
            title="Test Paper",
            authors=["John Doe"],
            year=2024,
            source="test",
        )
        d = result.to_dict()
        assert d["title"] == "Test Paper"
        assert d["authors"] == ["John Doe"]
        assert d["year"] == 2024


class TestSemanticScholarProvider:
    """Tests for SemanticScholarProvider."""

    @pytest.fixture
    def provider(self):
        """Create a provider instance."""
        return SemanticScholarProvider()

    def test_name(self, provider):
        """Test provider name."""
        assert provider.name == "semantic_scholar"

    @pytest.mark.asyncio
    async def test_search_success(self, provider):
        """Test successful search."""
        mock_response = {
            "data": [
                {
                    "paperId": "abc123",
                    "title": "Test Paper",
                    "abstract": "Test abstract",
                    "year": 2024,
                    "authors": [{"name": "John Doe"}],
                    "citationCount": 10,
                    "externalIds": {"DOI": "10.1234/test"},
                    "openAccessPdf": {"url": "https://example.com/paper.pdf"},
                }
            ]
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            results = await provider.search("test query", max_results=10)

            assert len(results) == 1
            assert results[0].title == "Test Paper"
            assert results[0].doi == "10.1234/test"
            assert results[0].pdf_url == "https://example.com/paper.pdf"

    @pytest.mark.asyncio
    async def test_search_empty_results(self, provider):
        """Test search with no results."""
        mock_response = {"data": []}

        with patch("httpx.AsyncClient") as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            results = await provider.search("nonexistent topic", max_results=10)
            assert len(results) == 0


class TestArxivProvider:
    """Tests for ArxivProvider."""

    @pytest.fixture
    def provider(self):
        """Create a provider instance."""
        return ArxivProvider()

    def test_name(self, provider):
        """Test provider name."""
        assert provider.name == "arxiv"
        assert ARXIV_API_BASE.startswith("https://")

    def test_extract_arxiv_id(self, provider):
        """Test arXiv ID extraction from URLs."""
        assert provider._extract_arxiv_id("http://arxiv.org/abs/2301.00001v1") == "2301.00001"
        assert provider._extract_arxiv_id("http://arxiv.org/abs/2301.00001") == "2301.00001"
        assert provider._extract_arxiv_id("2301.00001") == "2301.00001"

    @pytest.mark.asyncio
    async def test_search_success(self, provider):
        """Test successful arXiv search."""
        mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
            <entry>
                <id>http://arxiv.org/abs/2301.00001v1</id>
                <title>Test Paper Title</title>
                <summary>This is a test abstract.</summary>
                <author><name>John Doe</name></author>
                <published>2024-01-15T00:00:00Z</published>
                <category term="cs.AI"/>
            </entry>
        </feed>
        """

        with patch("httpx.AsyncClient") as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.text = mock_xml
            mock_response_obj.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            results = await provider.search("machine learning", max_results=10)

            assert len(results) == 1
            assert results[0].title == "Test Paper Title"
            assert results[0].arxiv_id == "2301.00001"
            assert results[0].pdf_url == "https://arxiv.org/pdf/2301.00001.pdf"


class TestUnpaywallProvider:
    """Tests for UnpaywallProvider."""

    @pytest.fixture
    def provider(self):
        """Create a provider instance."""
        return UnpaywallProvider(email="test@example.com")

    def test_name(self, provider):
        """Test provider name."""
        assert provider.name == "unpaywall"

    def test_requires_email(self):
        """Test that email is required."""
        with pytest.raises(ValueError):
            UnpaywallProvider(email="")

    @pytest.mark.asyncio
    async def test_search_not_supported(self, provider):
        """Test that text search returns empty list."""
        results = await provider.search("test query")
        assert results == []

    @pytest.mark.asyncio
    async def test_resolve_doi_success(self, provider):
        """Test successful DOI resolution."""
        mock_response = {
            "is_oa": True,
            "title": "Test Paper",
            "year": 2024,
            "best_oa_location": {
                "url_for_pdf": "https://example.com/paper.pdf",
            },
            "z_authors": [{"given": "John", "family": "Doe"}],
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            result = await provider.resolve_doi("10.1234/test")

            assert result is not None
            assert result.pdf_url == "https://example.com/paper.pdf"
            assert result.title == "Test Paper"

    @pytest.mark.asyncio
    async def test_resolve_doi_not_open_access(self, provider):
        """Test DOI resolution for non-OA paper."""
        mock_response = {
            "is_oa": False,
            "title": "Closed Access Paper",
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            result = await provider.resolve_doi("10.1234/closed")
            assert result is None

    @pytest.mark.asyncio
    async def test_resolve_doi_requires_direct_pdf_url(self, provider):
        """Test DOI resolution ignores non-PDF landing page URLs."""
        mock_response = {
            "is_oa": True,
            "title": "Landing Page Only",
            "year": 2024,
            "best_oa_location": {
                "url": "https://example.com/landing-page",
            },
            "oa_locations": [
                {"url": "https://example.com/another-landing-page"},
            ],
        }

        with patch("httpx.AsyncClient") as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()

            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            result = await provider.resolve_doi("10.1234/landing")
            assert result is None


class TestSemanticScholarRetry:
    """Retry behavior for Semantic Scholar provider."""

    @pytest.mark.asyncio
    async def test_search_retries_after_429(self):
        provider = SemanticScholarProvider(api_key="test-key")

        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"retry-after": "0"}

        success = MagicMock()
        success.status_code = 200
        success.headers = {}
        success.raise_for_status = MagicMock()
        success.json.return_value = {"data": []}

        with patch("httpx.AsyncClient") as mock_client, patch(
            "asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(side_effect=[rate_limited, success])
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            results = await provider.search("binder jet", max_results=5)

            assert results == []
            assert mock_client_instance.get.await_count == 2
            assert mock_sleep.await_count == 1
