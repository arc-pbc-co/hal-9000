"""Semantic Scholar API provider for paper search."""

import asyncio
import logging
from typing import Optional

import httpx

from hal9000.acquisition.providers.base import BaseProvider, SearchResult

logger = logging.getLogger(__name__)

# Semantic Scholar API base URL
API_BASE = "https://api.semanticscholar.org/graph/v1"

# Fields to request from the API
SEARCH_FIELDS = [
    "paperId",
    "title",
    "abstract",
    "year",
    "authors",
    "citationCount",
    "externalIds",
    "openAccessPdf",
    "url",
]


class SemanticScholarProvider(BaseProvider):
    """Search provider using Semantic Scholar API.

    Semantic Scholar provides excellent relevance ranking and comprehensive
    coverage across many academic fields. It includes citation metrics and
    often has direct links to open access PDFs.

    Rate limit: 100 requests per 5 minutes for unauthenticated requests.
    With API key: 1 request per second.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the provider.

        Args:
            api_key: Optional Semantic Scholar API key for higher rate limits
        """
        self.api_key = api_key
        self._rate_limit_delay = 0.5 if api_key else 3.0  # seconds between requests
        self._max_retries = 3

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "semantic_scholar"

    def _get_headers(self) -> dict[str, str]:
        """Get request headers."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers

    def _parse_result(self, data: dict) -> SearchResult:
        """Parse API response into SearchResult."""
        # Extract authors
        authors = []
        if data.get("authors"):
            authors = [a.get("name", "") for a in data["authors"] if a.get("name")]

        # Extract external IDs
        external_ids = data.get("externalIds") or {}
        doi = external_ids.get("DOI")
        arxiv_id = external_ids.get("ArXiv")

        # Extract PDF URL from openAccessPdf
        pdf_url = None
        if data.get("openAccessPdf"):
            pdf_url = data["openAccessPdf"].get("url")

        return SearchResult(
            title=data.get("title", "Unknown Title"),
            authors=authors,
            abstract=data.get("abstract"),
            year=data.get("year"),
            doi=doi,
            arxiv_id=arxiv_id,
            pdf_url=pdf_url,
            source=self.name,
            citation_count=data.get("citationCount"),
            external_ids={
                "semantic_scholar_id": data.get("paperId", ""),
                **{k: v for k, v in external_ids.items() if v},
            },
        )

    async def search(self, query: str, max_results: int = 20) -> list[SearchResult]:
        """Search for papers using Semantic Scholar API.

        Args:
            query: Search query string
            max_results: Maximum number of results (up to 100)

        Returns:
            List of SearchResult objects
        """
        max_results = min(max_results, 100)  # API limit

        url = f"{API_BASE}/paper/search"
        params = {
            "query": query,
            "limit": max_results,
            "fields": ",".join(SEARCH_FIELDS),
        }

        results = []

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = None
                for attempt in range(self._max_retries):
                    response = await client.get(
                        url, params=params, headers=self._get_headers()
                    )

                    if response.status_code != 429:
                        break

                    # Prefer provider hint, then exponential fallback.
                    retry_after = response.headers.get("retry-after")
                    if retry_after and retry_after.isdigit():
                        wait_time = float(retry_after)
                    else:
                        wait_time = max(self._rate_limit_delay, float(2 ** attempt))

                    if attempt < self._max_retries - 1:
                        logger.warning(
                            "Semantic Scholar rate limit exceeded, retrying in %.1fs "
                            "(attempt %d/%d)",
                            wait_time,
                            attempt + 1,
                            self._max_retries,
                        )
                        await asyncio.sleep(wait_time)
                        continue

                    logger.warning("Semantic Scholar rate limit exceeded")

                if response is None:
                    return results
                if response.status_code == 429:
                    return results

                response.raise_for_status()
                data = response.json()

                papers = data.get("data", [])
                for paper in papers:
                    try:
                        result = self._parse_result(paper)
                        results.append(result)
                    except Exception as e:
                        logger.warning(f"Failed to parse paper: {e}")
                        continue

                logger.info(f"Semantic Scholar: Found {len(results)} papers for '{query}'")

        except httpx.HTTPStatusError as e:
            logger.error(f"Semantic Scholar API error: {e}")
        except Exception as e:
            logger.error(f"Semantic Scholar search failed: {e}")

        return results

    async def get_paper_details(self, paper_id: str) -> Optional[SearchResult]:
        """Get detailed information about a specific paper.

        Args:
            paper_id: Semantic Scholar paper ID

        Returns:
            SearchResult with full details, or None if not found
        """
        url = f"{API_BASE}/paper/{paper_id}"
        params = {"fields": ",".join(SEARCH_FIELDS)}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url, params=params, headers=self._get_headers()
                )
                response.raise_for_status()
                data = response.json()
                return self._parse_result(data)

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Paper not found: {paper_id}")
            else:
                logger.error(f"Semantic Scholar API error: {e}")
        except Exception as e:
            logger.error(f"Failed to get paper details: {e}")

        return None

    async def search_by_doi(self, doi: str) -> Optional[SearchResult]:
        """Search for a paper by DOI.

        Args:
            doi: DOI of the paper (e.g., "10.1234/example")

        Returns:
            SearchResult if found, None otherwise
        """
        return await self.get_paper_details(f"DOI:{doi}")

    async def search_by_arxiv(self, arxiv_id: str) -> Optional[SearchResult]:
        """Search for a paper by arXiv ID.

        Args:
            arxiv_id: arXiv ID (e.g., "2301.00001")

        Returns:
            SearchResult if found, None otherwise
        """
        return await self.get_paper_details(f"ARXIV:{arxiv_id}")

    async def get_rate_limit_delay(self) -> float:
        """Get the recommended delay between requests."""
        return self._rate_limit_delay
