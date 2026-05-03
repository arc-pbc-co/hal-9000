"""Repository helpers for chunk embedding records."""

import json
import math
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from hal9000.db.models import (
    ChunkEmbedding,
    DocumentChunk,
    ExtractedClaim,
    ResearchOutput,
    ResearchRun,
    utc_now,
)
from hal9000.vector.embeddings import EmbeddingProvider


@dataclass(frozen=True)
class ChunkEmbeddingPayload:
    """Portable chunk embedding payload returned from vector records."""

    chunk_id: str
    embedding_provider: str
    embedding_model: str
    embedding: list[float]
    vector_uri: Optional[str] = None


@dataclass(frozen=True)
class ChunkSearchResult:
    """Semantic search result for a document chunk."""

    chunk_id: str
    document_id: str
    score: float
    content: str
    embedding_provider: str
    embedding_model: str
    document_title: Optional[str] = None
    run_id: Optional[str] = None
    vector_uri: Optional[str] = None

    def as_context_item(self, max_chars: int = 600) -> dict[str, object]:
        """Return a JSON-safe retrieval context item."""
        content = self.content.strip()
        if len(content) > max_chars:
            content = content[: max_chars - 3].rstrip() + "..."
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "run_id": self.run_id,
            "score": round(self.score, 6),
            "content": content,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "vector_uri": self.vector_uri,
        }


@dataclass(frozen=True)
class SemanticSearchResult:
    """Semantic search result for a claim or output."""

    target_type: str
    target_id: str
    score: float
    content: str
    title: Optional[str] = None
    document_id: Optional[str] = None
    run_id: Optional[str] = None
    project_id: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None

    def as_context_item(self, max_chars: int = 600) -> dict[str, object]:
        """Return a JSON-safe retrieval context item."""
        content = self.content.strip()
        if len(content) > max_chars:
            content = content[: max_chars - 3].rstrip() + "..."
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "score": round(self.score, 6),
            "title": self.title,
            "document_id": self.document_id,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "content": content,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
        }


