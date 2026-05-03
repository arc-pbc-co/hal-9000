"""Autoresearch-style research program loading and validation."""

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class ProgramParseError(ValueError):
    """Raised when a research program Markdown file cannot be parsed."""


class ResearchBudget(BaseModel):
    """Operational limits for a bounded autonomous research run."""

    max_runtime_minutes: int = Field(default=60, ge=1)
    max_llm_calls: int = Field(default=50, ge=1)
    max_papers: int = Field(default=25, ge=1)
    max_downloads: int = Field(default=10, ge=0)
    review_required: bool = True


class OutputContract(BaseModel):
    """Expected outputs from a research run."""

    required_outputs: list[str] = Field(default_factory=lambda: ["research_brief"])
    format: str = "markdown"
    citation_policy: str = "Every factual claim must cite source document ids or URLs."
    evidence_required: bool = True

    @field_validator("required_outputs")
    @classmethod
    def required_outputs_must_not_be_empty(cls, value: list[str]) -> list[str]:
        """Require at least one concrete output target."""
        if not value:
            raise ValueError("required_outputs must contain at least one item")
        return value


class ResearchProgramSpec(BaseModel):
    """Machine-readable front matter for a HAL research program."""

    name: str
    objective: str
    version: str = "0.1"
    owner: Optional[str] = None
    domain: str = "materials_science"
    tags: list[str] = Field(default_factory=list)
    scope: dict[str, Any] = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=lambda: ["search", "acquire", "ingest", "rlm"])
    constraints: list[str] = Field(default_factory=list)
    budget: ResearchBudget = Field(default_factory=ResearchBudget)
    output_contract: OutputContract = Field(default_factory=OutputContract)
    promotion_criteria: list[str] = Field(default_factory=list)

    @field_validator("name", "objective")
    @classmethod
    def text_fields_must_not_be_blank(cls, value: str) -> str:
        """Reject empty names and objectives."""
        if not value.strip():
            raise ValueError("field must not be blank")
        return value


class ResearchProgram(BaseModel):
    """A complete Markdown research program with validated front matter."""

    spec: ResearchProgramSpec
    instructions: str
    source_path: Optional[Path] = None

    @property
    def name(self) -> str:
        """Return the program name."""
        return self.spec.name

    @property
    def objective(self) -> str:
        """Return the program objective."""
        return self.spec.objective


def _split_front_matter(markdown: str) -> tuple[str, str]:
    """Split Markdown into YAML front matter and body."""
    normalized = markdown.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise ProgramParseError("Research program must start with YAML front matter delimited by ---")

    closing_index = normalized.find("\n---\n", 4)
    if closing_index == -1:
        raise ProgramParseError("Research program front matter is missing a closing --- delimiter")

    front_matter = normalized[4:closing_index]
    body = normalized[closing_index + len("\n---\n") :]
    return front_matter, body.strip()


def load_program(path: Path | str) -> ResearchProgram:
    """Load and validate a Markdown research program."""
    program_path = Path(path)
    markdown = program_path.read_text()
    front_matter, instructions = _split_front_matter(markdown)

    try:
        raw_spec = yaml.safe_load(front_matter) or {}
    except yaml.YAMLError as exc:
        raise ProgramParseError(f"Invalid YAML front matter: {exc}") from exc

    if not isinstance(raw_spec, dict):
        raise ProgramParseError("Research program front matter must be a YAML mapping")
    if not instructions:
        raise ProgramParseError("Research program must include agent instructions after front matter")

    spec = ResearchProgramSpec.model_validate(raw_spec)
    return ResearchProgram(spec=spec, instructions=instructions, source_path=program_path)


def render_program_template(
    name: str,
    objective: str,
    owner: Optional[str] = None,
    domain: str = "materials_science",
) -> str:
    """Render a starter research program Markdown file."""
    owner_line = f'owner: "{owner}"\n' if owner else "owner: null\n"
    return f"""---
name: "{name}"
objective: "{objective}"
version: "0.1"
{owner_line}domain: "{domain}"
tags:
  - literature-review
scope:
  include:
    - peer-reviewed papers
    - open access preprints
  exclude:
    - uncited claims without primary sources
allowed_tools:
  - search
  - acquire
  - ingest
  - rlm
  - adam_context
constraints:
  - Prefer primary sources over summaries.
  - Preserve source provenance for every extracted claim.
budget:
  max_runtime_minutes: 60
  max_llm_calls: 50
  max_papers: 25
  max_downloads: 10
  review_required: true
output_contract:
  required_outputs:
    - research_brief
    - evidence_table
    - open_questions
  format: markdown
  citation_policy: Every factual claim must cite source document ids or URLs.
  evidence_required: true
promotion_criteria:
  - Brief includes source-backed claims.
  - Evidence table links every recommendation to at least one paper.
  - Open questions are explicitly separated from established findings.
---

# Agent Instructions

You are running a bounded HAL 9000 research program. Work only inside the stated
scope, respect the budget, and write outputs that can be reviewed and promoted
into the shared research store.

## Run Loop

1. Restate the objective and identify the search strategy.
2. Acquire or retrieve candidate papers.
3. Extract claims, methods, materials, and evidence.
4. Produce the required outputs from the output contract.
5. End with reviewer notes, confidence, and unresolved questions.
"""
