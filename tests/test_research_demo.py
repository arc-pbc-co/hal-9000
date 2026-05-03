"""Tests for full-team demo seeding."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.collaboration import CollaborationService
from hal9000.research.demo import DemoSeedService
from hal9000.research.sheets import SheetsSyncService
from hal9000.vector.embeddings import FakeEmbeddingProvider
from hal9000.vector.store import VectorRepository


def test_demo_seed_service_creates_complete_walkthrough_dataset(temp_directory: Path):
    """Demo seed should create memory, staged outputs, review records, and Sheets rows."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'demo.db'}")
    session = session_factory()
    try:
        store = ResearchStore(session)
        result = DemoSeedService(store).seed(
            reviewer_email="reviewer@example.com",
            contributor_email="researcher@example.com",
        )
        session.commit()

        run = store.get_run(result.run_id)
        project = store.get_project_by_slug(result.project_slug)
        assert run.status == "staged"
        assert len(run.outputs) == 3
        assert len(run.claims) == 2
        assert len(CollaborationService(store).list_notifications(project=project)) == 3

        chunks = VectorRepository(session).search_chunks(
            "single crystal superalloy creep",
            FakeEmbeddingProvider(),
            project_id=project.id,
            limit=5,
        )
        memory = VectorRepository(session).search_memory(
            "single crystal superalloy creep",
            FakeEmbeddingProvider(),
            targets={"claims", "outputs"},
            project_id=project.id,
            limit=5,
        )
        assert chunks
        assert memory

        rows = SheetsSyncService(store).values_for_project_view(
            project,
            target="review_queue",
            reviewer_email=result.reviewer_email,
        )
        assert rows[0][0] == "run_id"
        assert rows[1][0] == result.run_id
    finally:
        session.close()


def test_demo_seed_cli_outputs_demo_commands(temp_directory: Path):
    """CLI should expose the one-command demo seed."""
    db_path = temp_directory / "demo_cli.db"
    config_path = temp_directory / "config.yaml"
    config_path.write_text(
        f"""hal9000:
  database:
    url: sqlite:///{db_path}
"""
    )

    result = CliRunner().invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "demo-seed",
            "--project-slug",
            "team-demo",
            "--reviewer",
            "reviewer@example.com",
            "--contributor",
            "researcher@example.com",
            "--json",
        ],
        obj={},
    )

    assert result.exit_code == 0, result.output
    assert '"project_slug": "team-demo"' in result.output
    assert '"review team-demo"' in result.output


def test_demo_seed_cli_can_run_repeatedly(temp_directory: Path):
    """Demo seed should be safe to rerun during live walkthrough setup."""
    db_path = temp_directory / "demo_repeat.db"
    config_path = temp_directory / "config.yaml"
    config_path.write_text(
        f"""hal9000:
  database:
    url: sqlite:///{db_path}
"""
    )
    runner = CliRunner()

    for _ in range(2):
        result = runner.invoke(
            cli,
            [
                "--config",
                str(config_path),
                "research",
                "demo-seed",
                "--project-slug",
                "repeat-demo",
                "--reviewer",
                "reviewer@example.com",
                "--contributor",
                "researcher@example.com",
                "--json",
            ],
            obj={},
        )
        assert result.exit_code == 0, result.output
        assert '"project_slug": "repeat-demo"' in result.output
