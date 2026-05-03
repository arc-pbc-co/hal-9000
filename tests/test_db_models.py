"""Tests for database model utilities."""

import json
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from hal9000.db.models import (
    ChunkEmbedding,
    Document,
    DocumentChunk,
    EvidenceLink,
    ExtractedClaim,
    ProjectPermission,
    ResearchOutput,
    ResearchProgramRecord,
    ResearchProject,
    ResearchRun,
    ResearchToolCall,
    ReviewDecision,
    Team,
    TeamMembership,
    UserAccount,
    init_db,
    normalize_database_url,
)


class TestDatabaseUrlNormalization:
    """Tests for sqlite URL normalization."""

    def test_normalize_database_url_expands_user_home(self, monkeypatch, temp_directory: Path):
        """`~` in sqlite URLs should be expanded."""
        monkeypatch.setenv("HOME", str(temp_directory))

        normalized = normalize_database_url("sqlite:///~/hal9000_test.db")
        normalized_path = Path(make_url(normalized).database)

        assert "~" not in normalized
        assert normalized_path == (temp_directory / "hal9000_test.db")

    def test_init_db_uses_normalized_sqlite_path(self, monkeypatch, temp_directory: Path):
        """init_db should create an engine with normalized sqlite paths."""
        monkeypatch.setenv("HOME", str(temp_directory))

        engine, _ = init_db("sqlite:///~/hal9000_init_test.db")
        engine_path = Path(engine.url.database)

        assert engine_path == (temp_directory / "hal9000_init_test.db")
        assert engine_path.exists()


class TestSharedResearchStoreModels:
    """Tests for firm-wide research store tables."""

    def test_init_db_creates_shared_research_tables(self, temp_directory: Path):
        """The canonical research store tables should be part of init_db."""
        engine, _ = init_db(f"sqlite:///{temp_directory / 'research_store.db'}")
        table_names = set(inspect(engine).get_table_names())

        assert "research_projects" in table_names
        assert "research_programs" in table_names
        assert "research_runs" in table_names
        assert "research_run_events" in table_names
        assert "research_tool_calls" in table_names
        assert "document_chunks" in table_names
        assert "chunk_embeddings" in table_names
        assert "extracted_claims" in table_names
        assert "evidence_links" in table_names
        assert "research_outputs" in table_names
        assert "review_decisions" in table_names
        assert "user_accounts" in table_names
        assert "teams" in table_names
        assert "team_memberships" in table_names
        assert "project_permissions" in table_names

    def test_identity_and_project_permission_relationships(self, temp_directory: Path):
        """Users and teams should connect to project permission grants."""
        _, session_factory = init_db(f"sqlite:///{temp_directory / 'identity.db'}")
        session = session_factory()

        try:
            project = ResearchProject(
                name="Governed Research",
                slug="governed-research",
                owner="research@example.com",
            )
            user = UserAccount(
                email="researcher@example.com",
                display_name="Researcher",
            )
            team = Team(slug="materials", name="Materials")
            session.add_all([project, user, team])
            session.flush()

            membership = TeamMembership(team=team, user=user, role="member")
            permission = ProjectPermission(
                project=project,
                principal_type="team",
                principal_id=team.id,
                role="reviewer",
                granted_by="admin@example.com",
            )

            session.add(membership)
            session.add(permission)
            session.commit()

            saved = session.query(ResearchProject).filter_by(slug="governed-research").one()

            assert saved.permissions[0].role == "reviewer"
            assert team.memberships[0].user.email == "researcher@example.com"
            assert user.team_memberships[0].team.slug == "materials"
        finally:
            session.close()

    def test_project_program_run_output_review_relationships(self, temp_directory: Path):
        """Projects should connect programs, runs, outputs, and review decisions."""
        _, session_factory = init_db(f"sqlite:///{temp_directory / 'relationships.db'}")
        session = session_factory()

        try:
            project = ResearchProject(
                name="Superalloy Research",
                slug="superalloy-research",
                owner="research@example.com",
            )
            program = ResearchProgramRecord(
                project=project,
                name="Creep Review",
                objective="Find source-backed creep resistance findings.",
                spec_json=json.dumps({"name": "Creep Review"}),
                instructions="Run a bounded review.",
            )
            run = ResearchRun(
                project=project,
                program=program,
                objective=program.objective,
                budget_json=json.dumps({"max_papers": 25}),
            )
            tool_call = ResearchToolCall(
                run=run,
                sequence=1,
                tool_name="acquisition.acquire",
                status="completed",
            )
            output = ResearchOutput(
                project=project,
                run=run,
                output_type="research_brief",
                title="Creep Resistance Brief",
                content="# Brief",
            )
            decision = ReviewDecision(
                output=output,
                decision="promoted",
                reviewer="head-of-engineering@example.com",
                rationale="Sufficient source coverage.",
            )

            session.add(project)
            session.add(tool_call)
            session.add(decision)
            session.commit()

            saved = session.query(ResearchProject).filter_by(slug="superalloy-research").one()

            assert saved.programs[0].name == "Creep Review"
            assert saved.runs[0].status == "queued"
            assert saved.outputs[0].review_decisions[0].decision == "promoted"
            assert saved.outputs[0].run.program.name == "Creep Review"
            assert saved.runs[0].tool_calls[0].tool_name == "acquisition.acquire"
        finally:
            session.close()

    def test_document_chunk_claim_evidence_relationships(self, temp_directory: Path):
        """Documents should connect chunks, extracted claims, and evidence links."""
        _, session_factory = init_db(f"sqlite:///{temp_directory / 'evidence.db'}")
        session = session_factory()

        try:
            document = Document(
                source_path="/papers/paper.pdf",
                source_type="local",
                file_hash="a" * 64,
                title="Test Paper",
            )
            run = ResearchRun(objective="Extract source-backed findings.")
            chunk = DocumentChunk(
                document=document,
                run=run,
                chunk_index=0,
                text_hash="b" * 64,
                content="Single crystal samples showed superior creep resistance.",
                char_start=0,
                char_end=60,
            )
            claim = ExtractedClaim(
                document=document,
                chunk=chunk,
                run=run,
                claim_text="Single crystal samples showed superior creep resistance.",
                confidence=0.8,
                evidence_text="Single crystal samples showed superior creep resistance.",
            )
            evidence = EvidenceLink(
                claim=claim,
                document=document,
                chunk=chunk,
                quote="Single crystal samples showed superior creep resistance.",
                locator="p. 4",
            )
            embedding = ChunkEmbedding(
                chunk=chunk,
                embedding_provider="fake",
                embedding_model="fake-4",
                embedding_dim=4,
                embedding_json="[0.1, 0.2, 0.3, 0.4]",
            )

            session.add(evidence)
            session.add(embedding)
            session.commit()

            saved = session.query(Document).filter_by(file_hash="a" * 64).one()

            assert saved.chunks[0].claims[0].claim_text.startswith("Single crystal")
            assert saved.chunks[0].embeddings[0].embedding_model == "fake-4"
            assert saved.claims[0].evidence_links[0].locator == "p. 4"
            assert saved.chunks[0].run.claims[0].confidence == 0.8
        finally:
            session.close()