class VectorRepository:
    """Small repository for chunk embedding records."""

    def __init__(self, session: Session):
        """Initialize the repository with a SQLAlchemy session."""
        self.session = session

    def store_chunk_embedding(
        self,
        chunk: DocumentChunk,
        embedding: list[float],
        embedding_provider: str,
        embedding_model: str,
        vector_uri: Optional[str] = None,
    ) -> ChunkEmbedding:
        """Create or update the embedding record for a chunk/provider/model."""
        if not embedding:
            raise ValueError("Embedding must not be empty")

        record = (
            self.session.query(ChunkEmbedding)
            .filter_by(
                chunk_id=chunk.id,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )
            .one_or_none()
        )
        payload = json.dumps(embedding)
        now = utc_now()

        if record is None:
            record = ChunkEmbedding(
                chunk=chunk,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                embedding_dim=len(embedding),
                embedding_json=payload,
                vector_uri=vector_uri,
                created_at=now,
                updated_at=now,
            )
            self.session.add(record)
        else:
            record.embedding_dim = len(embedding)
            record.embedding_json = payload
            record.vector_uri = vector_uri
            record.updated_at = now

        self.session.flush()
        return record

    def embed_and_store_chunk(
        self,
        chunk: DocumentChunk,
        provider: EmbeddingProvider,
        vector_uri: Optional[str] = None,
    ) -> ChunkEmbedding:
        """Embed a chunk's content and persist its vector metadata."""
        embedding = provider.embed_text(chunk.content)
        if len(embedding) != provider.dimension:
            raise ValueError(
                f"Embedding dimension mismatch: expected {provider.dimension}, got {len(embedding)}"
            )
        return self.store_chunk_embedding(
            chunk=chunk,
            embedding=embedding,
            embedding_provider=provider.name,
            embedding_model=provider.model,
            vector_uri=vector_uri,
        )

    def get_chunk_embedding(
        self,
        chunk_id: str,
        embedding_provider: str,
        embedding_model: str,
    ) -> Optional[ChunkEmbeddingPayload]:
        """Fetch a chunk embedding payload by provider/model."""
        record = (
            self.session.query(ChunkEmbedding)
            .filter_by(
                chunk_id=chunk_id,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )
            .one_or_none()
        )
        if record is None:
            return None
        return ChunkEmbeddingPayload(
            chunk_id=record.chunk_id,
            embedding_provider=record.embedding_provider,
            embedding_model=record.embedding_model,
            embedding=json.loads(record.embedding_json),
            vector_uri=record.vector_uri,
        )

    def search_chunks(
        self,
        query_text: str,
        provider: EmbeddingProvider,
        limit: int = 5,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> list[ChunkSearchResult]:
        """Search embedded chunks with a provider-generated query embedding."""
        query_embedding = provider.embed_text(query_text)
        return self.search_chunks_by_embedding(
            query_embedding=query_embedding,
            embedding_provider=provider.name,
            embedding_model=provider.model,
            limit=limit,
            project_id=project_id,
            run_id=run_id,
            min_score=min_score,
        )

    def search_chunks_by_embedding(
        self,
        query_embedding: list[float],
        embedding_provider: str,
        embedding_model: str,
        limit: int = 5,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> list[ChunkSearchResult]:
        """Search embedded chunks by cosine similarity.

        This portable path keeps local SQLite and tests useful. Production
        Postgres can later push the same contract down into pgvector indexes.
        """
        if not query_embedding:
            raise ValueError("Query embedding must not be empty")
        if limit <= 0:
            raise ValueError("Search limit must be positive")

        query = (
            self.session.query(ChunkEmbedding)
            .join(ChunkEmbedding.chunk)
            .filter(
                ChunkEmbedding.embedding_provider == embedding_provider,
                ChunkEmbedding.embedding_model == embedding_model,
            )
        )
        if run_id:
            query = query.filter(DocumentChunk.run_id == run_id)
        if project_id:
            query = query.join(DocumentChunk.run).filter(ResearchRun.project_id == project_id)

        results: list[ChunkSearchResult] = []
        for record in query.all():
            embedding = json.loads(record.embedding_json)
            if len(embedding) != len(query_embedding):
                continue
            score = _cosine_similarity(query_embedding, embedding)
            if min_score is not None and score < min_score:
                continue
            chunk = record.chunk
            results.append(
                ChunkSearchResult(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    score=score,
                    content=chunk.content,
                    embedding_provider=record.embedding_provider,
                    embedding_model=record.embedding_model,
                    document_title=chunk.document.title if chunk.document else None,
                    run_id=chunk.run_id,
                    vector_uri=record.vector_uri,
                )
            )

        results.sort(key=lambda result: result.score, reverse=True)
        return results[:limit]

    def search_claims(
        self,
        query_text: str,
        provider: EmbeddingProvider,
        limit: int = 5,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> list[SemanticSearchResult]:
        """Search extracted claims semantically with provider embeddings."""
        query_embedding = provider.embed_text(query_text)
        query = self.session.query(ExtractedClaim)
        if run_id:
            query = query.filter(ExtractedClaim.run_id == run_id)

        results = []
        for claim in query.all():
            if project_id and (claim.run is None or claim.run.project_id != project_id):
                continue
            content = _claim_search_text(claim)
            score = _score_text(query_embedding, content, provider)
            if min_score is not None and score < min_score:
                continue
            results.append(
                SemanticSearchResult(
                    target_type="claim",
                    target_id=claim.id,
                    score=score,
                    content=claim.claim_text,
                    title=claim.claim_type,
                    document_id=claim.document_id,
                    run_id=claim.run_id,
                    project_id=claim.run.project_id if claim.run else None,
                    embedding_provider=provider.name,
                    embedding_model=provider.model,
                )
            )

        results.sort(key=lambda result: result.score, reverse=True)
        return results[:limit]

    def search_outputs(
        self,
        query_text: str,
        provider: EmbeddingProvider,
        limit: int = 5,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> list[SemanticSearchResult]:
        """Search research outputs semantically with provider embeddings."""
        query = self.session.query(ResearchOutput)
        if run_id:
            query = query.filter(ResearchOutput.run_id == run_id)
        if project_id:
            query = query.filter(ResearchOutput.project_id == project_id)

        query_embedding = provider.embed_text(query_text)
        results = []
        for output in query.all():
            content = _output_search_text(output)
            score = _score_text(query_embedding, content, provider)
            if min_score is not None and score < min_score:
                continue
            results.append(
                SemanticSearchResult(
                    target_type="output",
                    target_id=output.id,
                    score=score,
                    content=output.content or output.title,
                    title=output.title,
                    run_id=output.run_id,
                    project_id=output.project_id,
                    embedding_provider=provider.name,
                    embedding_model=provider.model,
                )
            )

        results.sort(key=lambda result: result.score, reverse=True)
        return results[:limit]

    def search_memory(
        self,
        query_text: str,
        provider: EmbeddingProvider,
        targets: set[str] | None = None,
        limit: int = 5,
        project_id: Optional[str] = None,
        run_id: Optional[str] = None,
        min_score: Optional[float] = None,
    ) -> list[SemanticSearchResult]:
        """Search claims and outputs through one semantic memory API."""
        normalized_targets = targets or {"claims", "outputs"}
        results: list[SemanticSearchResult] = []
        if "claims" in normalized_targets:
            results.extend(
                self.search_claims(
                    query_text,
                    provider,
                    limit=limit,
                    project_id=project_id,
                    run_id=run_id,
                    min_score=min_score,
                )
            )
        if "outputs" in normalized_targets:
            results.extend(
                self.search_outputs(
                    query_text,
                    provider,
                    limit=limit,
                    project_id=project_id,
                    run_id=run_id,
                    min_score=min_score,
                )
            )
        results.sort(key=lambda result: result.score, reverse=True)
        return results[:limit]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """Compute cosine similarity for two equal-length vectors."""
    if len(left) != len(right):
        raise ValueError("Cosine similarity requires equal-length vectors")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right))
    return dot / (left_norm * right_norm)


def _score_text(
    query_embedding: list[float],
    content: str,
    provider: EmbeddingProvider,
) -> float:
    embedding = provider.embed_text(content)
    if len(embedding) != len(query_embedding):
        return 0.0
    return _cosine_similarity(query_embedding, embedding)


def _claim_search_text(claim: ExtractedClaim) -> str:
    parts = [
        claim.claim_text,
        claim.claim_type,
        claim.evidence_text or "",
        claim.normalized_subject or "",
        claim.normalized_predicate or "",
        claim.normalized_object or "",
    ]
    return "\n".join(part for part in parts if part)


def _output_search_text(output: ResearchOutput) -> str:
    parts = [
        output.title,
        output.output_type,
        output.format,
        output.content or "",
    ]
    return "\n".join(part for part in parts if part)
