# Phase 3: Channel Adapters - Agent Instructions

You are an autonomous coding agent implementing **Channel Adapters** for HAL-9000.

## Your Task

1. Read the PRD at `prd.json` (this directory)
2. Read `progress.txt` (check Codebase Patterns first)
3. Ensure you're on branch `ralph/phase-3-channels` (create from main if needed)
4. Pick highest priority story where `passes: false`
5. Implement that single user story
6. Run: `pytest`, `mypy src/`, `ruff check src/`
7. If checks pass, commit: `feat: [Story ID] - [Story Title]`
8. Update PRD: set `passes: true`
9. Append progress to `progress.txt`

## Phase 3 Context

You are building channel adapters that allow different clients to connect to the HAL-9000 gateway. This enables multi-interface access: CLI, web browsers, ADAM platform, REST API, and team chat tools.

### Key Components

```
src/hal9000/channels/
├── __init__.py
├── base.py              # ChannelAdapter abstract class
├── registry.py          # ChannelRegistry
├── cli.py               # CLIChannel (backward compatible)
├── web.py               # WebChannel (for browser UI)
├── adam.py              # ADAMChannel (platform integration)
├── api.py               # APIChannel (REST/HTTP)
└── slack.py             # SlackChannel (stub)
```

### Channel Adapter Interface

```python
class ChannelAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def receive(self) -> AsyncGenerator[dict, None]:
        pass

    @abstractmethod
    async def send(self, message: dict) -> None:
        pass

    @abstractmethod
    async def stream(self, generator: AsyncGenerator) -> None:
        pass
```

### CLI Command Mapping

Legacy CLI commands map to gateway operations:

| CLI Command | Gateway Operation |
|-------------|-------------------|
| `hal scan` | `literature.scan` |
| `hal process` | `literature.process` |
| `hal batch` | `literature.batch` |
| `hal acquire` | `literature.acquire` |
| `hal init-vault` | `knowledge.init_vault` |

### Dependencies to Add

```toml
# pyproject.toml
fastapi = "^0.109.0"
uvicorn = "^0.27.0"
sse-starlette = "^1.8.0"  # For SSE streaming
```

### Existing Patterns

- **CLI**: See `src/hal9000/cli.py` for Click patterns
- **Async HTTP**: See `src/hal9000/acquisition/downloader.py` for httpx
- **WebSocket**: See gateway/server.py from Phase 1

## Quality Requirements

- ALL commits must pass: pytest, mypy, ruff
- Channels must handle disconnections gracefully
- CLI backward compatibility is critical
- API endpoints must validate input

## Testing

- Unit tests: `tests/channels/test_*.py`
- Test channel registration
- Test message routing per channel
- Integration tests with actual connections

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
- CLI backward compatibility is CRITICAL
