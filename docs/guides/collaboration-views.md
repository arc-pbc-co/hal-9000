# Collaboration Views

HAL now has first-class collaboration records for shared project workflows:
collections, saved searches, shared views, notifications, and audit events.
These records are the backend contract for browser review UI, Slack, Sheets, and
future dashboard surfaces.

## Collections

Create a project collection:

```bash
hal research create-collection firm-research \
  --name "Head of Engineering Demo" \
  --owner owner@example.com
```

Add outputs, claims, runs, documents, or graph/literal targets:

```bash
hal research add-collection-item firm-research head-of-engineering-demo \
  --target-type output \
  --target-id <output-id> \
  --added-by owner@example.com \
  --note "Use in demo."
```

List collections:

```bash
hal research collections firm-research --json
```

## Saved Searches

Save reusable searches for non-CLI users and dashboards:

```bash
hal research save-search firm-research \
  --name "Creep Claims" \
  --query "single crystal creep resistance" \
  --target memory \
  --filters-json '{"target":["claims","outputs"]}'
```

List saved searches:

```bash
hal research saved-searches firm-research
```

## Shared Views

Create saved dashboard/review/audit views:

```bash
hal research create-shared-view firm-research \
  --name "Review Queue" \
  --view-type review_queue \
  --config-json '{"sections":["queue","failures","recent_outputs"]}'
```

List views:

```bash
hal research shared-views firm-research --json
```

## Notifications

Queue review-ready notifications for app adapters:

```bash
hal research notify-review-ready <run-id> \
  --recipient reviewer@example.com \
  --channel slack
```

List notifications:

```bash
hal research notifications --recipient reviewer@example.com --json
```

Deliver pending notifications:

```bash
hal research deliver-notifications --channel slack --limit 20
hal research deliver-notifications --channel sheets --dry-run --json
```

Delivery workers consume durable notification records and append delivery attempt
metadata to each record. In-app notifications mark sent without an external
provider. Slack uses `HAL9000_SLACK_WEBHOOK_URL`, email uses `HAL9000_SMTP_*`,
and Sheets uses `HAL9000_SHEETS_CSV_PATH` as a Google Sheets-compatible sync
bridge until the full app connector is wired in.

## Audit Events

Audit events are written for collaboration mutations and review decisions. Query
them by project, run, action, or target type:

```bash
hal research audit-events --project-slug firm-research
hal research audit-events --run-id <run-id> --json
hal research audit-events --action run.promoted
```

Audit events are designed for compliance-friendly review trails and lightweight
operator dashboards. The browser review UI exposes the same authorized audit
dashboard under `hal research review-ui`, including action/target filters and
summary counts.
