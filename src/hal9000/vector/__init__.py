"""Vector storage and embedding helpers."""

from hal9000.vector.embeddings import (
    EmbeddingProvider,
    FakeEmbeddingProvider,
    create_embedding_provider,
)
from hal9000.vector.store import (
    ChunkEmbeddingPayload,
    ChunkSearchResult,
    SemanticSearchResult,
    VectorRepository,
)

__all__ = [
    "ChunkEmbeddingPayload",
    "ChunkSearchResult",
    "SemanticSearchResult",
    "EmbeddingProvider",
    "FakeEmbeddingProvider",
    "VectorRepository",
    "create_embedding_provider",
]
