"""Tests for research graph relationship services."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import Document, init_db
from hal9000.db.store import ClaimEvidence, ResearchStore
from hal9000.research.graph import (
    ResearchGraphService,
    edge_payload,
    normalize_graph_relationship,
)


def test_research_graph_service_adds_and_lists_typed_edges(temp_directory: Path):
    """Graph service should persist and query typed research relationships."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'graph.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project("Graph", "graph")
        run = store.create_run("Build graph relationships.", project=project)
        document = Document(
            source_path="/papers/source.pdf",
            source_type="local",
            file_hash="a" * 64,
            title="Graph Source",
        )
        session.add(document)
        session.flush()
        chunk = store.add_document_chunk(
            document,
            "CMSX-4 studies single crystal creep resistance.",
            0,
            run=run,
        )
        claim = store.add_claim_with_evidence(
            document,
            ClaimEvidence(
                claim_text="CMSX-4 improves creep resistance.",
                quote="CMSX-4 studies single crystal creep resistance.",
            ),
            chunk=chunk,
            run=run,
        )
        output = store.stage_output(
            "Graph Brief",
            "research_brief",
            project=project,
            run=run,
            content="# Brief",
        )

        service = ResearchGraphService(store)
        support_edge = service.add_edge(
            "claim",
            claim.id,
            "supports",
            "output",
            output.id,
            confidence=0.82,
            evidence={"quote": "CMSX-4 studies single crystal creep resistance."},
            created_by="curator@example.com",
        )
        material_edge = service.add_edge(
            "claim",
            claim.id,
            "studies_material",
            "material",
            "CMSX-4",
        )
        session.commit()

        support_payload = edge_payload(support_edge).to_dict()
        claim_edges = service.edges_for_entity("claim", claim.id)
        material_edges = service.list_edges(relationship_type="studies-material")

        assert support_payload["relationship_type"] == "supports"
        assert support_payload["project_id"] == project.id
        assert support_payload["run_id"] == run.id
        assert support_payload["evidence"]["quote"].startswith("CMSX-4")
        assert {edge.id for edge in claim_edges} == {support_edge.id, material_edge.id}
        assert material_edges[0].target_id == "CMSX-4"
    finally:
        session.close()


def test_research_graph_service_validates_relationships(temp_directory: Path):
    """Unsupported graph relationship names should fail explicitly."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'graph_invalid.db'}")
    session = session_factory()
    try:
        store = ResearchStore(session)
        service = ResearchGraphService(store)

        with pytest.raises(ValueError, match="Unsupported graph relationship"):
            service.add_edge("material", "CMSX-4", "sort_of_related", "property", "creep")

        assert normalize_graph_relationship("uses-method") == "uses_method"
    finally:
        session.close()


def test_research_graph_cli_adds_and_lists_edges(temp_directory: Path):
    """CLI should add and list graph relationships."""
    db_path = temp_directory / "graph_cli.db"
    config_path = temp_directory / "config.yaml"
    config_path.write_text(
        f"""hal9000:
  database:
    url: sqlite:///{db_path}
"""
    )
    _, session_factory = init_db(f"sqlite:///{db_path}")
    session = session_factory()
    try:
        store = ResearchStore(session)
        project = store.create_project("Graph CLI", "graph-cli")
        run = store.create_run("Graph CLI.", project=project)
        document = Document(
            source_path="/papers/cli.pdf",
            source_type="local",
            file_hash="b" * 64,
            title="CLI Source",
        )
        session.add(document)
        session.flush()
        output = store.stage_output(
            "CLI Brief",
            "research_brief",
            project=project,
            run=run,
            content="# Brief",
        )
        document_id = document.id
        output_id = output.id
        session.commit()
    finally:
        session.close()

    runner = CliRunner()
    add_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "add-graph-edge",
            "--source-type",
            "output",
            "--source-id",
            output_id,
            "--relationship",
            "cites",
            "--target-type",
            "document",
            "--target-id",
            document_id,
            "--confidence",
            "0.9",
            "--created-by",
            "curator@example.com",
        ],
        obj={},
    )
    assert add_result.exit_code == 0, add_result.output
    assert "Research graph edge added" in add_result.output

    list_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "graph-edges",
            "--relationship",
            "cites",
            "--json",
        ],
        obj={},
    )
    assert list_result.exit_code == 0, list_result.output
    assert '"relationship_type": "cites"' in list_result.output
    assert output_id in list_result.output
