"""Generate Obsidian notes from document analysis."""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from hal9000.categorize.classifier import ClassificationResult
from hal9000.db.models import Document
from hal9000.ingest.metadata_extractor import DocumentMetadata
from hal9000.obsidian.vault import VaultManager
from hal9000.rlm.processor import DocumentAnalysis

logger = logging.getLogger(__name__)


@dataclass
class NoteContent:
    """Generated note content."""

    path: Path
    content: str
    frontmatter: dict


class NoteGenerator:
    """
    Generate Obsidian notes from document analysis.

    Creates interconnected notes for papers, concepts, and topics.
    """

    def __init__(self, vault: VaultManager):
        """
        Initialize note generator.

        Args:
            vault: VaultManager instance
        """
        self.vault = vault

    def generate_paper_note(
        self,
        document: Document,
        metadata: DocumentMetadata,
        analysis: DocumentAnalysis,
        classification: ClassificationResult,
    ) -> NoteContent:
        """
        Generate a paper note from document analysis.

        Args:
            document: Document database record
            metadata: Extracted metadata
            analysis: RLM analysis results
            classification: Classification results

        Returns:
            NoteContent with path and content
        """
        # Build frontmatter
        frontmatter = {
            "title": metadata.title or analysis.title or "Untitled",
            "authors": metadata.authors,
            "year": metadata.year,
            "doi": metadata.doi,
            "arxiv_id": metadata.arxiv_id,
            "topics": [t.name for t in classification.all_topics],
            "keywords": analysis.keywords[:10],
            "status": "processed",
            "hal9000_id": document.id,
            "adam_context_id": document.adam_context_id,
            "source_path": document.source_path,
            "created": datetime.now().isoformat(),
        }

        # Build content
        title = frontmatter["title"]
        content_parts = [
            self._format_frontmatter(frontmatter),
            f"# {title}",
            "",
            "## Metadata",
            self._format_metadata(metadata),
            "",
            "## Summary",
            analysis.summary or "_No summary available_",
            "",
            "## Key Concepts",
            self._format_concepts(analysis.keywords),
            "",
            "## Methodology",
            analysis.methodology_summary or "_No methodology summary available_",
            "",
            "## Key Findings",
            self._format_list(analysis.key_findings) or "_No findings extracted_",
            "",
            "## Materials",
            self._format_materials(analysis.materials),
            "",
            "## Potential Applications",
            self._format_list(analysis.potential_applications) or "_None identified_",
            "",
            "## ADAM Relevance",
            analysis.adam_relevance or "_Not analyzed_",
            "",
            "## Topics",
            self._format_topic_links(classification),
            "",
            "## Related Papers",
            "_Links will be added as more papers are processed_",
            "",
            "## Notes",
            "",
            "---",
            f"*Processed by HAL 9000 on {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        ]

        content = "\n".join(content_parts)

        # Determine path
        safe_title = self.vault._sanitize_filename(title)[:100]
        note_path = self.vault.vault_path / self.vault.config.papers_folder / f"{safe_title}.md"

        return NoteContent(
            path=note_path,
            content=content,
            frontmatter=frontmatter,
        )

    def generate_concept_note(
        self,
        concept_name: str,
        definition: Optional[str] = None,
        related_papers: Optional[list[str]] = None,
        related_concepts: Optional[list[str]] = None,
    ) -> NoteContent:
        """
        Generate a concept note.

        Args:
            concept_name: Name of the concept
            definition: Optional definition
            related_papers: Paper titles that discuss this concept
            related_concepts: Related concept names

        Returns:
            NoteContent with path and content
        """
        frontmatter = {
            "title": concept_name,
            "type": "concept",
            "related_papers": related_papers or [],
            "created": datetime.now().isoformat(),
        }

        paper_links = ""
        if related_papers:
            paper_links = "\n".join([f"- [[{p}]]" for p in related_papers])
        else:
            paper_links = "_No papers linked yet_"

        concept_links = ""
        if related_concepts:
            concept_links = "\n".join([f"- [[{c}]]" for c in related_concepts])
        else:
            concept_links = "_No related concepts_"

        content = f"""{self._format_frontmatter(frontmatter)}
# {concept_name}

## Definition
{definition or "_Definition not yet added_"}

## Key Properties
-

## Applications
-

## Related Concepts
{concept_links}

## Papers Discussing This Concept
{paper_links}

## Notes

---
*Auto-generated by HAL 9000*
"""

        note_path = self.vault.get_concept_path(concept_name)

        return NoteContent(
            path=note_path,
            content=content,
            frontmatter=frontmatter,
        )

    def generate_topic_note(
        self,
        topic_name: str,
        topic_slug: str,
        description: Optional[str] = None,
        parent_topic: Optional[str] = None,
        subtopics: Optional[list[str]] = None,
        papers: Optional[list[str]] = None,
    ) -> NoteContent:
        """
        Generate a topic note.

        Args:
            topic_name: Display name of the topic
            topic_slug: URL-safe slug
            description: Topic description
            parent_topic: Parent topic name
            subtopics: Child topic names
            papers: Paper titles in this topic

        Returns:
            NoteContent with path and content
        """
        frontmatter = {
            "title": topic_name,
            "type": "topic",
            "slug": topic_slug,
            "parent_topic": parent_topic,
            "created": datetime.now().isoformat(),
        }

        subtopic_links = ""
        if subtopics:
            subtopic_links = "\n".join([f"- [[{s}]]" for s in subtopics])
        else:
            subtopic_links = "_No subtopics_"

        paper_links = ""
        if papers:
            paper_links = "\n".join([f"- [[{p}]]" for p in papers])
        else:
            paper_links = "_No papers in this topic yet_"

        parent_link = f"[[{parent_topic}]]" if parent_topic else "_Root topic_"

        content = f"""{self._format_frontmatter(frontmatter)}
# {topic_name}

**Parent Topic**: {parent_link}

## Overview
{description or "_No description available_"}

## Subtopics
{subtopic_links}

## Papers in This Topic
{paper_links}

## Key Concepts
_Add key concepts here_

## Research Questions
-

## Notes

---
*Auto-generated by HAL 9000*
"""

        note_path = self.vault.get_topic_path(topic_slug)

        return NoteContent(
            path=note_path,
            content=content,
            frontmatter=frontmatter,
        )

    def write_note(self, note: NoteContent, overwrite: bool = False) -> bool:
        """
        Write a note to the vault.

        Args:
            note: NoteContent to write
            overwrite: Whether to overwrite existing notes

        Returns:
            True if written successfully
        """
        if note.path.exists() and not overwrite:
            logger.debug(f"Note already exists (skipping): {note.path}")
            return False

        try:
            note.path.parent.mkdir(parents=True, exist_ok=True)
            with open(note.path, "w", encoding="utf-8") as f:
                f.write(note.content)
            logger.info(f"Created note: {note.path.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to write note {note.path}: {e}")
            return False

    def update_note_links(
        self,
        note_path: Path,
        links_to_add: list[str],
        section: str = "Related Papers",
    ) -> bool:
        """
        Add links to an existing note.

        Args:
            note_path: Path to the note
            links_to_add: Wiki links to add
            section: Section name to add links to

        Returns:
            True if updated successfully
        """
        if not note_path.exists():
            return False

        try:
            with open(note_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Find the section
            section_marker = f"## {section}"
            if section_marker not in content:
                return False

            # Find where to insert links
            section_start = content.find(section_marker) + len(section_marker)
            next_section = content.find("\n## ", section_start)
            if next_section == -1:
                next_section = len(content)

            # Get existing content in section
            section_content = content[section_start:next_section]

            # Add new links that aren't already present
            new_links = []
            for link in links_to_add:
                if link not in section_content:
                    new_links.append(f"- {link}")

            if new_links:
                # Insert new links
                insert_pos = section_start
                # Find first newline after section header
                first_newline = content.find("\n", section_start)
                if first_newline != -1:
                    insert_pos = first_newline + 1

                new_content = (
                    content[:insert_pos]
                    + "\n".join(new_links)
                    + "\n"
                    + content[insert_pos:]
                )

                with open(note_path, "w", encoding="utf-8") as f:
                    f.write(new_content)

                return True

            return False

        except Exception as e:
            logger.error(f"Failed to update note {note_path}: {e}")
            return False

    def _format_frontmatter(self, frontmatter: dict) -> str:
        """Format frontmatter as YAML."""
        import yaml

        # Filter out None values
        clean_fm = {k: v for k, v in frontmatter.items() if v is not None}
        return "---\n" + yaml.dump(clean_fm, default_flow_style=False, allow_unicode=True) + "---\n"

    def _format_metadata(self, metadata: DocumentMetadata) -> str:
        """Format metadata as markdown."""
        lines = []

        if metadata.authors:
            authors_str = ", ".join(metadata.authors)
            lines.append(f"- **Authors**: {authors_str}")

        if metadata.year:
            lines.append(f"- **Year**: {metadata.year}")

        if metadata.doi:
            lines.append(f"- **DOI**: [{metadata.doi}](https://doi.org/{metadata.doi})")

        if metadata.arxiv_id:
            lines.append(f"- **arXiv**: [{metadata.arxiv_id}](https://arxiv.org/abs/{metadata.arxiv_id})")

        if metadata.journal:
            lines.append(f"- **Journal**: {metadata.journal}")

        return "\n".join(lines) if lines else "_No metadata available_"

    def _format_concepts(self, keywords: list[str]) -> str:
        """Format keywords as linked concepts."""
        if not keywords:
            return "_No concepts extracted_"

        # Create links for each concept
        links = [f"- [[{kw}]]" for kw in keywords[:15]]
        return "\n".join(links)

    def _format_list(self, items: list[str]) -> str:
        """Format a list as markdown."""
        if not items:
            return ""
        return "\n".join([f"- {item}" for item in items])

    def _format_materials(self, materials: list[dict]) -> str:
        """Format materials information."""
        if not materials:
            return "_No materials identified_"

        lines = []
        for mat in materials[:10]:
            if isinstance(mat, dict):
                name = mat.get("name", "Unknown")
                props = mat.get("properties", [])
                lines.append(f"- **{name}**")
                if props:
                    lines.append(f"  - Properties: {', '.join(props[:5])}")
            else:
                lines.append(f"- {mat}")

        return "\n".join(lines)

    def _format_topic_links(self, classification: ClassificationResult) -> str:
        """Format topic links."""
        if not classification.all_topics:
            return "_No topics assigned_"

        lines = []
        for topic in classification.primary_topics:
            lines.append(f"- [[{topic.slug}|{topic.name}]] (primary)")
        for topic in classification.secondary_topics:
            lines.append(f"- [[{topic.slug}|{topic.name}]]")

        return "\n".join(lines)
