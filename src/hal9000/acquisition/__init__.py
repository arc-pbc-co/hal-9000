"""Paper acquisition module for HAL 9000.

This module provides functionality to search for and download research papers
from academic databases like Semantic Scholar and arXiv.
"""

from hal9000.acquisition.providers.base import SearchResult
from hal9000.acquisition.downloader import DownloadManager, DownloadResult
from hal9000.acquisition.validator import PDFValidator
from hal9000.acquisition.search import SearchEngine
from hal9000.acquisition.orchestrator import AcquisitionOrchestrator, AcquisitionResult

__all__ = [
    "SearchResult",
    "DownloadManager",
    "DownloadResult",
    "PDFValidator",
    "SearchEngine",
    "AcquisitionOrchestrator",
    "AcquisitionResult",
]
