# HAL-9000 Ralph Agent System

This directory contains the autonomous agent system for refactoring HAL-9000 into a gateway-orchestrated research assistant for ADAM.

## Quick Start

```bash
# Navigate to a phase
cd .ralph/phase-1-gateway

# Run the agent loop
../ralph.sh

# Or with options
../ralph.sh --max 10  # Limit iterations
```

## Directory Structure

```
.ralph/
├── AGENTS.md              # Master agent instructions
├── README.md              # This file
├── ralph.sh               # Agent runner script
│
├── orchestrator/          # Coordinates all phases
│   ├── prd.json
│   ├── CLAUDE.md
│   └── progress.txt
│
├── phase-1-gateway/       # WebSocket gateway (10 stories)
│   ├── prd.json
│   ├── CLAUDE.md
│   └── progress.txt
│
├── phase-2-skills/        # Skill system (12 stories)
│   ├── prd.json
│   ├── CLAUDE.md
│   └── progress.txt
│
├── phase-3-channels/      # Channel adapters (10 stories)
│   ├── prd.json
│   ├── CLAUDE.md
│   └── progress.txt
│
├── phase-4-ui/            # Research Canvas UI (13 stories)
│   ├── prd.json
│   ├── CLAUDE.md
│   └── progress.txt
│
├── phase-5-intelligence/  # Enhanced RLM (13 stories)
│   ├── prd.json
│   ├── CLAUDE.md
│   └── progress.txt
│
└── skills/                # Reusable agent skills
    ├── prd-converter/
    └── code-review/
```

## Phase Summary

| Phase | Stories | Focus |
|-------|---------|-------|
| 1 - Gateway | 10 | WebSocket server, sessions, routing |
| 2 - Skills | 12 | Skill framework, ADAM orchestrator |
| 3 - Channels | 10 | CLI, Web, ADAM, API channels |
| 4 - UI | 13 | React canvas, chat, ADAM panel |
| 5 - Intelligence | 13 | Semantic clustering, feedback loops |
| **Total** | **58** | |

## Execution Order

Phases must run in order due to dependencies:

```
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
```

## How It Works

1. **ralph.sh** spawns Claude Code instances
2. Each instance reads **CLAUDE.md** for instructions
3. Agent picks highest-priority incomplete story from **prd.json**
4. Agent implements the story, runs tests, commits
5. Agent updates **prd.json** (passes: true) and **progress.txt**
6. Loop continues until all stories complete

## Key Files Per Phase

- **prd.json**: User stories with acceptance criteria
- **CLAUDE.md**: Agent instructions for that phase
- **progress.txt**: Append-only log with learnings

## Checking Progress

```bash
# Count completed stories
grep -c '"passes": true' phase-*/prd.json

# View recent progress
tail -50 phase-1-gateway/progress.txt
```

## Manual Intervention

If an agent gets stuck:

1. Check `progress.txt` for the last attempted story
2. Review the error in git diff
3. Add notes to `progress.txt` explaining the issue
4. Consider splitting the story if too complex
5. Restart the agent loop

## Quality Gates

All phases require:
- `pytest` passes
- `mypy src/` passes
- `ruff check src/` passes

UI phase also requires:
- `npm run typecheck` in ui/
- Browser verification

## Related Documentation

- **REFACTOR_PLAN.md**: Full architectural plan (repo root)
- **AGENTS.md**: Master agent instructions (this directory)
- **src/hal9000/**: Existing codebase to refactor
