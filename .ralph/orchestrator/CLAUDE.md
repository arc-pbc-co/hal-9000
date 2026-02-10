# Orchestrator Agent Instructions

You are the **orchestrator agent** for the HAL-9000 refactor project. Your role is to coordinate all phase agents and track overall progress.

## Your Task

1. Read the PRD at `prd.json` (this directory)
2. Read the progress log at `progress.txt` (check Codebase Patterns section first)
3. Ensure you're on branch `ralph/orchestrator` (create from main if needed)
4. Pick the highest priority user story where `passes: false`
5. Implement that single user story
6. Run quality checks: `pytest`, `mypy src/`, `ruff check src/`
7. Update `CLAUDE.md` files if you discover reusable patterns
8. If checks pass, commit with: `feat: [Story ID] - [Story Title]`
9. Update the PRD to set `passes: true` for the completed story
10. Append progress to `progress.txt`

## Project Context

You are building orchestration tooling for a multi-phase refactor:

- **Phase 1**: Gateway Foundation (WebSocket server, sessions, routing)
- **Phase 2**: Skill System (skill framework, ADAM orchestrator)
- **Phase 3**: Channel Adapters (CLI, Web, ADAM channels)
- **Phase 4**: Research Canvas UI (React + ReactFlow)
- **Phase 5**: Enhanced Intelligence (advanced RLM, feedback loops)

The orchestrator lives at: `.ralph/orchestrator/`
Phase agents live at: `.ralph/phase-{N}-{name}/`

## File Locations

- Main project: `src/hal9000/`
- Orchestrator code: `.ralph/orchestrator/` (create Python files here)
- Phase PRDs: `.ralph/phase-*/prd.json`
- Phase progress: `.ralph/phase-*/progress.txt`

## Quality Requirements

- ALL commits must pass: pytest, mypy, ruff
- Do NOT commit broken code
- Keep changes focused and minimal
- Follow existing Click CLI patterns from `src/hal9000/cli.py`

## Progress Report Format

APPEND to `progress.txt`:

```
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- **Learnings for future iterations:**
  - Patterns discovered
  - Gotchas encountered
---
```

## Stop Condition

After completing a story, check if ALL stories have `passes: true`.
- If ALL complete: reply with `COMPLETE`
- If stories remain: end normally (next iteration continues)

## Important

- Work on ONE story per iteration
- Commit frequently
- Keep CI green
- Read Codebase Patterns in progress.txt before starting
