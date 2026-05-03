"""Tests for corpus hardening services."""

from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import Document, init_db
from hal9000.db.store import ResearchStore
from hal9000.research.corpus import CorpusHardeningService, report_payload


def test_corpus_hardening_normalizes_citations_quality_and_refresh_policy(
    temp_directory: Path,
):
    """Corpus hardening should attach normalized source metadata to documents."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'corpus.db'}")
    session = session_factory()

    try:
        document = Document(
            source_path="/papers/source.pdf",
            source_type="local",
            file_hash="d" * 64,
            title="High-Temperature Creep Behavior",
            authors='["Jane Smith", "Robert Chen"]',
            year=2025,
            doi="https://doi.org/10.1016/j.actamat.2025.123456",
            abstract="A source-backed abstract.",
            full_text="Full text.",
            status="completed",
        )
        session.add(document)
        session.flush()

        result = CorpusHardeningService(ResearchStore(session)).harden_document(
            document,
            refresh_policy="interval",
            refresh_interval_days=14,
        )
        session.commit()

        assert result.source_identifier == "doi:10.1016/j.actamat.2025.123456"
        assert document.normalized_doi == "10.1016/j.actamat.2025.123456"
        assert document.citation_key == "smith-2025-high-temperature-creep-behavior"
        assert document.source_quality_label == "high"
        assert document.source_quality_score == 1.0
        assert document.version_group_key == result.source_identifier
        assert document.refresh_policy == "interval"
        assert document.next_refresh_at is not None
    finally:
        session.close()


def test_corpus_hardening_registers_document_versions(temp_directory: Path):
    """A new document version should supersede the previous current version."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'versions.db'}")
    session = session_factory()

    try:
        previous = Document(
            source_path="/papers/source-v1.pdf",
            source_type="local",
            file_hash="e" * 64,
            title="Versioned Source",
            year=2024,
            doi="10.1000/versioned",
        )
        new = Document(
            source_path="/papers/source-v2.pdf",
            source_type="local",
            file_hash="f" * 64,
            title="Versioned Source",
            year=2025,
            doi="10.1000/versioned",
        )
        session.add_all([previous, new])
        session.flush()

        service = CorpusHardeningService(ResearchStore(session))
        service.harden_document(previous, source_version="v1")
        service.register_new_version(previous, new, source_version="v2")
        session.commit()

        assert previous.is_current_version is False
        assert new.is_current_version is True
        assert new.supersedes_document_id == previous.id
        assert new.version_group_key == previous.version_group_key
        assert new.source_version == "v2"
    finally:
        session.close()


def test_corpus_dedupe_report_groups_duplicate_dois_and_titles(temp_directory: Path):
    """Dedupe reports should persist likely duplicate source groups."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'dedupe.db'}")
    session = session_factory()

    try:
        documents = [
            Document(
                source_path="/papers/a.pdf",
                source_type="local",
                file_hash="a" * 64,
                title="Duplicate Source",
                year=2024,
                doi="10.1000/duplicate",
            ),
            Document(
                source_path="/papers/b.pdf",
                source_type="local",
                file_hash="b" * 64,
                title="Duplicate Source",
                year=2024,
                doi="https://doi.org/10.1000/DUPLICATE",
            ),
            Document(
                source_path="/papers/c.pdf",
                source_type="local",
                file_hash="c" * 64,
                title="Unique Source",
                year=2024,
            ),
        ]
        session.add_all(documents)
        session.flush()

        service = CorpusHardeningService(ResearchStore(session))
        service.harden_documents()
        report = service.create_dedupe_report(created_by="curator@example.com")
        session.commit()

        payload = report_payload(report)

        assert report.duplicate_group_count >= 1
        assert report.duplicate_document_count == 2
        assert payload["created_by"] == "curator@example.com"
        assert any(group["match_type"] == "doi" for group in payload["groups"])
    finally:
        session.close()


def test_corpus_hardening_cli_commands(temp_directory: Path):
    """CLI should harden documents and create dedupe reports."""
    db_path = temp_directory / "corpus_cli.db"
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
        session.add_all(
            [
                Document(
                    source_path="/papers/a.pdf",
                    source_type="local",
                    file_hash="1" * 64,
                    title="CLI Duplicate",
                    year=2024,
                    doi="10.1000/cli",
                ),
                Document(
                    source_path="/papers/b.pdf",
                    source_type="local",
                    file_hash="2" * 64,
                    title="CLI Duplicate",
                    year=2024,
                    doi="https://doi.org/10.1000/CLI",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    runner = CliRunner()
    harden_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "harden-corpus",
            "--json",
        ],
        obj={},
    )
    assert harden_result.exit_code == 0, harden_result.output
    assert "doi:10.1000/cli" in harden_result.output

    report_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "dedupe-report",
            "--created-by",
            "curator@example.com",
            "--json",
        ],
        obj={},
    )
    assert report_result.exit_code == 0, report_result.output
    assert '"duplicate_document_count": 2' in report_result.output
