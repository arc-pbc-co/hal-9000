"""Release automation helpers for HAL 9000."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import date
from pathlib import Path

CHANGELOG_HEADING = "# Changelog"
UNRELEASED_HEADING = "## Unreleased"


def changelog_entry(version: str, changes: Sequence[str], release_date: date | None = None) -> str:
    """Render one changelog entry."""
    if not version.strip():
        raise ValueError("version is required")
    clean_changes = [change.strip() for change in changes if change.strip()]
    if not clean_changes:
        raise ValueError("at least one changelog change is required")
    released_on = release_date or date.today()
    lines = [f"## {version.strip()} - {released_on.isoformat()}", ""]
    lines.extend(f"- {change}" for change in clean_changes)
    return "\n".join(lines).rstrip() + "\n"


def update_changelog_text(
    existing: str,
    *,
    version: str,
    changes: Sequence[str],
    release_date: date | None = None,
) -> str:
    """Insert a changelog entry after the Unreleased heading."""
    entry = changelog_entry(version, changes, release_date=release_date)
    text = existing.strip()
    if not text:
        return f"{CHANGELOG_HEADING}\n\n{UNRELEASED_HEADING}\n\n{entry}"
    if UNRELEASED_HEADING in text:
        return text.replace(UNRELEASED_HEADING, f"{UNRELEASED_HEADING}\n\n{entry}", 1) + "\n"
    if text.startswith(CHANGELOG_HEADING):
        return text.replace(CHANGELOG_HEADING, f"{CHANGELOG_HEADING}\n\n{UNRELEASED_HEADING}\n\n{entry}", 1) + "\n"
    return f"{CHANGELOG_HEADING}\n\n{UNRELEASED_HEADING}\n\n{entry}\n{text}\n"


def update_changelog_file(
    path: Path,
    *,
    version: str,
    changes: Sequence[str],
    release_date: date | None = None,
) -> str:
    """Update a changelog file and return its new content."""
    existing = path.read_text() if path.exists() else ""
    updated = update_changelog_text(
        existing,
        version=version,
        changes=changes,
        release_date=release_date,
    )
    path.write_text(updated)
    return updated


def git_changelog_changes(limit: int = 25) -> list[str]:
    """Return recent git commit subjects as changelog bullets."""
    try:
        output = subprocess.check_output(
            ["git", "log", f"--max-count={max(1, limit)}", "--pretty=format:%s"],
            text=True,
        )
    except Exception:
        return []
    return [line.strip() for line in output.splitlines() if line.strip()]
