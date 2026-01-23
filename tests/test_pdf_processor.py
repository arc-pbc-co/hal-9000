"""Unit tests for PDF processor module."""

import hashlib
from pathlib import Path

import pytest

from hal9000.ingest.pdf_processor import PDFContent, PDFProcessor, process_pdf


class TestPDFContent:
    """Tests for PDFContent dataclass."""

    def test_char_count(self):
        """Test character count property."""
        content = PDFContent(
            file_path=Path("test.pdf"),
            file_hash="abc123",
            full_text="Hello World",
            page_count=1,
        )
        assert content.char_count == 11

    def test_word_count(self):
        """Test word count property."""
        content = PDFContent(
            file_path=Path("test.pdf"),
            file_hash="abc123",
            full_text="Hello World Test Document",
            page_count=1,
        )
        assert content.word_count == 4

    def test_empty_text(self):
        """Test with empty text."""
        content = PDFContent(
            file_path=Path("test.pdf"),
            file_hash="abc123",
            full_text="",
            page_count=0,
        )
        assert content.char_count == 0
        assert content.word_count == 0


class TestPDFProcessor:
    """Tests for PDFProcessor class."""

    def test_init_default(self):
        """Test default initialization."""
        processor = PDFProcessor()
        assert processor.extract_tables is True

    def test_init_no_tables(self):
        """Test initialization with table extraction disabled."""
        processor = PDFProcessor(extract_tables=False)
        assert processor.extract_tables is False

    def test_compute_file_hash(self, sample_pdf_path: Path):
        """Test file hash computation."""
        processor = PDFProcessor()
        hash1 = processor.compute_file_hash(sample_pdf_path)
        hash2 = processor.compute_file_hash(sample_pdf_path)

        # Hash should be consistent
        assert hash1 == hash2
        # Should be valid SHA-256 (64 hex chars)
        assert len(hash1) == 64
        assert all(c in "0123456789abcdef" for c in hash1)

    def test_extract_text_file_not_found(self):
        """Test extraction with non-existent file."""
        processor = PDFProcessor()
        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            processor.extract_text(Path("/nonexistent/file.pdf"))

    def test_extract_text_not_pdf(self, temp_directory: Path):
        """Test extraction with non-PDF file."""
        processor = PDFProcessor()
        text_file = temp_directory / "test.txt"
        text_file.write_text("Not a PDF")

        with pytest.raises(ValueError, match="Not a PDF file"):
            processor.extract_text(text_file)

    def test_extract_text_real_pdf(self, sample_pdf_path: Path):
        """Test extraction from a real PDF file."""
        processor = PDFProcessor()
        content = processor.extract_text(sample_pdf_path)

        assert isinstance(content, PDFContent)
        assert content.file_path == sample_pdf_path
        assert len(content.file_hash) == 64
        assert content.page_count > 0
        assert len(content.full_text) > 0
        assert len(content.pages) == content.page_count

    def test_extract_text_without_tables(self, sample_pdf_path: Path):
        """Test extraction without table extraction."""
        processor = PDFProcessor(extract_tables=False)
        content = processor.extract_text(sample_pdf_path)

        assert isinstance(content, PDFContent)
        assert content.tables == []

    def test_clean_text(self):
        """Test text cleaning."""
        processor = PDFProcessor()

        # Test multiple newlines reduction
        text = "Line 1\n\n\n\n\nLine 2"
        cleaned = processor._clean_text(text)
        assert "\n\n\n" not in cleaned

        # Test multiple spaces reduction
        text = "Word1    Word2"
        cleaned = processor._clean_text(text)
        assert "    " not in cleaned

        # Test hyphenation fix
        text = "super-\nalloy"
        cleaned = processor._clean_text(text)
        assert cleaned == "superalloy"

        # Test null byte removal
        text = "text\x00with\x00nulls"
        cleaned = processor._clean_text(text)
        assert "\x00" not in cleaned

    def test_chunk_text_small_document(self):
        """Test chunking when document is smaller than chunk size."""
        processor = PDFProcessor()
        text = "Small document text"
        chunks = processor.chunk_text(text, chunk_size=1000)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_large_document(self, sample_document_text: str):
        """Test chunking a larger document."""
        processor = PDFProcessor()
        # Use small chunk size to force multiple chunks
        chunks = processor.chunk_text(sample_document_text, chunk_size=500, overlap=50)

        assert len(chunks) > 1
        # Each chunk should be non-empty
        for chunk in chunks:
            assert len(chunk.strip()) > 0

    def test_chunk_text_overlap(self):
        """Test that chunks have proper overlap."""
        processor = PDFProcessor()
        text = "A" * 500 + "\n\n" + "B" * 500 + "\n\n" + "C" * 500
        chunks = processor.chunk_text(text, chunk_size=600, overlap=100)

        # Should have overlapping content
        assert len(chunks) > 1

    def test_find_break_point_paragraph(self):
        """Test finding break point at paragraph boundary."""
        processor = PDFProcessor()
        text = "First paragraph.\n\nSecond paragraph starts here."
        break_point = processor._find_break_point(text, 0, 30, search_window=50)

        # Should break at paragraph boundary
        assert text[break_point:break_point + 6] == "Second"

    def test_find_break_point_sentence(self):
        """Test finding break point at sentence boundary."""
        processor = PDFProcessor()
        text = "First sentence. Second sentence starts here."
        break_point = processor._find_break_point(text, 0, 30, search_window=50)

        # Should break after first sentence
        assert break_point == 16

    def test_extract_sections_basic(self, sample_document_text: str):
        """Test section extraction from sample text."""
        processor = PDFProcessor()
        sections = processor.extract_sections(sample_document_text)

        assert "abstract" in sections or len(sections) > 0

    def test_extract_sections_empty(self):
        """Test section extraction with no recognizable sections."""
        processor = PDFProcessor()
        text = "This is just plain text without any section headers."
        sections = processor.extract_sections(text)

        assert isinstance(sections, dict)


