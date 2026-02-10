# Code Review Skill

**name**: code-review
**description**: Review code changes for quality, patterns, and acceptance criteria
**user-invocable**: true

## Triggers

- "review this code"
- "check my changes"
- "does this meet criteria"

## The Job

Review code changes against:
1. Acceptance criteria from the current story
2. Codebase patterns from progress.txt
3. General quality standards

## Review Checklist

### Type Safety
- [ ] All functions have type hints
- [ ] No `Any` types (except where unavoidable)
- [ ] Pydantic models validate properly
- [ ] mypy passes with no errors

### Code Quality
- [ ] Functions are focused (single responsibility)
- [ ] No code duplication
- [ ] Error handling is appropriate
- [ ] Logging is present for debugging

### Testing
- [ ] Unit tests cover new code
- [ ] Tests are deterministic
- [ ] Mocks are used appropriately
- [ ] Edge cases are tested

### HAL-9000 Patterns
- [ ] Follows existing patterns in codebase
- [ ] Uses Pydantic for data models
- [ ] Uses Click for CLI commands
- [ ] Uses Rich for terminal output
- [ ] Async code uses proper patterns

### Documentation
- [ ] Docstrings on public functions
- [ ] Complex logic has comments
- [ ] CLAUDE.md updated if patterns discovered

## Output Format

```
## Code Review: [Story ID]

### Summary
[Brief assessment]

### Issues Found
1. [Issue description] - [Severity: high/medium/low]
   - Location: [file:line]
   - Suggestion: [how to fix]

### Acceptance Criteria Check
- [x] Criterion 1
- [ ] Criterion 2 (Issue: [why not met])

### Recommendation
[APPROVE / REQUEST CHANGES / NEEDS DISCUSSION]
```
