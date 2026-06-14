# HAL-9000 Demo Instructions

This runbook lets any ARC teammate run the HAL-9000 demo locally. Use the seeded
path for customer or partner meetings; use the live research path only after
rehearsal.

## What The Demo Proves

- HAL has shared research memory: documents, chunks, claims, outputs, graph
  edges, and review decisions.
- HAL has a governed agent runtime: sessions, model selection, approvals,
  compaction, replay, and history.
- HAL produces reviewable outputs: evidence-backed briefs, ADAM context, graph
  views, exports, and audit trails.

## 1. Prepare The Workspace

Run from the HAL repo root:

```bash
cd /path/to/hal-9000

python3 -m pip install -e '.[agent]'

export HAL9000_DEMO_ROOT="${PWD}/.hal9000_demo"
mkdir -p "$HAL9000_DEMO_ROOT"

export HAL9000_DATABASE__URL="sqlite:///${HAL9000_DEMO_ROOT}/hal-demo.db"
export HAL9000_STORAGE__ROOT_PATH="${HAL9000_DEMO_ROOT}/objects"
export HAL9000_ACQUISITION__UNPAYWALL_EMAIL="demo@arc-pbc.com"

python3 -m alembic upgrade head
```

## 2. Seed The Reliable Demo

```bash
python3 -m hal9000.cli research demo-seed \
  --project-slug hal-demo \
  --project-name "HAL-9000 Demo" \
  --owner demo@arc-pbc.com \
  --reviewer demo@arc-pbc.com \
  --contributor demo@arc-pbc.com
```

## 3. Start The Surfaces

Terminal A:

```bash
lsof -nP -iTCP:9101 -sTCP:LISTEN

python3 -m hal9000.cli gateway http --host 127.0.0.1 --port 9101
```

If `lsof` already shows a Python/HAL process on `9101`, the cockpit is already
running; open `http://127.0.0.1:9101/ui` and continue. To restart cleanly, stop
that process with `kill <PID>`, or use `--port 9104` and open
`http://127.0.0.1:9104/ui`.

Terminal B:

```bash
lsof -nP -iTCP:9102 -sTCP:LISTEN

python3 -m http.server 9102 --bind 127.0.0.1 --directory "$PWD"
```

If `lsof` already shows a Python process on `9102`, the deck server is already
running; open the deck URL below and continue. To restart cleanly, stop that
process with `kill <PID>`, or use port `9105` and open the deck URL with `9105`
instead of `9102`.

Open:

- `http://127.0.0.1:9102/artifacts/presentations/hal-9000-general-demo.html`
- `http://127.0.0.1:9101/ui`

## 4. Presenter Flow

1. Open the deck and frame HAL as ARC's source-backed research operating system.
2. Open the cockpit. Set `User email` to `demo@arc-pbc.com` and `Project slug`
   to `hal-demo`.
3. Click `Create Session` and show the chat/event feed plus model picker.
4. Open `Review`, click `Load Review`, select a run, and show staged outputs.
5. Open `Evidence` with the selected run id and show claims/chunks/outputs.
6. Open `Graph` and show the relationship view.

## 5. Review A Completed Run

Use this checklist after any live agent run. It is written for a nontechnical
demo operator.

### Green Run: Good To Present

- The final answer says HAL produced or staged outputs.
- The `Review` tab shows staged outputs such as a research brief, evidence
  table, open questions, or ADAM context.
- The `Evidence` tab shows nonzero chunks and claims for the selected run.
- The answer cites evidence IDs, claim IDs, documents, or output IDs.
- The `Graph` tab shows relationships connected to the project or run.

### Yellow Run: Explain As Partial

- HAL imported paper metadata but says it does not have full-text chunks.
- Search results look broad or off-topic.
- HAL asks to retry acquisition, process PDFs, or narrow the topic.
- The final answer is clearly labeled as orientation rather than source-backed
  findings.

### Red Run: Do Not Present As Research Output

- A tool reports an error such as `asyncio.run() cannot be called from a running
  event loop`.
- The `Evidence` tab shows zero chunks for the selected run.
- The `Review` tab has no staged outputs for that run.
- HAL refuses to write a polished report because it cannot trace claims to
  evidence.

If a run is yellow or red, tell the audience: "HAL is doing the right thing by
not fabricating a sourced report. We will use the seeded run to show the full
review workflow, then rerun live acquisition after rehearsal."

### Fast Review Path In The Cockpit

1. Click `Review`, then `Load Review`.
2. Select the newest staged run.
3. Read the research brief first.
4. Open the evidence table and check that each claim has a citation or evidence
   marker.
5. Click `Evidence`, paste the run id, and confirm chunks and claims are present.
6. Click `Graph`, load the project/run graph, and confirm the outputs connect
   back to documents or claims.
7. Only export or share the run after the review status is staged, promoted, or
   explicitly approved by the presenter.

## 6. Optional Custom Topic

Use this only when live acquisition and network conditions are safe:

```bash
python3 -m hal9000.cli research init-program \
  research/programs/custom-demo-topic.md \
  --name "Custom HAL Demo Research Program" \
  --objective "Research a focused technical topic selected for this audience, preserving source-backed claims, evidence tables, open questions, and ADAM-ready context." \
  --owner demo@arc-pbc.com \
  --domain materials_science

python3 -m hal9000.cli research save-program \
  research/programs/custom-demo-topic.md \
  --project-slug hal-demo

python3 -m hal9000.cli research queue-run \
  --project-slug hal-demo \
  --program-id <PROGRAM_ID> \
  --initiated-by demo@arc-pbc.com

python3 -m hal9000.cli research execute-run <RUN_ID> \
  --actor demo-worker \
  --live-acquisition \
  --max-attempts 2 \
  --phase-timeout-seconds 300
```

## Proof Commands

```bash
python3 -m hal9000.cli research review-queue \
  --reviewer demo@arc-pbc.com \
  --project-slug hal-demo

python3 -m hal9000.cli research search-memory \
  "source-backed evidence and open questions" \
  --project-slug hal-demo \
  --target claims \
  --target outputs \
  --graph-boost \
  --json

python3 -m hal9000.cli research graph-project hal-demo --mermaid

python3 -m hal9000.cli research export-run <RUN_ID> \
  --target adam \
  --target markdown \
  --target json \
  --status all \
  --as-user demo@arc-pbc.com \
  --json
```

## Troubleshooting

- Old styling: hard refresh the browser tab.
- Port already in use: the gateway or deck server is already running, or another
  process owns the port. Run `lsof -nP -iTCP:9101 -sTCP:LISTEN` for the cockpit
  and `lsof -nP -iTCP:9102 -sTCP:LISTEN` for the deck. Open the existing URL,
  stop it with `kill <PID>`, or use `9104` for the cockpit and `9105` for the
  deck.
- `LiteLLM is required`: run `python3 -m pip install -e '.[agent]'`, then restart
  the HAL app gateway.
- Empty review queue: re-run `demo-seed` with `hal-demo`.
- Live acquisition fails: continue with seeded data.
- Full reset: stop servers and remove `.hal9000_demo`.
