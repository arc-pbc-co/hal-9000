# Configuration

HAL 9000 supports three configuration inputs:

1. Built-in defaults (from `src/hal9000/config.py`)
2. Named environment profiles (`local`, `staging`, `production`)
3. Optional YAML file via `--config`
4. Environment variables / `.env`

## Quick Pattern

```bash
cp .env.example .env
hal --profile local status
hal --profile staging status
```

## Required Setting

Set one API key variable:

```dotenv
ANTHROPIC_API_KEY=your-key-here
# or
HAL9000_ANTHROPIC_API_KEY=your-key-here
```

## Environment Variable Convention

- Prefix: `HAL9000_`
- Nested fields: double underscore `__`

Examples:

```dotenv
HAL9000_ENVIRONMENT=local
HAL9000_DATABASE__URL=sqlite:///./hal9000.db
HAL9000_OBSIDIAN__VAULT_PATH=~/ObsidianVault/HAL9000Research
HAL9000_ACQUISITION__DOWNLOAD_DIR=~/Documents/Research/Acquired
HAL9000_GATEWAY__PORT=9000
HAL9000_PROCESSING__CHUNK_SIZE=50000
```

## Environment Profiles

Checked-in profile templates live in `config/`:

- `config/local.yaml`: SQLite, local filesystem object storage, fake deterministic embeddings.
- `config/staging.yaml`: Postgres URL shape, S3-compatible artifact storage, pgvector settings.
- `config/production.yaml`: production deployment template for managed Postgres, S3-compatible storage, and pgvector.

Use a profile directly:

```bash
hal --profile local status
hal --profile staging status
hal --profile production status
```

Or select it from the environment:

```dotenv
HAL9000_ENVIRONMENT=production
HAL9000_DATABASE__URL=postgresql+psycopg://user:password@host:5432/hal9000
HAL9000_STORAGE__BACKEND=s3
HAL9000_STORAGE__BUCKET=firm-hal-artifacts
HAL9000_STORAGE__PREFIX=production/
HAL9000_STORAGE__REGION=us-east-1
```

`hal status` reports profile readiness issues for staging/production when a
profile is still using local-only database, storage, or vector settings.

## YAML Config File

Default template: `config/default.yaml`

Use a custom file:

```bash
hal --profile production --config /path/to/config.yaml status
```

Minimal YAML:

```yaml
hal9000:
  sources:
    local_paths:
      - ~/Documents/Research
  database:
    url: sqlite:///./hal9000.db
  obsidian:
    vault_path: ~/ObsidianVault/HAL9000Research
```

## Common Sections

### `sources`

- `local_paths`: directories scanned by `hal scan` and `hal batch`
- `watch_mode`: continuous monitoring (future/optional workflows)

### `processing`

- `chunk_size`: text chunk size for RLM processing
- `max_concurrent_calls`: max concurrent LLM calls
- `cache_enabled`, `cache_path`: processing cache controls

### `acquisition`

- `download_dir`: target folder for downloaded papers
- `default_sources`: default providers (`semantic_scholar`, `arxiv`)
- `max_concurrent_downloads`, `rate_limit_seconds`
- `semantic_scholar_api_key`
- `unpaywall_email`
- `relevance_threshold`

### `obsidian`

- `vault_path`
- `templates_path`
- `create_canvas`
- `auto_link`

### `adam`

- `enabled`
- `output_path`
- `default_domain`

### `gateway`

- `host`
- `port`
- `max_connections`
- `session_timeout_minutes`

### `database`

- `url`: SQLAlchemy URL
- SQLite paths support `~` and relative paths
- staging/production should use `postgresql+psycopg://...`

Examples:

```yaml
database:
  url: sqlite:///~/hal9000/hal9000.db
```

```yaml
database:
  url: postgresql+psycopg://user:password@localhost/hal9000
```

### `storage`

- `backend`: `local` or `s3`
- `root_path`: local filesystem object-store root
- `bucket`, `prefix`, `region`, `endpoint_url`: S3-compatible object storage

### `vector`

- `backend`: `pgvector`
- `embedding_provider`: currently `fake` for deterministic local/test embeddings
- `embedding_dimension`: deployment contract for stored vectors
- `retrieval_limit`: default semantic retrieval result count

## CLI Options That Affect Runtime

- `hal --profile <local|staging|production> ...` loads a checked-in profile.
- `hal --config <file> ...` loads a specific YAML config on top of the selected profile.
- `hal acquire --sources semantic_scholar,arxiv` restricts providers.
- `hal acquire --output-dir <path>` overrides acquisition download directory for that run.

## Validate Current Configuration

```bash
hal status
```

Use verbose mode for troubleshooting:

```bash
hal -v status
```
