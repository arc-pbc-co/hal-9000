"""Tests for corpus hardening services."""

import hashlib
from datetime import timedelta
from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import Document, ExtractedClaim, init_db, utc_now
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


def test_scheduled_source_refresh_checks_due_local_sources_and_versions(temp_directory: Path):
    """Scheduled refresh should advance unchanged sources and version changed local files."""
    source = temp_directory / "source.txt"
    source.write_text("version one")
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'refresh.db'}")
    session = session_factory()

    try:
        document = Document(
            source_path=str(source),
            source_type="local",
            file_hash=original_hash,
            title="Refreshable Source",
            year=2024,
            doi="10.1000/refresh",
            full_text="version one",
            status="completed",
            refresh_policy="interval",
            refresh_interval_days=7,
            last_refreshed_at=utc_now() - timedelta(days=14),
            next_refresh_at=utc_now() - timedelta(days=1),
            source_version="v1",
        )
        session.add(document)
        session.flush()

        service = CorpusHardeningService(ResearchStore(session))
        unchanged = service.execute_scheduled_refresh(refreshed_by="scheduler@example.com")
        session.flush()

        assert [result.status for result in unchanged] == ["unchanged"]
        assert document.next_refresh_at > utc_now()
        assert session.query(Document).count() == 1

        source.write_text("version two")
        changed_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        document.next_refresh_at = utc_now() - timedelta(seconds=1)
        session.flush()
        changed = service.execute_scheduled_refresh(refreshed_by="scheduler@example.com")
        session.commit()

        new_document = session.get(Document, changed[0].new_document_id)

        assert changed[0].status == "new_version_detected"
        assert changed[0].previous_file_hash == original_hash
        assert changed[0].current_file_hash == changed_hash
        assert document.is_current_version is False
        assert new_document is not None
        assert new_document.file_hash == changed_hash
        assert new_document.supersedes_document_id == document.id
        assert new_document.source_version == "v2"
        assert new_document.status == "pending"
    finally:
        session.close()


def test_claim_dedupe_report_groups_duplicate_claim_text(temp_directory: Path):
    """Claim-level dedupe reports should persist duplicate extracted-claim groups."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'claim-dedupe.db'}")
    session = session_factory()

    try:
        first_document = Document(
            source_path="/papers/claim-a.pdf",
            source_type="local",
            file_hash="4" * 64,
            title="Claim A",
        )
        second_document = Document(
            source_path="/papers/claim-b.pdf",
            source_type="local",
            file_hash="5" * 64,
            title="Claim B",
        )
        session.add_all([first_document, second_document])
        session.flush()
        session.add_all(
            [
                ExtractedClaim(
                    document_id=first_document.id,
                    claim_text="Single crystal structure improves creep resistance.",
                    normalized_subject="single crystal structure",
                    normalized_predicate="improves",
                    normalized_object="creep resistance",
                    status="staged",
                ),
                ExtractedClaim(
                    document_id=second_document.id,
                    claim_text="single-crystal structure improves creep resistance",
                    normalized_subject="single crystal structure",
                    normalized_predicate="improves",
                    normalized_object="creep resistance",
                    status="staged",
                ),
                ExtractedClaim(
                    document_id=second_document.id,
                    claim_text="Gamma prime precipitates affect deformation.",
                    status="staged",
                ),
            ]
        )
        session.flush()

        report = CorpusHardeningService(ResearchStore(session)).create_claim_dedupe_report(
            created_by="curator@example.com"
        )
        session.commit()

        payload = report_payload(report)

        assert report.report_type == "claim_duplicates"
        assert report.duplicate_group_count >= 1
        assert payload["duplicate_claim_count"] == 2
        assert payload["created_by"] == "curator@example.com"
        assert any(group["match_type"] == "claim_triple" for group in payload["groups"])
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


def test_corpus_refresh_and_claim_dedupe_cli_commands(temp_directory: Path):
    """CLI should execute due source refreshes and claim-level dedupe reports."""
    db_path = temp_directory / "corpus_refresh_cli.db"
    config_path = temp_directory / "refresh_config.yaml"
    source = temp_directory / "refresh-source.txt"
    source.write_text("stable source")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    config_path.write_text(
        f"""hal9000:
  database:
    url: sqlite:///{db_path}
"""
    )
    _, session_factory = init_db(f"sqlite:///{db_path}")
    session = session_factory()
    try:
        refresh_document = Document(
            source_path=str(source),
            source_type="local",
            file_hash=source_hash,
            title="CLI Refresh Source",
            refresh_policy="interval",
            refresh_interval_days=3,
            last_refreshed_at=utc_now() - timedelta(days=6),
            next_refresh_at=utc_now() - timedelta(days=1),
            status="completed",
        )
        first_claim_document = Document(
            source_path="/papers/claim-cli-a.pdf",
            source_type="local",
            file_hash="6" * 64,
            title="Claim CLI A",
        )
        second_claim_document = Document(
            source_path="/papers/claim-cli-b.pdf",
            source_type="local",
            file_hash="7" * 64,
            title="Claim CLI B",
        )
        session.add_all([refresh_document, first_claim_document, second_claim_document])
        session.flush()
        session.add_all(
            [
                ExtractedClaim(
                    document_id=first_claim_document.id,
                    claim_text="Rhenium additions improve creep life.",
                    status="staged",
                ),
                ExtractedClaim(
                    document_id=second_claim_document.id,
                    claim_text="rhenium additions improve creep life",
                    status="staged",
                ),
            ]
        )
        session.commit()
    finally:
        session.close()

    runner = CliRunner()
    refresh_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "refresh-sources",
            "--json",
        ],
        obj={},
    )
    assert refresh_result.exit_code == 0, refresh_result.output
    assert '"status": "unchanged"' in refresh_result.output

    claim_report_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "dedupe-report",
            "--claims",
            "--created-by",
            "curator@example.com",
            "--json",
        ],
        obj={},
    )
    assert claim_report_result.exit_code == 0, claim_report_result.output
    assert '"report_type": "claim_duplicates"' in claim_report_result.output
    assert '"duplicate_claim_count": 2' in claim_report_result.output
