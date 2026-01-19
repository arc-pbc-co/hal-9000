# Ingest API Reference

Module: `hal9000.ingest`

PDF scanning, text extraction, and metadata parsing.

## Classes

### PDFProcessor

Extract text and content from PDF files.

```python
from hal9000.ingest import PDFProcessor

processor = PDFProcessor()
content = processor.extract_text(Path("paper.pdf"))
```

#### Methods

##### extract_text

```python
def extract_text(self, pdf_path: Path) -> PDFContent
```

Extract all text content from a PDF file.

**Parameters**:
- `pdf_path`: Path to PDF file

**Returns**: `PDFContent` with extracted text, metadata, and statistics

**Raises**: `Exception` if PDF cannot be read

**Example**:
```python
content = processor.extract_text(Path("paper.pdf"))
print(f"Pages: {content.page_count}")
print(f"Characters: {content.char_count}")
print(content.full_text[:500])
```

##### chunk_text

```python
def chunk_text(
    self,
    text: str,
    chunk_size: int = 50000,
    overlap: int = 1000
) -> list[str]
```

Split text into overlapping chunks at natural boundaries.

**Parameters**:
- `text`: Text to chunk
- `chunk_size`: Target characters per chunk
- `overlap`: Overlap between chunks

**Returns**: List of text chunks

**Example**:
```python
chunks = processor.chunk_text(content.full_text, chunk_size=25000)
print(f"Created {len(chunks)} chunks")
```

##### extract_sections

```python
def extract_sections(self, text: str) -> dict[str, str]
```

Extract standard academic paper sections.

**Parameters**:
- `text`: Full document text

**Returns**: Dict mapping section names to content

**Example**:
```python
sections = processor.extract_sections(content.full_text)
print(sections.get("abstract", "No abstract found"))
print(sections.get("methodology", ""))
```

##### compute_file_hash

```python
def compute_file_hash(self, file_path: Path) -> str
```

Compute SHA-256 hash of file for deduplication.

**Parameters**:
- `file_path`: Path to file

**Returns**: Hex-encoded SHA-256 hash

---

### PDFContent

Dataclass containing extracted PDF content.

```python
from hal9000.ingest import PDFContent
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `full_text` | `str` | Complete extracted text |
| `page_texts` | `list[str]` | Text per page |
| `page_count` | `int` | Number of pages |
| `tables` | `list[list]` | Extracted tables |
| `metadata` | `dict` | PDF metadata |
| `file_hash` | `str` | SHA-256 hash |
| `char_count` | `int` | Total characters |

---

### LocalScanner

Scan local directories for PDF files.

```python
from hal9000.ingest import LocalScanner

scanner = LocalScanner(
    paths=[Path("~/Documents/Research")],
    recursive=True
)
```

#### Constructor

```python
def __init__(
    self,
    paths: list[Path],
    recursive: bool = True
)
```

**Parameters**:
- `paths`: Directories to scan
- `recursive`: Scan subdirectories

#### Methods

##### scan

```python
def scan(self) -> Iterator[DiscoveredFile]
```

Scan directories and yield discovered PDFs.

**Yields**: `DiscoveredFile` for each PDF found

**Example**:
```python
for pdf in scanner.scan():
    print(f"{pdf.path.name}: {pdf.size_mb:.1f} MB")
```

##### get_stats

```python
def get_stats(self) -> dict
```

Get scanning statistics.

**Returns**: Dict with:
- `total_files`: Number of PDFs
- `total_size_mb`: Total size in MB
- `paths_configured`: Number of paths
- `paths_valid`: Number of valid paths

##### count_files

```python
def count_files(self) -> int
```

Count PDFs without loading them.

**Returns**: Total PDF count

---

### DiscoveredFile

Dataclass for discovered PDF files.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `path` | `Path` | File path |
| `size_bytes` | `int` | File size |
| `modified_time` | `datetime` | Last modified |

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `size_mb` | `float` | Size in megabytes |

---

### DirectoryWatcher

Watch directories for new PDF files.

```python
from hal9000.ingest import DirectoryWatcher

watcher = DirectoryWatcher(
    paths=[Path("~/Downloads")],
    callback=process_new_pdf
)
watcher.start()
```

#### Constructor

```python
def __init__(
    self,
    paths: list[Path],
    callback: Callable[[DiscoveredFile], None],
    recursive: bool = True
)
```

**Parameters**:
- `paths`: Directories to watch
- `callback`: Function called for new PDFs
- `recursive`: Watch subdirectories

#### Methods

##### start

```python
def start(self) -> None
```

Start watching for new files.

##### stop

```python
def stop(self) -> None
```

Stop watching.

---

### MetadataExtractor

Extract bibliographic metadata from documents.

```python
from hal9000.ingest import MetadataExtractor

extractor = MetadataExtractor()
metadata = extractor.extract(text, pdf_metadata)
```

#### Methods

##### extract

```python
def extract(
    self,
    text: str,
    pdf_metadata: Optional[dict] = None
) -> DocumentMetadata
```

Extract metadata from document text and PDF metadata.

**Parameters**:
- `text`: Full document text
- `pdf_metadata`: Optional PDF metadata dict

**Returns**: `DocumentMetadata` with extracted fields

**Example**:
```python
metadata = extractor.extract(content.full_text, content.metadata)
print(f"Title: {metadata.title}")
print(f"Authors: {', '.join(metadata.authors)}")
print(f"DOI: {metadata.doi}")
```

---

### DocumentMetadata

Dataclass for bibliographic metadata.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `title` | `Optional[str]` | Paper title |
| `authors` | `list[str]` | Author names |
| `year` | `Optional[int]` | Publication year |
| `doi` | `Optional[str]` | DOI identifier |
| `arxiv_id` | `Optional[str]` | arXiv ID |
| `abstract` | `Optional[str]` | Abstract text |
| `keywords` | `list[str]` | Keywords |
| `journal` | `Optional[str]` | Journal name |
| `institutions` | `list[str]` | Author affiliations |

#### Methods

##### to_dict

```python
def to_dict(self) -> dict
```

Convert to dictionary.

---

## Usage Examples

### Process a Single PDF

```python
from pathlib import Path
from hal9000.ingest import PDFProcessor, MetadataExtractor

# Extract content
processor = PDFProcessor()
content = processor.extract_text(Path("paper.pdf"))

# Extract metadata
extractor = MetadataExtractor()
metadata = extractor.extract(content.full_text, content.metadata)

print(f"Title: {metadata.title}")
print(f"Pages: {content.page_count}")
print(f"Abstract: {metadata.abstract[:200]}...")
```

### Scan a Directory

```python
from pathlib import Path
from hal9000.ingest import LocalScanner

scanner = LocalScanner([Path("~/Papers")])

# Get statistics
stats = scanner.get_stats()
print(f"Found {stats['total_files']} PDFs ({stats['total_size_mb']:.1f} MB)")

# Process each PDF
for pdf in scanner.scan():
    print(f"Processing: {pdf.path.name}")
    # ... process pdf
```

### Watch for New Files

```python
from pathlib import Path
from hal9000.ingest import DirectoryWatcher, DiscoveredFile

def on_new_pdf(file: DiscoveredFile):
    print(f"New PDF: {file.path.name}")
    # Process the new file

watcher = DirectoryWatcher(
    paths=[Path("~/Downloads")],
    callback=on_new_pdf
)

watcher.start()
# ... runs until watcher.stop() is called
```
