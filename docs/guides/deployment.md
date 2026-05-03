# Deployment

HAL 9000 now includes a Compose-based firmwide stack for local deployment
rehearsal and engineering review.

## Services

- `postgres`: Postgres using the `pgvector` image.
- `object-store`: MinIO S3-compatible artifact storage.
- `object-store-init`: creates the artifact bucket.
- `migrate`: runs Alembic migrations.
- `bootstrap`: creates the baseline firm project and starter programs.
- `gateway`: runs the WebSocket gateway.
- `app-gateway`: runs HTTP routes for Slack commands/actions and app webhooks.
- `worker`: polls queued research runs with `hal research work-queue`.
- `docs`: serves MkDocs.

## Run Locally

```bash
cp deploy/env.example deploy/.env
docker compose --env-file deploy/.env -f deploy/compose.yaml up --build
```

Useful endpoints:

- Gateway: `ws://localhost:9000`
- App gateway: `http://localhost:9101`
- Docs: `http://localhost:8000`
- MinIO console: `http://localhost:9001`
- Postgres: `localhost:5432`

## Operational Flow

1. `postgres` and `object-store` start first.
2. `object-store-init` creates the configured S3 bucket.
3. `migrate` applies Alembic migrations.
4. `bootstrap` seeds the firm research project and starter programs.
5. `gateway`, `worker`, and `docs` run continuously.

## Production Adaptation

The Compose stack is a deployment template, not the final production boundary.
For production, use firm-managed secrets, managed Postgres, and the firm object
store where available. Keep these deployment contracts:

- `HAL9000_DATABASE__URL` uses `postgresql+psycopg://...`.
- `HAL9000_STORAGE__BACKEND=s3`.
- `HAL9000_STORAGE__BUCKET` points at the artifact bucket.
- Workers run `hal research work-queue` with bounded attempts and timeouts.
- Slack request URLs point to the app gateway and use `HAL9000_SLACK_SIGNING_SECRET`.
- Migrations run before gateway and workers start.

## Backup and Restore

Use [Backup and Restore](backup-restore.md) as the operational runbook for
Postgres dumps, object-store sync, and restore validation. HAL state is only
fully recoverable when the database and object artifacts are backed up together.
