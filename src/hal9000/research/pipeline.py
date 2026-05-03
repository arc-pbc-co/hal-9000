"""Corpus preparation pipeline for bounded research runs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from hal9000.db.models import Document, DocumentChunk, ResearchRun
from hal9000.db.store import ClaimEvidence, ResearchStore
from hal9000.ingest import PDFProcessor
from hal9000.vector import EmbeddingProvider, VectorRepository


@dataclass
class CorpusPipelineResult:
    """Summary of corpus records prepared for a research run."""

    document_ids: list[str] = field(default_factory=list)
    chunk_ids: list[str] = field(default_factory=list)
    embedding_ids: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)


class ResearchCorpusPipeline:
    """Prepare documents, chunks, embeddings, and first-pass claims for a run."""

    def __init__(
        self,
        store: ResearchStore,
        embedding_provider: EmbeddingProvider,
        chunk_size: int = 50000,
        chunk_overlap: int = 1000,
        max_claims_per_document: int = 5,
    ):
        """Initialize the corpus pipeline."""
        self.store = store
        self.embedding_provider = embedding_provider
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_claims_per_document = max_claims_per_document
        self.vector_repository = VectorRepository(store.session)
        self.pdf_processor = PDFProcessor(extract_tables=False)

    @property
    def session(self) -> Session:
        """Return the underlying SQLAlchemy session."""
        return self.store.session

    def execute(self, run: ResearchRun) -> CorpusPipelineResult:
        """Prepare the best available local corpus for a run."""
        documents = self._candidate_documents(run)
        result = CorpusPipelineResult(document_ids=[document.id for document in documents])
        self.store.append_run_event(
            run,
            event_type="corpus.documents.selected",
            message=f"Selected {len(documents)} document(s) for corpus preparation.",
            actor="research-corpus-pipeline",
            payload={"document_ids": result.document_ids},
        )

        for document in documents:
            document_result = self.process_document(run, document)
            result.chunk_ids.extend(document_result.chunk_ids)
            result.embedding_ids.extend(document_result.embedding_ids)
            result.claim_ids.extend(document_result.claim_ids)

        self.store.append_run_event(
            run,
            event_type="corpus.prepared",
            message=(
                f"Prepared {len(result.chunk_ids)} chunk(s), "
                f"{len(result.embedding_ids)} embedding(s), and "
                f"{len(result.claim_ids)} claim(s)."
            ),
            actor="research-corpus-pipeline",
            payload={
                "document_count": len(result.document_ids),
                "chunk_count": len(result.chunk_ids),
                "embedding_count": len(result.embedding_ids),
                "claim_count": len(result.claim_ids),
            },
        )
        return result

    def process_document(self, run: ResearchRun, document: Document) -> CorpusPipelineResult:
        """Chunk, embed, and extract first-pass claims for one document."""
        existing_chunks = (
            self.session.query(DocumentChunk)
            .filter_by(document_id=document.id, run_id=run.id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
        if existing_chunks:
            return self._ensure_embeddings_and_claims(run, document, existing_chunks)

        if not document.full_text:
            return CorpusPipelineResult(document_ids=[document.id])

        chunks = self._chunk_document(run, document)
        return self._ensure_embeddings_and_claims(run, document, chunks)

    def _chunk_document(self, run: ResearchRun, document: Document) -> list[DocumentChunk]:
        """Persist canonical run chunks for a document."""
        text = document.full_text or ""
        chunk_texts = self.pdf_processor.chunk_text(
            text,
            chunk_size=self.chunk_size,
            overlap=self.chunk_overlap,
        )
        chunks = []
        cursor = 0
        for index, chunk_text in enumerate(chunk_texts):
            start = text.find(chunk_text, cursor)
            if start < 0:
                start = cursor
            end = start + len(chunk_text)
            cursor = end
            chunks.append(
                self.store.add_document_chunk(
                    document=document,
                    run=run,
                    chunk_index=index,
                    content=chunk_text,
                    char_start=start,
                    char_end=end,
                    token_count=len(chunk_text.split()),
                    extraction_metadata={
                        "pipeline": "ResearchCorpusPipeline",
                        "chunk_size": self.chunk_size,
                        "chunk_overlap": self.chunk_overlap,
                    },
                )
            )
        self.store.append_run_event(
            run,
            event_type="corpus.document.chunked",
            message=f"Chunked document '{document.title or document.id}'.",
            actor="research-corpus-pipeline",
            payload={"document_id": document.id, "chunk_count": len(chunks)},
        )
        return chunks

    def _ensure_embeddings_and_claims(
        self,
        run: ResearchRun,
        document: Document,
        chunks: list[DocumentChunk],
    ) -> CorpusPipelineResult:
        """Ensure chunks have embeddings and document claims."""
        result = CorpusPipelineResult(
            document_ids=[document.id],
            chunk_ids=[chunk.id for chunk in chunks],
        )
        for chunk in chunks:
            embedding = self.vector_repository.embed_and_store_chunk(
                chunk,
                self.embedding_provider,
            )
            result.embedding_ids.append(embedding.id)

        claims = self._extract_claim_candidates(document)
        for index, claim_text in enumerate(claims[: self.max_claims_per_document]):
            chunk = self._best_chunk_for_claim(chunks, claim_text)
            evidence_text = self._evidence_excerpt(chunk.content if chunk else document.full_text, claim_text)
            claim = self.store.add_claim_with_evidence(
                document=document,
                chunk=chunk,
                run=run,
                claim_evidence=ClaimEvidence(
                    claim_text=claim_text,
                    evidence_text=evidence_text,
                    quote=evidence_text,
                    locator=f"chunk {chunk.chunk_index}" if chunk else None,
                    confidence=0.65 if index else 0.7,
                    provenance={
                        "pipeline": "ResearchCorpusPipeline",
                        "source": self._claim_source(document),
                    },
                ),
            )
            result.claim_ids.append(claim.id)

        self.store.append_run_event(
            run,
            event_type="corpus.document.prepared",
            message=f"Prepared document '{document.title or document.id}' for retrieval and outputs.",
            actor="research-corpus-pipeline",
            payload={
                "document_id": document.id,
                "chunk_count": len(result.chunk_ids),
                "embedding_count": len(result.embedding_ids),
                "claim_count": len(result.claim_ids),
            },
        )
        return result

    def _candidate_documents(self, run: ResearchRun) -> list[Document]:
        """Select completed documents for the first local worker slice."""
        max_papers = self._max_papers(run)
        query = (
            self.session.query(Document)
            .filter(Document.full_text.isnot(None))
            .filter(Document.status == "completed")
            .order_by(Document.created_at.desc())
        )
        return query.limit(max_papers).all()

    def _max_papers(self, run: ResearchRun) -> int:
        """Read the max paper budget from the run payload."""
        if not run.budget_json:
            return 10
        try:
            budget = json.loads(run.budget_json)
        except json.JSONDecodeError:
            return 10
        return int(budget.get("max_papers") or 10)

    def _extract_claim_candidates(self, document: Document) -> list[str]:
        """Extract first-pass claim candidates from stored document analysis."""
        candidates = self._json_string_list(document.findings)
        if candidates:
            return _dedupe_preserving_order(candidates)
        if document.summary:
            candidates.extend(_sentence_candidates(document.summary))
        if not candidates and document.full_text:
            candidates.extend(_sentence_candidates(document.full_text[:3000]))
        return _dedupe_preserving_order(candidates)

    def _claim_source(self, document: Document) -> str:
        """Return the source field used for claim candidates."""
        if document.findings:
            return "document.findings"
        if document.summary:
            return "document.summary"
        return "document.full_text"

    def _json_string_list(self, raw_value: str | None) -> list[str]:
        """Parse a JSON string list or return a single textual value."""
        if not raw_value:
            return []
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return [raw_value]
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [str(parsed).strip()] if str(parsed).strip() else []

    def _best_chunk_for_claim(
        self,
        chunks: list[DocumentChunk],
        claim_text: str,
    ) -> DocumentChunk | None:
        """Choose the chunk with the largest token overlap for a claim."""
        if not chunks:
            return None
        claim_tokens = _tokens(claim_text)
        if not claim_tokens:
            return chunks[0]
        return max(chunks, key=lambda chunk: len(claim_tokens & _tokens(chunk.content)))

    def _evidence_excerpt(self, text: str | None, claim_text: str, max_chars: int = 500) -> str:
        """Return a compact evidence excerpt for a claim."""
        source = (text or "").strip()
        if not source:
            return claim_text
        claim_start = source.lower().find(claim_text.lower())
        if claim_start >= 0:
            start = max(0, claim_start - 80)
            end = min(len(source), claim_start + len(claim_text) + 120)
            return source[start:end].strip()
        return source[:max_chars].strip()


def _sentence_candidates(text: str) -> list[str]:
    """Extract simple sentence-like claim candidates from text."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [
        sentence.strip()
        for sentence in sentences
        if 40 <= len(sentence.strip()) <= 500
    ][:10]


def _tokens(text: str) -> set[str]:
    """Return normalized word tokens."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _dedupe_preserving_order(items: list[str]) -> list[str]:
    """Deduplicate textual items while preserving order."""
    seen = set()
    deduped = []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item.strip())
    return deduped
