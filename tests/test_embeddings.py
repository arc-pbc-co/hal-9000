"""Tests for embedding providers."""

import pytest

from hal9000.vector import FakeEmbeddingProvider, create_embedding_provider


def test_fake_embedding_provider_is_deterministic():
    """Fake embeddings should be stable for tests."""
    provider = FakeEmbeddingProvider(dimension=8)

    first = provider.embed_text("single crystal creep resistance")
    second = provider.embed_text("single crystal creep resistance")
    other = provider.embed_text("gamma prime strengthening")

    assert first == second
    assert first != other
    assert len(first) == 8
    assert all(-1 <= value <= 1 for value in first)


def test_fake_embedding_provider_batches_texts():
    """Batch embedding should preserve order and dimensions."""
    provider = FakeEmbeddingProvider(dimension=4)

    embeddings = provider.embed_batch(["alpha", "beta"])

    assert embeddings == [provider.embed_text("alpha"), provider.embed_text("beta")]
    assert all(len(embedding) == 4 for embedding in embeddings)


def test_create_embedding_provider_supports_fake_provider():
    """The provider factory should build the deterministic fake provider."""
    provider = create_embedding_provider("fake", dimension=12, model="fake-test")

    assert provider.name == "fake"
    assert provider.dimension == 12
    assert provider.model == "fake-test"


def test_create_embedding_provider_rejects_unknown_provider():
    """Unsupported embedding providers should fail explicitly."""
    with pytest.raises(ValueError):
        create_embedding_provider("unknown")
