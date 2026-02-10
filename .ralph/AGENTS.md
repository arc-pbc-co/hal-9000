# HAL-9000 Refactor Agent System

## Overview

This is a Ralph-style autonomous agent system for refactoring HAL-9000 from a CLI-based literature tool into a gateway-orchestrated research assistant for ADAM (Autonomous Discovery and Advanced Manufacturing).

## Architecture

```
orchestrator/          → Coordinates all phases, tracks dependencies
├── phase-1-gateway/   → WebSocket gateway foundation
├── phase-2-skills/    → Skill system + ADAM orchestrator
├── phase-3-channels/  → Channel adapters (CLI, Web, ADAM)
├── phase-4-ui/        → Research Canvas web UI
└── phase-5-intelligence/ → Enhanced RLM + feedback loops
```

## Running the Refactor

```bash
# Run from hal-9000 root directory

# Start with Phase 1 (Gateway)
cd .ralph/phase-1-gateway && ../ralph.sh

# After Phase 1 complete, move to Phase 2
cd .ralph/phase-2-skills && ../ralph.sh

# Continue through phases...
```

## Phase Dependencies

```
Phase 1 (Gateway)
    ↓
Phase 2 (Skills) ──────┐
    ↓                  │
Phase 3 (Channels)     │
    ↓                  │
Phase 4 (UI) ←─────────┘
    ↓
Phase 5 (Intelligence)
```

- **Phase 1** must complete before any other phase
- **Phase 2** must complete before Phase 3 (channels use skills)
- **Phase 3** must complete before Phase 4 (UI is a channel)
- **Phase 4** can run in parallel with Phase 2 completion for shared types
- **Phase 5** requires all prior phases

## Orchestrator Commands

The orchestrator agent can be invoked to:

1. **Check phase status**: Read all `prd.json` files, report completion %
2. **Validate dependencies**: Ensure phase N-1 is complete before starting N
3. **Run phase**: Execute a specific phase's agent loop
4. **Generate report**: Summarize progress across all phases

## Key Files Per Phase

Each phase directory contains:

| File | Purpose |
|------|---------|
| `prd.json` | User stories with acceptance criteria |
| `CLAUDE.md` | Agent instructions for that phase |
| `progress.txt` | Append-only progress log |

## Codebase Patterns

### Existing HAL-9000 Patterns (Preserve)

- **Click CLI**: All commands use `@click.command()` decorators
- **Rich output**: Use `rich.console.Console()` for terminal output
- **Pydantic config**: Settings via `pydantic-settings` with `HAL9000_` prefix
- **SQLAlchemy 2.0**: Async-ready ORM with typed models
- **Type hints**: Full typing throughout, mypy compatible

### New Patterns (Establish)

- **Gateway protocol**: All messages use `GatewayMessage` Pydantic model
- **Skill manifest**: Every skill exposes `SkillManifest` with tool definitions
- **Streaming generators**: All skill tools return `AsyncGenerator[dict, None]`
- **Session state**: Use `Session` dataclass for research context
- **ADAM prompts**: Generate via `ADAMPrompt` model with required fields

### Testing Requirements

- All new code must have pytest tests
- Gateway tests use `pytest-asyncio`
- UI tests use Playwright (Phase 4)
- Integration tests verify skill → gateway → channel flow

## Quality Gates

Before marking ANY story as `passes: true`:

1. `pytest` passes (all tests green)
2. `mypy src/` passes (no type errors)
3. `ruff check src/` passes (no lint errors)
4. Manual verification of acceptance criteria
5. For UI stories: browser verification screenshot

## Git Workflow

Each phase works on its own branch:

```
main
├── ralph/phase-1-gateway
├── ralph/phase-2-skills
├── ralph/phase-3-channels
├── ralph/phase-4-ui
└── ralph/phase-5-intelligence
```

After each phase completes:
1. Create PR to main
2. Review and merge
3. Next phase branches from updated main

## Emergency Stop

If an agent iteration produces broken code:

1. `git stash` or `git checkout .` to revert
2. Add notes to `progress.txt` explaining the issue
3. Reduce story scope if needed
4. Restart iteration

## Contact

This refactor plan was generated for the ADAM platform integration project.
See `REFACTOR_PLAN.md` in repo root for full architectural details.
