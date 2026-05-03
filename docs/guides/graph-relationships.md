# Graph Relationships

HAL stores typed graph relationships between research entities so reviewers,
retrieval, exports, and dashboards can reason over source connections instead
of only searching text.

Supported relationship types:

- `cites`
- `supports`
- `contradicts`
- `uses_method`
- `studies_material`
- `reports_property`

Supported entity types:

- Database entities: `document`, `chunk`, `claim`, `output`, `run`, `project`
- Literal research nodes: `method`, `material`, `property`, `concept`

## Add An Edge

Create a citation from a promoted or staged output to a source document:

```bash
hal research add-graph-edge \
  --source-type output \
  --source-id <output-id> \
  --relationship cites \
  --target-type document \
  --target-id <document-id> \
  --confidence 0.95 \
  --created-by curator@example.com
```

Create a scientific relationship from an extracted claim to a literal material:

```bash
hal research add-graph-edge \
  --source-type claim \
  --source-id <claim-id> \
  --relationship studies_material \
  --target-type material \
  --target-id "CMSX-4"
```

Evidence can be attached as JSON:

```bash
hal research add-graph-edge \
  --source-type claim \
  --source-id <claim-id> \
  --relationship supports \
  --target-type claim \
  --target-id <claim-id> \
  --evidence-json '{"quote":"The rupture life increased at 982 C."}'
```

## Query Edges

List all active edges:

```bash
hal research graph-edges
```

Filter by relationship or entity:

```bash
hal research graph-edges --relationship contradicts
hal research graph-edges --source-type claim --source-id <claim-id> --json
hal research graph-edges --target-type material --target-id "CMSX-4"
```

Edges infer `project_id` and `run_id` from database-backed source or target
entities whenever possible. Literal nodes such as materials, methods, and
properties can still be scoped explicitly with `--project-slug` or `--run-id`.
