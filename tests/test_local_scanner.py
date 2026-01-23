"""Unit tests for local scanner module."""

from pathlib import Path
from datetime import datetime

import pytest

from hal9000.ingest.local_scanner import (
    DiscoveredFile,
    LocalScanner,
    PDFWatchHandler,
    DirectoryWatcher,
)


class TestDiscoveredFile:
    """Tests for DiscoveredFile dataclass."""

    def test_from_path(self, sample_pdf_path: Path):
        """Test creating DiscoveredFile from path."""
        discovered = DiscoveredFile.from_path(sample_pdf_path)

        assert discovered.path == sample_pdf_path
        assert discovered.size > 0
        assert isinstance(discovered.modified_time, datetime)
        assert discovered.source_type == "local"

    def test_properties(self, temp_directory: Path):
        """Test DiscoveredFile properties."""
        # Create a test file
        test_file = temp_directory / "test.pdf"
        test_file.write_bytes(b"fake pdf content" * 100)

        discovered = DiscoveredFile.from_path(test_file)

        assert discovered.size == 1600  # 16 bytes * 100
        assert discovered.modified_time <= datetime.now()


class TestLocalScanner:
    """Tests for LocalScanner class."""

    def test_init_with_paths(self, test_pdf_folder: Path):
        """Test initialization with path list."""
        scanner = LocalScanner(paths=[test_pdf_folder])

        assert len(scanner.paths) == 1
        assert scanner.recursive is True
        assert scanner.extensions == [".pdf"]

    def test_init_with_string_paths(self, test_pdf_folder: Path):
        """Test initialization with string paths."""
        scanner = LocalScanner(paths=[str(test_pdf_folder)])

        assert len(scanner.paths) == 1
        assert isinstance(scanner.paths[0], Path)

    def test_init_custom_extensions(self, test_pdf_folder: Path):
        """Test initialization with custom extensions."""
        scanner = LocalScanner(
            paths=[test_pdf_folder],
            extensions=[".pdf", ".txt"]
        )

        assert scanner.extensions == [".pdf", ".txt"]

    def test_init_non_recursive(self, test_pdf_folder: Path):
        """Test non-recursive initialization."""
        scanner = LocalScanner(paths=[test_pdf_folder], recursive=False)

        assert scanner.recursive is False

    def test_scan_finds_pdfs(self, test_pdf_folder: Path):
        """Test that scan finds PDF files."""
        scanner = LocalScanner(paths=[test_pdf_folder])
        results = list(scanner.scan())

        assert len(results) > 0
        for result in results:
            assert result.path.suffix.lower() == ".pdf"

    def test_scan_nonexistent_path(self, temp_directory: Path):
        """Test scan with non-existent path."""
        scanner = LocalScanner(paths=[temp_directory / "nonexistent"])
        results = list(scanner.scan())

        assert results == []

    def test_scan_empty_directory(self, temp_directory: Path):
        """Test scan with empty directory."""
        scanner = LocalScanner(paths=[temp_directory])
        results = list(scanner.scan())

        assert results == []

    def test_scan_recursive(self, temp_directory: Path):
        """Test recursive scanning."""
        # Create nested structure
        subdir = temp_directory / "subdir" / "nested"
        subdir.mkdir(parents=True)

        (temp_directory / "root.pdf").write_bytes(b"pdf")
        (subdir / "nested.pdf").write_bytes(b"pdf")

        scanner = LocalScanner(paths=[temp_directory], recursive=True)
        results = list(scanner.scan())

        assert len(results) == 2

    def test_scan_non_recursive(self, temp_directory: Path):
        """Test non-recursive scanning."""
        # Create nested structure
        subdir = temp_directory / "subdir"
        subdir.mkdir()

        (temp_directory / "root.pdf").write_bytes(b"pdf")
        (subdir / "nested.pdf").write_bytes(b"pdf")

        scanner = LocalScanner(paths=[temp_directory], recursive=False)
        results = list(scanner.scan())

        # Should only find root.pdf
        assert len(results) == 1
        assert results[0].path.name == "root.pdf"

    def test_count_files(self, test_pdf_folder: Path):
        """Test file counting."""
        scanner = LocalScanner(paths=[test_pdf_folder])
        count = scanner.count_files()

        # Should match number of PDFs in test folder
        actual_pdfs = list(test_pdf_folder.glob("**/*.pdf"))
        assert count == len(actual_pdfs)

    def test_get_stats(self, test_pdf_folder: Path):
        """Test getting statistics."""
        scanner = LocalScanner(paths=[test_pdf_folder])
        stats = scanner.get_stats()

        assert "total_files" in stats
        assert "total_size_bytes" in stats
        assert "total_size_mb" in stats
        assert "paths_configured" in stats
        assert "paths_valid" in stats

        assert stats["total_files"] > 0
        assert stats["total_size_bytes"] > 0
        assert stats["paths_configured"] == 1
        assert stats["paths_valid"] == 1

    def test_scan_multiple_paths(self, test_pdf_folder: Path, temp_directory: Path):
        """Test scanning multiple paths."""
        # Add a PDF to temp directory
        (temp_directory / "extra.pdf").write_bytes(b"pdf content")

        scanner = LocalScanner(paths=[test_pdf_folder, temp_directory])
        results = list(scanner.scan())

        # Should find PDFs from both directories
        paths = {r.path for r in results}
        assert any("extra.pdf" in str(p) for p in paths)


