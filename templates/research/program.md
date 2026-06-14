---
name: "Example HAL Research Program"
objective: "Summarize the state of evidence for a focused research question."
version: "0.1"
owner: null
domain: "materials_science"
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
