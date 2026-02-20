"""Base provider interface for paper search."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    """Standardized search result from any provider."""

    title: str
    authors: list[str]
    abstract: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pdf_url: Optional[str] = None
    source: str = ""  # Provider name (e.g., "semantic_scholar", "arxiv")
    relevance_score: float = 0.0
    citation_count: Optional[int] = None
    external_ids: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize fields after initialization."""
        # Ensure authors is a list
        if self.authors is None:
            self.authors = []
        # Normalize DOI (remove URL prefix if present)
        if self.doi and self.doi.startswith("https://doi.org/"):
            self.doi = self.doi.replace("https://doi.org/", "")

    @property
    def has_pdf(self) -> bool:
        """Check if a PDF URL is available."""
        return bool(self.pdf_url)

    @property
    def identifier(self) -> str:
        """Get the best available identifier for this paper."""
        if self.doi:
            return f"doi:{self.doi}"
        if self.arxiv_id:
            return f"arxiv:{self.arxiv_id}"
        if self.external_ids:
            for key, value in self.external_ids.items():
                return f"{key}:{value}"
        return f"title:{self.title[:50]}"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "year": self.year,
            "doi": self.doi,
            "arxiv_id": self.arxiv_id,
            "pdf_url": self.pdf_url,
            "source": self.source,
            "relevance_score": self.relevance_score,
            "citation_count": self.citation_count,
            "external_ids": self.external_ids,
        }


class BaseProvider(ABC):
    """Abstract base class for paper search providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name."""
        ...

    @abstractmethod
    async def search(self, query: str, max_results: int = 20) -> list[SearchResult]:
        """Search for papers matching the query.

        Args:
            query: Search query string
            max_results: Maximum number of results to return

        Returns:
            List of SearchResult objects
        """
        ...

    @abstractmethod
    async def get_paper_details(self, paper_id: str) -> Optional[SearchResult]:
        """Get detailed information about a specific paper.

        Args:
            paper_id: Provider-specific paper identifier

        Returns:
            SearchResult with full details, or None if not found
        """
        ...

    async def resolve_pdf_url(self, result: SearchResult) -> Optional[str]:
        """Attempt to resolve a PDF URL for a search result.

        Override this method in providers that can resolve PDF URLs
        from DOIs or other identifiers.

        Args:
            result: SearchResult to resolve PDF URL for

        Returns:
            PDF URL if found, None otherwise
        """
        return result.pdf_url

    async def get_rate_limit_delay(self) -> float:
        """Get recommended delay between requests to this provider."""
        return 0.0
