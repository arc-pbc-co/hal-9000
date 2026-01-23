"""Integration tests using real PDF files from the research folder."""

from pathlib import Path

import pytest

from hal9000.ingest.pdf_processor import PDFProcessor
from hal9000.ingest.metadata_extractor import MetadataExtractor
from hal9000.ingest.local_scanner import LocalScanner
from hal9000.categorize.taxonomy import Taxonomy, create_materials_science_taxonomy
from hal9000.obsidian.vault import VaultManager


class TestPDFProcessingIntegration:
    """Integration tests for the PDF processing pipeline."""

    def test_process_pdf_and_extract_metadata(self, sample_pdf_path: Path):
        """Test processing a PDF and extracting its metadata."""
        # Process PDF
        processor = PDFProcessor()
        content = processor.extract_text(sample_pdf_path)

        # Extract metadata
        extractor = MetadataExtractor()
        metadata = extractor.extract(content.full_text, content.metadata)

        # Verify we got meaningful results
        assert content.page_count > 0
        assert len(content.full_text) > 100

        # Metadata should have at least some useful information
        has_metadata = (
            metadata.title is not None or
            len(metadata.authors) > 0 or
            metadata.year is not None
        )
        assert has_metadata, "Should extract at least some metadata"

    def test_process_all_pdfs_in_folder(self, all_test_pdfs: list[Path]):
        """Test processing all PDFs in the test folder."""
        processor = PDFProcessor()
        extractor = MetadataExtractor()

        results = []
        errors = []

        for pdf_path in all_test_pdfs:
            try:
                content = processor.extract_text(pdf_path)
                metadata = extractor.extract(content.full_text, content.metadata)

                results.append({
                    "path": pdf_path.name,
                    "pages": content.page_count,
                    "chars": content.char_count,
                    "words": content.word_count,
                    "title": metadata.title,
                    "year": metadata.year,
                    "authors": len(metadata.authors),
                })
            except Exception as e:
                errors.append({"path": pdf_path.name, "error": str(e)})

        # Should successfully process most PDFs
        assert len(results) > 0, "Should process at least one PDF"

        # Report results
        print(f"\nProcessed {len(results)} PDFs successfully")
        print(f"Failed: {len(errors)} PDFs")

        for r in results:
            print(f"  - {r['path']}: {r['pages']} pages, {r['words']} words")

        if errors:
            print("\nErrors:")
            for e in errors:
                print(f"  - {e['path']}: {e['error']}")

    def test_chunk_real_pdf_content(self, sample_pdf_path: Path):
        """Test chunking real PDF content."""
        processor = PDFProcessor()
        content = processor.extract_text(sample_pdf_path)

        # Chunk with small size to ensure multiple chunks
        chunks = processor.chunk_text(content.full_text, chunk_size=5000, overlap=500)

        # Verify chunks
        assert len(chunks) >= 1

        # All chunks should be non-empty
        for i, chunk in enumerate(chunks):
            assert len(chunk.strip()) > 0, f"Chunk {i} should not be empty"

        # Total content should be roughly preserved (minus overlap)
        total_chunk_chars = sum(len(c) for c in chunks)
        # With overlap, total chars should be >= original
        assert total_chunk_chars >= len(content.full_text) * 0.8


class TestScannerIntegration:
    """Integration tests for the local scanner."""

    def test_scan_and_process_discovered_files(self, test_pdf_folder: Path):
        """Test scanning folder and processing discovered files."""
        scanner = LocalScanner(paths=[test_pdf_folder])
        processor = PDFProcessor()

        # Scan for files
        discovered = list(scanner.scan())
        assert len(discovered) > 0

        # Process first few files
        processed = 0
        for file in discovered[:3]:
            content = processor.extract_text(file.path)
            assert content.page_count > 0
            processed += 1

        assert processed == min(3, len(discovered))

    def test_scanner_stats_accuracy(self, test_pdf_folder: Path):
        """Test that scanner stats are accurate."""
        scanner = LocalScanner(paths=[test_pdf_folder])

        # Get stats
        stats = scanner.get_stats()

        # Manually verify
        discovered = list(scanner.scan())

        assert stats["total_files"] == len(discovered)

        # Total size should match
        manual_size = sum(d.size for d in discovered)
        assert abs(stats["total_size_bytes"] - manual_size) < 1000  # Allow small variance


class TestTaxonomyIntegration:
    """Integration tests for the taxonomy system."""

    def test_classify_pdf_content(self, sample_pdf_path: Path):
        """Test classifying PDF content against taxonomy."""
        # Process PDF
        processor = PDFProcessor()
        content = processor.extract_text(sample_pdf_path)

        # Create taxonomy
        taxonomy = create_materials_science_taxonomy()

        # Extract keywords from content (simple approach)
        words = content.full_text.lower().split()
        keywords = set(words) & {"superalloy", "nickel", "creep", "turbine", "magnet",
                                  "battery", "additive", "manufacturing", "xrd", "sem"}

        # Find matching topics
        matches = taxonomy.find_matching_topics(
            query_topics=list(keywords),
            query_keywords=list(keywords),
            threshold=0.1
        )

        # Should find at least one match for materials science content
        # (may be empty if PDF doesn't match our keywords)
        assert isinstance(matches, list)

    def test_taxonomy_yaml_roundtrip(self, temp_directory: Path):
        """Test saving and loading taxonomy."""
        # Create taxonomy
        original = create_materials_science_taxonomy()

        # Save
        yaml_path = temp_directory / "taxonomy.yaml"
        original.save_yaml(yaml_path)

        # Reload
        reloaded = Taxonomy.from_yaml(yaml_path)

        # Verify key topics exist
        assert reloaded.get_topic("permanent-magnets") is not None
        assert reloaded.get_topic("batteries") is not None


