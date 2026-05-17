# Non-CLI App Roadmap

HAL's current working surface is CLI plus service APIs. The next collaboration
step is to meet firm users where they already work: Slack for conversational
updates and approvals, and Google Sheets for lightweight tracking, review, and
dashboard workflows.

## HAL Cockpit

The HTTP app gateway now serves a first browser cockpit at `/` and `/ui`. It is
a deliberate frontend graft over HAL's existing runtime instead of a new
application backend:

- Session creation, chat submission, event replay, history, interrupt, compact,
  and tool approval actions use `/api/agent/*`.
- The model picker passes per-session model metadata into
  `AgentGatewaySessionManager`, which resolves the LiteLLM adapter for the
  selected session.
- Review, evidence, and graph panels call `/api/frontend/review`,
  `/api/frontend/evidence`, and `/api/frontend/graph`, reusing HAL's
  authorization, review, evidence, and graph services.

Run it with the app gateway and open `http://127.0.0.1:9101/ui`:

```bash
hal gateway http --host 127.0.0.1 --port 9101
```

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
  - `/hal summary <run_id>`
  - `/hal exports <run_id>`
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

hal research slack-command \
  --user reviewer@example.com \
  --text "summary <run-id>" \
  --json

hal research slack-action \
  --payload-json '{"user":{"profile":{"email":"reviewer@example.com"}},"actions":[{"action_id":"hal_promote","value":"{\"run_id\":\"...\"}"}]}' \
  --json
```

Slack request verification should use `verify_slack_signature` at the HTTP edge
before dispatching into `SlackAppService`.

The first HTTP app gateway exposes these routes:

- `POST /slack/command`
- `POST /slack/action`
- `POST /slack/actions`
- `POST /slack/event`

`/slack/event` handles Slack Events API URL verification and app-mention or
message callbacks. Channel commands such as `<@HAL> summary <run-id>` and
`<@HAL> exports <run-id>` create durable Slack notifications with channel and
thread metadata so `hal research deliver-notifications --channel slack` can post
the response through the configured webhook.

Run it locally with:

```bash
hal gateway http --host 127.0.0.1 --port 9101
```

Real Slack slash-command payloads identify users by `user_id`. For staging,
map Slack user IDs into HAL emails with:

```bash
export HAL9000_SLACK_USER_MAP_JSON='{"U123456":"reviewer@example.com"}'
```

Production should replace this with OIDC-backed token-to-user mapping at the
gateway edge.

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

Sheets writeback is exposed through the HTTP app gateway at
`POST /sheets/writeback` when `app_gateway.sheets_writeback_enabled` is true and
the request includes the configured bearer token. The route applies actions
through HAL's normal authorization model:

- `add_comment`: requires `actor_email`, `target_type`, `target_id`, and `body`.
- `review_run`: requires `actor_email`, `run_id`, and `decision`.
- `queue_run`: requires `actor_email`, `project_slug`, and `objective`.

```json
{
  "action": "review_run",
  "actor_email": "reviewer@example.com",
  "run_id": "<run-id>",
  "decision": "promote",
  "rationale": "Reviewed from the Sheets cockpit."
}
```

## Build Order

1. Add HTTP/gateway adapter endpoints over existing services.
2. Add Slack app notification jobs for run lifecycle and review-ready events. Done for durable delivery workers.
3. Add Slack command/action handlers for status, queue, review detail, comments, summaries, export links, and review decisions. Done at service/CLI contract level.
4. Add Google Sheets project sync jobs for runs, review queue, outputs, and audit. Done at service/CLI contract level.
5. Add HTTP/gateway routes for Slack and Sheets webhooks. Done for Slack commands/actions/events and token-gated Sheets writeback.
6. Add Google Sheets writeback for review comments, decisions, and run queueing. Done at service/gateway contract level.
7. Add audit logging across both app surfaces. Done for Slack command/actions/events, Sheets sync, and Sheets writeback.
