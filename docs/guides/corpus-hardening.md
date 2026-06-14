# Corpus Hardening

HAL now has a first corpus curation layer for shared research memory. It adds
stable source identity, document version fields, refresh policy metadata,
normalized citations, source quality scoring, and persisted duplicate reports.

## Harden Existing Documents

Run corpus hardening against the configured database:

```bash
hal research harden-corpus
```

For scheduled source refresh planning, attach an interval policy:

```bash
hal research harden-corpus \
  --refresh-policy interval \
  --refresh-interval-days 30
```

The command updates each document with:

- `source_identifier`
- `source_version`
- `version_group_key`
- `is_current_version`
- `refresh_policy`
- `last_refreshed_at`
- `next_refresh_at`
- `normalized_doi`
- `citation_key`
- `normalized_citation`
- `source_quality_score`
- `source_quality_label`
- `source_quality_json`

Use JSON output for dashboards or Sheets sync:

```bash
hal research harden-corpus --json
```

## Dedupe Reports

Create a persisted duplicate-source report:

```bash
hal research dedupe-report --created-by curator@example.com
```

The report groups likely duplicate documents by DOI and normalized title/year
fingerprints. File-hash grouping is supported too, though the current document
table already enforces unique SHA-256 hashes.

For app surfaces:

```bash
hal research dedupe-report --json
```

## Versioning Model

Documents use `version_group_key` to represent the same logical source across
refreshes. A newer document version can set `supersedes_document_id` and mark the
older document `is_current_version = false`.

Changing source identity rules should be treated as a migration-level decision:
downstream citations, dedupe reports, retrieval, and output provenance all depend
on these fields staying stable.
