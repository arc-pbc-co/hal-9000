"""Document classifier using taxonomy and RLM analysis."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from hal9000.categorize.taxonomy import Taxonomy, TopicNode
from hal9000.rlm.processor import DocumentAnalysis

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    """Result of document classification."""

    primary_topics: list[TopicNode] = field(default_factory=list)
    secondary_topics: list[TopicNode] = field(default_factory=list)
    confidence_scores: dict[str, float] = field(default_factory=dict)
    suggested_folder_path: Optional[str] = None
    new_topics_created: list[TopicNode] = field(default_factory=list)

    @property
    def all_topics(self) -> list[TopicNode]:
        """Get all assigned topics."""
        return self.primary_topics + self.secondary_topics

    @property
    def topic_slugs(self) -> list[str]:
        """Get slugs of all assigned topics."""
        return [t.slug for t in self.all_topics]

    def get_folder_hierarchy(self) -> list[str]:
        """Get folder hierarchy based on primary topic."""
        if not self.primary_topics:
            return ["Uncategorized"]

        # Use the first primary topic's path
        topic = self.primary_topics[0]
        parts = []
        node = topic
        while node and node.slug != "root":
            parts.append(node.name)
            node = node.parent
        return list(reversed(parts))


class Classifier:
    """
    Classify documents into taxonomy categories.

    Uses RLM analysis results to match documents to taxonomy topics.
    """

    def __init__(
        self,
        taxonomy: Taxonomy,
        auto_extend: bool = True,
        min_confidence: float = 0.3,
        max_topics: int = 5,
    ):
        """
        Initialize the classifier.

        Args:
            taxonomy: The taxonomy to classify against
            auto_extend: Whether to create new topics for unmatched documents
            min_confidence: Minimum confidence score for topic assignment
            max_topics: Maximum topics to assign per document
        """
        self.taxonomy = taxonomy
        self.auto_extend = auto_extend
        self.min_confidence = min_confidence
        self.max_topics = max_topics

    def classify(self, analysis: DocumentAnalysis) -> ClassificationResult:
        """
        Classify a document based on its RLM analysis.

        Args:
            analysis: DocumentAnalysis from RLM processor

        Returns:
            ClassificationResult with assigned topics
        """
        result = ClassificationResult()

        # Combine topics and keywords from analysis
        query_topics = analysis.primary_topics + analysis.secondary_topics
        query_keywords = list(analysis.keywords)

        # Add material names as keywords
        for material in analysis.materials:
            if isinstance(material, dict) and material.get("name"):
                query_keywords.append(material["name"])

        # Find matching topics in taxonomy
        matches = self.taxonomy.find_matching_topics(
            query_topics,
            query_keywords,
            threshold=self.min_confidence,
        )

        # Assign topics based on scores
        for topic, score in matches[: self.max_topics]:
            result.confidence_scores[topic.slug] = score

            if score >= 0.6:
                result.primary_topics.append(topic)
            else:
                result.secondary_topics.append(topic)

        # Auto-extend taxonomy if enabled and no good matches
        if self.auto_extend:
            result = self._auto_extend_taxonomy(analysis, result)

        # Determine folder path
        result.suggested_folder_path = "/".join(result.get_folder_hierarchy())

        return result

    def _auto_extend_taxonomy(
        self, analysis: DocumentAnalysis, result: ClassificationResult
    ) -> ClassificationResult:
        """Create new topics if needed."""
        # If we have good matches, don't create new topics
        if len(result.primary_topics) >= 2:
            return result

        # Check if any analysis topics should become new taxonomy topics
        existing_topic_names = {
            t.name.lower() for t in self.taxonomy.get_all_topics()
        }

        # Find parent topic for new topics
        parent_slug = "root"
        if result.primary_topics:
            parent_slug = result.primary_topics[0].slug
        elif result.secondary_topics:
            parent_slug = result.secondary_topics[0].slug

        # Create new topics for strong signals not in taxonomy
        topics_to_create = []
        for topic_name in analysis.primary_topics[:3]:
            if topic_name.lower() not in existing_topic_names:
                # Check if this is a meaningful topic (not too generic)
                if len(topic_name) > 3 and " " in topic_name or len(topic_name) > 8:
                    topics_to_create.append(topic_name)

        for topic_name in topics_to_create[:2]:  # Limit to 2 new topics
            new_topic = self.taxonomy.add_topic(
                name=topic_name,
                parent_slug=parent_slug,
                keywords=analysis.keywords[:5],
            )
            result.new_topics_created.append(new_topic)
            result.secondary_topics.append(new_topic)
            result.confidence_scores[new_topic.slug] = 0.5

            logger.info(f"Auto-created topic: {new_topic.full_path}")

        return result

    def classify_batch(
        self, analyses: list[DocumentAnalysis]
    ) -> list[ClassificationResult]:
        """Classify multiple documents."""
        return [self.classify(analysis) for analysis in analyses]

    def get_topic_statistics(
        self, results: list[ClassificationResult]
    ) -> dict[str, int]:
        """Get statistics on topic distribution across documents."""
        stats = {}
        for result in results:
            for topic in result.all_topics:
                stats[topic.slug] = stats.get(topic.slug, 0) + 1
        return dict(sorted(stats.items(), key=lambda x: x[1], reverse=True))


class FolderOrganizer:
    """
    Organize documents into folders based on classification.
    """

    def __init__(
        self,
        base_path: Path,
        create_symlinks: bool = True,
        max_folder_depth: int = 3,
    ):
        """
        Initialize the folder organizer.

        Args:
            base_path: Base path for organized folders
            create_symlinks: Create symlinks instead of copying files
            max_folder_depth: Maximum folder nesting depth
        """
        self.base_path = Path(base_path)
        self.create_symlinks = create_symlinks
        self.max_folder_depth = max_folder_depth

    def get_destination_path(
        self, classification: ClassificationResult, filename: str
    ) -> Path:
        """
        Get the destination path for a classified document.

        Args:
            classification: Classification result
            filename: Original filename

        Returns:
            Destination path for the document
        """
        hierarchy = classification.get_folder_hierarchy()

        # Limit depth
        hierarchy = hierarchy[: self.max_folder_depth]

        # Build path
        dest_dir = self.base_path
        for folder in hierarchy:
            dest_dir = dest_dir / self._sanitize_folder_name(folder)

        return dest_dir / filename

    def organize_document(
        self,
        source_path: Path,
        classification: ClassificationResult,
    ) -> Optional[Path]:
        """
        Organize a document into the appropriate folder.

        Args:
            source_path: Source file path
            classification: Classification result

        Returns:
            Destination path, or None if organization failed
        """
        source_path = Path(source_path)
        if not source_path.exists():
            logger.error(f"Source file not found: {source_path}")
            return None

        dest_path = self.get_destination_path(classification, source_path.name)

        # Create destination directory
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if self.create_symlinks:
                # Create symlink
                if dest_path.exists() or dest_path.is_symlink():
                    dest_path.unlink()
                dest_path.symlink_to(source_path.resolve())
            else:
                # Copy file
                import shutil

                shutil.copy2(source_path, dest_path)

            logger.info(f"Organized: {source_path.name} -> {dest_path}")
            return dest_path

        except Exception as e:
            logger.error(f"Failed to organize {source_path}: {e}")
            return None

    def create_folder_structure(self, taxonomy: Taxonomy) -> None:
        """Pre-create folder structure based on taxonomy."""
        for topic in taxonomy.get_all_topics():
            if topic.slug == "root":
                continue

            hierarchy = []
            node = topic
            while node and node.slug != "root":
                hierarchy.append(node.name)
                node = node.parent

            hierarchy = list(reversed(hierarchy))[: self.max_folder_depth]

            folder_path = self.base_path
            for folder in hierarchy:
                folder_path = folder_path / self._sanitize_folder_name(folder)

            folder_path.mkdir(parents=True, exist_ok=True)

    def _sanitize_folder_name(self, name: str) -> str:
        """Make a folder name filesystem-safe."""
        import re

        # Remove/replace problematic characters
        safe_name = re.sub(r'[<>:"/\\|?*]', "", name)
        safe_name = safe_name.strip(". ")
        return safe_name[:100]  # Limit length
