"""Tests for release automation helpers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.release import update_changelog_text


def test_update_changelog_text_inserts_release_entry():
    """Changelog automation should insert entries under Unreleased."""
    updated = update_changelog_text(
        "# Changelog\n\n## Unreleased\n\n",
        version="0.2.0",
        release_date=date(2026, 5, 17),
        changes=["Add release gate"],
    )

    assert "## Unreleased\n\n## 0.2.0 - 2026-05-17" in updated
    assert "- Add release gate" in updated


def test_release_changelog_cli_dry_run(temp_directory: Path):
    """The CLI should render changelog updates without writing on dry-run."""
    changelog = temp_directory / "CHANGELOG.md"
    changelog.write_text("# Changelog\n\n## Unreleased\n")

    result = CliRunner().invoke(
        cli,
        [
            "release",
            "changelog",
            "--version",
            "0.2.0",
            "--date",
            "2026-05-17",
            "--change",
            "Ship polish",
            "--path",
            str(changelog),
            "--dry-run",
        ],
        obj={},
    )

    assert result.exit_code == 0, result.output
    assert "## 0.2.0 - 2026-05-17" in result.output
    assert "Ship polish" in result.output
    assert changelog.read_text() == "# Changelog\n\n## Unreleased\n"


def test_release_validate_staging_cli(temp_directory: Path):
    """The staging validator should seed and verify the demo walkthrough."""
    db_path = temp_directory / "staging_validate.db"
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
            "release",
            "validate-staging",
            "--project-slug",
            "staging-demo",
            "--json",
        ],
        obj={},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["passed"] is True
    assert payload["project_slug"] == "staging-demo"
    assert payload["checks"]["memory_search"] is True
