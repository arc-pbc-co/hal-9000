"""Tests for research compliance checks."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import Document, init_db
from hal9000.db.store import ResearchStore
from hal9000.research.compliance import ResearchComplianceService


def test_compliance_check_flags_restricted_pdfs_and_generated_summaries(temp_directory: Path):
    """Compliance reports should find PDF rights and generated summary gaps."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'compliance.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project("Compliance", "compliance")
        run = store.create_run("Review rights posture.", project=project)
        session.add(
            _document(
                "restricted",
                "/papers/restricted.pdf",
                {
                    "copyrighted": True,
                    "rights": "All rights reserved",
                },
            )
        )
        session.add(
            _document(
                "open",
                "/papers/open.pdf",
                {
                    "license": "CC-BY-4.0",
                    "open_access": True,
                },
            )
        )
        store.stage_output(
            "Generated literature summary",
            "literature_brief",
            project=project,
            run=run,
            content="A concise synthesis of the restricted paper.",
            source={"derived_from_copyrighted_pdf": True},
        )
        store.stage_output(
            "Cited summary",
            "literature_brief",
            project=project,
            run=run,
            content="A cited synthesis.",
            source={"citations": [{"document_id": "open"}]},
        )
        session.commit()

        report = ResearchComplianceService(session).check()
        issues = {issue.code: issue for issue in report.issues}

        assert report.checked == {"documents": 2, "outputs": 2}
        assert issues["copyrighted_pdf_review_required"].severity == "high"
        assert issues["generated_summary_copyright_source_review_required"].severity == "high"
        assert "pdf_rights_metadata_missing" not in issues
        assert "generated_summary_missing_provenance" not in issues
    finally:
        session.close()


def test_compliance_cli_json_and_fail_on(temp_directory: Path):
    """The CLI should emit reports and support compliance gates."""
    db_path = temp_directory / "compliance_cli.db"
    config_path = temp_directory / "config.yaml"
    _, session_factory = init_db(f"sqlite:///{db_path}")
    session = session_factory()

    try:
        session.add(_document("unknown", "/papers/unknown.pdf", {}))
        session.commit()
    finally:
        session.close()

    config_path.write_text(
        "\n".join(
            [
                "hal9000:",
                "  database:",
                f"    url: sqlite:///{db_path}",
            ]
        )
    )
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--config", str(config_path), "research", "compliance-check", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["issue_count"] == 1
    assert payload["issues"][0]["code"] == "pdf_rights_metadata_missing"

    fail = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "compliance-check",
            "--fail-on",
            "medium",
        ],
    )
    assert fail.exit_code != 0
    assert "Compliance findings meet --fail-on=medium" in fail.output


def _document(name: str, source_path: str, source_quality: dict[str, object]) -> Document:
    now = datetime(2026, 5, 16, tzinfo=timezone.utc)
    return Document(
        source_path=source_path,
        source_type="local",
        file_hash=f"{name:0<64}"[:64],
        title=f"{name} PDF",
        status="completed",
        source_quality_json=json.dumps(source_quality),
        created_at=now,
        updated_at=now,
        processed_at=now,
    )
