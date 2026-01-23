# HAL 9000 Test Suite

Comprehensive test suite for the HAL 9000 Research Assistant.

## Overview

This test suite provides thorough coverage of all HAL 9000 modules with unit tests, integration tests, and end-to-end tests.

## Test Structure

```
tests/
├── conftest.py                    # Pytest fixtures and configuration
├── test_pdf_processor.py          # PDF processing unit tests
├── test_metadata_extractor.py     # Metadata extraction tests
├── test_local_scanner.py          # File scanning tests
├── test_taxonomy.py               # Taxonomy system tests
├── test_config.py                 # Configuration tests
├── test_vault.py                  # Obsidian vault manager tests
├── test_rlm_processor.py          # RLM processor tests (with mocks)
├── test_adam_context.py           # ADAM context builder tests
└── test_integration.py            # Integration tests with real PDFs
```

## Test Data

The test suite uses PDFs from `/research/01-superalloys-nickel-materials/` as test data. These are real research papers that provide comprehensive test scenarios.

## Requirements

- Python 3.11+
- All project dependencies plus dev dependencies
- Test PDFs in the research folder

## Installation

```bash
# Install the project with dev dependencies
pip install -e ".[dev]"
```

This installs:
- pytest>=8.0.0
- pytest-asyncio>=0.23.0
- pytest-cov>=4.0.0
- ruff>=0.4.0
- mypy>=1.10.0

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Specific Test Files

```bash
# Test PDF processing
pytest tests/test_pdf_processor.py

# Test metadata extraction
pytest tests/test_metadata_extractor.py

# Test integration
pytest tests/test_integration.py
```

### Run with Verbose Output

```bash
pytest -v
```

### Run with Coverage Report

```bash
pytest --cov=hal9000 --cov-report=html
```

This generates an HTML coverage report in `htmlcov/index.html`.

### Run Specific Test Classes or Methods

```bash
# Run a specific test class
pytest tests/test_pdf_processor.py::TestPDFProcessor

# Run a specific test method
pytest tests/test_pdf_processor.py::TestPDFProcessor::test_extract_text_real_pdf
```

## Test Categories

### Unit Tests

Unit tests focus on individual components in isolation:

- **PDF Processor**: Text extraction, chunking, section detection
- **Metadata Extractor**: DOI, arXiv, author, title extraction
- **Local Scanner**: File discovery, directory watching
- **Taxonomy**: Topic trees, matching, classification
- **Config**: Settings loading, environment variables
- **Vault Manager**: Obsidian structure, note creation
- **RLM Processor**: Document analysis (mocked LLM calls)
- **ADAM Context**: Research context building (mocked)

### Integration Tests

Integration tests verify that components work together:

- PDF processing → metadata extraction
- Scanning → processing pipeline
- Taxonomy classification with real PDFs
- Vault population from scanned files
- End-to-end workflows

### Performance Tests

Performance tests ensure acceptable processing speed:

- Large PDF handling
- Chunking performance benchmarks
- Batch processing throughput

## Mocking Strategy

Tests that interact with external services (Anthropic API) use mocking:

- `test_rlm_processor.py`: Mocks Claude API calls
- `test_adam_context.py`: Mocks experiment generation

This allows tests to run quickly without API costs and ensures deterministic results.

## Test Fixtures

Key fixtures defined in `conftest.py`:

- `test_pdf_folder`: Path to test PDFs
- `sample_pdf_path`: Single PDF for quick tests
- `all_test_pdfs`: List of all test PDFs
- `temp_directory`: Temporary directory for test outputs
- `temp_vault_path`: Temporary Obsidian vault location
- `sample_document_text`: Mock document text
- `sample_taxonomy_yaml`: Sample taxonomy YAML file
- `mock_llm_response`: Mock LLM response data
- `mock_document_analysis`: Mock analysis results

## Test Coverage Goals

Target coverage by module:

- PDF Processing: >90%
- Metadata Extraction: >85%
- Scanner: >90%
- Taxonomy: >85%
- Config: >90%
- Vault Manager: >85%
- RLM Processor: >70% (core logic, mocked APIs)
- ADAM Context: >70% (core logic, mocked APIs)

## Writing New Tests

When adding new functionality:

1. Write unit tests first (TDD approach)
2. Test edge cases and error handling
3. Add integration tests for workflows
4. Update this README if adding new test files

### Test Naming Convention

- Test files: `test_<module_name>.py`
- Test classes: `Test<ComponentName>`
- Test methods: `test_<what_is_being_tested>`

### Example Test Structure

```python
class TestMyComponent:
    """Tests for MyComponent class."""

    def test_basic_functionality(self):
        """Test basic usage."""
        component = MyComponent()
        result = component.process()
        assert result is not None

    def test_edge_case(self):
        """Test edge case handling."""
        component = MyComponent()
        with pytest.raises(ValueError):
            component.process(invalid_input)
```

## Continuous Integration

These tests are designed to run in CI/CD pipelines:

- All tests are deterministic
- No external API dependencies (mocked)
- Fast execution (<5 minutes for full suite)
- Clear pass/fail criteria

## Troubleshooting

### Tests Fail with Import Errors

Ensure the project is installed in editable mode:

```bash
pip install -e .
```

### Tests Can't Find PDFs

Verify test PDFs exist:

```bash
ls research/01-superalloys-nickel-materials/*.pdf
```

### Mock Tests Fail

Check that mock patches are correctly applied:

```python
@patch('hal9000.rlm.processor.Anthropic')
def test_with_mock(self, mock_anthropic):
    # Test implementation
```

### Integration Tests Are Slow

Run only unit tests for faster iteration:

```bash
pytest -m "not integration"
```

(Note: Requires marking integration tests with `@pytest.mark.integration`)

## Test Metrics

Expected test execution times (on standard hardware):

- Unit tests: ~30 seconds
- Integration tests: ~2-3 minutes
- Full suite: ~3-4 minutes

Expected test counts:

- Total tests: ~150+
- PDF processor: ~25 tests
- Metadata extractor: ~20 tests
- Scanner: ~20 tests
- Taxonomy: ~25 tests
- Config: ~15 tests
- Vault: ~20 tests
- RLM processor: ~15 tests
- ADAM context: ~15 tests
- Integration: ~15 tests

## Contributing

When contributing:

1. All new code must have tests
2. Maintain or improve coverage
3. All tests must pass before PR
4. Follow existing test patterns

## License

MIT License - Same as the main project
