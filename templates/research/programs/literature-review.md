---
name: "Source-Backed Literature Review"
objective: "Produce a concise research brief with source-backed findings, evidence table, and open questions for a focused technical topic."
version: "0.1"
owner: null
domain: "materials_science"
tags:
  - literature-review
  - evidence-synthesis
scope:
  include:
    - peer-reviewed papers
    - open access preprints
    - source metadata from Semantic Scholar, arXiv, and Unpaywall
  exclude:
    - unsupported claims
    - non-technical commentary
allowed_tools:
  - search
  - acquire
  - ingest
  - rlm
  - shared_store
constraints:
  - Prefer primary sources over reviews when extracting claims.
  - Separate established findings from hypotheses and open questions.
  - Preserve provenance for every claim and evidence row.
budget:
  max_runtime_minutes: 90
  max_llm_calls: 80
  max_papers: 40
  max_downloads: 15
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
  - Brief includes only source-backed claims.
  - Evidence table includes source, locator, confidence, and claim type.
  - Open questions are explicitly labeled as unresolved.
---

# Agent Instructions

Run a bounded literature review for the requested topic.

## Run Loop

1. Restate the topic and define search terms.
2. Search and acquire candidate papers within budget.
3. Extract metadata, chunks, claims, and evidence links.
4. Rank findings by source quality and relevance.
5. Stage a research brief, evidence table, and open questions.
6. End with reviewer notes and confidence.

