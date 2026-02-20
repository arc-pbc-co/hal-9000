# Development Guide

This guide covers contributing to HAL 9000, extending its functionality, and development best practices.

## Development Setup

### Prerequisites

- Python 3.11+
- Git
- An Anthropic API key

### Clone and Install

```bash
# Clone the repository
git clone https://github.com/arc-pbc-co/hal-9000.git
cd hal-9000

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install in development mode with all dependencies
pip install -e ".[dev,ocr,gdrive,vector]"

# Set up pre-commit hooks (optional)
pre-commit install
```

### Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit with your API key
echo "ANTHROPIC_API_KEY=sk-ant-api03-your-key" >> .env
```

## Project Structure

```
hal-9000/
├── src/hal9000/           # Main source code
│   ├── __init__.py        # Package version
│   ├── cli.py             # CLI commands
│   ├── config.py          # Configuration
│   ├── ingest/            # PDF processing
│   ├── rlm/               # RLM engine
│   ├── categorize/        # Classification
│   ├── obsidian/          # Obsidian integration
│   ├── adam/              # ADAM context
│   └── db/                # Database models
├── tests/                 # Test suite
├── docs/                  # Documentation
├── config/                # Configuration files
├── templates/             # Note templates
├── pyproject.toml         # Package definition
└── README.md
```

## Running Tests

### Test Suite

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=hal9000 --cov-report=html

# Run specific test file
pytest tests/test_rlm.py

# Run specific test
pytest tests/test_rlm.py::test_chunk_text

# Verbose output
pytest -v
```

### Test Categories

```bash
# Unit tests only
pytest -m unit

# Integration tests (require API key)
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

### Writing Tests

```python
# tests/test_example.py
import pytest
from hal9000.ingest import PDFProcessor

class TestPDFProcessor:
    def test_extract_text(self, sample_pdf):
        """Test PDF text extraction."""
        processor = PDFProcessor()
        content = processor.extract_text(sample_pdf)

        assert content.full_text
        assert content.page_count > 0
        assert content.char_count > 0

    def test_chunk_text(self):
        """Test text chunking."""
        processor = PDFProcessor()
        text = "A" * 100000

        chunks = processor.chunk_text(text, chunk_size=10000)

        assert len(chunks) > 1
        assert all(len(c) <= 11000 for c in chunks)  # With overlap

    @pytest.mark.integration
    def test_process_real_pdf(self, real_pdf_path):
        """Integration test with real PDF (requires file)."""
        processor = PDFProcessor()
        content = processor.extract_text(real_pdf_path)

        assert "abstract" in content.full_text.lower()
```

### Fixtures

```python
# tests/conftest.py
import pytest
from pathlib import Path

@pytest.fixture
def sample_pdf(tmp_path):
    """Create a sample PDF for testing."""
    from reportlab.pdfgen import canvas

    pdf_path = tmp_path / "sample.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(100, 750, "Test PDF Content")
    c.save()

    return pdf_path

@pytest.fixture
def sample_analysis():
    """Create a sample DocumentAnalysis."""
    from hal9000.rlm import DocumentAnalysis

    return DocumentAnalysis(
        title="Test Paper",
        summary="Test summary",
        primary_topics=["topic1"],
        keywords=["keyword1", "keyword2"],
        key_findings=["finding1"],
        materials=[{"name": "Material1"}]
    )
```

## Code Style

### Formatting

HAL 9000 uses:
- **Black** for code formatting
- **isort** for import sorting
- **Ruff** for linting

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Lint
ruff check src/ tests/
```

### Type Hints

Use type hints throughout:

```python
from pathlib import Path
from typing import Optional

def process_document(
    path: Path,
    chunk_size: int = 50000,
    domain: Optional[str] = None
) -> DocumentAnalysis:
    """Process a document and return analysis."""
    ...
```

### Docstrings

Use Google-style docstrings:

```python
def extract_metadata(self, text: str, pdf_metadata: dict) -> DocumentMetadata:
    """
    Extract bibliographic metadata from document text.

    Args:
        text: Full document text.
        pdf_metadata: Metadata dict from PDF parsing.

    Returns:
        DocumentMetadata with extracted fields.

    Raises:
        ValueError: If text is empty.
    """
```

## Extending HAL 9000

### Adding a New CLI Command

```python
# In cli.py

@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Max results")
@click.pass_context
def search(ctx: click.Context, query: str, limit: int) -> None:
    """Search processed documents.

    QUERY: Search terms
    """
    from hal9000.db.models import Document, init_db
    from hal9000.config import get_settings

    settings = get_settings()
    engine, SessionLocal = init_db(settings.database.url)
    session = SessionLocal()

    # Implement search logic
    results = session.query(Document).filter(
        Document.title.contains(query)
    ).limit(limit).all()

    # Display results
    for doc in results:
        console.print(f"- {doc.title}")
```

### Adding a New Prompt

```python
# In rlm/prompts.py

CITATION_EXTRACTION_PROMPT = """
Extract all citations from the following text.

Text:
{text}

Return a JSON object with:
{{
    "citations": [
        {{
            "authors": ["Author 1", "Author 2"],
            "title": "Paper title",
            "year": 2024,
            "doi": "10.xxx/yyy"
        }}
    ]
}}
"""
```

Use it in the processor:

```python
# In rlm/processor.py

def extract_citations(self, text: str) -> list[dict]:
    """Extract citations from text."""
    response = self._call_llm(
        format_prompt(CITATION_EXTRACTION_PROMPT, text=text),
        max_tokens=2000
    )
    data = self._parse_json_response(response)
    return data.get("citations", [])
```

