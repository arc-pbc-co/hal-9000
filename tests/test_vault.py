"""Unit tests for Obsidian vault manager module."""

import json
from pathlib import Path

import pytest

from hal9000.obsidian.vault import VaultConfig, VaultManager


class TestVaultConfig:
    """Tests for VaultConfig dataclass."""

    def test_default_values(self, temp_directory: Path):
        """Test default configuration values."""
        config = VaultConfig(vault_path=temp_directory)

        assert config.vault_path == temp_directory
        assert config.papers_folder == "Papers"
        assert config.concepts_folder == "Concepts"
        assert config.topics_folder == "Topics"
        assert config.canvas_folder == "Canvas"
        assert config.templates_folder == "Templates"

    def test_custom_values(self, temp_directory: Path):
        """Test custom configuration values."""
        config = VaultConfig(
            vault_path=temp_directory,
            papers_folder="Research",
            concepts_folder="Ideas"
        )

        assert config.papers_folder == "Research"
        assert config.concepts_folder == "Ideas"


class TestVaultManager:
    """Tests for VaultManager class."""

    def test_init(self, temp_vault_path: Path):
        """Test basic initialization."""
        manager = VaultManager(temp_vault_path)

        assert manager.vault_path == temp_vault_path
        assert isinstance(manager.config, VaultConfig)
        assert manager._initialized is False

    def test_init_with_string_path(self, temp_directory: Path):
        """Test initialization with string path."""
        path_str = str(temp_directory / "vault")
        manager = VaultManager(path_str)

        assert isinstance(manager.vault_path, Path)

    def test_init_expands_user(self):
        """Test that ~ is expanded in path."""
        manager = VaultManager("~/TestVault")

        assert "~" not in str(manager.vault_path)

    def test_initialize_creates_structure(self, temp_vault_path: Path):
        """Test that initialize creates the vault structure."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        # Main vault directory
        assert temp_vault_path.exists()

        # Subdirectories
        assert (temp_vault_path / "Papers").exists()
        assert (temp_vault_path / "Concepts").exists()
        assert (temp_vault_path / "Topics").exists()
        assert (temp_vault_path / "Canvas").exists()
        assert (temp_vault_path / "Templates").exists()

        # .obsidian directory
        assert (temp_vault_path / ".obsidian").exists()

    def test_initialize_creates_config_files(self, temp_vault_path: Path):
        """Test that initialize creates Obsidian config files."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        # Check for config files
        app_config = temp_vault_path / ".obsidian" / "app.json"
        graph_config = temp_vault_path / ".obsidian" / "graph.json"

        assert app_config.exists()
        assert graph_config.exists()

        # Verify JSON is valid
        with open(app_config) as f:
            app_data = json.load(f)
            assert "alwaysUpdateLinks" in app_data

        with open(graph_config) as f:
            graph_data = json.load(f)
            assert "colorGroups" in graph_data

    def test_initialize_creates_templates(self, temp_vault_path: Path):
        """Test that initialize creates templates."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        templates_dir = temp_vault_path / "Templates"

        assert (templates_dir / "Paper.md").exists()
        assert (templates_dir / "Concept.md").exists()
        assert (templates_dir / "Topic.md").exists()

    def test_initialize_creates_index(self, temp_vault_path: Path):
        """Test that initialize creates index note."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        index_file = temp_vault_path / "Index.md"
        assert index_file.exists()

        content = index_file.read_text()
        assert "HAL 9000" in content

    def test_initialize_idempotent(self, temp_vault_path: Path):
        """Test that initialize can be called multiple times safely."""
        manager = VaultManager(temp_vault_path)

        manager.initialize()
        manager.initialize()  # Should not raise

        assert manager._initialized is True

    def test_initialize_preserves_existing_config(self, temp_vault_path: Path):
        """Test that existing config is not overwritten."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        # Modify the config
        app_config = temp_vault_path / ".obsidian" / "app.json"
        with open(app_config, "w") as f:
            json.dump({"custom": "value"}, f)

        # Re-initialize (but _initialized is True, so it won't run)
        manager._initialized = False
        manager.initialize()

        # Config should still have our custom value since file existed
        with open(app_config) as f:
            data = json.load(f)
            assert data.get("custom") == "value"

    def test_get_paper_path(self, temp_vault_path: Path):
        """Test getting paper path."""
        manager = VaultManager(temp_vault_path)

        path = manager.get_paper_path("my-paper-id")

        assert path == temp_vault_path / "Papers" / "my-paper-id.md"

    def test_get_concept_path(self, temp_vault_path: Path):
        """Test getting concept path."""
        manager = VaultManager(temp_vault_path)

        path = manager.get_concept_path("Gamma Prime")

        assert path.parent == temp_vault_path / "Concepts"
        assert path.suffix == ".md"

    def test_get_topic_path(self, temp_vault_path: Path):
        """Test getting topic path."""
        manager = VaultManager(temp_vault_path)

        path = manager.get_topic_path("superalloys")

        assert path == temp_vault_path / "Topics" / "superalloys.md"

    def test_note_exists(self, temp_vault_path: Path):
        """Test checking if note exists."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        # Index should exist
        assert manager.note_exists(temp_vault_path / "Index.md")

        # Non-existent note
        assert not manager.note_exists(temp_vault_path / "NonExistent.md")

    def test_create_wikilink(self, temp_vault_path: Path):
        """Test creating wikilinks."""
        manager = VaultManager(temp_vault_path)

        # Basic wikilink
        link = manager.create_wikilink("Note Name")
        assert link == "[[Note Name]]"

        # With display text
        link = manager.create_wikilink("Long Note Name", "Short")
        assert link == "[[Long Note Name|Short]]"

    def test_create_tag(self, temp_vault_path: Path):
        """Test creating tags."""
        manager = VaultManager(temp_vault_path)

        tag = manager.create_tag("superalloy")
        assert tag == "#superalloy"

        # With spaces
        tag = manager.create_tag("Nickel Alloy")
        assert tag == "#nickel-alloy"

    def test_sanitize_filename(self, temp_vault_path: Path):
        """Test filename sanitization."""
        manager = VaultManager(temp_vault_path)

        # Basic sanitization
        safe = manager._sanitize_filename("Normal Name")
        assert safe == "Normal Name"

        # Special characters
        safe = manager._sanitize_filename('Test: "Special" <chars>')
        assert ":" not in safe
        assert '"' not in safe
        assert "<" not in safe

        # Multiple spaces
        safe = manager._sanitize_filename("Multiple   Spaces   Here")
        assert "   " not in safe

        # Very long name
        long_name = "A" * 300
        safe = manager._sanitize_filename(long_name)
        assert len(safe) <= 200

    def test_get_all_papers_empty(self, temp_vault_path: Path):
        """Test getting papers from empty vault."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        papers = manager.get_all_papers()
        assert papers == []

    def test_get_all_papers(self, temp_vault_path: Path):
        """Test getting all paper notes."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        # Create some paper notes
        papers_dir = temp_vault_path / "Papers"
        (papers_dir / "paper1.md").write_text("# Paper 1")
        (papers_dir / "paper2.md").write_text("# Paper 2")

        papers = manager.get_all_papers()

        assert len(papers) == 2
        assert all(p.suffix == ".md" for p in papers)

    def test_get_all_concepts(self, temp_vault_path: Path):
        """Test getting all concept notes."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        # Create some concept notes
        concepts_dir = temp_vault_path / "Concepts"
        (concepts_dir / "concept1.md").write_text("# Concept 1")

        concepts = manager.get_all_concepts()

        assert len(concepts) == 1

    def test_get_all_topics(self, temp_vault_path: Path):
        """Test getting all topic notes."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        # Create some topic notes
        topics_dir = temp_vault_path / "Topics"
        (topics_dir / "topic1.md").write_text("# Topic 1")
        (topics_dir / "topic2.md").write_text("# Topic 2")
        (topics_dir / "topic3.md").write_text("# Topic 3")

        topics = manager.get_all_topics()

        assert len(topics) == 3

    def test_get_vault_stats(self, temp_vault_path: Path):
        """Test getting vault statistics."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        # Create some notes
        (temp_vault_path / "Papers" / "paper1.md").write_text("# Paper")
        (temp_vault_path / "Concepts" / "concept1.md").write_text("# Concept")
        (temp_vault_path / "Topics" / "topic1.md").write_text("# Topic")

        stats = manager.get_vault_stats()

        assert stats["papers"] == 1
        assert stats["concepts"] == 1
        assert stats["topics"] == 1
        assert stats["vault_path"] == str(temp_vault_path)

    def test_get_vault_stats_empty(self, temp_vault_path: Path):
        """Test getting stats from empty vault."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        stats = manager.get_vault_stats()

        assert stats["papers"] == 0
        assert stats["concepts"] == 0
        assert stats["topics"] == 0


class TestVaultManagerTemplates:
    """Tests for vault template content."""

    def test_paper_template_has_frontmatter(self, temp_vault_path: Path):
        """Test that paper template has proper frontmatter."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        template_path = temp_vault_path / "Templates" / "Paper.md"
        content = template_path.read_text()

        assert "---" in content
        assert "title:" in content
        assert "authors:" in content
        assert "doi:" in content

    def test_concept_template_structure(self, temp_vault_path: Path):
        """Test concept template structure."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        template_path = temp_vault_path / "Templates" / "Concept.md"
        content = template_path.read_text()

        assert "Definition" in content
        assert "Key Properties" in content
        assert "Applications" in content

    def test_topic_template_structure(self, temp_vault_path: Path):
        """Test topic template structure."""
        manager = VaultManager(temp_vault_path)
        manager.initialize()

        template_path = temp_vault_path / "Templates" / "Topic.md"
        content = template_path.read_text()

        assert "Overview" in content
        assert "Subtopics" in content
        assert "Key Papers" in content
