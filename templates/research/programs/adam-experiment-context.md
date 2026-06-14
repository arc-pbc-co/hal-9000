---
name: "ADAM Experiment Context Builder"
objective: "Convert source-backed literature findings into an ADAM-ready context with hypotheses, candidate experiments, variables, and evidence links."
version: "0.1"
owner: null
domain: "materials_science"
tags:
  - adam-context
  - experimental-design
  - hypothesis-generation
scope:
  include:
    - processed HAL documents
    - staged and promoted evidence-backed claims
    - materials, methods, performance metrics, and experimental conditions
  exclude:
    - recommendations without evidence links
    - experiments outside the requested domain
allowed_tools:
  - rlm
  - shared_store
  - adam_context
constraints:
  - Every proposed experiment must cite supporting evidence or identify itself as exploratory.
  - Distinguish literature-backed variables from inferred variables.
  - Prefer actionable experiment designs over broad research directions.
budget:
  max_runtime_minutes: 60
  max_llm_calls: 40
  max_papers: 25
  max_downloads: 0
  review_required: true
output_contract:
  required_outputs:
    - adam_context
    - hypothesis_cards
    - experiment_suggestions
  format: json
  citation_policy: Each hypothesis and experiment suggestion must link to source claim or document ids.
  evidence_required: true
promotion_criteria:
  - ADAM context validates against the expected JSON shape.
  - Hypothesis cards include rationale, variables, expected outcomes, and evidence links.
  - Exploratory recommendations are clearly labeled.
---

# Agent Instructions

Build an ADAM-ready experimental context from source-backed HAL research data.

## Run Loop

1. Identify the topic focus and relevant processed documents or claims.
2. Group evidence by material, method, property, and performance metric.
3. Generate hypotheses only where the evidence trail is explicit.
4. Draft candidate experiments with variables and expected outcomes.
5. Stage the ADAM context and hypothesis cards for review.
6. End with validation notes and unresolved assumptions.

