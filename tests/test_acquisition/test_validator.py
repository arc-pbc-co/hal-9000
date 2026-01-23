"""Tests for PDF validator."""

import pytest
from pathlib import Path
import tempfile

from hal9000.acquisition.validator import PDFValidator, BatchValidator


class TestPDFValidator:
    """Tests for PDFValidator."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def validator(self):
        """Create a validator without database."""
        return PDFValidator(db_session=None)

    def test_compute_file_hash(self, validator, temp_dir):
        """Test file hash computation."""
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content")

        hash1 = validator.compute_file_hash(test_file)
        hash2 = validator.compute_file_hash(test_file)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256

    def test_compute_file_hash_different_content(self, validator, temp_dir):
        """Test different files have different hashes."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"
        file1.write_text("content 1")
        file2.write_text("content 2")

        hash1 = validator.compute_file_hash(file1)
        hash2 = validator.compute_file_hash(file2)

        assert hash1 != hash2

    def test_is_valid_pdf_valid(self, validator, temp_dir):
        """Test valid PDF detection."""
        pdf_file = temp_dir / "valid.pdf"
        # Minimal valid PDF structure
        pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [] /Count 0 >>
endobj
xref
0 3
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
trailer
<< /Size 3 /Root 1 0 R >>
startxref
109
%%EOF"""
        pdf_file.write_bytes(pdf_content)

        assert validator.is_valid_pdf(pdf_file) is True

    def test_is_valid_pdf_invalid_header(self, validator, temp_dir):
        """Test file with invalid header."""
        not_pdf = temp_dir / "not_pdf.pdf"
        not_pdf.write_bytes(b"This is not a PDF file at all")

        assert validator.is_valid_pdf(not_pdf) is False

    def test_is_valid_pdf_missing_structure(self, validator, temp_dir):
        """Test file with PDF header but missing structure."""
        bad_pdf = temp_dir / "bad.pdf"
        bad_pdf.write_bytes(b"%PDF-1.4\nThis has no real content")

        assert validator.is_valid_pdf(bad_pdf) is False

    def test_is_valid_pdf_too_small(self, validator, temp_dir):
        """Test file that's too small."""
        tiny_file = temp_dir / "tiny.pdf"
        tiny_file.write_bytes(b"%PDF")  # Too small

        assert validator.is_valid_pdf(tiny_file) is False

    def test_is_valid_pdf_nonexistent(self, validator, temp_dir):
        """Test nonexistent file."""
        assert validator.is_valid_pdf(temp_dir / "nonexistent.pdf") is False

    def test_is_duplicate_by_hash_no_db(self, validator):
        """Test duplicate check without database."""
        result = validator.is_duplicate_by_hash("abc123")
        assert result is None

    def test_is_duplicate_by_doi_no_db(self, validator):
        """Test DOI duplicate check without database."""
        result = validator.is_duplicate_by_doi("10.1234/test")
        assert result is None

    def test_find_similar_titles_no_db(self, validator):
        """Test title search without database."""
        result = validator.find_similar_titles("Test Paper")
        assert result == []

    def test_validate_and_check_duplicate(self, validator, temp_dir):
        """Test combined validation and duplicate check."""
        pdf_file = temp_dir / "test.pdf"
        pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [] /Count 0 >>
endobj
xref
0 3
trailer
<< /Size 3 /Root 1 0 R >>
startxref
100
%%EOF"""
        pdf_file.write_bytes(pdf_content)

        is_valid, is_dup, existing = validator.validate_and_check_duplicate(
            pdf_file, doi="10.1234/test", title="Test Paper"
        )

        assert is_valid is True
        assert is_dup is False
        assert existing is None


class TestBatchValidator:
    """Tests for BatchValidator."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def validator(self):
        """Create a validator."""
        return PDFValidator(db_session=None)

    @pytest.fixture
    def batch_validator(self, validator):
        """Create a batch validator."""
        return BatchValidator(validator)

    def test_validate_batch(self, batch_validator, temp_dir):
        """Test batch validation."""
        # Create valid PDF (must be >100 bytes with proper structure)
        valid_pdf = temp_dir / "valid.pdf"
        valid_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [] /Count 0 >>
endobj
xref
0 3
trailer
<< /Size 3 /Root 1 0 R >>
startxref
100
%%EOF"""
        valid_pdf.write_bytes(valid_content)

        invalid_file = temp_dir / "invalid.pdf"
        invalid_file.write_bytes(b"Not a PDF - this is just text content that is long enough")

        results = batch_validator.validate_batch(
            [valid_pdf, invalid_file],
            dois=[None, None],
            titles=["Valid Paper", "Invalid Paper"],
        )

        assert len(results) == 2
        # First should be valid
        assert results[0][1] is True  # is_valid
        # Second should be invalid
        assert results[1][1] is False

    def test_get_stats(self, batch_validator, temp_dir):
        """Test statistics tracking."""
        valid_pdf = temp_dir / "valid.pdf"
        valid_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [] /Count 0 >>
endobj
xref
0 3
trailer
<< /Size 3 /Root 1 0 R >>
startxref
100
%%EOF"""
        valid_pdf.write_bytes(valid_content)

        invalid_file = temp_dir / "invalid.pdf"
        invalid_file.write_bytes(b"Not a PDF - this is just text content that is long enough")

        batch_validator.validate_batch([valid_pdf, invalid_file])

        stats = batch_validator.get_stats()
        assert stats["valid"] == 1
        assert stats["invalid"] == 1
        assert stats["total"] == 2
