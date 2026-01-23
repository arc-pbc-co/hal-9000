"""Download manager for acquiring research papers."""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import httpx

from hal9000.acquisition.providers.base import SearchResult

logger = logging.getLogger(__name__)

# Common user agent for academic downloads
USER_AGENT = (
    "HAL9000-Research-Assistant/1.0 "
    "(https://github.com/hal9000; research-paper-acquisition)"
)


@dataclass
class DownloadResult:
    """Result of a download attempt."""

    success: bool
    local_path: Optional[Path]
    source_url: str
    error: Optional[str] = None
    file_hash: Optional[str] = None
    file_size: int = 0
    download_time: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "success": self.success,
            "local_path": str(self.local_path) if self.local_path else None,
            "source_url": self.source_url,
            "error": self.error,
            "file_hash": self.file_hash,
            "file_size": self.file_size,
            "download_time": self.download_time,
        }


class DownloadManager:
    """Manages PDF downloads with rate limiting, retries, and validation.

    Features:
    - Concurrent download limiting via semaphore
    - Rate limiting between requests
    - Automatic retry with exponential backoff
    - PDF validation
    - File hash computation for deduplication
    - Organized folder structure by topic/date
    """

    def __init__(
        self,
        download_dir: Path,
        max_concurrent: int = 3,
        rate_limit_seconds: float = 1.0,
        max_retries: int = 3,
        timeout: int = 60,
    ):
        """Initialize the download manager.

        Args:
            download_dir: Base directory for downloads
            max_concurrent: Maximum concurrent downloads
            rate_limit_seconds: Minimum seconds between download starts
            max_retries: Maximum retry attempts per download
            timeout: Download timeout in seconds
        """
        self.download_dir = Path(download_dir).expanduser()
        self.max_concurrent = max_concurrent
        self.rate_limit_seconds = rate_limit_seconds
        self.max_retries = max_retries
        self.timeout = timeout

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._last_request_time = 0.0

    def _sanitize_filename(self, name: str, max_length: int = 100) -> str:
        """Sanitize a string for use as a filename.

        Args:
            name: String to sanitize
            max_length: Maximum length of the result

        Returns:
            Sanitized filename string
        """
        # Remove or replace problematic characters
        sanitized = re.sub(r'[<>:"/\\|?*]', "", name)
        sanitized = re.sub(r"\s+", "_", sanitized)
        sanitized = sanitized.strip("._")

        # Truncate if too long
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rstrip("_")

        return sanitized or "unnamed"

    def _generate_filename(self, result: SearchResult) -> str:
        """Generate a filename for a search result.

        Format: {year}_{first_author}_{title_snippet}_{id_suffix}.pdf

        Args:
            result: SearchResult to generate filename for

        Returns:
            Generated filename
        """
        parts = []

        # Year
        if result.year:
            parts.append(str(result.year))

        # First author's last name
        if result.authors:
            first_author = result.authors[0]
            # Extract last name (after last space)
            last_name = first_author.split()[-1] if first_author else "Unknown"
            parts.append(self._sanitize_filename(last_name, 30))

        # Title snippet
        title_snippet = self._sanitize_filename(result.title, 50)
        parts.append(title_snippet)

        # Identifier suffix for uniqueness
        if result.arxiv_id:
            parts.append(result.arxiv_id.replace("/", "_"))
        elif result.doi:
            # Use last part of DOI
            doi_suffix = result.doi.split("/")[-1][:20]
            parts.append(self._sanitize_filename(doi_suffix, 20))

        filename = "_".join(parts)
        return f"{filename}.pdf"

    def _get_session_dir(self, topic: str) -> Path:
        """Get or create the session directory for downloads.

        Args:
            topic: Research topic

        Returns:
            Path to session directory
        """
        # Sanitize topic for use as folder name
        topic_slug = self._sanitize_filename(topic.lower().replace(" ", "-"), 50)

        # Create dated session folder
        date_str = datetime.now().strftime("%Y-%m-%d")
        session_dir = self.download_dir / "by-topic" / topic_slug / f"{date_str}_session"

        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    async def _wait_for_rate_limit(self) -> None:
        """Wait if necessary to respect rate limiting."""
        import time

        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self.rate_limit_seconds:
            await asyncio.sleep(self.rate_limit_seconds - elapsed)
        self._last_request_time = time.time()

    def _compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of a file.

        Args:
            file_path: Path to file

        Returns:
            Hex digest of file hash
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _is_valid_pdf(self, file_path: Path) -> bool:
        """Check if a file is a valid PDF.

        Args:
            file_path: Path to file to check

        Returns:
            True if file appears to be a valid PDF
        """
        try:
            file_size = file_path.stat().st_size
            if file_size < 20:  # Minimum reasonable PDF size
                return False

            with open(file_path, "rb") as f:
                header = f.read(8)
                # PDF files start with %PDF-
                if not header.startswith(b"%PDF-"):
                    return False

                # Check for EOF marker at end (handle small files)
                seek_pos = min(1024, file_size)
                f.seek(-seek_pos, 2)
                tail = f.read()
                if b"%%EOF" not in tail:
                    logger.warning(f"PDF missing EOF marker: {file_path}")
                    # Still might be valid, just truncated

                return True
        except Exception as e:
            logger.error(f"Error validating PDF: {e}")
            return False

    async def download(
        self,
        result: SearchResult,
        topic: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> DownloadResult:
        """Download a paper.

        Args:
            result: SearchResult with PDF URL
            topic: Research topic (for folder organization)
            progress_callback: Optional callback(bytes_downloaded, total_bytes)

        Returns:
            DownloadResult with status and file info
        """
        if not result.pdf_url:
            return DownloadResult(
                success=False,
                local_path=None,
                source_url="",
                error="No PDF URL available",
            )

        session_dir = self._get_session_dir(topic)
        filename = self._generate_filename(result)
        local_path = session_dir / filename

        # Skip if already exists
        if local_path.exists():
            file_hash = self._compute_file_hash(local_path)
            return DownloadResult(
                success=True,
                local_path=local_path,
                source_url=result.pdf_url,
                file_hash=file_hash,
                file_size=local_path.stat().st_size,
            )

        import time
        start_time = time.time()

        async with self._semaphore:
            await self._wait_for_rate_limit()

            for attempt in range(self.max_retries):
                try:
                    async with httpx.AsyncClient(
                        timeout=self.timeout,
                        follow_redirects=True,
                    ) as client:
                        headers = {"User-Agent": USER_AGENT}

                        async with client.stream(
                            "GET", result.pdf_url, headers=headers
                        ) as response:
                            response.raise_for_status()

                            # Get total size if available
                            total_size = int(
                                response.headers.get("content-length", 0)
                            )

                            # Download to temporary file first
                            temp_path = local_path.with_suffix(".tmp")
                            bytes_downloaded = 0

                            with open(temp_path, "wb") as f:
                                async for chunk in response.aiter_bytes(8192):
                                    f.write(chunk)
                                    bytes_downloaded += len(chunk)
                                    if progress_callback:
                                        progress_callback(
                                            bytes_downloaded, total_size
                                        )

                            # Validate PDF
                            if not self._is_valid_pdf(temp_path):
                                temp_path.unlink()
                                return DownloadResult(
                                    success=False,
                                    local_path=None,
                                    source_url=result.pdf_url,
                                    error="Downloaded file is not a valid PDF",
                                )

                            # Move to final location
                            temp_path.rename(local_path)

                            # Compute hash
                            file_hash = self._compute_file_hash(local_path)

                            download_time = time.time() - start_time
                            logger.info(
                                f"Downloaded: {filename} ({bytes_downloaded} bytes)"
                            )

                            return DownloadResult(
                                success=True,
                                local_path=local_path,
                                source_url=result.pdf_url,
                                file_hash=file_hash,
                                file_size=bytes_downloaded,
                                download_time=download_time,
                            )

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 404:
                        return DownloadResult(
                            success=False,
                            local_path=None,
                            source_url=result.pdf_url,
                            error=f"PDF not found (404)",
                        )
                    elif e.response.status_code == 429:
                        # Rate limited, wait longer
                        wait_time = 2 ** (attempt + 2)
                        logger.warning(f"Rate limited, waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.warning(
                            f"HTTP error {e.response.status_code} "
                            f"(attempt {attempt + 1}/{self.max_retries})"
                        )

                except httpx.TimeoutException:
                    logger.warning(
                        f"Timeout downloading {result.pdf_url} "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )

                except Exception as e:
                    logger.warning(
                        f"Download error: {e} "
                        f"(attempt {attempt + 1}/{self.max_retries})"
                    )

                # Exponential backoff between retries
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        return DownloadResult(
            success=False,
            local_path=None,
            source_url=result.pdf_url,
            error=f"Failed after {self.max_retries} attempts",
        )

    async def download_batch(
        self,
        results: list[SearchResult],
        topic: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[DownloadResult]:
        """Download multiple papers.

        Args:
            results: List of SearchResults to download
            topic: Research topic (for folder organization)
            progress_callback: Optional callback(completed, total, current_title)

        Returns:
            List of DownloadResults
        """
        download_results = []
        total = len(results)

        for i, result in enumerate(results):
            if progress_callback:
                progress_callback(i, total, result.title[:50])

            download_result = await self.download(result, topic)
            download_results.append(download_result)

        if progress_callback:
            progress_callback(total, total, "Complete")

        return download_results
