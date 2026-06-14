# Backup and Restore

HAL production state is split across Postgres and object storage. Treat both as
one recovery unit: Postgres stores canonical metadata, review state, run logs,
tool calls, chunks, claims, and output records; object storage stores exported
artifacts, PDFs, extracted payloads, and generated bundles.

## Recovery Contract

- Back up Postgres with `pg_dump`.
- Back up object storage with S3-compatible sync or MinIO `mc mirror`.
- Pause workers before a consistent backup when possible.
- Restore into staging before trusting a production restore procedure.
- Keep backup encryption, retention, and access policy in the firm's managed
  backup system.

## Local Compose Backup

Create a backup directory:

```bash
mkdir -p backups/postgres backups/object-store
```

Pause queue workers for a clean snapshot:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml stop worker
```

Back up Postgres:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml exec -T postgres \
  pg_dump -U "${POSTGRES_USER:-hal9000}" -d "${POSTGRES_DB:-hal9000}" -Fc \
  > backups/postgres/hal9000.dump
```

Back up MinIO object storage from the host with `mc`:

```bash
mc alias set hal9000-local http://localhost:9002 \
  "${MINIO_ROOT_USER:-hal9000}" \
  "${MINIO_ROOT_PASSWORD:-hal9000-dev-secret}"

mc mirror hal9000-local/"${HAL9000_STORAGE__BUCKET:-hal9000-artifacts}" \
  backups/object-store
```

Restart workers:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml start worker
```

## Local Compose Restore

Stop services that write state:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml stop worker gateway
```

Restore Postgres:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml exec -T postgres \
  pg_restore --clean --if-exists \
  -U "${POSTGRES_USER:-hal9000}" \
  -d "${POSTGRES_DB:-hal9000}" \
  < backups/postgres/hal9000.dump
```

Restore object storage:

```bash
mc mirror --overwrite backups/object-store \
  hal9000-local/"${HAL9000_STORAGE__BUCKET:-hal9000-artifacts}"
```

Run migrations after restore so the restored database reaches the current app
schema:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm migrate
```

Restart services:

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml start gateway worker
```

## Production Backup

Use the managed Postgres provider's scheduled snapshots as the primary backup,
then keep a portable logical dump for migration and audit workflows:

```bash
PG_DUMP_URL="${HAL9000_DATABASE__URL/postgresql+psycopg:/postgresql:}"
pg_dump "$PG_DUMP_URL" -Fc > backups/postgres/hal9000-prod.dump
```

For AWS S3-compatible storage:

```bash
aws s3 sync s3://<bucket>/<prefix> backups/object-store
```

For non-AWS S3-compatible stores, use the provider's supported sync tool or
MinIO Client:

```bash
mc mirror <alias>/<bucket>/<prefix> backups/object-store
```

## Production Restore

Restore into a new database and bucket first, then point a staging HAL profile
at the restored resources:

```bash
PG_RESTORE_URL="${RESTORE_DATABASE_URL/postgresql+psycopg:/postgresql:}"
pg_restore --clean --if-exists -d "$PG_RESTORE_URL" \
  backups/postgres/hal9000-prod.dump

aws s3 sync backups/object-store s3://<restore-bucket>/<prefix>
```

After restore:

1. Run `alembic upgrade head`.
2. Run `hal --profile staging status`.
3. Run `hal --profile staging research observe --json`.
4. Export a known promoted run with `hal research export-run <run-id> --target json`.
5. Only then promote the restored resources for production use.
