"""PDF validation and deduplication for paper acquisition."""

import hashlib
import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from hal9000.db.models import Document

logger = logging.getLogger(__name__)


class PDFValidator:
    """Validates PDFs and checks for duplicates in the database.

    Features:
    - PDF format validation (header/structure check)
    - File hash computation (SHA-256)
    - Database deduplication by hash
    - Title-based fuzzy matching for potential duplicates
    """

    def __init__(self, db_session: Optional["Session"] = None):
        """Initialize the validator.

        Args:
            db_session: Optional SQLAlchemy session for deduplication checks
        """
        self.db_session = db_session

    def compute_file_hash(self, file_path: Path) -> str:
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

    def is_valid_pdf(self, file_path: Path) -> bool:
        """Check if a file is a valid PDF.

        Performs basic structural validation:
        - PDF header check (%PDF-)
        - EOF marker presence
        - Minimum file size

        Args:
            file_path: Path to file to check

        Returns:
            True if file appears to be a valid PDF
        """
        try:
            if not file_path.exists():
                return False

            # Minimum size check (a valid PDF is at least a few hundred bytes)
            if file_path.stat().st_size < 100:
                logger.warning(f"File too small to be valid PDF: {file_path}")
                return False

            with open(file_path, "rb") as f:
                # Check PDF header
                header = f.read(8)
                if not header.startswith(b"%PDF-"):
                    logger.warning(f"Invalid PDF header: {file_path}")
                    return False

                # Check for xref or startxref (PDF structure markers)
                f.seek(0)
                content = f.read()

                # Look for basic PDF structure
                has_obj = b" obj" in content or b"\nobj" in content
                has_endobj = b"endobj" in content

                if not (has_obj and has_endobj):
                    logger.warning(f"PDF missing object structure: {file_path}")
                    return False

                # Check for EOF marker (should be near the end)
                if b"%%EOF" not in content[-1024:]:
                    logger.warning(f"PDF missing EOF marker: {file_path}")
                    # This might still be a valid but truncated PDF

                return True

        except Exception as e:
            logger.error(f"Error validating PDF {file_path}: {e}")
            return False

    def is_duplicate_by_hash(self, file_hash: str) -> Optional["Document"]:
        """Check if a file with this hash exists in the database.

        Args:
            file_hash: SHA-256 hash of the file

        Returns:
            Existing Document if found, None otherwise
        """
        if not self.db_session:
            return None

        try:
            from hal9000.db.models import Document

            existing = (
                self.db_session.query(Document)
                .filter(Document.file_hash == file_hash)
                .first()
            )
            return existing
        except Exception as e:
            logger.error(f"Error checking for duplicate: {e}")
            return None

    def is_duplicate_by_doi(self, doi: str) -> Optional["Document"]:
        """Check if a paper with this DOI exists in the database.

        Args:
            doi: DOI of the paper

        Returns:
            Existing Document if found, None otherwise
        """
        if not self.db_session or not doi:
            return None

        try:
            from hal9000.db.models import Document

            existing = (
                self.db_session.query(Document)
                .filter(Document.doi == doi)
                .first()
            )
            return existing
        except Exception as e:
            logger.error(f"Error checking for DOI duplicate: {e}")
            return None

    def find_similar_titles(
        self, title: str, threshold: float = 0.8
    ) -> list["Document"]:
        """Find documents with similar titles.

        Uses simple word overlap for fuzzy matching.

        Args:
            title: Title to search for
            threshold: Minimum similarity score (0-1)

        Returns:
            List of potentially matching Documents
        """
        if not self.db_session or not title:
            return []

        try:
            from hal9000.db.models import Document

            # Normalize title for comparison
            title_words = set(title.lower().split())

            # Get all documents (could be optimized with full-text search)
            documents = self.db_session.query(Document).all()

            similar = []
            for doc in documents:
                if not doc.title:
                    continue

                doc_words = set(doc.title.lower().split())

                # Jaccard similarity
                if not title_words or not doc_words:
                    continue

                intersection = len(title_words & doc_words)
                union = len(title_words | doc_words)
                similarity = intersection / union if union > 0 else 0

                if similarity >= threshold:
                    similar.append(doc)

            return similar

        except Exception as e:
            logger.error(f"Error finding similar titles: {e}")
            return []

    def validate_and_check_duplicate(
        self,
        file_path: Path,
        doi: Optional[str] = None,
        title: Optional[str] = None,
    ) -> tuple[bool, bool, Optional["Document"]]:
        """Validate a PDF and check for duplicates.

        Args:
            file_path: Path to the PDF file
            doi: Optional DOI for duplicate checking
            title: Optional title for fuzzy matching

        Returns:
            Tuple of (is_valid, is_duplicate, existing_document)
        """
        # Validate PDF
        is_valid = self.is_valid_pdf(file_path)
        if not is_valid:
            return False, False, None

        # Check for hash duplicate
        file_hash = self.compute_file_hash(file_path)
        existing = self.is_duplicate_by_hash(file_hash)
        if existing:
            logger.info(f"Duplicate found by hash: {existing.title}")
            return True, True, existing

        # Check for DOI duplicate
        if doi:
            existing = self.is_duplicate_by_doi(doi)
            if existing:
                logger.info(f"Duplicate found by DOI: {existing.title}")
                return True, True, existing

        # Check for similar titles (optional, more expensive)
        if title:
            similar = self.find_similar_titles(title, threshold=0.9)
            if similar:
                # Return the most likely match
                logger.info(f"Potential duplicate by title: {similar[0].title}")
                return True, True, similar[0]

        return True, False, None


class BatchValidator:
    """Batch validation helper for multiple files."""

    def __init__(self, validator: PDFValidator):
        """Initialize with a PDFValidator instance."""
        self.validator = validator
        self.valid_count = 0
        self.invalid_count = 0
        self.duplicate_count = 0

    def validate_batch(
        self,
        file_paths: list[Path],
        dois: Optional[list[Optional[str]]] = None,
        titles: Optional[list[Optional[str]]] = None,
    ) -> list[tuple[Path, bool, bool, Optional["Document"]]]:
        """Validate multiple files.

        Args:
            file_paths: List of paths to validate
            dois: Optional list of DOIs (parallel to file_paths)
            titles: Optional list of titles (parallel to file_paths)

        Returns:
            List of (path, is_valid, is_duplicate, existing_doc) tuples
        """
        results = []

        for i, path in enumerate(file_paths):
            doi = dois[i] if dois and i < len(dois) else None
            title = titles[i] if titles and i < len(titles) else None

            is_valid, is_dup, existing = self.validator.validate_and_check_duplicate(
                path, doi, title
            )

            if not is_valid:
                self.invalid_count += 1
            elif is_dup:
                self.duplicate_count += 1
            else:
                self.valid_count += 1

            results.append((path, is_valid, is_dup, existing))

        return results

    def get_stats(self) -> dict:
        """Get validation statistics."""
        return {
            "valid": self.valid_count,
            "invalid": self.invalid_count,
            "duplicate": self.duplicate_count,
            "total": self.valid_count + self.invalid_count + self.duplicate_count,
        }
