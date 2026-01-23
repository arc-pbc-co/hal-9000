"""Tests for the download manager."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import tempfile

from hal9000.acquisition.downloader import DownloadManager, DownloadResult
from hal9000.acquisition.providers.base import SearchResult


class TestDownloadResult:
    """Tests for DownloadResult dataclass."""

    def test_creation(self):
        """Test basic DownloadResult creation."""
        result = DownloadResult(
            success=True,
            local_path=Path("/tmp/test.pdf"),
            source_url="https://example.com/paper.pdf",
            file_hash="abc123",
            file_size=1024,
        )
        assert result.success is True
        assert result.file_size == 1024

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = DownloadResult(
            success=True,
            local_path=Path("/tmp/test.pdf"),
            source_url="https://example.com/paper.pdf",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["local_path"] == "/tmp/test.pdf"


class TestDownloadManager:
    """Tests for DownloadManager."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for downloads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manager(self, temp_dir):
        """Create a DownloadManager instance."""
        return DownloadManager(
            download_dir=temp_dir,
            max_concurrent=2,
            rate_limit_seconds=0.1,
            max_retries=2,
        )

    def test_sanitize_filename(self, manager):
        """Test filename sanitization."""
        assert manager._sanitize_filename("test file.pdf") == "test_file.pdf"
        assert manager._sanitize_filename('file:with/special?chars*') == "filewithspecialchars"
        assert manager._sanitize_filename("  spaces  ") == "spaces"
        assert len(manager._sanitize_filename("a" * 200)) <= 100

    def test_generate_filename(self, manager):
        """Test filename generation from SearchResult."""
        result = SearchResult(
            title="A Very Long Paper Title About Materials Science",
            authors=["John Smith", "Jane Doe"],
            year=2024,
            arxiv_id="2301.00001",
            source="arxiv",
        )
        filename = manager._generate_filename(result)
        assert filename.endswith(".pdf")
        assert "2024" in filename
        assert "Smith" in filename
        assert "2301.00001" in filename

    def test_get_session_dir(self, manager):
        """Test session directory creation."""
        session_dir = manager._get_session_dir("battery materials")
        assert session_dir.exists()
        assert "battery-materials" in str(session_dir)
        assert "_session" in str(session_dir)

    @pytest.mark.asyncio
    async def test_download_no_url(self, manager):
        """Test download fails gracefully when no URL."""
        result = SearchResult(
            title="Test Paper",
            authors=[],
            source="test",
            pdf_url=None,
        )
        download_result = await manager.download(result, "test topic")
        assert download_result.success is False
        assert "No PDF URL" in download_result.error

    @pytest.mark.asyncio
    async def test_download_success(self, manager, temp_dir):
        """Test successful download."""
        # Create a mock PDF content (must be >20 bytes)
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< >>\nendobj\n%%EOF"

        result = SearchResult(
            title="Test Paper",
            authors=["Author"],
            year=2024,
            source="test",
            pdf_url="https://example.com/paper.pdf",
        )

        with patch("httpx.AsyncClient") as mock_client:
            # Create mock response that streams content
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {"content-length": str(len(pdf_content))}

            async def mock_aiter_bytes(chunk_size):
                yield pdf_content

            mock_response.aiter_bytes = mock_aiter_bytes

            # Create context manager for the stream
            mock_stream_cm = AsyncMock()
            mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
            mock_stream_cm.__aexit__ = AsyncMock(return_value=None)

            mock_client_instance = AsyncMock()
            mock_client_instance.stream = MagicMock(return_value=mock_stream_cm)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_client_instance

            download_result = await manager.download(result, "test topic")

            assert download_result.success is True
            assert download_result.local_path is not None
            assert download_result.local_path.exists()
            assert download_result.file_hash is not None


class TestDownloadManagerValidation:
    """Tests for PDF validation in DownloadManager."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def manager(self, temp_dir):
        """Create a DownloadManager instance."""
        return DownloadManager(download_dir=temp_dir)

    def test_is_valid_pdf_success(self, manager, temp_dir):
        """Test valid PDF detection."""
        pdf_path = temp_dir / "valid.pdf"
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF"
        pdf_path.write_bytes(pdf_content)

        assert manager._is_valid_pdf(pdf_path) is True

    def test_is_valid_pdf_invalid_header(self, manager, temp_dir):
        """Test invalid PDF detection (wrong header)."""
        pdf_path = temp_dir / "invalid.pdf"
        pdf_path.write_bytes(b"This is not a PDF file")

        assert manager._is_valid_pdf(pdf_path) is False

    def test_compute_file_hash(self, manager, temp_dir):
        """Test file hash computation."""
        test_path = temp_dir / "test.txt"
        test_path.write_text("test content")

        hash1 = manager._compute_file_hash(test_path)
        hash2 = manager._compute_file_hash(test_path)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest
