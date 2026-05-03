# Shared Store Services

The shared-store service layer is the first clean API over the firm-wide
research database schema.

Callers should use `ResearchStore` for project, program, run, output, review,
chunk, claim, and evidence writes instead of constructing every relationship
directly with SQLAlchemy models.

## Example

### CLI

```bash
hal research create-project superalloys \
  --name "Superalloys" \
  --owner research@example.com

hal research save-program ./program.md \
  --project-slug superalloys

hal research bootstrap \
  --project-slug firm-research \
  --owner research@example.com

hal research queue-run \
  --program-id <saved-program-id> \
  --initiated-by research@example.com

hal research runs --project-slug superalloys
hal research observe
hal research run-log <run-id>
hal research run-summary <run-id>
hal research review-run <run-id> \
  --decision request-changes \
  --reviewer head-of-engineering@example.com \
  --rationale "Add stronger citation coverage."
hal research export-run <run-id> --target markdown
hal research export-project firm-research --target dashboard --json
hal research log-run-event <run-id> \
  --event-type tool.search \
  --message "Search started."
hal research update-run <run-id> \
  --status running \
  --message "Worker started."

hal research execute-run <run-id> --actor hal-worker
hal research cancel-run <run-id> --actor reviewer@example.com
hal research work-queue --limit 5 --max-attempts 2
```

The first output generator can stage all required outputs declared by a saved
program contract and can generate a run report from the append-only event log.
The bounded worker wraps that generator to execute queued runs through
`running` and `staged`.

### Python

```python
from hal9000.db.models import init_db
from hal9000.db.store import ClaimEvidence, ResearchStore
from hal9000.research import load_program

_, SessionLocal = init_db("sqlite:///./hal9000.db")
session = SessionLocal()
store = ResearchStore(session)

project = store.create_project(
    name="Superalloys",
    slug="superalloys",
    owner="research@example.com",
)

program = load_program("./program.md")
program_record = store.save_program(program, project=project)

run = store.create_run(
    objective=program_record.objective,
    project=project,
    program=program_record,
    budget={"max_papers": 25},
)

output = store.stage_output(
    title="Creep Review Brief",
    output_type="research_brief",
    project=project,
    run=run,
    content="# Brief",
)

store.record_review_decision(
    output,
    decision="promoted",
    reviewer="head-of-engineering@example.com",
)

session.commit()
```

## Current Responsibilities

- Create and fetch research projects by slug.
- Persist validated research programs.
- Create queued research runs with budget and tool policy payloads.
- Append ordered run events and update run status with lifecycle events.
- Record durable worker tool calls for acquisition and RLM LLM-call usage.
- Mirror per-paper acquisition outcomes into ordered run events.
- Summarize run telemetry for reviewers across events, tool calls, acquisition
  outcomes, budgets, warnings, outputs, and reviewer notes.
- Record run-level review decisions across every staged output and advance runs
  to `promoted`, `rejected`, or `changes_requested`.
- Export promoted run and project outputs into ADAM, Obsidian, Markdown, JSON,
  and dashboard object-store artifacts.
- Bootstrap baseline firm research projects and starter programs idempotently.
- Summarize operations health across run status, queue depth, worker outcomes,
  tool-call costs/failures, recent failed runs, and recent run activity.
- Provide CLI commands for creating projects, saving programs, queuing runs,
  bootstrapping starter programs, listing runs, inspecting run logs/summaries,
  reviewing staged runs, appending events, and advancing run state.
- Stage generated research outputs.
- Record review decisions and mirror them onto output status.
- Persist canonical document chunks.
- Persist staged claims with first evidence links.
- Stage required contract outputs and run reports through `ResearchOutputGenerator`.
- Execute queued runs through `BoundedResearchWorker`.
- Execute queued run batches through `hal research work-queue`.
- Record cancellation requests and worker cancellation acknowledgement events.
- Record worker phase retries and timeout events for safer long-running jobs.

## Design Notes

- JSON payloads are serialized into text columns for SQLite compatibility.
- The service intentionally stays small until orchestration requirements are clearer.
- Future migration work should move selected payloads to Postgres JSONB and add indexes.
- `ResearchRunEvent` is append-only by convention; callers should add new events rather than mutating old event rows.
- Current generated outputs are deterministic first-pass renderers. They use
  attached run claims and evidence when available and otherwise produce
  reviewable placeholders that identify missing evidence.
