"""Unit tests for metadata extractor module."""

import pytest

from hal9000.ingest.metadata_extractor import DocumentMetadata, MetadataExtractor


class TestDocumentMetadata:
    """Tests for DocumentMetadata dataclass."""

    def test_default_values(self):
        """Test default values are properly set."""
        metadata = DocumentMetadata()

        assert metadata.title is None
        assert metadata.authors == []
        assert metadata.year is None
        assert metadata.doi is None
        assert metadata.abstract is None
        assert metadata.keywords == []

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metadata = DocumentMetadata(
            title="Test Paper",
            authors=["John Doe", "Jane Smith"],
            year=2024,
            doi="10.1234/test",
        )

        result = metadata.to_dict()

        assert result["title"] == "Test Paper"
        assert result["authors"] == ["John Doe", "Jane Smith"]
        assert result["year"] == 2024
        assert result["doi"] == "10.1234/test"

    def test_to_json(self):
        """Test JSON serialization."""
        metadata = DocumentMetadata(
            title="Test Paper",
            authors=["John Doe"],
        )

        json_str = metadata.to_json()

        assert '"title": "Test Paper"' in json_str
        assert '"John Doe"' in json_str

    def test_authors_string(self):
        """Test authors_string property."""
        metadata = DocumentMetadata(authors=["John Doe", "Jane Smith", "Bob Wilson"])

        assert metadata.authors_string == "John Doe, Jane Smith, Bob Wilson"

    def test_authors_string_empty(self):
        """Test authors_string with no authors."""
        metadata = DocumentMetadata()

        assert metadata.authors_string == ""


