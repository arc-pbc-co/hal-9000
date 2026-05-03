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
  - `/hal queue`
  - `/hal status`
  - `/hal review`
  - `/hal export`
- Button actions for promote, reject, request changes, add comment, and resolve
  comment.
- Threaded discussion tied back to run IDs, output IDs, and review annotations.
- Permission checks through `ResearchAuthorizer`, using the same HAL user/team
  model as the CLI and future gateway/API adapters.

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

The first implementation should sync from HAL's JSON/dashboard exports and
observability summaries. Once stable, it can move to direct API reads and write
actions for comments, review decisions, and run queueing.

## Build Order

1. Add HTTP/gateway adapter endpoints over existing services.
2. Add Slack app notification jobs for run lifecycle and review-ready events.
3. Add Slack command/action handlers for read-only status, queue, and review
   detail.
4. Add Slack write actions for comments and review decisions.
5. Add Google Sheets export sync from dashboard JSON.
6. Add Google Sheets writeback for review comments and decisions.
7. Add audit logging across both app surfaces.
