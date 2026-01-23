"""Search providers for paper acquisition."""

from hal9000.acquisition.providers.base import BaseProvider, SearchResult
from hal9000.acquisition.providers.semantic_scholar import SemanticScholarProvider
from hal9000.acquisition.providers.arxiv import ArxivProvider
from hal9000.acquisition.providers.unpaywall import UnpaywallProvider

__all__ = [
    "BaseProvider",
    "SearchResult",
    "SemanticScholarProvider",
    "ArxivProvider",
    "UnpaywallProvider",
]
