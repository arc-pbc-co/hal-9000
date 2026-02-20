"""arXiv API provider for paper search."""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import urlencode

import httpx

from hal9000.acquisition.providers.base import BaseProvider, SearchResult

logger = logging.getLogger(__name__)

# arXiv API base URL
API_BASE = "https://export.arxiv.org/api/query"

# XML namespaces used in arXiv API responses
NAMESPACES = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


class ArxivProvider(BaseProvider):
    """Search provider using arXiv API.

    arXiv provides free access to preprints in physics, mathematics,
    computer science, and related fields. All papers have directly
    accessible PDF URLs.

    Rate limit: 1 request per 3 seconds (be polite to the service).
    """

    def __init__(self):
        """Initialize the provider."""
        self._rate_limit_delay = 3.0  # seconds between requests

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "arxiv"

    def _extract_arxiv_id(self, entry_id: str) -> str:
        """Extract arXiv ID from entry URL.

        Args:
            entry_id: Full arXiv URL (e.g., "http://arxiv.org/abs/2301.00001v1")

        Returns:
            arXiv ID (e.g., "2301.00001")
        """
        # Extract ID from URL like http://arxiv.org/abs/2301.00001v1
        match = re.search(r"arxiv.org/abs/(.+?)(?:v\d+)?$", entry_id)
        if match:
            return match.group(1)
        # Already just an ID - remove version suffix like v1, v2, etc.
        arxiv_id = entry_id.split("/")[-1]
        # Remove version suffix (v followed by digits at the end)
        version_match = re.match(r"(.+?)v\d+$", arxiv_id)
        if version_match:
            return version_match.group(1)
        return arxiv_id

    def _parse_entry(self, entry: ET.Element) -> SearchResult:
        """Parse an arXiv API entry into SearchResult."""
        # Extract basic fields
        title = entry.find("atom:title", NAMESPACES)
        title_text = title.text.strip().replace("\n", " ") if title is not None else "Unknown"

        summary = entry.find("atom:summary", NAMESPACES)
        abstract = summary.text.strip() if summary is not None else None

        # Extract authors
        authors = []
        for author in entry.findall("atom:author", NAMESPACES):
            name = author.find("atom:name", NAMESPACES)
            if name is not None and name.text:
                authors.append(name.text)

        # Extract publication date (year)
        published = entry.find("atom:published", NAMESPACES)
        year = None
        if published is not None and published.text:
            year = int(published.text[:4])

        # Extract arXiv ID from entry ID
        entry_id = entry.find("atom:id", NAMESPACES)
        arxiv_id = ""
        if entry_id is not None and entry_id.text:
            arxiv_id = self._extract_arxiv_id(entry_id.text)

        # Construct PDF URL
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        # Extract DOI if available
        doi = None
        doi_elem = entry.find("arxiv:doi", NAMESPACES)
        if doi_elem is not None and doi_elem.text:
            doi = doi_elem.text

        # Extract categories for external_ids
        categories = []
        for category in entry.findall("atom:category", NAMESPACES):
            term = category.get("term")
            if term:
                categories.append(term)

        return SearchResult(
            title=title_text,
            authors=authors,
            abstract=abstract,
            year=year,
            doi=doi,
            arxiv_id=arxiv_id,
            pdf_url=pdf_url,
            source=self.name,
            external_ids={
                "arxiv_id": arxiv_id,
                "categories": ",".join(categories),
            },
        )

    async def search(self, query: str, max_results: int = 20) -> list[SearchResult]:
        """Search for papers on arXiv.

        Args:
            query: Search query string
            max_results: Maximum number of results

        Returns:
            List of SearchResult objects
        """
        # Build query parameters
        # arXiv uses a specific query syntax
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        url = f"{API_BASE}?{urlencode(params)}"
        results = []

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

                # Parse XML response
                root = ET.fromstring(response.text)

                # Find all entries
                for entry in root.findall("atom:entry", NAMESPACES):
                    try:
                        result = self._parse_entry(entry)
                        results.append(result)
                    except Exception as e:
                        logger.warning(f"Failed to parse arXiv entry: {e}")
                        continue

                logger.info(f"arXiv: Found {len(results)} papers for '{query}'")

        except httpx.HTTPStatusError as e:
            logger.error(f"arXiv API error: {e}")
        except ET.ParseError as e:
            logger.error(f"Failed to parse arXiv XML: {e}")
        except Exception as e:
            logger.error(f"arXiv search failed: {e}")

        return results

    async def get_paper_details(self, paper_id: str) -> Optional[SearchResult]:
        """Get detailed information about a specific paper.

        Args:
            paper_id: arXiv paper ID (e.g., "2301.00001")

        Returns:
            SearchResult with full details, or None if not found
        """
        params = {
            "id_list": paper_id,
            "max_results": 1,
        }

        url = f"{API_BASE}?{urlencode(params)}"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

                root = ET.fromstring(response.text)
                entries = root.findall("atom:entry", NAMESPACES)

                if entries:
                    return self._parse_entry(entries[0])

        except Exception as e:
            logger.error(f"Failed to get arXiv paper details: {e}")

        return None

    async def search_by_category(
        self, category: str, query: str = "", max_results: int = 20
    ) -> list[SearchResult]:
        """Search for papers in a specific arXiv category.

        Args:
            category: arXiv category (e.g., "cond-mat.mtrl-sci", "cs.AI")
            query: Optional additional search query
            max_results: Maximum number of results

        Returns:
            List of SearchResult objects
        """
        search_query = f"cat:{category}"
        if query:
            search_query = f"{search_query} AND all:{query}"

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        url = f"{API_BASE}?{urlencode(params)}"
        results = []

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()

                root = ET.fromstring(response.text)
                for entry in root.findall("atom:entry", NAMESPACES):
                    try:
                        result = self._parse_entry(entry)
                        results.append(result)
                    except Exception as e:
                        logger.warning(f"Failed to parse arXiv entry: {e}")
                        continue

        except Exception as e:
            logger.error(f"arXiv category search failed: {e}")

        return results

    async def get_rate_limit_delay(self) -> float:
        """Get the recommended delay between requests."""
        return self._rate_limit_delay
