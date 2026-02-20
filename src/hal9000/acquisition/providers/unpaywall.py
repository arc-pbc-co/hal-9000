"""Unpaywall API provider for open access PDF resolution."""

import logging
from typing import Optional

import httpx

from hal9000.acquisition.providers.base import BaseProvider, SearchResult

logger = logging.getLogger(__name__)

# Unpaywall API base URL
API_BASE = "https://api.unpaywall.org/v2"


class UnpaywallProvider(BaseProvider):
    """Provider for resolving DOIs to open access PDF URLs.

    Unpaywall finds legal, open-access versions of academic papers.
    It searches multiple sources including publisher sites, repositories,
    and preprint servers.

    Rate limit: 100,000 requests per day (free tier).
    Requires an email address for identification.
    """

    def __init__(self, email: str):
        """Initialize the provider.

        Args:
            email: Email address for API identification (required)
        """
        if not email:
            raise ValueError("Email address is required for Unpaywall API")
        self.email = email
        self._rate_limit_delay = 0.1  # Be polite, but Unpaywall is fast

    @property
    def name(self) -> str:
        """Return the provider name."""
        return "unpaywall"

    async def search(self, query: str, max_results: int = 20) -> list[SearchResult]:
        """Unpaywall doesn't support text search.

        Use resolve_doi() instead for DOI-based lookups.

        Args:
            query: Search query (not supported)
            max_results: Maximum results (not supported)

        Returns:
            Empty list (search not supported)
        """
        logger.warning("Unpaywall does not support text search. Use resolve_doi() instead.")
        return []

    async def get_paper_details(self, paper_id: str) -> Optional[SearchResult]:
        """Get paper details by DOI.

        Args:
            paper_id: DOI of the paper

        Returns:
            SearchResult with open access info, or None if not found
        """
        return await self.resolve_doi(paper_id)

    async def resolve_doi(self, doi: str) -> Optional[SearchResult]:
        """Resolve a DOI to find open access PDF URL.

        Args:
            doi: DOI of the paper (e.g., "10.1234/example")

        Returns:
            SearchResult with PDF URL if OA version found, None otherwise
        """
        # Clean DOI
        doi = doi.strip()
        if doi.startswith("https://doi.org/"):
            doi = doi.replace("https://doi.org/", "")
        if doi.startswith("doi:"):
            doi = doi.replace("doi:", "")

        url = f"{API_BASE}/{doi}"
        params = {"email": self.email}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)

                if response.status_code == 404:
                    logger.debug(f"DOI not found in Unpaywall: {doi}")
                    return None

                response.raise_for_status()
                data = response.json()

                # Check if open access
                if not data.get("is_oa"):
                    logger.debug(f"No open access version found for: {doi}")
                    return None

                # Extract best open access location.
                # Only use explicit PDF URLs to avoid landing pages that are
                # frequently blocked and not directly downloadable.
                pdf_url = None
                oa_location = data.get("best_oa_location")
                if oa_location:
                    pdf_url = oa_location.get("url_for_pdf")

                if not pdf_url:
                    # Try other OA locations
                    for location in data.get("oa_locations", []):
                        if location.get("url_for_pdf"):
                            pdf_url = location["url_for_pdf"]
                            break

                if not pdf_url:
                    logger.debug(f"Open access but no PDF URL found for: {doi}")
                    return None

                # Extract authors
                authors = []
                for author in data.get("z_authors", []) or []:
                    name_parts = []
                    if author.get("given"):
                        name_parts.append(author["given"])
                    if author.get("family"):
                        name_parts.append(author["family"])
                    if name_parts:
                        authors.append(" ".join(name_parts))

                return SearchResult(
                    title=data.get("title", "Unknown Title"),
                    authors=authors,
                    year=data.get("year"),
                    doi=doi,
                    pdf_url=pdf_url,
                    source=self.name,
                    external_ids={
                        "unpaywall": doi,
                        "oa_status": data.get("oa_status", "unknown"),
                        "is_oa": str(data.get("is_oa", False)),
                    },
                )

        except httpx.HTTPStatusError as e:
            logger.error(f"Unpaywall API error for {doi}: {e}")
        except Exception as e:
            logger.error(f"Failed to resolve DOI {doi}: {e}")

        return None

    async def resolve_pdf_url(self, result: SearchResult) -> Optional[str]:
        """Resolve PDF URL for a search result using its DOI.

        Args:
            result: SearchResult to resolve PDF URL for

        Returns:
            PDF URL if found, None otherwise
        """
        if result.pdf_url:
            return result.pdf_url

        if not result.doi:
            return None

        resolved = await self.resolve_doi(result.doi)
        if resolved and resolved.pdf_url:
            return resolved.pdf_url

        return None

    async def batch_resolve(
        self, dois: list[str]
    ) -> dict[str, Optional[SearchResult]]:
        """Resolve multiple DOIs.

        Args:
            dois: List of DOIs to resolve

        Returns:
            Dictionary mapping DOIs to SearchResults (or None if not found)
        """
        results = {}
        for doi in dois:
            results[doi] = await self.resolve_doi(doi)
            # Small delay between requests
            import asyncio
            await asyncio.sleep(self._rate_limit_delay)
        return results

    async def get_rate_limit_delay(self) -> float:
        """Get the recommended delay between requests."""
        return self._rate_limit_delay
