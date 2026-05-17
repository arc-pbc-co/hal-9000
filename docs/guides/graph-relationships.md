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

## Project Graphs And Neighborhoods

Render the active project graph as JSON for dashboards or as Mermaid for quick
visual review:

```bash
hal research graph-project firm-research --json
hal research graph-project firm-research --mermaid
```

Inspect the one-hop neighborhood around any database-backed or literal node:

```bash
hal research graph-neighborhood claim <claim-id> --json
hal research graph-neighborhood material "CMSX-4" --depth 2 --mermaid
```

Neighborhoods accept `--direction incoming|outgoing|both`, `--relationship`,
`--project-slug`, `--run-id`, `--status`, and `--limit`.

## Graph-Aware Retrieval

Semantic memory search can optionally boost claim/output results connected in
the graph. Without a focus node, any active edge touching a result can boost it.
With a focus node, only results connected to that entity receive the boost:

```bash
hal research search-memory "creep resistance" \
  --project-slug firm-research \
  --graph-boost \
  --graph-entity-type material \
  --graph-entity-id "CMSX-4" \
  --json
```

The returned JSON includes `base_score`, `graph_boost_score`, and compact
`graph_connections` for boosted results.

## Graph Export

Exports can include graph JSON and Mermaid artifacts alongside output bundles:

```bash
hal research export-project firm-research --target graph --json
hal research export-run <run-id> --target graph --status all --json
```
