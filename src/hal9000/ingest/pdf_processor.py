"""PDF document processor for text extraction."""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber


@dataclass
class PDFContent:
    """Extracted content from a PDF document."""

    file_path: Path
    file_hash: str
    full_text: str
    page_count: int
    pages: list[str] = field(default_factory=list)
    tables: list[list[list[str]]] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        """Total character count."""
        return len(self.full_text)

    @property
    def word_count(self) -> int:
        """Approximate word count."""
        return len(self.full_text.split())


class PDFProcessor:
    """Process PDF documents to extract text and metadata."""

    def __init__(self, extract_tables: bool = True):
        """
        Initialize PDF processor.

        Args:
            extract_tables: Whether to extract tables from PDFs
        """
        self.extract_tables = extract_tables

    def compute_file_hash(self, file_path: Path) -> str:
        """Compute SHA-256 hash of file for deduplication."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def extract_text(self, file_path: Path) -> PDFContent:
        """
        Extract text content from a PDF file.

        Args:
            file_path: Path to the PDF file

        Returns:
            PDFContent object with extracted data

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is not a valid PDF
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        if file_path.suffix.lower() != ".pdf":
            raise ValueError(f"Not a PDF file: {file_path}")

        # Compute file hash first
        file_hash = self.compute_file_hash(file_path)

        pages: list[str] = []
        tables: list[list[list[str]]] = []
        metadata: dict = {}

        try:
            with pdfplumber.open(file_path) as pdf:
                # Extract metadata
                metadata = pdf.metadata or {}

                # Process each page
                for page in pdf.pages:
                    # Extract text
                    page_text = page.extract_text() or ""
                    pages.append(page_text)

                    # Extract tables if enabled
                    if self.extract_tables:
                        page_tables = page.extract_tables()
                        if page_tables:
                            tables.extend(page_tables)

        except Exception as e:
            raise ValueError(f"Failed to process PDF: {e}") from e

        # Combine all pages into full text
        full_text = self._clean_text("\n\n".join(pages))

        return PDFContent(
            file_path=file_path,
            file_hash=file_hash,
            full_text=full_text,
            page_count=len(pages),
            pages=pages,
            tables=tables,
            metadata=metadata,
        )

    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        # Remove excessive whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)

        # Remove common PDF artifacts
        text = re.sub(r"\x00", "", text)  # Null bytes

        # Fix hyphenation at line breaks (common in PDFs)
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

        return text.strip()

    def chunk_text(
        self,
        text: str,
        chunk_size: int = 50000,
        overlap: int = 1000,
    ) -> list[str]:
        """
        Split text into chunks for RLM processing.

        Uses intelligent chunking that tries to break at paragraph/section boundaries.

        Args:
            text: Full text to chunk
            chunk_size: Target size per chunk in characters
            overlap: Overlap between chunks for context continuity

        Returns:
            List of text chunks
        """
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        current_pos = 0

        while current_pos < len(text):
            # Calculate end position
            end_pos = min(current_pos + chunk_size, len(text))

            # If not at the end, try to find a good break point
            if end_pos < len(text):
                # Look for paragraph break first
                break_pos = self._find_break_point(text, current_pos, end_pos)
                if break_pos > current_pos:
                    end_pos = break_pos

            chunk = text[current_pos:end_pos]
            chunks.append(chunk.strip())

            # Move position, accounting for overlap, but always make forward progress
            if end_pos < len(text):
                current_pos = max(end_pos - overlap, current_pos + 1)
            else:
                current_pos = end_pos

        return chunks

    def _find_break_point(
        self, text: str, start: int, end: int, search_window: int = 2000
    ) -> int:
        """Find a good break point (paragraph or sentence boundary)."""
        search_start = max(start, end - search_window)
        search_text = text[search_start:end]

        # Try to break at a double newline (paragraph)
        last_para = search_text.rfind("\n\n")
        if last_para != -1:
            return search_start + last_para + 2

        # Try to break at a sentence end
        sentence_ends = [
            search_text.rfind(". "),
            search_text.rfind(".\n"),
            search_text.rfind("? "),
            search_text.rfind("! "),
        ]
        best_end = max(sentence_ends)
        if best_end != -1:
            return search_start + best_end + 2

        # Fall back to any newline
        last_newline = search_text.rfind("\n")
        if last_newline != -1:
            return search_start + last_newline + 1

        # Last resort: break at space
        last_space = search_text.rfind(" ")
        if last_space != -1:
            return search_start + last_space + 1

        # No good break point found
        return end

    def extract_sections(self, text: str) -> dict[str, str]:
        """
        Attempt to extract standard paper sections (abstract, intro, etc.).

        This is a heuristic-based approach that works for many academic papers.

        Args:
            text: Full text of the document

        Returns:
            Dictionary mapping section names to content
        """
        sections = {}

        # Common section patterns
        section_patterns = [
            (r"(?i)abstract[:\s]*\n", "abstract"),
            (r"(?i)introduction[:\s]*\n", "introduction"),
            (r"(?i)(?:related work|background)[:\s]*\n", "related_work"),
            (r"(?i)(?:method(?:ology)?|approach)[:\s]*\n", "methodology"),
            (r"(?i)(?:experiment(?:s)?|evaluation)[:\s]*\n", "experiments"),
            (r"(?i)(?:result(?:s)?|finding(?:s)?)[:\s]*\n", "results"),
            (r"(?i)(?:discussion)[:\s]*\n", "discussion"),
            (r"(?i)(?:conclusion(?:s)?|summary)[:\s]*\n", "conclusion"),
            (r"(?i)(?:reference(?:s)?|bibliography)[:\s]*\n", "references"),
        ]

        # Find all section starts
        section_starts = []
        for pattern, name in section_patterns:
            matches = list(re.finditer(pattern, text))
            for match in matches:
                section_starts.append((match.start(), match.end(), name))

        # Sort by position
        section_starts.sort(key=lambda x: x[0])

        # Extract section content
        for i, (start, content_start, name) in enumerate(section_starts):
            # End is either next section or end of text
            if i + 1 < len(section_starts):
                end = section_starts[i + 1][0]
            else:
                end = len(text)

            content = text[content_start:end].strip()

            # Only keep if we have meaningful content
            if len(content) > 100:
                sections[name] = content

        return sections


def process_pdf(file_path: Path) -> PDFContent:
    """Convenience function to process a single PDF."""
    processor = PDFProcessor()
    return processor.extract_text(file_path)
