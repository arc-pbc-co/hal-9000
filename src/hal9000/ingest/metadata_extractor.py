"""Extract metadata from PDF documents."""

import json
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DocumentMetadata:
    """Extracted metadata from a research document."""

    title: Optional[str] = None
    authors: list[str] = field(default_factory=list)
    year: Optional[int] = None
    doi: Optional[str] = None
    abstract: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    pages: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    institution: Optional[str] = None
    arxiv_id: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "doi": self.doi,
            "abstract": self.abstract,
            "journal": self.journal,
            "volume": self.volume,
            "pages": self.pages,
            "keywords": self.keywords,
            "institution": self.institution,
            "arxiv_id": self.arxiv_id,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @property
    def authors_string(self) -> str:
        """Get authors as a comma-separated string."""
        return ", ".join(self.authors)


class MetadataExtractor:
    """Extract metadata from PDF content and PDF metadata."""

    # Common patterns for metadata extraction
    DOI_PATTERN = re.compile(
        r"(?:doi[:\s]*)?(?:https?://(?:dx\.)?doi\.org/)?("
        r"10\.\d{4,}/[^\s\]\)\"'<>]+)",
        re.IGNORECASE,
    )
    ARXIV_PATTERN = re.compile(
        r"arXiv[:\s]*(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE
    )
    YEAR_PATTERN = re.compile(r"\b((?:19|20)\d{2})\b")

    def extract(
        self, text: str, pdf_metadata: Optional[dict] = None
    ) -> DocumentMetadata:
        """
        Extract metadata from document text and PDF metadata.

        Args:
            text: Full text of the document
            pdf_metadata: Optional PDF metadata dictionary from pdfplumber

        Returns:
            DocumentMetadata object
        """
        metadata = DocumentMetadata()

        # Try PDF metadata first (often more reliable)
        if pdf_metadata:
            metadata = self._extract_from_pdf_metadata(pdf_metadata, metadata)

        # Extract from text
        metadata = self._extract_from_text(text, metadata)

        return metadata

    def _extract_from_pdf_metadata(
        self, pdf_metadata: dict, metadata: DocumentMetadata
    ) -> DocumentMetadata:
        """Extract metadata from PDF metadata dictionary."""
        # Title
        if not metadata.title and pdf_metadata.get("Title"):
            metadata.title = self._clean_string(pdf_metadata["Title"])

        # Author
        if not metadata.authors and pdf_metadata.get("Author"):
            author_str = pdf_metadata["Author"]
            metadata.authors = self._parse_authors(author_str)

        # Keywords
        if not metadata.keywords and pdf_metadata.get("Keywords"):
            keywords_str = pdf_metadata["Keywords"]
            if isinstance(keywords_str, str):
                metadata.keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

        # Creation date for year
        for date_field in ["CreationDate", "ModDate"]:
            if not metadata.year and pdf_metadata.get(date_field):
                year = self._extract_year_from_pdf_date(pdf_metadata[date_field])
                if year:
                    metadata.year = year
                    break

        return metadata

    def _extract_from_text(
        self, text: str, metadata: DocumentMetadata
    ) -> DocumentMetadata:
        """Extract metadata from document text."""
        # Use first few pages for metadata (header area)
        header_text = text[:10000] if len(text) > 10000 else text

        # DOI
        if not metadata.doi:
            doi_match = self.DOI_PATTERN.search(text)
            if doi_match:
                metadata.doi = doi_match.group(1)

        # arXiv ID
        if not metadata.arxiv_id:
            arxiv_match = self.ARXIV_PATTERN.search(text)
            if arxiv_match:
                metadata.arxiv_id = arxiv_match.group(1)

        # Title (if not from PDF metadata)
        if not metadata.title:
            metadata.title = self._extract_title_from_text(header_text)

        # Authors (if not from PDF metadata)
        if not metadata.authors:
            metadata.authors = self._extract_authors_from_text(header_text)

        # Abstract
        if not metadata.abstract:
            metadata.abstract = self._extract_abstract(text)

        # Year
        if not metadata.year:
            metadata.year = self._extract_year_from_text(header_text)

        # Institution
        if not metadata.institution:
            metadata.institution = self._extract_institution(header_text)

        return metadata

    def _extract_title_from_text(self, text: str) -> Optional[str]:
        """
        Extract title from document text.

        Heuristic: Title is usually the first prominent text before authors/abstract.
        """
        lines = text.split("\n")

        # Look for the first substantial line that looks like a title
        for i, line in enumerate(lines[:20]):  # Check first 20 lines
            line = line.strip()

            # Skip empty lines and very short lines
            if len(line) < 10:
                continue

            # Skip lines that look like headers/footers
            if any(skip in line.lower() for skip in [
                "abstract", "introduction", "arxiv:", "doi:", "copyright",
                "journal", "volume", "page", "preprint", "draft"
            ]):
                continue

            # Skip lines with email addresses
            if "@" in line and "." in line:
                continue

            # Skip lines that are mostly numbers or special chars
            alpha_ratio = sum(1 for c in line if c.isalpha()) / len(line)
            if alpha_ratio < 0.5:
                continue

            # This looks like a title
            # Clean it up
            title = re.sub(r"\s+", " ", line)
            title = title.strip()

            # Reasonable title length
            if 10 < len(title) < 300:
                return title

        return None

    def _extract_authors_from_text(self, text: str) -> list[str]:
        """Extract author names from text."""
        authors = []

        # Common patterns for author lines
        # Look for lines with multiple names separated by commas or "and"
        lines = text.split("\n")

        for line in lines[:30]:  # Check first 30 lines
            line = line.strip()

            # Skip if too short or too long
            if len(line) < 5 or len(line) > 500:
                continue

            # Skip if looks like title or abstract
            if any(skip in line.lower() for skip in [
                "abstract", "introduction", "arxiv", "doi", "university",
                "department", "institute", "©", "copyright"
            ]):
                continue

            # Check if line has author-like pattern (names with commas/and)
            if self._looks_like_author_line(line):
                parsed = self._parse_authors(line)
                if parsed:
                    authors.extend(parsed)
                    break

        return authors

    def _looks_like_author_line(self, line: str) -> bool:
        """Check if a line looks like an author line."""
        # Should have multiple capital letters (names)
        capitals = sum(1 for c in line if c.isupper())
        if capitals < 2:
            return False

        # Should have commas or "and"
        if "," not in line and " and " not in line.lower():
            return False

        # Should not have too many numbers
        numbers = sum(1 for c in line if c.isdigit())
        if numbers > len(line) * 0.2:
            return False

        return True

    def _parse_authors(self, author_string: str) -> list[str]:
        """Parse an author string into individual names."""
        # Clean up - remove ASCII digits and Unicode superscripts
        author_string = re.sub(r"[\d¹²³⁴⁵⁶⁷⁸⁹⁰]+", "", author_string)
        author_string = re.sub(r"[*†‡§¶]", "", author_string)  # Remove symbols
        author_string = re.sub(r"\s+", " ", author_string)

        # Split by "and" or comma
        parts = re.split(r",\s*|\s+and\s+", author_string, flags=re.IGNORECASE)

        authors = []
        for part in parts:
            part = part.strip()
            # Filter out non-name parts
            if len(part) > 2 and not any(skip in part.lower() for skip in [
                "university", "institute", "department", "email", "@"
            ]):
                # Check it looks like a name (has at least one capital letter)
                if any(c.isupper() for c in part):
                    authors.append(part)

        return authors

    def _extract_abstract(self, text: str) -> Optional[str]:
        """Extract abstract from text."""
        # Look for "Abstract" section
        abstract_patterns = [
            r"(?i)abstract[:\s]*\n(.+?)(?=\n\s*(?:introduction|1[\.\s]|keywords))",
            r"(?i)abstract[:\s]*(.+?)(?=\n\n)",
        ]

        for pattern in abstract_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                abstract = match.group(1).strip()
                # Clean up
                abstract = re.sub(r"\s+", " ", abstract)
                # Reasonable abstract length
                if 100 < len(abstract) < 3000:
                    return abstract

        return None

    def _extract_year_from_text(self, text: str) -> Optional[int]:
        """Extract publication year from text."""
        # Look for year patterns
        matches = self.YEAR_PATTERN.findall(text)

        if matches:
            # Convert to integers and find most likely year
            years = [int(f"{m}") for m in matches]
            # Filter to reasonable range
            current_year = 2026
            valid_years = [y for y in years if 1950 <= y <= current_year]

            if valid_years:
                # Prefer years that appear multiple times
                from collections import Counter
                year_counts = Counter(valid_years)
                return year_counts.most_common(1)[0][0]

        return None

    def _extract_year_from_pdf_date(self, date_str: str) -> Optional[int]:
        """Extract year from PDF date string."""
        if not date_str:
            return None

        # PDF dates often in format: D:YYYYMMDDHHmmSS
        match = re.search(r"(?:D:)?(\d{4})", date_str)
        if match:
            year = int(match.group(1))
            if 1950 <= year <= 2026:
                return year

        return None

    def _extract_institution(self, text: str) -> Optional[str]:
        """Extract institution/affiliation from text."""
        # Look for common institution patterns
        patterns = [
            r"((?:University|Institute|Laboratory|Lab|College|School|Center|Centre)\s+(?:of\s+)?[\w\s]+)",
            r"([\w\s]+(?:University|Institute|Laboratory|College))",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text[:5000], re.IGNORECASE)
            if matches:
                # Return first reasonable match
                for match in matches:
                    if 10 < len(match) < 100:
                        return match.strip()

        return None

    def _clean_string(self, s: str) -> str:
        """Clean a string value."""
        if not s:
            return s
        # Remove control characters and excessive whitespace
        s = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip()