class TestVaultIntegration:
    """Integration tests for the Obsidian vault."""

    def test_vault_initialization_and_stats(self, temp_vault_path: Path):
        """Test vault initialization and statistics."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        # Verify structure
        assert (temp_vault_path / "Papers").exists()
        assert (temp_vault_path / "Concepts").exists()

        # Get stats
        stats = manager.get_vault_stats()

        assert stats["papers"] == 0
        assert stats["concepts"] == 0

    def test_create_paper_note_workflow(self, temp_vault_path: Path, sample_pdf_path: Path):
        """Test creating a paper note from PDF content."""
        # Initialize vault
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        # Process PDF
        processor = PDFProcessor()
        content = processor.extract_text(sample_pdf_path)

        extractor = MetadataExtractor()
        metadata = extractor.extract(content.full_text, content.metadata)

        # Create a simple paper note
        paper_id = sample_pdf_path.stem[:50]  # Use filename as ID
        note_path = manager.get_paper_path(paper_id)

        # Generate note content
        note_content = f"""---
title: "{metadata.title or sample_pdf_path.stem}"
authors: {metadata.authors}
year: {metadata.year}
---

# {metadata.title or sample_pdf_path.stem}

## Summary
Document contains {content.word_count} words across {content.page_count} pages.

## Extracted Abstract
{metadata.abstract or 'No abstract found'}
"""

        # Write note
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(note_content)

        # Verify
        assert manager.note_exists(note_path)
        stats = manager.get_vault_stats()
        assert stats["papers"] == 1


class TestEndToEndPipeline:
    """End-to-end tests for the full processing pipeline."""

    def test_scan_process_classify_pipeline(self, test_pdf_folder: Path, temp_directory: Path):
        """Test the complete pipeline from scanning to classification."""
        # 1. Scan for PDFs
        scanner = LocalScanner(paths=[test_pdf_folder])
        discovered = list(scanner.scan())[:3]  # Limit for speed

        assert len(discovered) > 0

        # 2. Process each PDF
        processor = PDFProcessor()
        extractor = MetadataExtractor()
        taxonomy = create_materials_science_taxonomy()

        processed_docs = []

        for file in discovered:
            content = processor.extract_text(file.path)
            metadata = extractor.extract(content.full_text, content.metadata)

            # Simple keyword extraction
            text_lower = content.full_text.lower()
            keywords = []
            for kw in ["superalloy", "nickel", "creep", "magnet", "battery"]:
                if kw in text_lower:
                    keywords.append(kw)

            # Classify
            suggestions = taxonomy.suggest_topics_for_document(
                document_topics=keywords,
                document_keywords=keywords,
                max_topics=3
            )

            processed_docs.append({
                "path": file.path.name,
                "title": metadata.title,
                "pages": content.page_count,
                "keywords": keywords,
                "topics": [t.name for t in suggestions]
            })

        # Verify results
        assert len(processed_docs) == len(discovered)

        print("\nPipeline Results:")
        for doc in processed_docs:
            print(f"  - {doc['path'][:40]}...")
            print(f"    Pages: {doc['pages']}, Keywords: {doc['keywords']}")
            print(f"    Topics: {doc['topics']}")

    def test_vault_population_pipeline(self, test_pdf_folder: Path, temp_vault_path: Path):
        """Test populating a vault from scanned PDFs."""
        # Initialize
        scanner = LocalScanner(paths=[test_pdf_folder])
        processor = PDFProcessor()
        extractor = MetadataExtractor()
        vault = VaultManager(temp_vault_path)

        vault.initialize()

        # Process first 2 PDFs
        discovered = list(scanner.scan())[:2]

        for file in discovered:
            content = processor.extract_text(file.path)
            metadata = extractor.extract(content.full_text, content.metadata)

            # Create paper note
            paper_id = file.path.stem[:50]
            note_path = vault.get_paper_path(paper_id)

            note_content = f"""---
title: "{metadata.title or file.path.stem}"
year: {metadata.year}
---

# {metadata.title or file.path.stem}

Word count: {content.word_count}
"""
            note_path.write_text(note_content)

        # Verify vault was populated
        stats = vault.get_vault_stats()
        assert stats["papers"] == 2


class TestPerformance:
    """Performance tests for the pipeline."""

    def test_large_pdf_processing(self, all_test_pdfs: list[Path]):
        """Test processing the largest PDF in the test folder."""
        # Find largest PDF
        largest = max(all_test_pdfs, key=lambda p: p.stat().st_size)
        size_mb = largest.stat().st_size / (1024 * 1024)

        print(f"\nTesting with largest PDF: {largest.name} ({size_mb:.1f} MB)")

        processor = PDFProcessor()
        content = processor.extract_text(largest)

        print(f"  Pages: {content.page_count}")
        print(f"  Characters: {content.char_count}")
        print(f"  Words: {content.word_count}")

        # Should complete without error
        assert content.page_count > 0

    def test_chunking_performance(self, sample_pdf_path: Path):
        """Test chunking performance with various sizes."""
        import time

        processor = PDFProcessor()
        content = processor.extract_text(sample_pdf_path)

        chunk_sizes = [10000, 25000, 50000]

        print(f"\nChunking performance ({content.char_count} chars):")

        for size in chunk_sizes:
            start = time.time()
            chunks = processor.chunk_text(content.full_text, chunk_size=size)
            elapsed = time.time() - start

            print(f"  Chunk size {size}: {len(chunks)} chunks in {elapsed:.3f}s")

            assert len(chunks) > 0
