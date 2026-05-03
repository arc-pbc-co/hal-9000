# Research Programs

Research programs are HAL's first implementation of the autoresearch-style
operating model.

A program is a Markdown file with YAML front matter:

```markdown
---
name: "Nickel Superalloy Review"
objective: "Identify evidence gaps in creep-resistant nickel superalloys."
version: "0.1"
owner: "research@example.com"
domain: "materials_science"
allowed_tools:
  - search
  - acquire
  - ingest
  - rlm
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
---

# Agent Instructions

Run the literature review...
```

## CLI

Create a starter program:

```bash
hal research init-program ./program.md \
  --name "Nickel Superalloy Review" \
  --objective "Identify evidence gaps in creep-resistant nickel superalloys."
```

Validate a program:

```bash
hal research validate-program ./program.md
```

Persist a valid program in the shared store:

```bash
hal research create-project superalloys --name "Superalloys"
hal research save-program ./program.md --project-slug superalloys
```

Queue a run from a saved program:

```bash
hal research queue-run --program-id <saved-program-id>
```

## Dogfood Programs

The repo includes two starter programs for early HAL dogfooding:

- `templates/research/programs/literature-review.md`
- `templates/research/programs/adam-experiment-context.md`

Both are validated by the test suite.

They are also dogfooded through the shared store in tests: each program is saved
to a shared project, queued as a run, advanced to `running`, staged with required
outputs, and given a run report.

The bounded worker can now execute a saved run:

```bash
hal research execute-run <run-id> --actor hal-worker
```

## Required Fields

- `name`: Human-readable program name.
- `objective`: The outcome the run is optimizing for.
- Markdown instructions after the front matter.

## Important Optional Fields

- `scope`: Inclusion and exclusion rules.
- `allowed_tools`: Tool names the orchestrator may use.
- `constraints`: Standing rules for the agent.
- `budget`: Runtime, model-call, paper, and download limits.
- `output_contract`: Required outputs and citation policy.
- `promotion_criteria`: Conditions for moving staged outputs into shared knowledge.

## Why This Matters

The program file lets engineering review autonomous behavior before it runs.
It also gives future workers and orchestrators a stable machine-readable contract.
