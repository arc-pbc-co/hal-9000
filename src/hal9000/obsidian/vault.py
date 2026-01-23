"""Obsidian vault management."""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class VaultConfig:
    """Configuration for an Obsidian vault."""

    vault_path: Path
    papers_folder: str = "Papers"
    concepts_folder: str = "Concepts"
    topics_folder: str = "Topics"
    canvas_folder: str = "Canvas"
    templates_folder: str = "Templates"


class VaultManager:
    """
    Manage an Obsidian vault for research documents.

    Creates and maintains the vault structure, handles note linking,
    and manages the knowledge graph.
    """

    def __init__(self, vault_path: Union[Path, str]):
        """
        Initialize vault manager.

        Args:
            vault_path: Path to the Obsidian vault
        """
        self.vault_path = Path(vault_path).expanduser()
        self.config = VaultConfig(vault_path=self.vault_path)
        self._initialized = False

    def initialize(self) -> None:
        """
        Initialize the vault structure.

        Creates the vault directory and required subdirectories.
        """
        if self._initialized:
            return

        # Create main vault directory
        self.vault_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        for folder in [
            self.config.papers_folder,
            self.config.concepts_folder,
            self.config.topics_folder,
            self.config.canvas_folder,
            self.config.templates_folder,
        ]:
            (self.vault_path / folder).mkdir(exist_ok=True)

        # Create .obsidian directory for settings
        obsidian_dir = self.vault_path / ".obsidian"
        obsidian_dir.mkdir(exist_ok=True)

        # Create basic Obsidian config
        self._create_obsidian_config(obsidian_dir)

        # Create templates
        self._create_templates()

        # Create index note
        self._create_index_note()

        self._initialized = True
        logger.info(f"Initialized Obsidian vault at: {self.vault_path}")

    def _create_obsidian_config(self, obsidian_dir: Path) -> None:
        """Create basic Obsidian configuration."""
        import json

        # App config
        app_config = {
            "alwaysUpdateLinks": True,
            "newFileLocation": "folder",
            "newFileFolderPath": self.config.papers_folder,
            "attachmentFolderPath": "Attachments",
        }

        app_path = obsidian_dir / "app.json"
        if not app_path.exists():
            with open(app_path, "w") as f:
                json.dump(app_config, f, indent=2)

        # Graph view config (for nice visualization)
        graph_config = {
            "collapse-filter": False,
            "search": "",
            "showTags": True,
            "showAttachments": False,
            "hideUnresolved": False,
            "showOrphans": True,
            "collapse-color-groups": False,
            "colorGroups": [
                {"query": f'path:"{self.config.papers_folder}"', "color": {"a": 1, "rgb": 3066993}},
                {"query": f'path:"{self.config.concepts_folder}"', "color": {"a": 1, "rgb": 15844367}},
                {"query": f'path:"{self.config.topics_folder}"', "color": {"a": 1, "rgb": 10181046}},
            ],
            "collapse-display": False,
            "showArrow": True,
            "textFadeMultiplier": 0,
            "nodeSizeMultiplier": 1,
            "lineSizeMultiplier": 1,
        }

        graph_path = obsidian_dir / "graph.json"
        if not graph_path.exists():
            with open(graph_path, "w") as f:
                json.dump(graph_config, f, indent=2)

    def _create_templates(self) -> None:
        """Create note templates."""
        templates_dir = self.vault_path / self.config.templates_folder

        # Paper template
        paper_template = """---
title: "{{title}}"
authors: {{authors}}
year: {{year}}
doi: "{{doi}}"
topics: [{{topics}}]
status: unread
adam_context_id: "{{adam_context_id}}"
created: {{date}}
---

# {{title}}

## Metadata
- **Authors**: {{authors}}
- **Year**: {{year}}
- **DOI**: {{doi}}

## Summary
{{summary}}

## Key Concepts
{{concepts}}

## Methodology
{{methodology}}

## Key Findings
{{findings}}

## Relevance to Research
{{relevance}}

## Related Papers
{{related}}

## Notes

"""
        with open(templates_dir / "Paper.md", "w") as f:
            f.write(paper_template)

        # Concept template
        concept_template = """---
title: "{{title}}"
type: concept
related_papers: []
created: {{date}}
---

# {{title}}

## Definition
{{definition}}

## Key Properties
-

## Applications
-

## Related Concepts
{{related_concepts}}

## Papers Discussing This Concept
{{papers}}

## Notes

"""
        with open(templates_dir / "Concept.md", "w") as f:
            f.write(concept_template)

        # Topic template
        topic_template = """---
title: "{{title}}"
type: topic
parent_topic: "{{parent}}"
created: {{date}}
---

# {{title}}

## Overview
{{description}}

## Subtopics
{{subtopics}}

## Key Papers
{{papers}}

## Key Concepts
{{concepts}}

## Research Questions
-

## Notes

"""
        with open(templates_dir / "Topic.md", "w") as f:
            f.write(topic_template)

    def _create_index_note(self) -> None:
        """Create the main index note."""
        index_content = f"""---
title: HAL 9000 Research Index
created: {datetime.now().isoformat()}
---

# HAL 9000 Research Index

Welcome to your AI-powered research knowledge base.

## Quick Navigation

- [[{self.config.topics_folder}/Topics Index|Topics Index]]
- [[{self.config.concepts_folder}/Concepts Index|Concepts Index]]
- [[Recent Papers]]

## Statistics
- Total Papers: {{{{papers_count}}}}
- Topics: {{{{topics_count}}}}
- Concepts: {{{{concepts_count}}}}

## Recent Additions
{{{{recent_papers}}}}

## Knowledge Graph
Open the Graph View (Ctrl/Cmd + G) to visualize connections between papers, concepts, and topics.

---
*Managed by HAL 9000 Research Assistant*
"""
        with open(self.vault_path / "Index.md", "w") as f:
            f.write(index_content)

    def get_paper_path(self, paper_id: str) -> Path:
        """Get the path for a paper note."""
        return self.vault_path / self.config.papers_folder / f"{paper_id}.md"

    def get_concept_path(self, concept_name: str) -> Path:
        """Get the path for a concept note."""
        safe_name = self._sanitize_filename(concept_name)
        return self.vault_path / self.config.concepts_folder / f"{safe_name}.md"

    def get_topic_path(self, topic_slug: str) -> Path:
        """Get the path for a topic note."""
        return self.vault_path / self.config.topics_folder / f"{topic_slug}.md"

    def note_exists(self, path: Path) -> bool:
        """Check if a note exists."""
        return path.exists()

    def create_wikilink(self, note_name: str, display_text: Optional[str] = None) -> str:
        """Create an Obsidian wikilink."""
        if display_text:
            return f"[[{note_name}|{display_text}]]"
        return f"[[{note_name}]]"

    def create_tag(self, tag_name: str) -> str:
        """Create an Obsidian tag."""
        safe_tag = tag_name.replace(" ", "-").lower()
        return f"#{safe_tag}"

    def _sanitize_filename(self, name: str) -> str:
        """Make a filename safe for the filesystem."""
        import re

        # Remove/replace problematic characters
        safe_name = re.sub(r'[<>:"/\\|?*]', "", name)
        safe_name = re.sub(r"\s+", " ", safe_name).strip()
        return safe_name[:200]  # Limit length

    def get_all_papers(self) -> list[Path]:
        """Get all paper notes in the vault."""
        papers_dir = self.vault_path / self.config.papers_folder
        if not papers_dir.exists():
            return []
        return list(papers_dir.glob("*.md"))

    def get_all_concepts(self) -> list[Path]:
        """Get all concept notes in the vault."""
        concepts_dir = self.vault_path / self.config.concepts_folder
        if not concepts_dir.exists():
            return []
        return list(concepts_dir.glob("*.md"))

    def get_all_topics(self) -> list[Path]:
        """Get all topic notes in the vault."""
        topics_dir = self.vault_path / self.config.topics_folder
        if not topics_dir.exists():
            return []
        return list(topics_dir.glob("*.md"))

    def get_vault_stats(self) -> dict:
        """Get statistics about the vault."""
        return {
            "papers": len(self.get_all_papers()),
            "concepts": len(self.get_all_concepts()),
            "topics": len(self.get_all_topics()),
            "vault_path": str(self.vault_path),
        }
