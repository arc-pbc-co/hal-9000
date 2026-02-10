"""Orchestrator for the paper acquisition workflow."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from hal9000.acquisition.downloader import DownloadManager, DownloadResult
from hal9000.acquisition.providers import (
    ArxivProvider,
    SemanticScholarProvider,
    UnpaywallProvider,
)
from hal9000.acquisition.providers.base import SearchResult
from hal9000.acquisition.search import SearchEngine
from hal9000.acquisition.validator import PDFValidator

if TYPE_CHECKING:
    from hal9000.config import Settings
    from hal9000.db.models import Document
    from hal9000.ingest import PDFProcessor
    from hal9000.obsidian import VaultManager
    from hal9000.rlm import RLMProcessor

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


@dataclass
class AcquisitionResult:
    """Result of an acquisition session."""

    topic: str
    session_id: str
    session_dir: Path

    # Counts
    papers_found: int = 0
    papers_downloaded: int = 0
    papers_processed: int = 0
    duplicates_skipped: int = 0
    download_failures: int = 0
    processing_failures: int = 0

    # Details
    search_results: list[SearchResult] = field(default_factory=list)
    download_results: list[DownloadResult] = field(default_factory=list)
    documents: list["Document"] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    # Timing
    started_at: datetime = field(default_factory=utc_now)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "topic": self.topic,
            "session_id": self.session_id,
            "session_dir": str(self.session_dir),
            "papers_found": self.papers_found,
            "papers_downloaded": self.papers_downloaded,
            "papers_processed": self.papers_processed,
            "duplicates_skipped": self.duplicates_skipped,
            "download_failures": self.download_failures,
            "processing_failures": self.processing_failures,
            "errors": self.errors,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    def save_log(self) -> Path:
        """Save session log to the session directory."""
        log_path = self.session_dir / "session_log.json"
        with open(log_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return log_path


class AcquisitionOrchestrator:
    """Coordinates the full paper acquisition workflow.

    The orchestrator manages the complete pipeline:
    1. Search for papers using Claude-enhanced queries
    2. Filter by relevance
    3. Resolve PDF URLs (including via Unpaywall)
    4. Download PDFs
    5. Validate and deduplicate
    6. Process through RLM pipeline
    7. Generate Obsidian notes
    """

    def __init__(
        self,
        settings: "Settings",
        db_session=None,
        pdf_processor: Optional["PDFProcessor"] = None,
        rlm_processor: Optional["RLMProcessor"] = None,
        vault_manager: Optional["VaultManager"] = None,
    ):
        """Initialize the orchestrator.

        Args:
            settings: HAL 9000 settings
            db_session: SQLAlchemy database session
            pdf_processor: PDF processor for content extraction
            rlm_processor: RLM processor for analysis
            vault_manager: Obsidian vault manager
        """
        self.settings = settings
        self.db_session = db_session
        self.pdf_processor = pdf_processor
        self.rlm_processor = rlm_processor
        self.vault_manager = vault_manager

        # Get acquisition config
        acq_config = getattr(settings, "acquisition", None)

        # Initialize providers
        self.providers = []

        # Semantic Scholar
        ss_api_key = getattr(acq_config, "semantic_scholar_api_key", None) if acq_config else None
        self.providers.append(SemanticScholarProvider(api_key=ss_api_key))

        # arXiv
        self.providers.append(ArxivProvider())

        # Unpaywall (for PDF URL resolution)
        unpaywall_email = getattr(acq_config, "unpaywall_email", None) if acq_config else None
        self.unpaywall = None
        if unpaywall_email:
            self.unpaywall = UnpaywallProvider(email=unpaywall_email)

        # Initialize search engine
        self.search_engine = SearchEngine(
            providers=self.providers,
            anthropic_api_key=settings.anthropic_api_key,
        )

        # Initialize download manager
        download_dir = Path(
            getattr(acq_config, "download_dir", "~/Documents/Research/Acquired")
            if acq_config
            else "~/Documents/Research/Acquired"
        )
        max_concurrent = getattr(acq_config, "max_concurrent_downloads", 3) if acq_config else 3
        rate_limit = getattr(acq_config, "rate_limit_seconds", 1.0) if acq_config else 1.0

        self.download_manager = DownloadManager(
            download_dir=download_dir,
            max_concurrent=max_concurrent,
            rate_limit_seconds=rate_limit,
        )

        # Initialize validator
        self.validator = PDFValidator(db_session=db_session)

    async def _resolve_pdf_urls(
        self, results: list[SearchResult]
    ) -> list[SearchResult]:
        """Attempt to resolve PDF URLs for results that don't have them.

        Uses Unpaywall to find open access versions when available.

        Args:
            results: Search results to resolve URLs for

        Returns:
            Results with resolved PDF URLs where possible
        """
        if not self.unpaywall:
            return results

        resolved_count = 0
        for result in results:
            if result.pdf_url:
                continue  # Already has URL

            if result.doi:
                try:
                    resolved = await self.unpaywall.resolve_doi(result.doi)
                    if resolved and resolved.pdf_url:
                        result.pdf_url = resolved.pdf_url
                        resolved_count += 1
                except Exception as e:
                    logger.debug(f"Failed to resolve PDF for DOI {result.doi}: {e}")

        logger.info(f"Resolved {resolved_count} additional PDF URLs via Unpaywall")
        return results

    async def _process_paper(
        self,
        download_result: DownloadResult,
        search_result: SearchResult,
        topic: str,
    ) -> Optional["Document"]:
        """Process a downloaded paper through the HAL pipeline.

        Args:
            download_result: Result of the download
            search_result: Original search result
            topic: Research topic (for metadata)

        Returns:
            Created Document, or None if processing failed
        """
        if not download_result.success or not download_result.local_path:
            return None

        if not self.pdf_processor or not self.rlm_processor:
            logger.warning("PDF/RLM processors not configured, skipping processing")
            return None

        try:
            from hal9000.categorize import Classifier
            from hal9000.categorize.taxonomy import create_materials_science_taxonomy
            from hal9000.db.models import Document
            from hal9000.ingest import MetadataExtractor
            from hal9000.obsidian import NoteGenerator

            # Extract PDF content
            pdf_content = self.pdf_processor.extract_text(download_result.local_path)

            # Extract metadata
            metadata_extractor = MetadataExtractor()
            metadata = metadata_extractor.extract(
                pdf_content.full_text, pdf_content.metadata
            )

            # Override with search result metadata if available
            if search_result.title and not metadata.title:
                metadata.title = search_result.title
            if search_result.authors and not metadata.authors:
                metadata.authors = search_result.authors
            if search_result.doi and not metadata.doi:
                metadata.doi = search_result.doi
            if search_result.year and not metadata.year:
                metadata.year = search_result.year
            if search_result.abstract and not metadata.abstract:
                metadata.abstract = search_result.abstract

            # RLM Analysis
            analysis = self.rlm_processor.process_document(pdf_content.full_text)

            # Classification
            taxonomy = create_materials_science_taxonomy()
            classifier = Classifier(taxonomy)
            classification = classifier.classify(analysis)

            # Create database record
            document = Document(
                source_path=str(download_result.local_path),
                source_type="acquisition",
                file_hash=download_result.file_hash,
                title=metadata.title or analysis.title,
                authors=json.dumps(metadata.authors),
                year=metadata.year,
                doi=metadata.doi,
                abstract=metadata.abstract,
                summary=analysis.summary,
                key_concepts=json.dumps(analysis.keywords),
                full_text=pdf_content.full_text[:100000],
                page_count=pdf_content.page_count,
                status="completed",
                acquisition_source=search_result.source,
                acquisition_query=topic,
            )

            if self.db_session:
                self.db_session.add(document)
                self.db_session.commit()

            # Generate Obsidian note
            if self.vault_manager:
                note_generator = NoteGenerator(self.vault_manager)
                note = note_generator.generate_paper_note(
                    document, metadata, analysis, classification
                )
                note_generator.write_note(note)
                logger.info(f"Created Obsidian note: {note.path.name}")

            return document

        except Exception as e:
            logger.error(f"Failed to process paper: {e}")
            return None

    async def acquire(
        self,
        topic: str,
        max_papers: int = 20,
        sources: Optional[list[str]] = None,
        process_papers: bool = True,
        generate_notes: bool = True,
        relevance_threshold: float = 0.5,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> AcquisitionResult:
        """Execute the full acquisition workflow.

        Args:
            topic: Research topic to search for
            max_papers: Maximum papers to acquire
            sources: List of sources to use (default: all)
            process_papers: Whether to process papers through RLM
            generate_notes: Whether to generate Obsidian notes
            relevance_threshold: Minimum relevance score (0-1)
            progress_callback: Optional callback(stage, current, total)

        Returns:
            AcquisitionResult with detailed status
        """
        import uuid

        session_id = str(uuid.uuid4())[:8]
        session_dir = self.download_manager._get_session_dir(topic)

        result = AcquisitionResult(
            topic=topic,
            session_id=session_id,
            session_dir=session_dir,
        )

        def update_progress(stage: str, current: int, total: int) -> None:
            if progress_callback:
                progress_callback(stage, current, total)

        try:
            # Stage 1: Search
            update_progress("Searching", 0, 1)
            logger.info(f"Searching for papers on: {topic}")

            search_results = await self.search_engine.search_and_filter(
                topic=topic,
                max_results=max_papers * 2,  # Get extra for filtering
                relevance_threshold=relevance_threshold,
                expand_query=True,
                sources=sources,
            )

            result.papers_found = len(search_results)
            result.search_results = search_results
            logger.info(f"Found {result.papers_found} relevant papers")
            update_progress("Searching", 1, 1)

            if not search_results:
                result.errors.append("No papers found matching the topic")
                result.completed_at = utc_now()
                result.save_log()
                return result

            # Stage 2: Resolve PDF URLs
            update_progress("Resolving URLs", 0, 1)
            search_results = await self._resolve_pdf_urls(search_results)

            # Filter to papers with PDF URLs
            downloadable = [r for r in search_results if r.pdf_url]
            logger.info(f"{len(downloadable)} papers have downloadable PDFs")
            update_progress("Resolving URLs", 1, 1)

            # Stage 3: Download
            update_progress("Downloading", 0, len(downloadable))
            download_results = []

            for i, search_result in enumerate(downloadable[:max_papers]):
                # Check for duplicates before downloading
                if search_result.doi:
                    existing = self.validator.is_duplicate_by_doi(search_result.doi)
                    if existing:
                        logger.info(f"Skipping duplicate: {search_result.title[:50]}")
                        result.duplicates_skipped += 1
                        continue

                download_result = await self.download_manager.download(
                    search_result, topic
                )
                download_results.append((search_result, download_result))

                if download_result.success:
                    result.papers_downloaded += 1

                    # Check hash-based duplicate
                    if download_result.file_hash:
                        existing = self.validator.is_duplicate_by_hash(
                            download_result.file_hash
                        )
                        if existing:
                            result.duplicates_skipped += 1
                            # Remove the duplicate file
                            if download_result.local_path:
                                download_result.local_path.unlink(missing_ok=True)
                else:
                    result.download_failures += 1
                    if download_result.error:
                        result.errors.append(
                            f"Download failed for '{search_result.title[:50]}': "
                            f"{download_result.error}"
                        )

                update_progress("Downloading", i + 1, len(downloadable))

            result.download_results = [dr for _, dr in download_results]

            # Stage 4: Process papers
            if process_papers:
                successful_downloads = [
                    (sr, dr) for sr, dr in download_results
                    if dr.success and dr.local_path
                ]

                update_progress("Processing", 0, len(successful_downloads))

                for i, (search_result, download_result) in enumerate(successful_downloads):
                    document = await self._process_paper(
                        download_result, search_result, topic
                    )

                    if document:
                        result.papers_processed += 1
                        result.documents.append(document)
                    else:
                        result.processing_failures += 1

                    update_progress("Processing", i + 1, len(successful_downloads))

            result.completed_at = utc_now()

            # Save session log
            result.save_log()

            logger.info(
                f"Acquisition complete: {result.papers_downloaded} downloaded, "
                f"{result.papers_processed} processed, "
                f"{result.duplicates_skipped} duplicates skipped"
            )

        except Exception as e:
            logger.error(f"Acquisition failed: {e}")
            result.errors.append(f"Acquisition failed: {str(e)}")
            result.completed_at = utc_now()
            result.save_log()

        return result

    async def acquire_dry_run(
        self,
        topic: str,
        max_papers: int = 20,
        relevance_threshold: float = 0.5,
        sources: Optional[list[str]] = None,
    ) -> list[SearchResult]:
        """Search for papers without downloading (dry run).

        Args:
            topic: Research topic to search for
            max_papers: Maximum papers to return
            relevance_threshold: Minimum relevance score
            sources: Optional provider names to include

        Returns:
            List of SearchResults that would be downloaded
        """
        results = await self.search_engine.search_and_filter(
            topic=topic,
            max_results=max_papers,
            relevance_threshold=relevance_threshold,
            expand_query=True,
            sources=sources,
        )

        # Resolve PDF URLs
        results = await self._resolve_pdf_urls(results)

        # Filter to downloadable
        downloadable = [r for r in results if r.pdf_url]

        return downloadable
