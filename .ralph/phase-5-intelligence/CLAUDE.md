# Phase 5: Enhanced Intelligence - Agent Instructions

You are an autonomous coding agent implementing **Enhanced Intelligence** for HAL-9000.

## Your Task

1. Read the PRD at `prd.json` (this directory)
2. Read `progress.txt` (check Codebase Patterns first)
3. Ensure you're on branch `ralph/phase-5-intelligence` (create from main if needed)
4. Pick highest priority story where `passes: false`
5. Implement that single user story
6. Run: `pytest`, `mypy src/`, `ruff check src/`
7. If checks pass, commit: `feat: [Story ID] - [Story Title]`
8. Update PRD: set `passes: true`
9. Append progress to `progress.txt`

## Phase 5 Context

You are adding advanced intelligence capabilities: semantic clustering for RLM aggregation, vector database for knowledge storage, feedback loops for learning from ADAM executions, and hypothesis generation.

### Key Components

```
src/hal9000/rlm/
├── embeddings.py         # Sentence transformer embeddings
├── clustering.py         # HDBSCAN semantic clustering
├── advanced_processor.py # Enhanced RLM with clustering
├── vectordb.py           # ChromaDB vector store
└── cache.py              # LLM response caching

src/hal9000/skills/adam/
├── feedback_handler.py   # Process ADAM feedback
├── knowledge_updater.py  # Store learnings
└── hypothesis_generator.py # Generate research hypotheses
```

### Dependencies to Add

```toml
# pyproject.toml
sentence-transformers = "^2.2.0"
scikit-learn = "^1.3.0"
hdbscan = "^0.8.33"
chromadb = "^0.4.0"
```

### Semantic Clustering Flow

```
Document chunks
    ↓
RLM extraction (per chunk)
    ↓
Embed findings with SentenceTransformer
    ↓
Cluster with HDBSCAN
    ↓
Synthesize each cluster → representative finding
    ↓
Final aggregated results
```

### Feedback Loop Flow

```
ADAM executes prompt
    ↓
Returns execution results (success/failure)
    ↓
FeedbackHandler.process_feedback()
    ↓
If success: extract successful parameters → store in VectorDB
If failure: analyze failure → suggest corrections
    ↓
Update session context with learnings
    ↓
suggest_next_experiment() uses learnings
```

### Existing Patterns

- **RLM processing**: See `src/hal9000/rlm/processor.py`
- **Claude API calls**: See `src/hal9000/rlm/processor.py` for patterns
- **Config**: Use `HAL9000_RLM__*` for new settings

### Vector DB Schema

```python
# Papers collection
{
    "id": "doc-uuid",
    "embedding": [...],
    "metadata": {
        "title": "...",
        "doi": "...",
        "topics": ["..."],
        "type": "paper"
    }
}

# Experiments collection
{
    "id": "exp-uuid",
    "embedding": [...],
    "metadata": {
        "prompt_id": "...",
        "material": "...",
        "process": "...",
        "success": true,
        "parameters": {...}
    }
}
```

## Quality Requirements

- ALL commits must pass: pytest, mypy, ruff
- Embeddings must be deterministic (set random seeds)
- Vector DB operations must handle failures gracefully
- LLM cache must not return stale results for dynamic queries

## Testing

- Unit tests: `tests/rlm/test_*.py`, `tests/skills/adam/test_*.py`
- Mock embeddings in unit tests (use small random vectors)
- Use in-memory ChromaDB for tests
- Integration tests verify full workflow

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
- This phase completes the refactor - ensure quality
