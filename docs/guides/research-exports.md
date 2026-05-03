# Research Exports

HAL exports promoted research outputs from the canonical shared store into
firm-wide formats that downstream teams can consume without reading database
tables directly.

## Targets

| Target | Use |
|--------|-----|
| `adam` | ADAM-ready context JSON bundles built from `adam_context` outputs. |
| `obsidian` | Vault-ready Markdown notes plus an index note. |
| `markdown` | One readable Markdown bundle for review, sharing, and archiving. |
| `json` | Full canonical output payloads for downstream tools. |
| `dashboard` | Compact rows and summaries for dashboards and status surfaces. |

Exports are written through the configured object store. Local development uses
`hal-local://...` URIs; production S3-compatible storage uses `s3://...` URIs.

## Export a Run

```bash
hal research export-run <run-id>
```

By default, HAL exports promoted outputs to every target. To export only one
target:

```bash
hal research export-run <run-id> --target markdown
hal research export-run <run-id> --target json --json
```

To export staged outputs before promotion:

```bash
hal research export-run <run-id> --status staged
```

To include every output status:

```bash
hal research export-run <run-id> --status all
```

## Export a Project

```bash
hal research export-project firm-research --target dashboard --json
hal research export-project firm-research --target obsidian --status promoted
```

Project exports collect outputs attached to the project across runs. Use project
exports for firm dashboards, knowledge base refreshes, and periodic vault
publishing.

## Artifact Layout

Artifacts are stored under the configured prefix, which defaults to `exports`:

```text
exports/
  runs/<run-id>/<timestamp>/<target>/manifest.json
  projects/<project-slug>/<timestamp>/<target>/manifest.json
```

Each target writes a manifest plus target-specific artifacts:

- Markdown: `bundle.md`
- JSON: `outputs.json`
- Dashboard: `dashboard.json`
- ADAM: `adam-contexts.json`
- Obsidian: `index.md` and one note per output

## ADAM Validation

ADAM exports validate each `adam_context` output before writing the bundle. The
first schema pass requires:

- `output_type`
- `context_id`
- `name`
- `description`
- `literature_summary`
- `metadata`

Malformed ADAM contexts fail fast so a reviewer can request changes before the
context is handed to downstream ADAM workflows.
