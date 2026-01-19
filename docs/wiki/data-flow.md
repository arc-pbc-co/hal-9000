# Data Flow Wiki

Understanding the end-to-end data flow in HAL 9000.

## Overview

HAL 9000 processes research papers through a multi-stage pipeline:

```
PDF Files → Ingestion → Processing → Classification → Storage → Output
```

## Complete Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        HAL 9000 Data Flow                                │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────┐
│ PDF File │
└────┬─────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           INGESTION STAGE                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────────────┐  │
│  │ LocalScanner │      │ PDFProcessor │      │ MetadataExtractor    │  │
│  │              │      │              │      │                      │  │
│  │ - Find PDFs  │ ───▶ │ - Extract    │ ───▶ │ - DOI detection      │  │
│  │ - Watch dirs │      │   text       │      │ - Author parsing     │  │
│  │ - Get stats  │      │ - Get pages  │      │ - Title extraction   │  │
│  └──────────────┘      │ - Compute    │      │ - Abstract finding   │  │
│                        │   hash       │      └──────────┬───────────┘  │
│                        └──────┬───────┘                 │              │
│                               │                         │              │
│                               ▼                         ▼              │
│                        ┌──────────────┐         ┌──────────────┐      │
│                        │ PDFContent   │         │ DocumentMeta │      │
│                        │ - full_text  │         │ - title      │      │
│                        │ - page_texts │         │ - authors    │      │
│                        │ - metadata   │         │ - doi        │      │
│                        │ - file_hash  │         │ - abstract   │      │
│                        └──────┬───────┘         └──────┬───────┘      │
│                               │                         │              │
└───────────────────────────────┼─────────────────────────┼──────────────┘
                                │                         │
                                ▼                         │
┌─────────────────────────────────────────────────────────┼──────────────┐
│                        PROCESSING STAGE                  │              │
├─────────────────────────────────────────────────────────┼──────────────┤
│                                                          │              │
│  ┌────────────────────────────────────────────────────┐ │              │
│  │                   RLMProcessor                      │ │              │
│  ├────────────────────────────────────────────────────┤ │              │
│  │                                                     │ │              │
│  │  ┌─────────────┐                                   │ │              │
│  │  │  Chunking   │                                   │ │              │
│  │  │ (50k chars) │                                   │ │              │
│  │  └──────┬──────┘                                   │ │              │
│  │         │                                          │ │              │
│  │    ┌────┼────┬────┐                               │ │              │
│  │    ▼    ▼    ▼    ▼                               │ │              │
│  │  Chunk Chunk Chunk Chunk                          │ │              │
│  │    │    │    │    │                               │ │              │
│  │    ▼    ▼    ▼    ▼                               │ │              │
│  │  ┌─────────────────────────┐                      │ │              │
│  │  │    Claude API Calls     │                      │ │              │
│  │  │ - Topic extraction      │                      │ │              │
│  │  │ - Materials analysis    │                      │ │              │
│  │  │ - Findings extraction   │                      │ │              │
│  │  └───────────┬─────────────┘                      │ │              │
│  │              │                                     │ │              │
│  │    ┌─────────┼─────────┐                          │ │              │
│  │    ▼         ▼         ▼                          │ │              │
│  │  Result1  Result2  Result3                        │ │              │
│  │    │         │         │                          │ │              │
│  │    └─────────┼─────────┘                          │ │              │
│  │              ▼                                     │ │              │
│  │  ┌─────────────────────────┐                      │ │              │
│  │  │      Aggregation        │                      │ │              │
│  │  │ - Frequency ranking     │                      │ │              │
│  │  │ - Deduplication         │                      │ │              │
│  │  │ - Summary generation    │                      │ │              │
│  │  └───────────┬─────────────┘                      │ │              │
│  │              │                                     │ │              │
│  └──────────────┼─────────────────────────────────────┘ │              │
│                 ▼                                       │              │
│          ┌──────────────────┐                          │              │
│          │ DocumentAnalysis │ ◀────────────────────────┘              │
│          │ - title          │                                         │
│          │ - summary        │                                         │
│          │ - topics         │                                         │
│          │ - keywords       │                                         │
│          │ - findings       │                                         │
│          │ - materials      │                                         │
│          └────────┬─────────┘                                         │
│                   │                                                    │
└───────────────────┼────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      CLASSIFICATION STAGE                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐      ┌──────────────┐      ┌──────────────────────┐  │
│  │   Taxonomy   │      │  Classifier  │      │ ClassificationResult │  │
│  │              │      │              │      │                      │  │
│  │ - Topics     │ ───▶ │ - Match      │ ───▶ │ - primary_topics     │  │
│  │ - Keywords   │      │   keywords   │      │ - secondary_topics   │  │
│  │ - Hierarchy  │      │ - Score      │      │ - confidence_scores  │  │
│  │              │      │   confidence │      │ - folder_path        │  │
│  └──────────────┘      │ - Auto-      │      └──────────┬───────────┘  │
│                        │   extend     │                 │              │
│                        └──────────────┘                 │              │
│                                                          │              │
└──────────────────────────────────────────────────────────┼──────────────┘
                                                           │
                    ┌──────────────────────────────────────┤
                    │                                      │
                    ▼                                      ▼
