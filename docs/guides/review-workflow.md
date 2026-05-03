# Review Workflow

HAL review workflows now have an authorized service API that can support both
CLI usage and a future review UI.

## Permission Model

Review actions require `reviewer` access on the run's project. Access can come
from a direct user grant, a team grant, or the global `admin` role.

Use [Access Control](access-control.md) to create users, teams, memberships, and
project grants before asking reviewers to act on staged outputs.

## Queue

List staged runs a reviewer can review:

```bash
hal research review-queue \
  --reviewer reviewer@example.com \
  --project-slug firm-research
```

For UI and dashboard adapters:

```bash
hal research review-queue \
  --reviewer reviewer@example.com \
  --json
```

## Detail

Reviewer-facing detail is available through the Python service API:

```python
from hal9000.research.review import ResearchReviewService

detail = ResearchReviewService(store).get_review_detail(
    run,
    reviewer_email="reviewer@example.com",
)
```

The detail payload includes run telemetry, output metadata, and output content.
This is the intended source contract for a review UI.

The same payload is available from the CLI for frontend prototyping:

```bash
hal research review-detail <run-id> \
  --reviewer reviewer@example.com \
  --json
```

## Decision

Record a decision from the CLI:

```bash
hal research review-run <run-id> \
  --decision promote \
  --reviewer reviewer@example.com \
  --rationale "Ready for firm sharing."
```

Supported decisions:

- `promote`
- `reject`
- `request-changes`

The service validates reviewer access before recording decisions. Successful
reviews update every staged output on the run and advance the run lifecycle to
`promoted`, `rejected`, or `changes_requested`.

## Comments and Annotations

Reviewers and contributors can annotate staged outputs and extracted claims:

```bash
hal research add-review-comment \
  --target-type output \
  --target-id <output-id> \
  --author reviewer@example.com \
  --annotation-type change_request \
  --body "Add stronger citation coverage."

hal research review-comments \
  --target-type output \
  --target-id <output-id> \
  --viewer reviewer@example.com \
  --json

hal research resolve-review-comment <annotation-id> \
  --resolver reviewer@example.com
```

Comment creation requires `contributor` access on the target's project. Resolving
comments requires `reviewer` access. Open comments are returned by default;
`--include-resolved` includes resolved history for audit and UI views.

## Read Access

Run logs, run summaries, and exports can enforce viewer access when an actor is
provided:

```bash
hal research run-summary <run-id> --as-user reviewer@example.com
hal research run-log <run-id> --as-user reviewer@example.com
hal research export-run <run-id> --as-user reviewer@example.com
```

This keeps local administrative workflows lightweight while giving shared
gateway/API adapters a reusable authorization path.
