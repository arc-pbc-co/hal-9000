# HAL 9000 Deployment Manifests

This directory contains the first firmwide deployment shape for HAL 9000.

## Services

- `postgres`: Postgres with pgvector extension image.
- `object-store`: MinIO S3-compatible artifact storage.
- `object-store-init`: creates the artifact bucket.
- `migrate`: runs `alembic upgrade head`.
- `bootstrap`: creates or reuses the baseline firm research project and starter programs.
- `gateway`: runs the HAL WebSocket gateway.
- `worker`: polls queued research runs with `hal research work-queue`.
- `docs`: serves MkDocs for internal engineering review.

## Local Compose

```bash
cp deploy/env.example deploy/.env
docker compose --env-file deploy/.env -f deploy/compose.yaml up --build
```

Useful endpoints:

- Gateway: `ws://localhost:9000`
- Docs: `http://localhost:8000`
- MinIO console: `http://localhost:9001`
- Postgres: `localhost:5432`

## Production Notes

- Replace development secrets in `deploy/.env` with firm-managed secrets.
- Point `HAL9000_DATABASE__URL` at managed Postgres when not using the bundled service.
- Point S3 settings at the firm object store or AWS S3 when not using MinIO.
- Run `migrate` before starting `gateway` and `worker`.
- Run `bootstrap` once per environment; it is idempotent.
