# PRD Converter Skill

**name**: prd-converter
**description**: Convert markdown PRDs to prd.json format for Ralph agents
**user-invocable**: true

## Triggers

- "convert this prd"
- "create prd.json from this"
- "break this into user stories"

## The Job

Take a PRD (Product Requirements Document) in markdown format and convert it to the structured prd.json format used by HAL-9000 Ralph agents.

## Output Format

```json
{
  "project": "HAL-9000 Refactor",
  "branchName": "ralph/[phase-name]",
  "description": "[Phase description]",
  "userStories": [
    {
      "id": "[PHASE]-001",
      "title": "[Short title]",
      "description": "As a [role], I want [feature] so that [benefit]",
      "acceptanceCriteria": [
        "Criterion 1",
        "Criterion 2",
        "Typecheck passes"
      ],
      "priority": 1,
      "passes": false,
      "notes": ""
    }
  ]
}
```

## Story Sizing Rules

Each story MUST be completable in ONE context window. Ralph spawns fresh instances with no memory between iterations.

**Right-sized stories:**
- Add a Pydantic model with 3-5 fields
- Create a single class with 2-3 methods
- Add one CLI command
- Write tests for one module

**Too big (split these):**
- "Build the entire gateway" → Split by component
- "Add all ADAM tools" → One tool per story
- "Create the UI" → One component per story

## Acceptance Criteria Rules

Every criterion must be **verifiable**:

✅ Good:
- "Add status field with type Enum['pending', 'complete']"
- "Method returns AsyncGenerator[dict, None]"
- "Typecheck passes"

❌ Bad:
- "Works correctly"
- "Good performance"
- "Handles edge cases"

**Required criteria for all stories:**
- "Typecheck passes" (always)
- "Unit tests pass" (for logic)
- "Verify in browser" (for UI)

## HAL-9000 Specific Patterns

- IDs: `P1-001` (Phase 1), `P2-001` (Phase 2), etc.
- Branch names: `ralph/phase-1-gateway`, etc.
- All Python code: mypy + ruff + pytest
- All TypeScript: tsc --noEmit
