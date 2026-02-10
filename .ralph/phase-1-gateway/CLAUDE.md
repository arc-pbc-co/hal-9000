# Phase 1: Gateway Foundation - Agent Instructions

You are an autonomous coding agent implementing the **Gateway Foundation** for HAL-9000.

## Your Task

1. Read the PRD at `prd.json` (this directory)
2. Read `progress.txt` (check Codebase Patterns first)
3. Ensure you're on branch `ralph/phase-1-gateway` (create from main if needed)
4. Pick highest priority story where `passes: false`
5. Implement that single user story
6. Run: `pytest`, `mypy src/`, `ruff check src/`
7. If checks pass, commit: `feat: [Story ID] - [Story Title]`
8. Update PRD: set `passes: true`
9. Append progress to `progress.txt`

## Phase 1 Context

You are building the WebSocket gateway that will serve as the communication backbone for HAL-9000. This replaces the CLI-only interface with a real-time, multi-client architecture.

### Key Components

```
src/hal9000/gateway/
├── __init__.py
├── protocol.py      # Message types and models
├── session.py       # Session management
├── events.py        # Event streaming
├── router.py        # Message routing
└── server.py        # WebSocket server
```

### Dependencies to Add

```toml
# pyproject.toml
websockets = "^12.0"
```

### Existing Patterns to Follow

- **Pydantic models**: See `src/hal9000/rlm/prompts.py` for model patterns
- **Async patterns**: See `src/hal9000/acquisition/downloader.py`
- **Config**: See `src/hal9000/config.py` for Settings patterns
- **CLI**: See `src/hal9000/cli.py` for Click patterns
- **DB models**: See `src/hal9000/db/models.py` for SQLAlchemy patterns

### Example Message Flow

```python
# Client sends
{
  "id": "msg-123",
  "type": "query",
  "session_id": "sess-456",
  "timestamp": "2026-02-01T10:00:00Z",
  "payload": {"action": "search", "query": "HEA synthesis"}
}

# Gateway responds (streaming)
{
  "id": "resp-789",
  "type": "stream_chunk",
  "session_id": "sess-456",
  "timestamp": "2026-02-01T10:00:01Z",
  "payload": {"chunk": "Found 15 papers..."}
}
```

## Quality Requirements

- ALL commits must pass: pytest, mypy, ruff
- Gateway must handle connection errors gracefully
- Use `asyncio` for all I/O operations
- Log errors but don't crash on client issues

## Testing

- Unit tests: `tests/gateway/test_*.py`
- Use `pytest-asyncio` for async tests
- Mock WebSocket connections in unit tests
- Integration tests can use actual server

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
- Keep CI green
