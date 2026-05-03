"""Tests for vector repository helpers."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from hal9000.db.models import Base, Document, DocumentChunk
from hal9000.vector import FakeEmbeddingProvider, VectorRepository


def test_vector_repository_stores_and_retrieves_chunk_embeddings():
    """Chunk embeddings should be persisted and read through the repository."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    try:
        document = Document(
            source_path="/papers/paper.pdf",
            source_type="local",
            file_hash="a" * 64,
            title="Test Paper",
        )
        chunk = DocumentChunk(
            document=document,
            chunk_index=0,
            text_hash="b" * 64,
            content="Single crystal samples showed superior creep resistance.",
        )
        session.add(chunk)
        session.flush()

        provider = FakeEmbeddingProvider(dimension=6)
        repository = VectorRepository(session)
        record = repository.embed_and_store_chunk(chunk, provider)
        payload = repository.get_chunk_embedding(chunk.id, provider.name, provider.model)

        assert record.chunk_id == chunk.id
        assert record.embedding_provider == "fake"
        assert record.embedding_model == "fake-6"
        assert record.embedding_dim == 6
        assert payload is not None
        assert payload.embedding == provider.embed_text(chunk.content)
        assert chunk.embeddings[0].id == record.id
    finally:
        session.close()


def test_vector_repository_updates_existing_chunk_embedding():
    """Storing the same chunk/provider/model should update instead of duplicating."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    try:
        document = Document(
            source_path="/papers/paper.pdf",
            source_type="local",
            file_hash="c" * 64,
        )
        chunk = DocumentChunk(
            document=document,
            chunk_index=0,
            text_hash="d" * 64,
            content="Original chunk text.",
        )
        session.add(chunk)
        session.flush()

        repository = VectorRepository(session)
        first = repository.store_chunk_embedding(chunk, [0.1, 0.2], "fake", "fake-2")
        second = repository.store_chunk_embedding(
            chunk,
            [0.3, 0.4],
            "fake",
            "fake-2",
            vector_uri="pgvector://chunk_embeddings/1",
        )
        payload = repository.get_chunk_embedding(chunk.id, "fake", "fake-2")

        assert first.id == second.id
        assert session.query(type(first)).count() == 1
        assert payload is not None
        assert payload.embedding == [0.3, 0.4]
        assert payload.vector_uri == "pgvector://chunk_embeddings/1"
    finally:
        session.close()


def test_vector_repository_searches_chunks_by_cosine_similarity():
    """Semantic search should return chunks ranked by cosine similarity."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    try:
        document = Document(
            source_path="/papers/search.pdf",
            source_type="local",
            file_hash="e" * 64,
            title="Search Paper",
        )
        first = DocumentChunk(
            document=document,
            chunk_index=0,
            text_hash="f" * 64,
            content="Creep resistance improves with single crystal structure.",
        )
        second = DocumentChunk(
            document=document,
            chunk_index=1,
            text_hash="g" * 64,
            content="Oxidation resistance is controlled by coating chemistry.",
        )
        session.add_all([first, second])
        session.flush()

        repository = VectorRepository(session)
        repository.store_chunk_embedding(first, [1.0, 0.0], "fake", "fake-2")
        repository.store_chunk_embedding(second, [0.0, 1.0], "fake", "fake-2")

        results = repository.search_chunks_by_embedding(
            query_embedding=[0.9, 0.1],
            embedding_provider="fake",
            embedding_model="fake-2",
            limit=2,
        )

        assert [result.chunk_id for result in results] == [first.id, second.id]
        assert results[0].score > results[1].score
        assert results[0].document_title == "Search Paper"
        assert results[0].as_context_item()["content"].startswith("Creep resistance")
    finally:
        session.close()
