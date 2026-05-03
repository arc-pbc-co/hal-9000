"""Tests for research corpus preparation."""

import json
from pathlib import Path

from hal9000.db.models import Document, init_db
from hal9000.db.store import ResearchStore
from hal9000.research import load_program
from hal9000.research.pipeline import ResearchCorpusPipeline
from hal9000.vector import FakeEmbeddingProvider


def test_research_corpus_pipeline_chunks_embeds_and_extracts_claims(temp_directory: Path):
    """The corpus pipeline should prepare local documents for run outputs."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'pipeline.db'}")
    session = session_factory()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        program = load_program(repo_root / "templates/research/programs/literature-review.md")

        store = ResearchStore(session)
        project = store.create_project(name="Pipeline Test", slug="pipeline-test")
        record = store.save_program(program, project=project)
        run = store.create_run(
            objective="Find source-backed creep resistance findings.",
            project=project,
            program=record,
            budget={"max_papers": 2},
        )
        document = Document(
            source_path="/papers/pipeline.pdf",
            source_type="acquisition",
            file_hash="p" * 64,
            title="Pipeline Source",
            summary=(
                "Single crystal samples showed superior creep resistance at elevated "
                "temperature compared with directionally solidified samples."
            ),
            findings=json.dumps(
                [
                    "Single crystal samples showed superior creep resistance at elevated temperature.",
                    "Directional solidification reduced defect density in test coupons.",
                ]
            ),
            full_text=(
                "Single crystal samples showed superior creep resistance at elevated "
                "temperature compared with directionally solidified samples. "
                "Directional solidification reduced defect density in test coupons."
            ),
            status="completed",
        )
        session.add(document)
        session.flush()

        result = ResearchCorpusPipeline(
            store,
            embedding_provider=FakeEmbeddingProvider(dimension=8),
            chunk_size=80,
            chunk_overlap=10,
        ).execute(run)
        session.commit()

        assert result.document_ids == [document.id]
        assert len(result.chunk_ids) >= 1
        assert len(result.embedding_ids) == len(result.chunk_ids)
        assert len(result.claim_ids) == 2
        assert run.chunks[0].embeddings[0].embedding_dim == 8
        assert run.claims[0].claim_text.startswith("Single crystal")
        assert run.claims[0].evidence_links[0].locator.startswith("chunk")
        assert "corpus.prepared" in [event.event_type for event in run.events]
    finally:
        session.close()
