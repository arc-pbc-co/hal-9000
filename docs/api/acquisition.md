# Acquisition API Reference

Module: `hal9000.acquisition`

Search for and download research papers from academic databases with Claude-powered query expansion.

## Overview

The acquisition module provides functionality to:
- Search multiple academic databases (Semantic Scholar, arXiv)
- Expand queries using Claude for better coverage
- Resolve PDF URLs via Unpaywall for open access versions
- Download and validate PDFs
- Deduplicate papers by DOI and file hash
- Orchestrate the full acquisition pipeline

## Classes

### AcquisitionOrchestrator

Coordinates the full paper acquisition workflow.

```python
from hal9000.acquisition import AcquisitionOrchestrator
from hal9000.config import get_settings

settings = get_settings()
orchestrator = AcquisitionOrchestrator(settings=settings)
```

#### Constructor

```python
def __init__(
    self,
    settings: Settings,
    db_session=None,
    pdf_processor: Optional[PDFProcessor] = None,
    rlm_processor: Optional[RLMProcessor] = None,
    vault_manager: Optional[VaultManager] = None,
)
```

**Parameters**:
- `settings`: HAL 9000 settings instance
- `db_session`: SQLAlchemy database session (optional)
- `pdf_processor`: PDF processor for content extraction (optional)
- `rlm_processor`: RLM processor for analysis (optional)
- `vault_manager`: Obsidian vault manager (optional)

#### Methods

##### acquire

```python
async def acquire(
    self,
    topic: str,
    max_papers: int = 20,
    sources: Optional[list[str]] = None,
    process_papers: bool = True,
    generate_notes: bool = True,
    relevance_threshold: float = 0.5,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> AcquisitionResult
```

Execute the full acquisition workflow.

**Parameters**:
- `topic`: Research topic to search for
- `max_papers`: Maximum papers to acquire
- `sources`: List of sources to use (default: all)
- `process_papers`: Whether to process papers through RLM
- `generate_notes`: Whether to generate Obsidian notes
- `relevance_threshold`: Minimum relevance score (0-1)
- `progress_callback`: Optional callback(stage, current, total)

**Returns**: `AcquisitionResult` with detailed status

**Example**:
```python
import asyncio
from hal9000.acquisition import AcquisitionOrchestrator
from hal9000.config import get_settings

settings = get_settings()
orchestrator = AcquisitionOrchestrator(settings=settings)

async def main():
    result = await orchestrator.acquire(
        topic="nickel superalloys creep resistance",
        max_papers=20,
        relevance_threshold=0.6,
    )
    print(f"Downloaded: {result.papers_downloaded}")
    print(f"Processed: {result.papers_processed}")

asyncio.run(main())
```

##### acquire_dry_run

```python
async def acquire_dry_run(
    self,
    topic: str,
    max_papers: int = 20,
    relevance_threshold: float = 0.5,
) -> list[SearchResult]
```

Search for papers without downloading (dry run).

**Parameters**:
- `topic`: Research topic to search for
- `max_papers`: Maximum papers to return
- `relevance_threshold`: Minimum relevance score

**Returns**: List of `SearchResult` that would be downloaded

---

### AcquisitionResult

Dataclass containing results of an acquisition session.

```python
from hal9000.acquisition import AcquisitionResult
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `topic` | `str` | Research topic searched |
| `session_id` | `str` | Unique session identifier |
| `session_dir` | `Path` | Directory containing downloads |
| `papers_found` | `int` | Total papers found |
| `papers_downloaded` | `int` | Papers successfully downloaded |
| `papers_processed` | `int` | Papers processed through RLM |
| `duplicates_skipped` | `int` | Duplicates skipped |
| `download_failures` | `int` | Failed downloads |
| `processing_failures` | `int` | Failed processing |
| `search_results` | `list[SearchResult]` | All search results |
| `download_results` | `list[DownloadResult]` | All download results |
| `documents` | `list[Document]` | Created documents |
| `errors` | `list[str]` | Error messages |
| `started_at` | `datetime` | Start time |
| `completed_at` | `Optional[datetime]` | Completion time |

#### Methods

##### to_dict

```python
def to_dict(self) -> dict
```

Convert to dictionary for serialization.

##### save_log

```python
def save_log(self) -> Path
```

Save session log to JSON file.

---

### SearchEngine

Orchestrates searches across multiple providers with Claude enhancement.

```python
from hal9000.acquisition import SearchEngine
from hal9000.acquisition.providers import SemanticScholarProvider, ArxivProvider