┌─────────────────────────────────┐    ┌─────────────────────────────────┐
│         STORAGE STAGE           │    │          OUTPUT STAGE            │
├─────────────────────────────────┤    ├─────────────────────────────────┤
│                                 │    │                                  │
│  ┌──────────────────────────┐  │    │  ┌──────────────────────────┐   │
│  │        Database          │  │    │  │    NoteGenerator         │   │
│  │                          │  │    │  │                          │   │
│  │  ┌────────────────────┐  │  │    │  │ - Paper notes            │   │
│  │  │     Document       │  │  │    │  │ - Concept notes          │   │
│  │  │ - title, authors   │  │  │    │  │ - Topic notes            │   │
│  │  │ - summary, topics  │  │  │    │  │ - Wikilinks              │   │
│  │  │ - full_text        │  │  │    │  └────────────┬─────────────┘   │
│  │  └────────────────────┘  │  │    │               │                 │
│  │                          │  │    │               ▼                 │
│  │  ┌────────────────────┐  │  │    │  ┌──────────────────────────┐   │
│  │  │      Topic         │  │  │    │  │    Obsidian Vault        │   │
│  │  │ - hierarchy        │  │  │    │  │                          │   │
│  │  │ - documents        │  │  │    │  │  Papers/                 │   │
│  │  └────────────────────┘  │  │    │  │  Concepts/               │   │
│  │                          │  │    │  │  Topics/                 │   │
│  └──────────────────────────┘  │    │  └──────────────────────────┘   │
│                                 │    │                                  │
└─────────────────────────────────┘    │  ┌──────────────────────────┐   │
                                       │  │    ContextBuilder        │   │
                                       │  │                          │   │
                                       │  │ - Aggregate analyses     │   │
                                       │  │ - Build knowledge graph  │   │
                                       │  │ - Generate experiments   │   │
                                       │  └────────────┬─────────────┘   │
                                       │               │                 │
                                       │               ▼                 │
                                       │  ┌──────────────────────────┐   │
                                       │  │    ADAM Context JSON     │   │
                                       │  │                          │   │
                                       │  │ - literature_summary     │   │
                                       │  │ - experiment_suggestions │   │
                                       │  │ - knowledge_graph        │   │
                                       │  └──────────────────────────┘   │
                                       │                                  │
                                       └──────────────────────────────────┘
```

## Stage Details

### 1. Ingestion Stage

**Input**: PDF file path

**Components**:
- `LocalScanner`: Discovers PDF files
- `PDFProcessor`: Extracts text content
- `MetadataExtractor`: Extracts bibliographic info

**Output**: `PDFContent` + `DocumentMetadata`

**Data Transformations**:
```
PDF Binary → Raw Text → Structured Content
           ↘ Metadata → Bibliographic Info
```

### 2. Processing Stage

**Input**: `PDFContent.full_text`

**Components**:
- `RLMProcessor`: Orchestrates analysis
- Claude API: Performs analysis

**Output**: `DocumentAnalysis`

**Data Transformations**:
```
Full Text → Chunks (50k each)
         → Per-chunk analysis
         → Aggregated results
