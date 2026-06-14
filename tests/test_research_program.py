"""Tests for research program validation."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from hal9000.research import ProgramParseError, load_program, render_program_template


def test_rendered_program_loads(tmp_path):
    """A generated starter program should validate."""
    path = tmp_path / "program.md"
    path.write_text(
        render_program_template(
            name="Nickel Superalloy Review",
            objective="Identify evidence gaps in creep-resistant nickel superalloys.",
            owner="research@example.com",
        )
    )

    program = load_program(path)

    assert program.name == "Nickel Superalloy Review"
    assert program.spec.owner == "research@example.com"
    assert program.spec.budget.max_papers == 25
    assert "research_brief" in program.spec.output_contract.required_outputs
    assert "Run Loop" in program.instructions


def test_program_requires_front_matter(tmp_path):
    """Programs must include YAML front matter for machine validation."""
    path = tmp_path / "program.md"
    path.write_text("# Missing front matter")

    with pytest.raises(ProgramParseError):
        load_program(path)


def test_program_rejects_empty_required_outputs(tmp_path):
    """Output contracts must name at least one artifact."""
    path = tmp_path / "program.md"
    path.write_text(
        """---
name: "Bad Program"
objective: "Test validation"
output_contract:
  required_outputs: []
---

# Instructions

Do the work.
"""
    )

    with pytest.raises(ValidationError):
        load_program(path)


def test_checked_in_research_program_templates_are_valid():
    """All checked-in research program templates should validate."""
    repo_root = Path(__file__).resolve().parents[1]
    templates = sorted((repo_root / "templates" / "research").rglob("*.md"))

    assert templates
    for template in templates:
        program = load_program(template)
        assert program.name
        assert program.objective