engine = SearchEngine(
    providers=[SemanticScholarProvider(), ArxivProvider()],
    anthropic_api_key="sk-ant-..."
)
```

#### Constructor

```python
def __init__(
    self,
    providers: list[BaseProvider],
    anthropic_api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-20250514",
)
```

**Parameters**:
- `providers`: List of search providers
- `anthropic_api_key`: Anthropic API key for query expansion
- `model`: Claude model to use

#### Methods

##### search

```python
async def search(
    self,
    topic: str,
    max_results: int = 50,
    expand_query: bool = True,
) -> list[SearchResult]
```

Search for papers across all providers.

**Parameters**:
- `topic`: Research topic
- `max_results`: Maximum results per provider
- `expand_query`: Use Claude to expand query

**Returns**: Deduplicated list of `SearchResult`

##### search_and_filter

```python
async def search_and_filter(
    self,
    topic: str,
    max_results: int = 50,
    relevance_threshold: float = 0.5,
    expand_query: bool = True,
) -> list[SearchResult]
```

Search and filter by Claude-scored relevance.

**Returns**: Results filtered by relevance threshold

##### expand_query

```python
async def expand_query(self, topic: str) -> dict
```

Use Claude to expand a research topic into multiple queries.

**Returns**: Dict with `queries`, `suggested_keywords`, `year_range`

---

### SearchResult

Dataclass representing a paper found in search.

```python
from hal9000.acquisition import SearchResult
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `title` | `str` | Paper title |
| `authors` | `list[str]` | Author names |
| `abstract` | `Optional[str]` | Abstract text |
| `year` | `Optional[int]` | Publication year |
| `doi` | `Optional[str]` | DOI identifier |
| `arxiv_id` | `Optional[str]` | arXiv ID |
| `pdf_url` | `Optional[str]` | Direct PDF URL |
| `source` | `str` | Source database |
| `source_id` | `Optional[str]` | ID in source database |
| `relevance_score` | `float` | Claude relevance score (0-1) |
| `citation_count` | `int` | Number of citations |

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `has_pdf` | `bool` | Whether PDF URL is available |
| `identifier` | `str` | DOI or arXiv ID or title |

#### Methods

##### to_dict

```python
def to_dict(self) -> dict
```

Convert to dictionary.

---

### DownloadManager

Manages PDF downloads with rate limiting and validation.

```python
from hal9000.acquisition import DownloadManager

manager = DownloadManager(
    download_dir=Path("~/Papers"),
    max_concurrent=3,
    rate_limit_seconds=1.0,
)
```

#### Constructor

```python
def __init__(
    self,
    download_dir: Path,
    max_concurrent: int = 3,
    rate_limit_seconds: float = 1.0,
    max_retries: int = 3,
    timeout: int = 60,
)
```

**Parameters**:
- `download_dir`: Base directory for downloads
- `max_concurrent`: Maximum concurrent downloads
- `rate_limit_seconds`: Minimum seconds between requests
- `max_retries`: Maximum retry attempts
- `timeout`: Download timeout in seconds

#### Methods

##### download

```python
async def download(
    self,
    result: SearchResult,
    topic: str,
) -> DownloadResult
```

Download a paper PDF.

**Parameters**:
- `result`: Search result to download
- `topic`: Topic for folder organization

**Returns**: `DownloadResult` with status and path

---

### DownloadResult

Dataclass containing download result.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `success` | `bool` | Whether download succeeded |
| `local_path` | `Optional[Path]` | Path to downloaded file |
| `source_url` | `str` | Original URL |
| `error` | `Optional[str]` | Error message if failed |
| `file_hash` | `Optional[str]` | SHA-256 hash |
| `file_size` | `int` | File size in bytes |
| `download_time` | `float` | Time taken in seconds |

---

### PDFValidator

Validate downloaded PDFs and check for duplicates.

```python
from hal9000.acquisition import PDFValidator

validator = PDFValidator(db_session=session)
```

#### Methods

##### is_valid_pdf

```python
def is_valid_pdf(self, path: Path) -> bool
```

Check if file is a valid PDF.

##### is_duplicate_by_hash

```python
def is_duplicate_by_hash(self, file_hash: str) -> Optional[Document]
```

Check if file hash exists in database.

##### is_duplicate_by_doi

