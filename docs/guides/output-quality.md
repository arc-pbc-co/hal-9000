# Output Quality

HAL outputs are now versioned review artifacts. The first source-rich renderer
uses extracted claims and evidence links to produce citation markers, source
notes, figure/table references, and JSON citation payloads.

## Source-Rich Renderers

When a run has extracted claims and evidence, generated outputs include:

- citation markers such as `[S1]`
- source notes from normalized corpus citations when available
- claim confidence and locators
- evidence quotes
- figure/table references from claim provenance or chunk extraction metadata
- JSON citation payloads for ADAM, dashboards, and review UI surfaces

Run the normal worker path to stage outputs:

```bash
hal research execute-run <run-id> --actor hal-worker
```

The generated `research_brief`, `evidence_table`, and JSON output types now use
the same source-backed citation helpers.

## Output Version History

Every staged output starts with version `1`. Later output updates can create
additional versions while preserving prior content.

List versions:

```bash
hal research output-versions <output-id>
hal research output-versions <output-id> --json
```

Diff two versions:

```bash
hal research diff-output <output-id> --from-version 1 --to-version 2
```

Version history is intentionally stored next to canonical outputs so reviewers
can compare changes before promotion and downstream exports can point to the
exact reviewed version.
