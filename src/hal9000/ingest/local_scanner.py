"""Local filesystem scanner for PDF discovery."""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileMovedEvent
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


@dataclass
class DiscoveredFile:
    """A discovered PDF file."""

    path: Path
    size: int
    modified_time: datetime
    source_type: str = "local"

    @classmethod
    def from_path(cls, path: Path) -> "DiscoveredFile":
        """Create from a file path."""
        stat = path.stat()
        return cls(
            path=path,
            size=stat.st_size,
            modified_time=datetime.fromtimestamp(stat.st_mtime),
        )


class LocalScanner:
    """
    Scan local directories for PDF files.

    Supports both one-time scanning and continuous watching.
    """

    def __init__(
        self,
        paths: list[Path] | list[str],
        recursive: bool = True,
        extensions: list[str] | None = None,
    ):
        """
        Initialize the scanner.

        Args:
            paths: List of directory paths to scan
            recursive: Whether to scan subdirectories
            extensions: File extensions to look for (default: [".pdf"])
        """
        self.paths = [Path(p).expanduser() for p in paths]
        self.recursive = recursive
        self.extensions = extensions or [".pdf"]

        # Validate paths
        for path in self.paths:
            if not path.exists():
                logger.warning(f"Source path does not exist: {path}")
            elif not path.is_dir():
                logger.warning(f"Source path is not a directory: {path}")

    def scan(self) -> Iterator[DiscoveredFile]:
        """
        Perform a one-time scan of all configured paths.

        Yields:
            DiscoveredFile objects for each PDF found
        """
        for base_path in self.paths:
            if not base_path.exists() or not base_path.is_dir():
                continue

            yield from self._scan_directory(base_path)

    def _scan_directory(self, directory: Path) -> Iterator[DiscoveredFile]:
        """Scan a single directory for PDFs."""
        try:
            if self.recursive:
                # Use rglob for recursive search
                for ext in self.extensions:
                    pattern = f"**/*{ext}"
                    for file_path in directory.glob(pattern):
                        if file_path.is_file():
                            yield DiscoveredFile.from_path(file_path)
            else:
                # Non-recursive: only immediate children
                for file_path in directory.iterdir():
                    if file_path.is_file() and file_path.suffix.lower() in self.extensions:
                        yield DiscoveredFile.from_path(file_path)

        except PermissionError as e:
            logger.warning(f"Permission denied accessing {directory}: {e}")
        except Exception as e:
            logger.error(f"Error scanning {directory}: {e}")

    def count_files(self) -> int:
        """Count total PDF files without loading them all."""
        count = 0
        for _ in self.scan():
            count += 1
        return count

    def get_stats(self) -> dict:
        """Get statistics about available files."""
        total_files = 0
        total_size = 0

        for discovered in self.scan():
            total_files += 1
            total_size += discovered.size

        return {
            "total_files": total_files,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "paths_configured": len(self.paths),
            "paths_valid": sum(1 for p in self.paths if p.exists() and p.is_dir()),
        }


class PDFWatchHandler(FileSystemEventHandler):
    """File system event handler for PDF files."""

    def __init__(
        self,
        callback,
        extensions: list[str] | None = None,
    ):
        """
        Initialize the watch handler.

        Args:
            callback: Function to call when a PDF is discovered
            extensions: File extensions to watch
        """
        super().__init__()
        self.callback = callback
        self.extensions = extensions or [".pdf"]

    def on_created(self, event: FileCreatedEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return

        path = Path(event.src_path)
        if path.suffix.lower() in self.extensions:
            logger.info(f"New PDF detected: {path}")
            discovered = DiscoveredFile.from_path(path)
            self.callback(discovered)

    def on_moved(self, event: FileMovedEvent) -> None:
        """Handle file move events (including renames)."""
        if event.is_directory:
            return

        dest_path = Path(event.dest_path)
        if dest_path.suffix.lower() in self.extensions:
            logger.info(f"PDF moved/renamed to: {dest_path}")
            discovered = DiscoveredFile.from_path(dest_path)
            self.callback(discovered)


class DirectoryWatcher:
    """
    Watch directories for new PDF files.

    Uses watchdog for efficient filesystem monitoring.
    """

    def __init__(
        self,
        paths: list[Path] | list[str],
        callback,
        recursive: bool = True,
    ):
        """
        Initialize the watcher.

        Args:
            paths: Directories to watch
            callback: Function to call when PDFs are discovered
            recursive: Whether to watch subdirectories
        """
        self.paths = [Path(p).expanduser() for p in paths]
        self.callback = callback
        self.recursive = recursive
        self.observer: Optional[Observer] = None
        self._running = False

    def start(self) -> None:
        """Start watching for file changes."""
        if self._running:
            return

        self.observer = Observer()
        handler = PDFWatchHandler(self.callback)

        for path in self.paths:
            if path.exists() and path.is_dir():
                self.observer.schedule(handler, str(path), recursive=self.recursive)
                logger.info(f"Watching directory: {path}")

        self.observer.start()
        self._running = True
        logger.info("Directory watcher started")

    def stop(self) -> None:
        """Stop watching for file changes."""
        if not self._running or not self.observer:
            return

        self.observer.stop()
        self.observer.join()
        self._running = False
        logger.info("Directory watcher stopped")

    @property
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._running

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False
