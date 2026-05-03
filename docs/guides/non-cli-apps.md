# Non-CLI App Roadmap

HAL's current working surface is CLI plus service APIs. The next collaboration
step is to meet firm users where they already work: Slack for conversational
updates and approvals, and Google Sheets for lightweight tracking, review, and
dashboard workflows.

## Slack App

The recommended channel is `#hal-9000-dev` for development progress, demo notes,
review-ready runs, and implementation decisions. A later production channel can
be split out once the team distinguishes engineering chatter from research
operations.

The Slack app should support:

- Posting run lifecycle updates when runs are queued, staged, promoted, failed,
  cancelled, or ready for review.
- Posting compact run summaries with links to docs, exports, dashboard JSON, and
  review detail.
- Slash commands for common workflows:
  - `/hal queue <project_slug> <objective>`
  - `/hal status <run_id>`
  - `/hal review [project_slug]`
  - `/hal comment <output_id> <comment>`
  - `/hal promote|request-changes|reject <run_id> [rationale]`
- Button actions for promote, reject, request changes, add comment, and resolve
  comment.
- Threaded discussion tied back to run IDs, output IDs, and review annotations.
- Permission checks through `ResearchAuthorizer`, using the same HAL user/team
  model as the CLI and future gateway/API adapters.

The first app contract now exists in `SlackAppService`. Gateway workers can call
it directly, or smoke test command/action payloads from the CLI:

```bash
hal research slack-command \
  --user reviewer@example.com \
  --text "review firm-research" \
  --json

hal research slack-action \
  --payload-json '{"user":{"profile":{"email":"reviewer@example.com"}},"actions":[{"action_id":"hal_promote","value":"{\"run_id\":\"...\"}"}]}' \
  --json
```

Slack request verification should use `verify_slack_signature` at the HTTP edge
before dispatching into `SlackAppService`.

## Google Sheets App

The Google Sheets app should provide a non-CLI project cockpit for reviewers,
operators, and leadership.

Initial sheets:

- Run queue and status tracker.
- Review queue with output count, reviewer, status, and next action.
- Export index for ADAM, Obsidian, Markdown, JSON, and dashboard artifacts.
- Cost/tool-call summary by project, program, and time window.
- Acquisition telemetry for searched, downloaded, processed, skipped, and failed
  papers.

The first native sync job writes direct HAL project views through the Google
Sheets Values API. It supports `runs`, `review_queue`, `outputs`, and `audit`
targets:

```bash
HAL9000_GOOGLE_SHEETS_TOKEN=... \
hal research sync-sheets firm-research \
  --target review_queue \
  --spreadsheet-id <spreadsheet-id> \
  --range-name "Review Queue!A1" \
  --actor reviewer@example.com \
  --reviewer reviewer@example.com
```

Use `--dry-run --json` to verify rows and permissions without writing to Google
Sheets.

## Build Order

1. Add HTTP/gateway adapter endpoints over existing services.
2. Add Slack app notification jobs for run lifecycle and review-ready events. Done for durable delivery workers.
3. Add Slack command/action handlers for status, queue, review detail, comments, and review decisions. Done at service/CLI contract level.
4. Add Google Sheets project sync jobs for runs, review queue, outputs, and audit. Done at service/CLI contract level.
5. Add HTTP/gateway routes for Slack and Sheets webhooks.
6. Add Google Sheets writeback for review comments and decisions.
7. Add audit logging across both app surfaces. Started.
