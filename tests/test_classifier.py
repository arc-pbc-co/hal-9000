"""Tests for classifier behavior."""

from hal9000.categorize.classifier import Classifier
from hal9000.categorize.taxonomy import create_materials_science_taxonomy
from hal9000.rlm.processor import DocumentAnalysis


class TestClassifier:
    """Tests for document classification."""

    def test_classify_does_not_mutate_analysis_keywords(self):
        """Classification should not mutate source analysis keywords."""
        taxonomy = create_materials_science_taxonomy()
        classifier = Classifier(taxonomy=taxonomy)

        analysis = DocumentAnalysis(
            primary_topics=["batteries"],
            keywords=["electrolyte", "cathode"],
            materials=[{"name": "LLZO"}],
        )
        original_keywords = list(analysis.keywords)

        classifier.classify(analysis)

        assert analysis.keywords == original_keywords
