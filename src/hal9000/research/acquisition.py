"""Acquisition runner seam for bounded research workers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Callable, Protocol

ProgressCallback = Callable[[str, int, int], None]
LLMCallCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class WorkerAcquisitionResult:
    """Summary of acquisition work performed for a run."""

    papers_found: int = 0
    papers_downloaded: int = 0
    papers_processed: int = 0
    duplicates_skipped: int = 0
    download_failures: int = 0
    processing_failures: int = 0
    document_ids: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    progress_events: list[dict[str, object]] = field(default_factory=list)
    llm_calls: int = 0

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe payload."""
        return {
            "papers_found": self.papers_found,
            "papers_downloaded": self.papers_downloaded,
            "papers_processed": self.papers_processed,
            "duplicates_skipped": self.duplicates_skipped,
            "download_failures": self.download_failures,
            "processing_failures": self.processing_failures,
            "document_ids": self.document_ids,
            "errors": self.errors,
            "progress_events": self.progress_events,
            "llm_calls": self.llm_calls,
        }


class AcquisitionRunner(Protocol):
    """Protocol for live or fake acquisition implementations."""

    def acquire(
        self,
        topic: str,
        max_papers: int,
        progress_callback: ProgressCallback | None = None,
        llm_call_callback: LLMCallCallback | None = None,
    ) -> WorkerAcquisitionResult:
        """Acquire documents for a research topic."""
        ...


class LiveAcquisitionRunner:
    """Run HAL's live acquisition orchestrator from the bounded worker."""

    def __init__(self, settings, db_session):
        """Initialize with app settings and an existing DB session."""
        self.settings = settings
        self.db_session = db_session

    def acquire(
        self,
        topic: str,
        max_papers: int,
        progress_callback: ProgressCallback | None = None,
        llm_call_callback: LLMCallCallback | None = None,
    ) -> WorkerAcquisitionResult:
        """Search, download, and process papers through the acquisition stack."""
        from hal9000.acquisition.orchestrator import AcquisitionOrchestrator
        from hal9000.ingest import PDFProcessor
        from hal9000.rlm import RLMProcessor

        orchestrator = AcquisitionOrchestrator(
            settings=self.settings,
            db_session=self.db_session,
            pdf_processor=PDFProcessor(),
            rlm_processor=RLMProcessor(
                api_key=self.settings.anthropic_api_key,
                chunk_size=self.settings.processing.chunk_size,
                max_concurrent_calls=self.settings.processing.max_concurrent_calls,
                llm_call_callback=llm_call_callback,
            ),
        )
        progress_events: list[dict[str, object]] = []

        def record_progress(stage: str, current: int, total: int) -> None:
            event = {"stage": stage, "current": current, "total": total}
            progress_events.append(event)
            if progress_callback:
                progress_callback(stage, current, total)

        result = asyncio.run(
            orchestrator.acquire(
                topic=topic,
                max_papers=max_papers,
                process_papers=True,
                generate_notes=False,
                relevance_threshold=self.settings.acquisition.relevance_threshold,
                sources=self.settings.acquisition.default_sources,
                progress_callback=record_progress,
            )
        )
        return WorkerAcquisitionResult(
            papers_found=result.papers_found,
            papers_downloaded=result.papers_downloaded,
            papers_processed=result.papers_processed,
            duplicates_skipped=result.duplicates_skipped,
            download_failures=result.download_failures,
            processing_failures=result.processing_failures,
            document_ids=[document.id for document in result.documents],
            errors=result.errors,
            progress_events=progress_events,
            llm_calls=getattr(orchestrator.rlm_processor, "llm_calls_made", 0),
        )
