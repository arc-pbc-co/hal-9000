"""Unit tests for taxonomy module."""

from pathlib import Path

import pytest

from hal9000.categorize.taxonomy import (
    TopicNode,
    Taxonomy,
    create_materials_science_taxonomy,
)


class TestTopicNode:
    """Tests for TopicNode dataclass."""

    def test_basic_creation(self):
        """Test basic node creation."""
        node = TopicNode(name="Test Topic", slug="test-topic")

        assert node.name == "Test Topic"
        assert node.slug == "test-topic"
        assert node.parent is None
        assert node.children == []
        assert node.keywords == []
        assert node.level == 0

    def test_with_keywords(self):
        """Test node with keywords."""
        node = TopicNode(
            name="Materials",
            slug="materials",
            keywords=["metal", "alloy", "composite"]
        )

        assert len(node.keywords) == 3
        assert "metal" in node.keywords

    def test_hash_and_equality(self):
        """Test that nodes are hashable and comparable by slug."""
        node1 = TopicNode(name="Topic A", slug="topic-a")
        node2 = TopicNode(name="Topic A Different", slug="topic-a")
        node3 = TopicNode(name="Topic B", slug="topic-b")

        # Same slug = equal
        assert node1 == node2
        assert hash(node1) == hash(node2)

        # Different slug = not equal
        assert node1 != node3

    def test_full_path(self):
        """Test full_path property."""
        root = TopicNode(name="Root", slug="root")
        child = TopicNode(name="Child", slug="child")
        grandchild = TopicNode(name="Grandchild", slug="grandchild")

        root.add_child(child)
        child.add_child(grandchild)

        assert grandchild.full_path == "Root > Child > Grandchild"
        assert child.full_path == "Root > Child"
        assert root.full_path == "Root"

    def test_add_child(self):
        """Test adding child nodes."""
        parent = TopicNode(name="Parent", slug="parent")
        child = TopicNode(name="Child", slug="child")

        parent.add_child(child)

        assert child in parent.children
        assert child.parent == parent
        assert child.level == 1

    def test_add_multiple_children(self):
        """Test adding multiple children."""
        parent = TopicNode(name="Parent", slug="parent")

        for i in range(3):
            child = TopicNode(name=f"Child {i}", slug=f"child-{i}")
            parent.add_child(child)

        assert len(parent.children) == 3

    def test_find_child(self):
        """Test finding direct child by slug."""
        parent = TopicNode(name="Parent", slug="parent")
        child1 = TopicNode(name="Child 1", slug="child-1")
        child2 = TopicNode(name="Child 2", slug="child-2")

        parent.add_child(child1)
        parent.add_child(child2)

        found = parent.find_child("child-2")
        assert found == child2

        not_found = parent.find_child("nonexistent")
        assert not_found is None

    def test_find_descendant(self):
        """Test finding any descendant by slug."""
        root = TopicNode(name="Root", slug="root")
        child = TopicNode(name="Child", slug="child")
        grandchild = TopicNode(name="Grandchild", slug="grandchild")

        root.add_child(child)
        child.add_child(grandchild)

        # Should find grandchild from root
        found = root.find_descendant("grandchild")
        assert found == grandchild

        # Should find self
        found = root.find_descendant("root")
        assert found == root

    def test_get_all_descendants(self):
        """Test getting all descendants."""
        root = TopicNode(name="Root", slug="root")
        child1 = TopicNode(name="Child 1", slug="child-1")
        child2 = TopicNode(name="Child 2", slug="child-2")
        grandchild = TopicNode(name="Grandchild", slug="grandchild")

        root.add_child(child1)
        root.add_child(child2)
        child1.add_child(grandchild)

        descendants = root.get_all_descendants()

        assert len(descendants) == 3
        assert child1 in descendants
        assert child2 in descendants
        assert grandchild in descendants

    def test_to_dict(self):
        """Test conversion to dictionary."""
        parent = TopicNode(
            name="Parent",
            slug="parent",
            description="A parent topic",
            keywords=["key1", "key2"]
        )
        child = TopicNode(name="Child", slug="child")
        parent.add_child(child)

        result = parent.to_dict()

        assert result["name"] == "Parent"
        assert result["slug"] == "parent"
        assert result["description"] == "A parent topic"
        assert result["keywords"] == ["key1", "key2"]
        assert len(result["children"]) == 1
        assert result["children"][0]["name"] == "Child"