### Adding a Cloud Connector

```python
# In ingest/cloud_connectors/dropbox.py

from pathlib import Path
from typing import Iterator
from hal9000.ingest.local_scanner import DiscoveredFile

class DropboxConnector:
    """Connect to Dropbox for PDF discovery."""

    def __init__(self, access_token: str):
        """Initialize with Dropbox access token."""
        import dropbox
        self.dbx = dropbox.Dropbox(access_token)

    def scan(self, folder_path: str = "") -> Iterator[DiscoveredFile]:
        """Scan Dropbox folder for PDFs."""
        result = self.dbx.files_list_folder(folder_path)

        for entry in result.entries:
            if entry.name.lower().endswith(".pdf"):
                yield DiscoveredFile(
                    path=Path(entry.path_display),
                    size_bytes=entry.size,
                    modified_time=entry.server_modified
                )

    def download(self, path: str, local_path: Path) -> Path:
        """Download a PDF to local path."""
        self.dbx.files_download_to_file(str(local_path), path)
        return local_path
```

### Adding a Database Model

```python
# In db/models.py

class Experiment(Base):
    """Track ADAM experiment suggestions."""

    __tablename__ = "experiments"

    id = Column(Integer, primary_key=True)
    context_id = Column(String, ForeignKey("adam_contexts.id"))
    hypothesis = Column(Text, nullable=False)
    methodology = Column(Text)
    status = Column(String, default="suggested")  # suggested, planned, executed
    priority = Column(String, default="medium")
    confidence_score = Column(Float)

    # Relationships
    context = relationship("ADAMContext", back_populates="experiments")

    created_at = Column(DateTime, default=datetime.utcnow)
    executed_at = Column(DateTime, nullable=True)
    results = Column(JSON, nullable=True)
```

Run migrations:

```bash
# Generate migration
alembic revision --autogenerate -m "Add experiments table"

# Apply migration
alembic upgrade head
```

## Debugging

### Verbose Mode

```bash
hal -v process paper.pdf
```

### Logging

```python
import logging

logger = logging.getLogger(__name__)

# In your code
logger.debug("Processing chunk %d", chunk_index)
logger.info("Completed processing")
logger.warning("No topics matched")
logger.error("API call failed: %s", error)
```

### Debug Prompts

Save prompts and responses for debugging:

```python
# Temporary debugging
import json

prompt = format_prompt(TOPIC_EXTRACTION_PROMPT, text=chunk)
with open("debug_prompt.txt", "w") as f:
    f.write(prompt)

response = self._call_llm(prompt)
with open("debug_response.txt", "w") as f:
    f.write(response)
```

### Interactive Debugging

```bash
# Run with debugger
python -m pdb -c continue src/hal9000/cli.py process paper.pdf

# Or use IPython
ipython -i -c "from hal9000.rlm import RLMProcessor; p = RLMProcessor()"
```

## Performance Optimization

### Profiling

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Code to profile
process_document(pdf_path)

profiler.disable()
stats = pstats.Stats(profiler).sort_stats("cumtime")
stats.print_stats(20)
```

### Caching

```python
from functools import lru_cache

@lru_cache(maxsize=100)
def get_topic_keywords(topic_slug: str) -> list[str]:
    """Cache topic keywords lookups."""
    topic = taxonomy.get_topic(topic_slug)
    return topic.keywords if topic else []
```

### Batch Processing

```python
# Process chunks in parallel
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [
        executor.submit(self._process_chunk, chunk, i)
        for i, chunk in enumerate(chunks)
    ]
    results = [f.result() for f in futures]
```

## Documentation

### Building Docs

```bash
# Install docs dependencies
pip install mkdocs mkdocs-material

# Serve locally
mkdocs serve

# Build static site
mkdocs build
```

### Documentation Structure

```
docs/
├── index.md                 # Main index
├── guides/
│   ├── getting-started.md
│   ├── configuration.md
│   ├── cli-reference.md
│   ├── architecture.md
│   ├── obsidian-integration.md
│   ├── adam-integration.md
│   ├── taxonomy.md
│   └── development.md
├── api/
│   ├── config.md
│   ├── ingest.md
│   ├── rlm.md
│   ├── categorize.md
│   ├── obsidian.md
│   ├── adam.md
│   └── db.md
└── wiki/
    ├── rlm-patterns.md
    ├── materials-taxonomy.md
    ├── knowledge-graph.md
    ├── data-flow.md
    └── faq.md
```

## Release Process

### Version Bump

```bash
# Update version in src/hal9000/__init__.py
__version__ = "0.2.0"

# Update CHANGELOG.md
```

### Create Release

```bash
# Tag release
git tag -a v0.2.0 -m "Release 0.2.0"
git push origin v0.2.0

# Build package
python -m build

# Upload to PyPI
twine upload dist/*
```

## Contributing

### Pull Request Process

1. Fork the repository
2. Create feature branch: `git checkout -b feature/my-feature`
3. Make changes with tests
4. Run tests: `pytest`
5. Format code: `black src/ tests/`
6. Commit: `git commit -m "Add my feature"`
7. Push: `git push origin feature/my-feature`
8. Open Pull Request

### Code Review Checklist

- [ ] Tests pass
- [ ] Code is formatted
- [ ] Type hints added
- [ ] Docstrings complete
- [ ] Documentation updated
- [ ] CHANGELOG updated
- [ ] No security issues

### Commit Messages

Follow conventional commits:

```
feat: add citation extraction
fix: handle empty PDF text
docs: update CLI reference
test: add RLM processor tests
refactor: simplify chunking logic
```
