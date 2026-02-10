"""Tests for database model utilities."""

from pathlib import Path

from sqlalchemy.engine import make_url

from hal9000.db.models import init_db, normalize_database_url


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