class TestTaxonomy:
    """Tests for Taxonomy class."""

    def test_init_default(self):
        """Test default initialization."""
        taxonomy = Taxonomy()

        assert taxonomy.root.name == "Research"
        assert taxonomy.root.slug == "root"
        assert "root" in taxonomy._slug_index

    def test_init_custom_root(self):
        """Test initialization with custom root name."""
        taxonomy = Taxonomy(root_name="Materials Science")

        assert taxonomy.root.name == "Materials Science"

    def test_from_yaml(self, sample_taxonomy_yaml: Path):
        """Test loading taxonomy from YAML."""
        taxonomy = Taxonomy.from_yaml(sample_taxonomy_yaml)

        # Should have loaded topics
        superalloys = taxonomy.get_topic("superalloys")
        assert superalloys is not None
        assert superalloys.name == "Superalloys"

        # Should have children
        ni_superalloys = taxonomy.get_topic("nickel-superalloys")
        assert ni_superalloys is not None
        assert ni_superalloys.parent == superalloys

    def test_from_yaml_nonexistent(self, temp_directory: Path):
        """Test loading from nonexistent file."""
        taxonomy = Taxonomy.from_yaml(temp_directory / "nonexistent.yaml")

        # Should create empty taxonomy
        assert len(taxonomy.root.children) == 0

    def test_save_yaml(self, sample_taxonomy_yaml: Path, temp_directory: Path):
        """Test saving taxonomy to YAML."""
        import yaml

        # Load and save
        taxonomy = Taxonomy.from_yaml(sample_taxonomy_yaml)
        output_path = temp_directory / "output_taxonomy.yaml"
        taxonomy.save_yaml(output_path)

        # Verify saved content
        with open(output_path) as f:
            data = yaml.safe_load(f)

        assert "taxonomy" in data
        assert len(data["taxonomy"]) > 0

    def test_get_topic(self, sample_taxonomy_yaml: Path):
        """Test getting topic by slug."""
        taxonomy = Taxonomy.from_yaml(sample_taxonomy_yaml)

        topic = taxonomy.get_topic("superalloys")
        assert topic is not None

        # Non-existent
        topic = taxonomy.get_topic("nonexistent")
        assert topic is None

    def test_get_all_topics(self, sample_taxonomy_yaml: Path):
        """Test getting all topics."""
        taxonomy = Taxonomy.from_yaml(sample_taxonomy_yaml)

        all_topics = taxonomy.get_all_topics()

        # Should include root and all loaded topics
        assert len(all_topics) > 1
        slugs = [t.slug for t in all_topics]
        assert "root" in slugs
        assert "superalloys" in slugs

    def test_add_topic_to_root(self):
        """Test adding topic to root."""
        taxonomy = Taxonomy()

        topic = taxonomy.add_topic(
            name="New Topic",
            description="A new topic",
            keywords=["keyword1"]
        )

        assert topic.name == "New Topic"
        assert topic in taxonomy.root.children
        assert topic.parent == taxonomy.root

    def test_add_topic_to_parent(self, sample_taxonomy_yaml: Path):
        """Test adding topic to specific parent."""
        taxonomy = Taxonomy.from_yaml(sample_taxonomy_yaml)

        topic = taxonomy.add_topic(
            name="Iron-Based Superalloys",
            parent_slug="superalloys",
            keywords=["iron", "Fe"]
        )

        assert topic.parent.slug == "superalloys"
        assert topic.level == 2

    def test_add_topic_unique_slug(self):
        """Test that duplicate slugs are made unique."""
        taxonomy = Taxonomy()

        topic1 = taxonomy.add_topic(name="Test Topic")
        topic2 = taxonomy.add_topic(name="Test Topic")

        assert topic1.slug != topic2.slug
        assert topic2.slug == "test-topic-1"

    def test_find_matching_topics(self, sample_taxonomy_yaml: Path):
        """Test finding matching topics."""
        taxonomy = Taxonomy.from_yaml(sample_taxonomy_yaml)

        matches = taxonomy.find_matching_topics(
            query_topics=["superalloy", "nickel"],
            query_keywords=["creep", "turbine"],
            threshold=0.2
        )

        assert len(matches) > 0
        # First match should be most relevant
        top_topic, top_score = matches[0]
        assert top_score > 0

    def test_find_matching_topics_no_match(self):
        """Test finding topics with no matches."""
        taxonomy = Taxonomy()

        matches = taxonomy.find_matching_topics(
            query_topics=["completely unrelated"],
            query_keywords=["nothing"],
            threshold=0.5
        )

        assert len(matches) == 0

    def test_calculate_match_score(self, sample_taxonomy_yaml: Path):
        """Test match score calculation."""
        taxonomy = Taxonomy.from_yaml(sample_taxonomy_yaml)
        superalloys = taxonomy.get_topic("superalloys")

        # Direct name match should score high
        score = taxonomy._calculate_match_score(
            superalloys,
            {"superalloys"},
            {"creep", "turbine"}
        )
        assert score > 0.5

        # Keyword match should contribute
        score = taxonomy._calculate_match_score(
            superalloys,
            {"unrelated"},
            {"nickel", "creep"}
        )
        assert score > 0

    def test_suggest_topics_for_document(self, sample_taxonomy_yaml: Path):
        """Test topic suggestions for a document."""
        taxonomy = Taxonomy.from_yaml(sample_taxonomy_yaml)

        suggestions = taxonomy.suggest_topics_for_document(
            document_topics=["nickel", "Inconel", "Waspaloy"],
            document_keywords=["superalloy", "turbine", "nickel"],
            max_topics=3
        )

        # Should return a list (may be empty if threshold not met)
        assert isinstance(suggestions, list)
        assert len(suggestions) <= 3

    def test_suggest_topics_with_auto_create(self):
        """Test topic suggestions with auto-create enabled."""
        taxonomy = Taxonomy()

        suggestions = taxonomy.suggest_topics_for_document(
            document_topics=["quantum materials", "superconductors"],
            document_keywords=["quantum", "low temperature"],
            auto_create=True
        )

        # Should create new topics
        assert len(suggestions) > 0

        # New topic should be in taxonomy
        all_topics = taxonomy.get_all_topics()
        slugs = [t.slug for t in all_topics]
        assert any("quantum" in s for s in slugs)

    def test_make_slug(self):
        """Test slug generation."""
        taxonomy = Taxonomy()

        assert taxonomy._make_slug("Test Topic") == "test-topic"
        assert taxonomy._make_slug("Test  Multiple   Spaces") == "test-multiple-spaces"
        assert taxonomy._make_slug("Special!@#Characters") == "specialcharacters"