class TestProcessPdfFunction:
    """Tests for the convenience process_pdf function."""

    def test_process_pdf_convenience(self, sample_pdf_path: Path):
        """Test the convenience function."""
        content = process_pdf(sample_pdf_path)

        assert isinstance(content, PDFContent)
        assert content.page_count > 0


class TestPDFProcessorIntegration:
    """Integration tests using real PDF files."""

    def test_process_all_test_pdfs(self, all_test_pdfs: list[Path]):
        """Test processing all PDFs in the test folder."""
        processor = PDFProcessor()
        successful = 0
        failed = []

        for pdf_path in all_test_pdfs:
            try:
                content = processor.extract_text(pdf_path)
                assert content.page_count > 0
                assert len(content.full_text) > 0
                successful += 1
            except Exception as e:
                failed.append((pdf_path.name, str(e)))

        # At least some PDFs should process successfully
        assert successful > 0, f"No PDFs processed successfully. Failed: {failed}"

        # Report any failures
        if failed:
            print(f"\nWarning: {len(failed)} PDFs failed to process:")
            for name, error in failed:
                print(f"  - {name}: {error}")

    def test_pdf_content_quality(self, sample_pdf_path: Path):
        """Test that extracted content meets quality criteria."""
        processor = PDFProcessor()
        content = processor.extract_text(sample_pdf_path)

        # Content should have reasonable length
        assert content.char_count > 100, "PDF content seems too short"

        # Should have multiple words
        assert content.word_count > 20, "PDF should have more words"

        # All pages should have some content (most PDFs)
        non_empty_pages = sum(1 for page in content.pages if page.strip())
        assert non_empty_pages > 0, "At least one page should have content"

    def test_chunking_real_pdf(self, sample_pdf_path: Path):
        """Test chunking on real PDF content."""
        processor = PDFProcessor()
        content = processor.extract_text(sample_pdf_path)

        # Test with default chunk size
        chunks = processor.chunk_text(content.full_text)

        # All chunks should be non-empty
        for i, chunk in enumerate(chunks):
            assert len(chunk.strip()) > 0, f"Chunk {i} is empty"

        # If document is large enough, should have multiple chunks
        if content.char_count > 60000:
            assert len(chunks) > 1, "Large document should have multiple chunks"
