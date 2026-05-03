"""Tests for Alembic migrations."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_head_creates_current_schema(temp_directory: Path):
    """Alembic should be able to create the current schema from scratch."""
    db_path = temp_directory / "migrated.db"
    repo_root = Path(__file__).resolve().parents[1]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    table_names = set(inspect(engine).get_table_names())

    assert "alembic_version" in table_names
    assert "documents" in table_names
    assert "research_projects" in table_names
    assert "research_run_events" in table_names
    assert "research_outputs" in table_names
    assert "evidence_links" in table_names
    assert "chunk_embeddings" in table_names
    assert "research_tool_calls" in table_names


def test_alembic_autogenerate_is_clean(temp_directory: Path):
    """Alembic autogenerate should not find model/schema drift after upgrade."""
    db_path = temp_directory / "clean.db"
    repo_root = Path(__file__).resolve().parents[1]
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(config, "head")
    command.check(config)
