# Production Hardening

This guide tracks the first production-readiness controls around HAL's shared
research OS and the ml-intern-style agent runtime graft.

## App Gateway Deployment

The HTTP app gateway exposes:

- `GET /` and `GET /ui`: browser HAL cockpit for agent sessions, approvals,
  and research panels.
- `GET /health`: liveness probe.
- `GET /ready`: readiness probe for database connectivity and enabled
  integration secrets.
- `POST /slack/command`: Slack slash-command ingress.
- `POST /slack/action` and `POST /slack/actions`: Slack interactive action
  ingress.
- `POST /slack/event`: Slack Events API URL verification and channel callback
  ingress.
- `POST /sheets/writeback`: Google Sheets writeback ingress, disabled by
  default.

Use `/health` for container liveness and `/ready` for deployment readiness.
When Slack signing is required, set:

```bash
HAL9000_APP_GATEWAY__SLACK_REQUIRED=true
HAL9000_APP_GATEWAY__SLACK_SIGNING_SECRET=<managed-secret>
```

`HAL9000_SLACK_SIGNING_SECRET` remains supported for existing deployments.

Sheets writeback is deliberately opt-in:

```bash
HAL9000_APP_GATEWAY__SHEETS_WRITEBACK_ENABLED=true
HAL9000_APP_GATEWAY__SHEETS_WRITEBACK_TOKEN=<managed-bearer-token>
```

Requests must send `Authorization: Bearer <token>` or
`X-HAL-Sheets-Token: <token>`. Accepted payloads are not echoed back; the
gateway applies `add_comment`, `review_run`, and `queue_run` through HAL's
authorized services and returns the resulting action ids.

## Secrets Management

Store production secrets in the platform secret manager, not in checked-in
config files or Compose env files. The deployment template keeps placeholder
values only. Secret-bearing payload keys such as `token`, `secret`,
`password`, `api_key`, `authorization`, `cookie`, and `signature` are redacted
by shared security helpers before app-facing echoes.

HAL provider adapters resolve credentials through the shared secret-manager
contract. The current backend supports environment-backed secrets plus injected
managers for tests and future cloud secret stores. Supported provider aliases
include:

| Provider | Secret names |
| --- | --- |
| Anthropic | `HAL9000_ANTHROPIC_API_KEY`, `ANTHROPIC_API_KEY` |
| OpenAI | `HAL9000_OPENAI_API_KEY`, `OPENAI_API_KEY` |
| Hugging Face | `INFERENCE_TOKEN`, `HF_TOKEN`, `HUGGING_FACE_HUB_TOKEN` |
| GitHub | `GITHUB_TOKEN` |
| Semantic Scholar | `HAL9000_ACQUISITION__SEMANTIC_SCHOLAR_API_KEY`, `SEMANTIC_SCHOLAR_API_KEY` |
| Slack | `HAL9000_SLACK_SIGNING_SECRET` |
| Google Sheets | `HAL9000_GOOGLE_SHEETS_TOKEN` |

Provider code should ask the secret manager for aliases instead of reading
environment variables directly. Diagnostics may report the secret source and
name, but never the value.

## Retention Policy

Retention is dry-run-first and disabled by default:

```bash
hal --profile production research retention-plan
hal --profile production research retention-apply --confirm
```

The apply command deletes expired rows only when
`HAL9000_RETENTION__ENABLED=true` and `--confirm` is present. Current governed
records and artifacts are:

| Rule | Default |
| --- | ---: |
| Run ledger events | 365 days |
| Tool-call accounting | 365 days |
| Notifications | 180 days |
| Audit events | 730 days |
| Persisted gateway sessions | 30 days |
| PDF/source object artifacts | 2555 days |
| Generated output artifacts | 1095 days |

Tune with `HAL9000_RETENTION__RUN_EVENT_DAYS`,
`HAL9000_RETENTION__TOOL_CALL_DAYS`,
`HAL9000_RETENTION__NOTIFICATION_DAYS`,
`HAL9000_RETENTION__AUDIT_EVENT_DAYS`, and
`HAL9000_RETENTION__GATEWAY_SESSION_DAYS`. Tune object artifact windows with
`HAL9000_RETENTION__PDF_ARTIFACT_DAYS` and
`HAL9000_RETENTION__OUTPUT_ARTIFACT_DAYS`.

Artifact retention is conservative: it deletes only URIs that map back to the
configured HAL object store, leaves database records in place, and reports
legal-hold skips. Mark document or output metadata with `legal_hold: true`,
`retention_hold: true`, `copyright_hold: true`, `retention_policy:
legal_hold`, or a future `legal_hold_until` value to preserve the referenced
object.

## Compliance Notes

- Keep audit events longer than transient notifications.
- Run `retention-plan --json` before any confirmed apply in production.
- Run `compliance-check --json` before sharing PDF-derived generated summaries
  with a broader audience.
- Preserve Postgres and object-store backups before shortening retention
  windows.
- Treat Slack user maps and Sheets writeback tokens as secrets.
- Require OIDC issuer and audience before enabling shared production auth.

`hal research compliance-check` reports restricted/copyrighted PDF sources,
missing PDF rights metadata, generated summaries derived from restricted
sources, and generated summaries missing citation/source provenance. Mark
records as reviewed with metadata such as `compliance_reviewed: true`,
`allowed_use: true`, `open_access: true`, or explicit open-license metadata.

## CI And Release

CI runs lint, the full test suite, release-critical type checks, docs build,
and an Alembic migration smoke test. The release workflow runs the same quality
gate on `v*.*.*` tags and manual dispatch, verifies changelog generation, then
builds package artifacts into `dist/`.

Recommended release flow:

```bash
python -m ruff check src/hal9000 tests
python -m pytest -q
python -m mypy src/hal9000/release.py src/hal9000/security.py src/hal9000/research/compliance.py src/hal9000/research/queue.py src/hal9000/research/retention.py
python -m mkdocs build --strict
hal release changelog --version 0.1.0 --change "Release 0.1.0"
hal --profile staging release validate-staging --json
git tag -a v0.1.0 -m "Release v0.1.0"
git push origin v0.1.0
```

The packaged worker service is the production process-manager target:

```bash
hal --profile production research worker-service \
  --limit 5 \
  --poll-seconds 30 \
  --max-attempts 2 \
  --phase-timeout-seconds 900
```