class TestCreateMaterialsScienceTaxonomy:
    """Tests for the default materials science taxonomy."""

    def test_creates_taxonomy(self):
        """Test that it creates a valid taxonomy."""
        taxonomy = create_materials_science_taxonomy()

        assert taxonomy.root.name == "Materials Science Research"
        assert len(taxonomy.root.children) > 0

    def test_has_expected_topics(self):
        """Test that expected topics exist."""
        taxonomy = create_materials_science_taxonomy()

        # Check for main categories
        magnets = taxonomy.get_topic("permanent-magnets")
        assert magnets is not None

        batteries = taxonomy.get_topic("batteries")
        assert batteries is not None

        am = taxonomy.get_topic("additive-manufacturing")
        assert am is not None

    def test_has_subtopics(self):
        """Test that subtopics are properly nested."""
        taxonomy = create_materials_science_taxonomy()

        # Check for nested topics
        ree_free = taxonomy.get_topic("rare-earth-free-magnets")
        assert ree_free is not None
        assert ree_free.parent.slug == "permanent-magnets"

        solid_state = taxonomy.get_topic("solid-state-batteries")
        assert solid_state is not None
        assert solid_state.parent.slug == "batteries"

    def test_has_keywords(self):
        """Test that topics have keywords."""
        taxonomy = create_materials_science_taxonomy()

        magnets = taxonomy.get_topic("permanent-magnets")
        assert len(magnets.keywords) > 0
        assert "magnet" in magnets.keywords or "magnetic" in magnets.keywords
