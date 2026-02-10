# Phase 2: Skill System - Agent Instructions

You are an autonomous coding agent implementing the **Skill System** for HAL-9000.

## Your Task

1. Read the PRD at `prd.json` (this directory)
2. Read `progress.txt` (check Codebase Patterns first)
3. Ensure you're on branch `ralph/phase-2-skills` (create from main if needed)
4. Pick highest priority story where `passes: false`
5. Implement that single user story
6. Run: `pytest`, `mypy src/`, `ruff check src/`
7. If checks pass, commit: `feat: [Story ID] - [Story Title]`
8. Update PRD: set `passes: true`
9. Append progress to `progress.txt`

## Phase 2 Context

You are building the skill framework that allows modular capabilities to be added to HAL-9000. The crown jewel is the **ADAM Orchestrator Skill** that generates prompts for the autonomous manufacturing platform.

### Key Components

```
src/hal9000/skills/
├── __init__.py
├── base.py              # BaseSkill, ToolDefinition, SkillManifest
├── registry.py          # SkillRegistry
├── executor.py          # SkillExecutor
│
├── literature/          # Literature research skill
│   ├── __init__.py
│   └── skill.py
│
├── materials/           # Materials science skill
│   ├── __init__.py
│   └── skill.py
│
├── adam/                # ADAM orchestrator skill (CRITICAL)
│   ├── __init__.py
│   ├── models.py        # ADAMPrompt, CellType, PromptType
│   ├── prompt_generator.py
│   ├── context_builder.py
│   └── skill.py
│
└── knowledge/           # Knowledge graph skill
    ├── __init__.py
    └── skill.py
```

### ADAM Prompt Structure

This is the critical output format for ADAM:

```python
class ADAMPrompt(BaseModel):
    prompt_id: str
    prompt_type: PromptType
    objective: str
    detailed_instructions: str
    context_window: dict
    literature_support: list[dict]
    material_constraints: list[str]
    process_constraints: list[str]
    safety_constraints: list[str]
    target_cell: Optional[CellType]
    cell_capabilities_required: list[str]
    success_criteria: list[str]
    expected_outputs: list[str]
    measurement_requirements: list[str]
    priority: str
    estimated_duration: Optional[str]
    depends_on: list[str]
```

### Reuse Existing Code

- `src/hal9000/ingest/` → LiteratureSkill
- `src/hal9000/acquisition/` → LiteratureSkill
- `src/hal9000/categorize/` → MaterialsSkill
- `src/hal9000/obsidian/` → KnowledgeGraphSkill
- `src/hal9000/rlm/` → All skills (for LLM calls)
- `src/hal9000/adam/context.py` → ADAMOrchestratorSkill

### Existing Patterns

- **Anthropic calls**: See `src/hal9000/rlm/processor.py` for Claude API usage
- **Async generators**: Use `async def execute(...) -> AsyncGenerator[dict, None]`
- **Error handling**: Return error dicts, don't raise exceptions in tools

## Quality Requirements

- ALL commits must pass: pytest, mypy, ruff
- Skills must be stateless (state lives in Session)
- Tools must validate input parameters
- Tools must handle LLM failures gracefully

## Testing

- Unit tests: `tests/skills/test_*.py`
- Test each tool in isolation
- Mock LLM responses for unit tests
- Integration tests verify skill → executor flow

## Progress Report Format

APPEND to `progress.txt`:

```
## [Date/Time] - [Story ID]
- What was implemented
- Files changed
- **Learnings:**
  - Patterns discovered
  - Gotchas encountered
---
```

## Stop Condition

- ALL stories `passes: true` → reply `COMPLETE`
- Stories remain → end normally

## Important

- ONE story per iteration
- Commit frequently
- The ADAM skill is the most critical - ensure it generates valid prompts