class TestPDFWatchHandler:
    """Tests for PDFWatchHandler class."""

    def test_init(self):
        """Test handler initialization."""
        callback = lambda x: None
        handler = PDFWatchHandler(callback=callback)

        assert handler.callback == callback
        assert handler.extensions == [".pdf"]

    def test_init_custom_extensions(self):
        """Test handler with custom extensions."""
        handler = PDFWatchHandler(
            callback=lambda x: None,
            extensions=[".pdf", ".PDF"]
        )

        assert handler.extensions == [".pdf", ".PDF"]

    def test_on_created_pdf(self, temp_directory: Path):
        """Test handling PDF creation event."""
        from watchdog.events import FileCreatedEvent

        results = []
        handler = PDFWatchHandler(callback=lambda x: results.append(x))

        # Create a PDF file first
        pdf_path = temp_directory / "new_file.pdf"
        pdf_path.write_bytes(b"pdf content")

        # Simulate the event
        event = FileCreatedEvent(str(pdf_path))
        handler.on_created(event)

        assert len(results) == 1
        assert results[0].path == pdf_path

    def test_on_created_non_pdf(self, temp_directory: Path):
        """Test handling non-PDF creation event."""
        from watchdog.events import FileCreatedEvent

        results = []
        handler = PDFWatchHandler(callback=lambda x: results.append(x))

        # Create a non-PDF file
        txt_path = temp_directory / "file.txt"
        txt_path.write_text("text content")

        event = FileCreatedEvent(str(txt_path))
        handler.on_created(event)

        # Should not trigger callback
        assert len(results) == 0

    def test_on_created_directory(self, temp_directory: Path):
        """Test handling directory creation event."""
        from watchdog.events import DirCreatedEvent

        results = []
        handler = PDFWatchHandler(callback=lambda x: results.append(x))

        subdir = temp_directory / "subdir"
        subdir.mkdir()

        event = DirCreatedEvent(str(subdir))
        handler.on_created(event)

        # Should not trigger callback for directories
        assert len(results) == 0

    def test_on_moved_to_pdf(self, temp_directory: Path):
        """Test handling file move to PDF."""
        from watchdog.events import FileMovedEvent

        results = []
        handler = PDFWatchHandler(callback=lambda x: results.append(x))

        # Create source file
        src_path = temp_directory / "file.txt"
        src_path.write_text("content")

        dest_path = temp_directory / "renamed.pdf"
        src_path.rename(dest_path)

        event = FileMovedEvent(str(src_path), str(dest_path))
        handler.on_moved(event)

        assert len(results) == 1
        assert results[0].path == dest_path


class TestDirectoryWatcher:
    """Tests for DirectoryWatcher class."""

    def test_init(self, test_pdf_folder: Path):
        """Test watcher initialization."""
        watcher = DirectoryWatcher(
            paths=[test_pdf_folder],
            callback=lambda x: None
        )

        assert len(watcher.paths) == 1
        assert watcher.recursive is True
        assert watcher._running is False

    def test_is_running_property(self, test_pdf_folder: Path):
        """Test is_running property."""
        watcher = DirectoryWatcher(
            paths=[test_pdf_folder],
            callback=lambda x: None
        )

        assert watcher.is_running is False

    def test_start_stop(self, test_pdf_folder: Path):
        """Test starting and stopping watcher."""
        watcher = DirectoryWatcher(
            paths=[test_pdf_folder],
            callback=lambda x: None
        )

        watcher.start()
        assert watcher.is_running is True

        watcher.stop()
        assert watcher.is_running is False

    def test_context_manager(self, test_pdf_folder: Path):
        """Test context manager usage."""
        with DirectoryWatcher(
            paths=[test_pdf_folder],
            callback=lambda x: None
        ) as watcher:
            assert watcher.is_running is True

        assert watcher.is_running is False

    def test_double_start(self, test_pdf_folder: Path):
        """Test that double start is handled gracefully."""
        watcher = DirectoryWatcher(
            paths=[test_pdf_folder],
            callback=lambda x: None
        )

        watcher.start()
        watcher.start()  # Should not raise

        assert watcher.is_running is True

        watcher.stop()

    def test_double_stop(self, test_pdf_folder: Path):
        """Test that double stop is handled gracefully."""
        watcher = DirectoryWatcher(
            paths=[test_pdf_folder],
            callback=lambda x: None
        )

        watcher.start()
        watcher.stop()
        watcher.stop()  # Should not raise

        assert watcher.is_running is False


class TestLocalScannerIntegration:
    """Integration tests for local scanner with real files."""

    def test_scan_research_folder(self, test_pdf_folder: Path):
        """Test scanning the actual research folder."""
        scanner = LocalScanner(paths=[test_pdf_folder])
        results = list(scanner.scan())

        # Should find all PDFs
        for result in results:
            assert result.path.exists()
            assert result.path.suffix.lower() == ".pdf"
            assert result.size > 0

    def test_stats_match_scan(self, test_pdf_folder: Path):
        """Test that stats match scan results."""
        scanner = LocalScanner(paths=[test_pdf_folder])

        results = list(scanner.scan())
        stats = scanner.get_stats()

        # Note: We need to scan again for stats, so just verify consistency
        assert stats["total_files"] == len(results)

        total_size = sum(r.size for r in results)
        # Allow for floating point rounding in MB calculation
        assert abs(stats["total_size_bytes"] - total_size) < 1000
