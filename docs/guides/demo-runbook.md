# Full-Team Demo Runbook

This runbook gives the HAL demo a repeatable path from seeded research memory to
review, Slack interaction, Sheets rows, and auditability.

## Seed Demo Data

Create a project, demo users, a staged run, source-backed claims, outputs,
comments, notifications, saved views, graph relationships, and audit events:

```bash
hal research demo-seed \
  --project-slug hal-demo \
  --owner bwisk@arc-pbc.com \
  --reviewer reviewer@example.com \
  --contributor researcher@example.com
```

Use `--json` when feeding scripts or copying IDs into a demo sheet.

## Demo Flow

1. Show shared memory:

```bash
hal research search-memory \
  "single crystal superalloy creep" \
  --project-slug hal-demo \
  --target chunks \
  --target claims \
  --target outputs \
  --json
```

2. Start the browser review UI:

```bash
hal research review-ui --host 127.0.0.1 --port 9100
```

Open `http://127.0.0.1:9100/`, enter the reviewer email, set project slug to
`hal-demo`, and load the review queue. Walk through output detail, comments,
review actions, and audit filters.

3. Exercise Slack command handling from CLI:

```bash
hal research slack-command \
  --user reviewer@example.com \
  --text "review hal-demo" \
  --json
```

For HTTP app gateway testing:

```bash
hal gateway http --host 127.0.0.1 --port 9101
```

Then point Slack slash commands at `POST /slack/command` and interactive actions
at `POST /slack/action`. Point Slack Events API callbacks at
`POST /slack/event` for channel mentions such as `<@HAL> summary <run-id>` and
`<@HAL> exports <run-id>`. Production requests should set
`HAL9000_SLACK_SIGNING_SECRET` so the gateway verifies Slack signatures.
For staging click-throughs, set `HAL9000_SLACK_USER_MAP_JSON` to map Slack
`user_id` values to HAL reviewer emails.

4. Create or open a demo Google Sheet with tabs named:

- `Runs`
- `Review Queue`
- `Outputs`
- `Audit`

Set `HAL9000_GOOGLE_SHEETS_TOKEN` and sync the project cockpit rows:

```bash
hal research sync-sheets hal-demo \
  --target runs \
  --spreadsheet-id <spreadsheet-id> \
  --range-name "Runs!A1" \
  --actor reviewer@example.com

hal research sync-sheets hal-demo \
  --target review_queue \
  --spreadsheet-id <spreadsheet-id> \
  --range-name "Review Queue!A1" \
  --actor reviewer@example.com \
  --reviewer reviewer@example.com

hal research sync-sheets hal-demo \
  --target outputs \
  --spreadsheet-id <spreadsheet-id> \
  --range-name "Outputs!A1" \
  --actor reviewer@example.com

hal research sync-sheets hal-demo \
  --target audit \
  --spreadsheet-id <spreadsheet-id> \
  --range-name "Audit!A1" \
  --actor reviewer@example.com
```

Use `--dry-run --json` first when no Google token is available.

## Verification

Before the demo, run:

```bash
python3 -m pytest -q
python3 -m mkdocs build --strict
python3 -m alembic upgrade head
```

For a clean migration smoke test, use a temporary SQLite database:

```bash
HAL9000_DATABASE__URL=sqlite:////tmp/hal9000-demo-migration.db \
  python3 -m alembic upgrade head
```

## Storyline

The clean demo narrative is:

1. HAL has shared memory, not one-off chat state.
2. A run turns memory into reviewable, source-backed outputs.
3. Reviewers can act in the browser or Slack.
4. Non-CLI users can track work in Sheets.
5. Every action leaves an audit trail.
