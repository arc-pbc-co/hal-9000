"""Topic taxonomy management for document categorization."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class TopicNode:
    """A node in the topic taxonomy tree."""

    name: str
    slug: str
    description: Optional[str] = None
    parent: Optional["TopicNode"] = None
    children: list["TopicNode"] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    level: int = 0

    def __hash__(self):
        return hash(self.slug)

    def __eq__(self, other):
        if isinstance(other, TopicNode):
            return self.slug == other.slug
        return False

    @property
    def full_path(self) -> str:
        """Get full path from root to this node."""
        parts = []
        node = self
        while node:
            parts.append(node.name)
            node = node.parent
        return " > ".join(reversed(parts))

    def add_child(self, child: "TopicNode") -> None:
        """Add a child node."""
        child.parent = self
        child.level = self.level + 1
        self.children.append(child)

    def find_child(self, slug: str) -> Optional["TopicNode"]:
        """Find a direct child by slug."""
        for child in self.children:
            if child.slug == slug:
                return child
        return None

    def find_descendant(self, slug: str) -> Optional["TopicNode"]:
        """Find any descendant by slug (DFS)."""
        if self.slug == slug:
            return self

        for child in self.children:
            result = child.find_descendant(slug)
            if result:
                return result

        return None

    def get_all_descendants(self) -> list["TopicNode"]:
        """Get all descendant nodes."""
        descendants = []
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_all_descendants())
        return descendants

    def to_dict(self) -> dict:
        """Convert to dictionary (for serialization)."""
        return {
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "keywords": self.keywords,
            "children": [child.to_dict() for child in self.children],
        }


class Taxonomy:
    """
    Manages a hierarchical topic taxonomy for document categorization.

    The taxonomy supports:
    - Loading from YAML configuration
    - Auto-extension with new topics
    - Topic matching with keyword support
    """

    def __init__(self, root_name: str = "Research"):
        """Initialize taxonomy with a root node."""
        self.root = TopicNode(name=root_name, slug="root")
        self._slug_index: dict[str, TopicNode] = {"root": self.root}

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "Taxonomy":
        """Load taxonomy from a YAML file."""
        taxonomy = cls()

        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            logger.warning(f"Taxonomy file not found: {yaml_path}")
            return taxonomy

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        if data and "taxonomy" in data:
            taxonomy._load_nodes(taxonomy.root, data["taxonomy"])

        return taxonomy

    def _load_nodes(self, parent: TopicNode, nodes_data: list[dict]) -> None:
        """Recursively load nodes from YAML data."""
        for node_data in nodes_data:
            slug = node_data.get("slug", self._make_slug(node_data["name"]))
            node = TopicNode(
                name=node_data["name"],
                slug=slug,
                description=node_data.get("description"),
                keywords=node_data.get("keywords", []),
            )
            parent.add_child(node)
            self._slug_index[slug] = node

            if "children" in node_data:
                self._load_nodes(node, node_data["children"])

    def save_yaml(self, yaml_path: Path) -> None:
        """Save taxonomy to a YAML file."""
        data = {
            "taxonomy": [child.to_dict() for child in self.root.children]
        }

        with open(yaml_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def get_topic(self, slug: str) -> Optional[TopicNode]:
        """Get a topic by slug."""
        return self._slug_index.get(slug)

    def get_all_topics(self) -> list[TopicNode]:
        """Get all topics in the taxonomy."""
        return list(self._slug_index.values())

    def add_topic(
        self,
        name: str,
        parent_slug: str = "root",
        description: Optional[str] = None,
        keywords: Optional[list[str]] = None,
    ) -> TopicNode:
        """
        Add a new topic to the taxonomy.

        Args:
            name: Topic name
            parent_slug: Parent topic slug (default: root)
            description: Optional description
            keywords: Optional list of keywords

        Returns:
            The created TopicNode
        """
        parent = self._slug_index.get(parent_slug)
        if not parent:
            logger.warning(f"Parent topic not found: {parent_slug}, using root")
            parent = self.root

        slug = self._make_slug(name)

        # Ensure unique slug
        base_slug = slug
        counter = 1
        while slug in self._slug_index:
            slug = f"{base_slug}-{counter}"
            counter += 1

        node = TopicNode(
            name=name,
            slug=slug,
            description=description,
            keywords=keywords or [],
        )
        parent.add_child(node)
        self._slug_index[slug] = node

        logger.info(f"Added topic: {node.full_path}")
        return node

    def find_matching_topics(
        self,
        query_topics: list[str],
        query_keywords: list[str],
        threshold: float = 0.3,
    ) -> list[tuple[TopicNode, float]]:
        """
        Find topics that match the given topics/keywords.

        Args:
            query_topics: Topics extracted from a document
            query_keywords: Keywords extracted from a document
            threshold: Minimum match score to include

        Returns:
            List of (topic, score) tuples, sorted by score descending
        """
        matches = []

        # Normalize queries
        query_topics_lower = {t.lower() for t in query_topics}
        query_keywords_lower = {k.lower() for k in query_keywords}

        for topic in self._slug_index.values():
            if topic.slug == "root":
                continue

            score = self._calculate_match_score(
                topic, query_topics_lower, query_keywords_lower
            )

            if score >= threshold:
                matches.append((topic, score))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def _calculate_match_score(
        self,
        topic: TopicNode,
        query_topics: set[str],
        query_keywords: set[str],
    ) -> float:
        """Calculate how well a topic matches the query."""
        score = 0.0

        # Direct name match (highest weight)
        if topic.name.lower() in query_topics:
            score += 1.0

        # Name in query topics (partial match)
        topic_words = set(topic.name.lower().split())
        topic_word_matches = len(topic_words & query_topics)
        if topic_word_matches > 0:
            score += 0.5 * (topic_word_matches / len(topic_words))

        # Keyword matches
        topic_keywords = {k.lower() for k in topic.keywords}
        keyword_matches = len(topic_keywords & query_keywords)
        if topic_keywords and keyword_matches > 0:
            score += 0.3 * (keyword_matches / len(topic_keywords))

        # Query topics match topic keywords
        topic_keyword_in_query = len(topic_keywords & query_topics)
        if topic_keyword_in_query > 0:
            score += 0.4 * (topic_keyword_in_query / max(len(topic_keywords), 1))

        return min(score, 1.0)  # Cap at 1.0

    def suggest_topics_for_document(
        self,
        document_topics: list[str],
        document_keywords: list[str],
        max_topics: int = 5,
        auto_create: bool = False,
    ) -> list[TopicNode]:
        """
        Suggest taxonomy topics for a document.

        Args:
            document_topics: Topics extracted from document
            document_keywords: Keywords extracted from document
            max_topics: Maximum topics to suggest
            auto_create: Whether to create new topics if no match found

        Returns:
            List of suggested TopicNode objects
        """
        # Find matching existing topics
        matches = self.find_matching_topics(
            document_topics, document_keywords, threshold=0.3
        )

        suggested = [topic for topic, score in matches[:max_topics]]

        # If auto_create and no good matches, create new topics
        if auto_create and len(suggested) < 2 and document_topics:
            for topic_name in document_topics[:2]:
                if not any(topic_name.lower() == s.name.lower() for s in suggested):
                    new_topic = self.add_topic(
                        name=topic_name,
                        keywords=document_keywords[:5],
                    )
                    suggested.append(new_topic)

        return suggested

    def _make_slug(self, name: str) -> str:
        """Create a URL-safe slug from a name."""
        import re

        slug = name.lower()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = slug.strip("-")
        return slug

    def print_tree(self, node: Optional[TopicNode] = None, indent: int = 0) -> None:
        """Print the taxonomy tree (for debugging)."""
        if node is None:
            node = self.root

        prefix = "  " * indent
        print(f"{prefix}- {node.name} ({node.slug})")

        for child in node.children:
            self.print_tree(child, indent + 1)


def create_materials_science_taxonomy() -> Taxonomy:
    """Create a default Materials Science taxonomy."""
    taxonomy = Taxonomy(root_name="Materials Science Research")

    # Main categories
    magnets = taxonomy.add_topic(
        "Permanent Magnets",
        description="Research on permanent magnetic materials",
        keywords=["magnet", "magnetic", "coercivity", "remanence", "Curie temperature"],
    )

    taxonomy.add_topic(
        "Rare-Earth-Free Magnets",
        parent_slug="permanent-magnets",
        description="Magnets without rare earth elements",
        keywords=["rare-earth-free", "iron-nitride", "MnBi", "MnAl", "ferrite"],
    )

    taxonomy.add_topic(
        "Rare-Earth Magnets",
        parent_slug="permanent-magnets",
        keywords=["NdFeB", "SmCo", "neodymium", "samarium", "dysprosium"],
    )

    batteries = taxonomy.add_topic(
        "Batteries",
        description="Battery and energy storage research",
        keywords=["battery", "energy storage", "electrode", "electrolyte", "capacity"],
    )

    taxonomy.add_topic(
        "Solid-State Batteries",
        parent_slug="batteries",
        keywords=["solid electrolyte", "all-solid-state", "LLZO", "sulfide", "oxide"],
    )

    taxonomy.add_topic(
        "Lithium-Ion Batteries",
        parent_slug="batteries",
        keywords=["Li-ion", "lithium", "cathode", "anode", "LFP", "NMC", "graphite"],
    )

    taxonomy.add_topic(
        "Additive Manufacturing",
        description="3D printing and additive manufacturing",
        keywords=["3D printing", "binder jetting", "SLM", "powder bed", "sintering"],
    )

    taxonomy.add_topic(
        "Characterization",
        description="Materials characterization techniques",
        keywords=["XRD", "SEM", "TEM", "XPS", "SQUID", "VSM", "microscopy"],
    )

    taxonomy.add_topic(
        "Synthesis",
        description="Materials synthesis methods",
        keywords=["synthesis", "fabrication", "processing", "annealing", "milling"],
    )

    taxonomy.add_topic(
        "Computational Materials",
        description="Computational and theoretical materials science",
        keywords=["DFT", "simulation", "machine learning", "modeling", "first-principles"],
    )

    return taxonomy
