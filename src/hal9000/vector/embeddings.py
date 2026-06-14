"""Embedding provider abstractions for HAL vector storage."""

import hashlib
import struct
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Protocol implemented by text embedding providers."""

    name: str
    dimension: int
    model: str

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text strings."""
        ...


class FakeEmbeddingProvider:
    """Deterministic test embedding provider with stable dimensions."""

    name = "fake"

    def __init__(self, dimension: int = 1536, model: str | None = None):
        """Initialize the provider with a fixed output dimension."""
        if dimension <= 0:
            raise ValueError("Embedding dimension must be positive")
        self.dimension = dimension
        self.model = model or f"fake-{dimension}"

    def embed_text(self, text: str) -> list[float]:
        """Embed text deterministically using SHA-256 blocks."""
        values: list[float] = []
        counter = 0
        text_bytes = text.encode("utf-8")
        while len(values) < self.dimension:
            digest = hashlib.sha256(text_bytes + counter.to_bytes(4, "big")).digest()
            for offset in range(0, len(digest), 4):
                integer = struct.unpack(">I", digest[offset : offset + 4])[0]
                values.append((integer / 2**32) * 2 - 1)
                if len(values) == self.dimension:
                    break
            counter += 1
        return values

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts deterministically."""
        return [self.embed_text(text) for text in texts]


def create_embedding_provider(
    provider: str = "fake",
    dimension: int = 1536,
    model: str | None = None,
) -> EmbeddingProvider:
    """Create an embedding provider by name."""
    normalized = provider.lower().strip()
    if normalized == "fake":
        return FakeEmbeddingProvider(dimension=dimension, model=model)
    raise ValueError(f"Unsupported embedding provider: {provider}")