```python
def is_duplicate_by_doi(self, doi: str) -> Optional[Document]
```

Check if DOI exists in database.

##### compute_file_hash

```python
def compute_file_hash(self, path: Path) -> str
```

Compute SHA-256 hash of file.

---

## Providers

### SemanticScholarProvider

Search Semantic Scholar API.

```python
from hal9000.acquisition.providers import SemanticScholarProvider

provider = SemanticScholarProvider(api_key="optional-api-key")
results = await provider.search("battery cathode materials", max_results=50)
```

### ArxivProvider

Search arXiv API.

```python
from hal9000.acquisition.providers import ArxivProvider

provider = ArxivProvider()
results = await provider.search("machine learning", max_results=50)
```

### UnpaywallProvider

Resolve DOIs to open access PDF URLs.

```python
from hal9000.acquisition.providers import UnpaywallProvider

provider = UnpaywallProvider(email="your@email.com")
result = await provider.resolve_doi("10.1000/example.123")
if result and result.pdf_url:
    print(f"Open access PDF: {result.pdf_url}")
```

---

## Configuration

Configure acquisition in your settings or environment:

```yaml
# config/default.yaml
acquisition:
  download_dir: ~/Documents/Research/Acquired
  max_concurrent_downloads: 3
  rate_limit_seconds: 1.0
  semantic_scholar_api_key: null  # Optional
  unpaywall_email: your@email.com  # Required for Unpaywall
```

Environment variables:
- `HAL9000_ACQUISITION_DOWNLOAD_DIR`
- `HAL9000_ACQUISITION_SEMANTIC_SCHOLAR_API_KEY`
- `HAL9000_ACQUISITION_UNPAYWALL_EMAIL`

---

## Usage Examples

### Basic Acquisition

```python
import asyncio
from hal9000.acquisition import AcquisitionOrchestrator
from hal9000.config import get_settings

async def acquire_papers():
    settings = get_settings()
    orchestrator = AcquisitionOrchestrator(settings=settings)

    result = await orchestrator.acquire(
        topic="solid state battery electrolytes",
        max_papers=10,
    )

    print(f"Found: {result.papers_found}")
    print(f"Downloaded: {result.papers_downloaded}")
    print(f"Session dir: {result.session_dir}")

asyncio.run(acquire_papers())
```

### Dry Run Search

```python
import asyncio
from hal9000.acquisition import AcquisitionOrchestrator
from hal9000.config import get_settings

async def preview_search():
    settings = get_settings()
    orchestrator = AcquisitionOrchestrator(settings=settings)

    results = await orchestrator.acquire_dry_run(
        topic="rare earth free magnets",
        max_papers=20,
    )

    for r in results:
        pdf_status = "PDF" if r.pdf_url else "No PDF"
        print(f"[{pdf_status}] {r.title[:60]}...")

asyncio.run(preview_search())
```

### Custom Search Engine

```python
import asyncio
from hal9000.acquisition import SearchEngine
from hal9000.acquisition.providers import ArxivProvider

async def search_arxiv_only():
    engine = SearchEngine(
        providers=[ArxivProvider()],
        anthropic_api_key="sk-ant-...",
    )

    # Expand query with Claude
    expanded = await engine.expand_query("neural network optimization")
    print(f"Expanded queries: {expanded['queries']}")

    # Search with relevance filtering
    results = await engine.search_and_filter(
        topic="neural network optimization",
        max_results=30,
        relevance_threshold=0.7,
    )

    for r in results:
        print(f"[{r.relevance_score:.2f}] {r.title}")

asyncio.run(search_arxiv_only())
```

### Download with Validation

```python
import asyncio
from pathlib import Path
from hal9000.acquisition import DownloadManager, PDFValidator, SearchResult

async def download_paper():
    manager = DownloadManager(download_dir=Path("~/Papers"))
    validator = PDFValidator()

    result = SearchResult(
        title="Example Paper",
        authors=["Smith, J."],
        source="manual",
        pdf_url="https://example.com/paper.pdf",
    )

    download = await manager.download(result, topic="test")

    if download.success:
        if validator.is_valid_pdf(download.local_path):
            print(f"Valid PDF: {download.local_path}")
            print(f"Hash: {download.file_hash}")
        else:
            print("Downloaded file is not a valid PDF")
    else:
        print(f"Download failed: {download.error}")

asyncio.run(download_paper())
```
