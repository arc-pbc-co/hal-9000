"""Tests for acquisition orchestrator URL resolution behavior."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from hal9000.acquisition.downloader import DownloadResult
from hal9000.acquisition.orchestrator import AcquisitionOrchestrator
from hal9000.acquisition.providers.base import SearchResult
from hal9000.config import Settings


class TestAcquisitionOrchestrator:
    """Tests for orchestrator PDF URL resolution."""

    @pytest.mark.asyncio
    async def test_resolve_pdf_urls_prefers_unpaywall_for_non_pdf_links(self):
        settings = Settings()
        orchestrator = AcquisitionOrchestrator(settings=settings)
        orchestrator.unpaywall = AsyncMock()
        orchestrator.unpaywall.resolve_doi = AsyncMock(
            return_value=SearchResult(
                title="Resolved",
                authors=[],
                doi="10.1234/test",
                pdf_url="https://repository.example.org/paper.pdf",
                source="unpaywall",
            )
        )

        results = [
            SearchResult(
                title="Original",
                authors=[],
                doi="10.1234/test",
                pdf_url="https://www.sciencedirect.com/science/article/pii/example",
                source="semantic_scholar",
            )
        ]

        resolved = await orchestrator._resolve_pdf_urls(results)

        assert resolved[0].pdf_url == "https://repository.example.org/paper.pdf"
        orchestrator.unpaywall.resolve_doi.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resolve_pdf_urls_keeps_existing_direct_pdf(self):
        settings = Settings()
        orchestrator = AcquisitionOrchestrator(settings=settings)
        orchestrator.unpaywall = AsyncMock()
        orchestrator.unpaywall.resolve_doi = AsyncMock(return_value=None)

        results = [
            SearchResult(
                title="Direct PDF",
                authors=[],
                doi="10.1234/test",
                pdf_url="https://example.org/paper.pdf",
                source="arxiv",
            )
        ]

        resolved = await orchestrator._resolve_pdf_urls(results)

        assert resolved[0].pdf_url == "https://example.org/paper.pdf"
        orchestrator.unpaywall.resolve_doi.assert_not_called()

    @pytest.mark.asyncio
    async def test_acquire_retries_download_with_unpaywall_url(self, tmp_path):
        settings = Settings(acquisition={"download_dir": str(tmp_path)})
        orchestrator = AcquisitionOrchestrator(settings=settings)

        search_result = SearchResult(
            title="Retry DOI paper",
            authors=[],
            doi="10.1234/test",
            pdf_url="https://blocked.example.org/paper.pdf",
            source="arxiv",
        )
        orchestrator.search_engine.search_and_filter = AsyncMock(return_value=[search_result])
        orchestrator.validator.is_duplicate_by_doi = MagicMock(return_value=False)
        orchestrator.validator.is_duplicate_by_hash = MagicMock(return_value=False)

        successful_path = Path(tmp_path) / "paper.pdf"
        successful_path.write_bytes(b"%PDF-1.4\n%%EOF")

        orchestrator.download_manager.download = AsyncMock(
            side_effect=[
                DownloadResult(
                    success=False,
                    local_path=None,
                    source_url=search_result.pdf_url or "",
                    error="Failed after 3 attempts",
                ),
                DownloadResult(
                    success=True,
                    local_path=successful_path,
                    source_url="https://repository.example.org/paper.pdf",
                    file_hash=None,
                ),
            ]
        )

        orchestrator.unpaywall = AsyncMock()
        orchestrator.unpaywall.resolve_doi = AsyncMock(
            return_value=SearchResult(
                title="Resolved",
                authors=[],
                doi="10.1234/test",
                pdf_url="https://repository.example.org/paper.pdf",
                source="unpaywall",
            )
        )

        result = await orchestrator.acquire(
            topic="retry topic",
            max_papers=1,
            process_papers=False,
            generate_notes=False,
        )

        assert result.papers_downloaded == 1
        assert result.download_failures == 0
        assert orchestrator.download_manager.download.await_count == 2