```

### 3. Classification Stage

**Input**: `DocumentAnalysis`

**Components**:
- `Taxonomy`: Topic hierarchy
- `Classifier`: Matching logic

**Output**: `ClassificationResult`

**Data Transformations**:
```
Analysis keywords → Taxonomy matching
                 → Confidence scores
                 → Topic assignments
```

### 4. Storage Stage

**Input**: All previous outputs

**Components**:
- SQLAlchemy models
- SQLite/PostgreSQL

**Output**: Persistent records

**Tables**:
- `documents`: Paper records
- `topics`: Topic hierarchy
- `document_topics`: Many-to-many
- `processing_jobs`: Job tracking

### 5. Output Stage

**Input**: Stored data + analysis

**Components**:
- `NoteGenerator`: Creates Obsidian notes
- `ContextBuilder`: Creates ADAM contexts

**Output**:
- Markdown notes with wikilinks
- ADAM context JSON files

## Data Structures

### PDFContent

```python
@dataclass
class PDFContent:
    full_text: str           # Complete extracted text
    page_texts: list[str]    # Text per page
    page_count: int          # Number of pages
    tables: list[list]       # Extracted tables
    metadata: dict           # PDF metadata
    file_hash: str           # SHA-256 hash
    char_count: int          # Character count
```

### DocumentMetadata

```python
@dataclass
class DocumentMetadata:
    title: Optional[str]
    authors: list[str]
    year: Optional[int]
    doi: Optional[str]
    arxiv_id: Optional[str]
    abstract: Optional[str]
    keywords: list[str]
    journal: Optional[str]
    institutions: list[str]
```

### DocumentAnalysis

```python
@dataclass
class DocumentAnalysis:
    title: str
    summary: str
    primary_topics: list[str]
    secondary_topics: list[str]
    keywords: list[str]
    key_findings: list[str]
    materials: list[dict]
    methodology_summary: str
    potential_applications: list[str]
    adam_relevance: str
    chunk_count: int
    processing_stats: dict
```

### ClassificationResult

```python
@dataclass
class ClassificationResult:
    primary_topics: list[TopicNode]
    secondary_topics: list[TopicNode]
    confidence_scores: dict[str, float]
    suggested_folder_path: str
    auto_extended: bool
```

## Batch Processing Flow

```
┌─────────────────┐
│  PDF Directory  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  LocalScanner   │
│  scan()         │
└────────┬────────┘
         │ Iterator[DiscoveredFile]
         ▼
┌─────────────────────────────────┐
│  For each PDF:                   │
│  ┌─────────────────────────────┐│
│  │ PDFProcessor.extract_text() ││
│  │ MetadataExtractor.extract() ││
│  │ RLMProcessor.process_doc()  ││
│  │ Classifier.classify()       ││
│  │ Database.save()             ││
│  │ NoteGenerator.write()       ││
│  └─────────────────────────────┘│
└────────┬────────────────────────┘
         │ List[DocumentAnalysis]
         ▼
┌─────────────────────────────────┐
│  ContextBuilder.build_context() │
│  - Aggregate literature         │
│  - Build knowledge graph        │
│  - Generate experiments         │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────┐
│  ADAM Context   │
│  JSON Export    │
└─────────────────┘
```

## Error Handling

### Per-Document Errors

```python
for pdf in scanner.scan():
    try:
        content = processor.extract_text(pdf.path)
        analysis = rlm.process_document(content.full_text)
        # Continue processing...
    except Exception as e:
        logger.error(f"Failed to process {pdf.path}: {e}")
        # Continue with next document
```

### Per-Chunk Errors

```python
chunk_results = []
for i, chunk in enumerate(chunks):
    try:
        result = self._process_chunk(chunk, i)
        chunk_results.append(result)
    except Exception as e:
        logger.warning(f"Chunk {i} failed: {e}")
        chunk_results.append(ChunkResult(
            chunk_index=i,
            error=str(e)
        ))
```

## Performance Characteristics

| Stage | Bottleneck | Typical Time |
|-------|------------|--------------|
| PDF Extraction | I/O | ~1-5 sec |
| RLM Processing | API calls | ~30-60 sec |
| Classification | CPU | <1 sec |
| Database | I/O | <1 sec |
| Note Generation | I/O | <1 sec |

Total per document: ~30-90 seconds (dominated by LLM API)