class TestMetadataExtractor:
    """Tests for MetadataExtractor class."""

    def test_extract_doi_standard(self):
        """Test DOI extraction with standard format."""
        extractor = MetadataExtractor()
        text = "This paper is available at DOI: 10.1016/j.actamat.2024.001234"

        metadata = extractor.extract(text)

        assert metadata.doi == "10.1016/j.actamat.2024.001234"

    def test_extract_doi_url_format(self):
        """Test DOI extraction from URL format."""
        extractor = MetadataExtractor()
        text = "Available at https://doi.org/10.1038/nature12345"

        metadata = extractor.extract(text)

        assert metadata.doi == "10.1038/nature12345"

    def test_extract_doi_dx_url(self):
        """Test DOI extraction from dx.doi.org URL."""
        extractor = MetadataExtractor()
        text = "See https://dx.doi.org/10.1234/test.2024"

        metadata = extractor.extract(text)

        assert metadata.doi == "10.1234/test.2024"

    def test_extract_arxiv_id(self):
        """Test arXiv ID extraction."""
        extractor = MetadataExtractor()
        text = "Preprint available at arXiv: 2401.12345v2"

        metadata = extractor.extract(text)

        assert metadata.arxiv_id == "2401.12345v2"

    def test_extract_arxiv_id_without_version(self):
        """Test arXiv ID extraction without version."""
        extractor = MetadataExtractor()
        text = "See arXiv:2305.67890"

        metadata = extractor.extract(text)

        assert metadata.arxiv_id == "2305.67890"

    def test_extract_year_from_text(self, sample_metadata_text: str):
        """Test year extraction from text."""
        extractor = MetadataExtractor()

        metadata = extractor.extract(sample_metadata_text)

        assert metadata.year == 2024

    def test_extract_year_multiple_occurrences(self):
        """Test year extraction when multiple years appear."""
        extractor = MetadataExtractor()
        text = """
        Published in 2024. This builds on work from 2020 and 2021.
        Reference from 1995 is also cited.
        Copyright 2024.
        """

        metadata = extractor.extract(text)

        # Should prefer most common year
        assert metadata.year == 2024

    def test_extract_year_from_pdf_metadata(self):
        """Test year extraction from PDF metadata."""
        extractor = MetadataExtractor()
        pdf_metadata = {"CreationDate": "D:20230615120000"}

        metadata = extractor.extract("", pdf_metadata)

        assert metadata.year == 2023

    def test_extract_title_from_text(self):
        """Test title extraction from text."""
        extractor = MetadataExtractor()
        text = """
High-Temperature Creep Behavior of Nickel-Based Superalloys

John Smith, Jane Doe

Department of Materials Science

Abstract

This paper presents...
"""

        metadata = extractor.extract(text)

        assert metadata.title is not None
        assert "Nickel" in metadata.title or "Creep" in metadata.title

    def test_extract_title_from_pdf_metadata(self):
        """Test title extraction from PDF metadata."""
        extractor = MetadataExtractor()
        pdf_metadata = {"Title": "Advanced Materials for Aerospace Applications"}

        metadata = extractor.extract("", pdf_metadata)

        assert metadata.title == "Advanced Materials for Aerospace Applications"

    def test_extract_authors_from_text(self, sample_metadata_text: str):
        """Test author extraction from text."""
        extractor = MetadataExtractor()

        metadata = extractor.extract(sample_metadata_text)

        # Should find at least some authors
        assert len(metadata.authors) > 0

    def test_extract_authors_from_pdf_metadata(self):
        """Test author extraction from PDF metadata."""
        extractor = MetadataExtractor()
        pdf_metadata = {"Author": "John Smith, Jane Doe, Bob Wilson"}

        metadata = extractor.extract("", pdf_metadata)

        assert len(metadata.authors) >= 2

    def test_extract_abstract(self):
        """Test abstract extraction."""
        extractor = MetadataExtractor()
        text = """
Title of Paper

Authors

Abstract

This paper presents a comprehensive study of materials science. We investigate
the properties of advanced alloys and their applications in aerospace engineering.
The results show significant improvements over previous work.

Introduction

The field of materials science...
"""

        metadata = extractor.extract(text)

        assert metadata.abstract is not None
        assert "comprehensive study" in metadata.abstract

    def test_extract_keywords_from_pdf(self):
        """Test keyword extraction from PDF metadata."""
        extractor = MetadataExtractor()
        pdf_metadata = {"Keywords": "superalloys, nickel, creep, high temperature"}

        metadata = extractor.extract("", pdf_metadata)

        assert "superalloys" in metadata.keywords
        assert "nickel" in metadata.keywords

    def test_extract_institution(self):
        """Test institution extraction."""
        extractor = MetadataExtractor()
        text = """
Authors from Oak Ridge National Laboratory and
Massachusetts Institute of Technology conducted this research.
"""

        metadata = extractor.extract(text)

        assert metadata.institution is not None

    def test_looks_like_author_line_positive(self):
        """Test author line detection with valid author line."""
        extractor = MetadataExtractor()

        assert extractor._looks_like_author_line("John Smith, Jane Doe, and Bob Wilson")
        assert extractor._looks_like_author_line("A. Einstein and N. Bohr")

    def test_looks_like_author_line_negative(self):
        """Test author line detection with non-author lines."""
        extractor = MetadataExtractor()

        assert not extractor._looks_like_author_line("this is just regular text")
        assert not extractor._looks_like_author_line("12345, 67890, 11111")
        assert not extractor._looks_like_author_line("A")

    def test_parse_authors_with_superscripts(self):
        """Test parsing authors with superscript markers."""
        extractor = MetadataExtractor()

        authors = extractor._parse_authors("John Smith¹, Jane Doe², Bob Wilson*")

        assert "John Smith" in authors
        assert "Jane Doe" in authors
        assert "Bob Wilson" in authors

    def test_parse_authors_with_and(self):
        """Test parsing authors connected with 'and'."""
        extractor = MetadataExtractor()

        authors = extractor._parse_authors("John Smith and Jane Doe")

        assert len(authors) == 2

    def test_clean_string(self):
        """Test string cleaning."""
        extractor = MetadataExtractor()

        # Test control character removal
        result = extractor._clean_string("Test\x00String\x1f")
        assert "\x00" not in result
        assert "\x1f" not in result

        # Test whitespace normalization
        result = extractor._clean_string("Multiple   spaces   here")
        assert "   " not in result

    def test_extract_year_from_pdf_date_various_formats(self):
        """Test year extraction from various PDF date formats."""
        extractor = MetadataExtractor()

        assert extractor._extract_year_from_pdf_date("D:20230615120000") == 2023
        assert extractor._extract_year_from_pdf_date("2024") == 2024
        assert extractor._extract_year_from_pdf_date("D:20220101") == 2022

    def test_extract_year_invalid_range(self):
        """Test that years outside valid range are rejected."""
        extractor = MetadataExtractor()

        # Year too old
        assert extractor._extract_year_from_pdf_date("1800") is None

        # Year too far in future
        assert extractor._extract_year_from_pdf_date("2099") is None


class TestMetadataExtractorIntegration:
    """Integration tests for metadata extraction."""

    def test_full_extraction_sample(self, sample_metadata_text: str):
        """Test full extraction pipeline with sample text."""
        extractor = MetadataExtractor()

        metadata = extractor.extract(sample_metadata_text)

        # Should extract DOI
        assert metadata.doi == "10.1016/j.actamat.2024.001234"

        # Should extract arXiv
        assert metadata.arxiv_id == "2401.12345v2"

        # Should extract year
        assert metadata.year == 2024

        # Should have title
        assert metadata.title is not None

    def test_extraction_with_pdf_content(self, sample_pdf_path, sample_document_text: str):
        """Test extraction from actual PDF content."""
        from hal9000.ingest.pdf_processor import PDFProcessor

        processor = PDFProcessor()
        content = processor.extract_text(sample_pdf_path)

        extractor = MetadataExtractor()
        metadata = extractor.extract(content.full_text, content.metadata)

        # Should extract something useful
        assert metadata.title is not None or metadata.year is not None or len(metadata.authors) > 0
