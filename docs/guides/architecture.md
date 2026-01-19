# Architecture Guide

This document describes the system architecture of HAL 9000, including its design principles, module structure, and data flow.

## Design Principles

HAL 9000 is built on principles from the **Recursive Language Models (RLM)** paper:

### 1. Context as Environment

Instead of stuffing entire documents into prompts, HAL 9000 treats documents as external "environment variables" that can be queried programmatically.

```python
# Traditional approach (problematic for large documents)
response = llm.complete(f"Analyze this document: {full_document_text}")

# RLM approach (HAL 9000's method)
env = {"document": full_document_text}
chunks = chunk_document(env["document"])
results = [llm.complete(f"Analyze: {chunk}") for chunk in chunks]
final = aggregate(results)
```

### 2. Recursive Decomposition

Large documents are processed through recursive sub-LM calls:

1. **Chunk** the document into manageable pieces
2. **Process** each chunk independently
3. **Aggregate** results using frequency ranking and deduplication

### 3. Structured Output

All LLM outputs are structured as JSON for reliable parsing and aggregation:

```json
{
  "primary_topics": ["topic1", "topic2"],
  "keywords": ["keyword1", "keyword2"],
  "key_findings": ["finding1", "finding2"]
}
```

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           HAL 9000 Core                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │   Ingest     │───▶│   RLM        │───▶│   Categorize             │  │
│  │   Module     │    │   Engine     │    │   (Classification)       │  │
│  └──────────────┘    └──────────────┘    └──────────────────────────┘  │
│         │                   │                        │                  │
│         ▼                   ▼                        ▼                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │ PDF Sources  │    │ Claude API   │    │   Obsidian Integration   │  │
│  │ - Local FS   │    │ (Anthropic)  │    │   (Mind Maps)            │  │
│  │ - Cloud      │    └──────────────┘    └──────────────────────────┘  │
│  └──────────────┘                                    │                  │
│                                                      ▼                  │
│  ┌──────────────┐                       ┌──────────────────────────┐   │
│  │   Database   │◀─────────────────────▶│  ADAM Context Generator  │   │
│  │   (SQLite)   │                       │  (Experiment Design)     │   │
│  └──────────────┘                       └──────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Module Structure

```
src/hal9000/
├── __init__.py          # Package version
├── cli.py               # Command-line interface
├── config.py            # Configuration management
│
├── ingest/              # Document ingestion
│   ├── __init__.py
│   ├── local_scanner.py      # Filesystem scanning
│   ├── pdf_processor.py      # PDF text extraction
│   └── metadata_extractor.py # Bibliographic metadata
│
├── rlm/                 # RLM processing engine
│   ├── __init__.py
│   ├── processor.py     # Core RLM logic
│   └── prompts.py       # LLM prompt templates
│
├── categorize/          # Topic classification
│   ├── __init__.py
│   ├── taxonomy.py      # Topic hierarchy
│   └── classifier.py    # Document classification
│
├── obsidian/            # Obsidian integration
│   ├── __init__.py
│   ├── vault.py         # Vault management
│   └── notes.py         # Note generation
│
├── adam/                # ADAM Platform integration
│   ├── __init__.py
│   └── context.py       # Context generation
│
└── db/                  # Database layer
    ├── __init__.py
    └── models.py        # SQLAlchemy models
```

## Data Flow

### Single Document Processing

```
┌─────────────┐
│   PDF File  │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│   PDFProcessor      │
│   - Extract text    │
│   - Extract tables  │
│   - Compute hash    │
└──────┬──────────────┘
       │ PDFContent
       ▼
┌─────────────────────┐
│ MetadataExtractor   │
│   - DOI detection   │
│   - Author parsing  │
│   - Title extract   │
└──────┬──────────────┘
       │ DocumentMetadata
       ▼
┌─────────────────────┐
│   RLMProcessor      │
│   - Chunk text      │◀──────┐
│   - Process chunks  │       │ Claude API
│   - Aggregate       │───────┘
└──────┬──────────────┘
       │ DocumentAnalysis
       ▼
┌─────────────────────┐
│    Classifier       │
│   - Match topics    │
│   - Score confidence│
│   - Auto-extend     │
└──────┬──────────────┘
       │ ClassificationResult
       ▼
┌─────────────────────┐
│    Database         │
│   - Store Document  │
│   - Link Topics     │
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│   NoteGenerator     │
│   - Create note     │
│   - Add wikilinks   │
│   - Write to vault  │
└─────────────────────┘
```

### Batch Processing with ADAM Context

```
┌──────────────────┐
│  Multiple PDFs   │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  LocalScanner    │
│  - Discover PDFs │
│  - Filter/limit  │
└────────┬─────────┘
         │ List[DiscoveredFile]
         ▼
┌──────────────────────────────────────┐
│  Process Each Document               │
│  (PDFProcessor → RLM → Classifier)   │
└────────┬─────────────────────────────┘
         │ List[DocumentAnalysis]
         ▼
┌──────────────────────────────────────┐
│  ContextBuilder                       │
│  - Aggregate literature              │
│  - Build knowledge graph             │
│  - Extract materials                 │
│  - Generate experiments              │
└────────┬─────────────────────────────┘
         │ ADAMResearchContext
         ▼
┌──────────────────┐
│  JSON Export     │
│  (ADAM-compatible)│
└──────────────────┘
```

## Key Classes

### Configuration

```python
class Settings(BaseSettings):
    """Main configuration container."""
    sources: SourcesConfig
    cloud: CloudConfig
    obsidian: ObsidianConfig
    adam: ADAMConfig
    processing: ProcessingConfig
    taxonomy: TaxonomyConfig
    database: DatabaseConfig
    anthropic_api_key: Optional[str]
    log_level: str
    verbose: bool
```

### Document Processing

```python
@dataclass
class PDFContent:
    """Extracted PDF content."""
    full_text: str
    page_texts: list[str]
    page_count: int
    tables: list[list]
    metadata: dict
    file_hash: str
    char_count: int

@dataclass
class DocumentMetadata:
    """Bibliographic metadata."""
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

### RLM Processing

```python
@dataclass
class ChunkResult:
    """Analysis of a single chunk."""
    chunk_index: int
    primary_topics: list[str]
    secondary_topics: list[str]
    keywords: list[str]
    key_findings: list[str]
    materials: list[dict]
    methodology_notes: str
    error: Optional[str]

@dataclass
class DocumentAnalysis:
    """Complete document analysis."""
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

### Classification

```python
@dataclass
class TopicNode:
    """A node in the topic taxonomy."""
    name: str
    slug: str
    description: str
    keywords: list[str]
    parent: Optional['TopicNode']
    children: list['TopicNode']
    level: int

@dataclass
class ClassificationResult:
    """Document classification result."""
    primary_topics: list[TopicNode]
    secondary_topics: list[TopicNode]
    confidence_scores: dict[str, float]
    suggested_folder_path: str
    auto_extended: bool
```

### ADAM Context

```python
@dataclass
class ADAMResearchContext:
    """Research context for ADAM Platform."""
    context_id: str
    name: str
    description: str
    research_domain: str
    topic_focus: str
    literature_summary: LiteratureSummary
    experiment_suggestions: list[ExperimentSuggestion]
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]
    materials_of_interest: list[str]
    recommended_characterization: list[str]
    source_documents: list[str]
    created_at: str
    updated_at: str
```

## Database Schema

```
┌─────────────────┐       ┌─────────────────┐
│    Document     │       │     Topic       │
├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │
│ source_path     │       │ name            │
│ source_type     │       │ slug            │
│ file_hash       │◀──┐   │ description     │
│ title           │   │   │ keywords        │
│ authors (JSON)  │   │   │ parent_id (FK)  │
│ year            │   │   │ level           │
│ doi             │   │   │ auto_generated  │
│ abstract        │   │   └────────┬────────┘
│ summary         │   │            │
│ key_concepts    │   │            │
│ full_text       │   │   ┌────────▼────────┐
│ page_count      │   │   │ document_topics │
│ status          │   │   ├─────────────────┤
│ note_path       │   └───│ document_id(FK) │
│ adam_context_id │       │ topic_id (FK)   │
│ created_at      │       │ confidence      │
│ updated_at      │       │ is_primary      │
│ processed_at    │       └─────────────────┘
└─────────────────┘
         │
         │         ┌─────────────────────┐
         │         │  document_relations │
         └────────▶├─────────────────────┤
                   │ source_id (FK)      │
                   │ target_id (FK)      │
                   │ relationship_type   │
                   │ confidence          │
                   └─────────────────────┘
```

## RLM Processing Pipeline

### 1. Document Chunking

```python
def chunk_text(self, text: str, chunk_size: int = 50000, overlap: int = 1000):
    """
    Chunk text at paragraph/sentence boundaries.

    - Prefer breaking at double newlines (paragraphs)
    - Fall back to sentence boundaries (. ? !)
    - Overlap ensures context continuity
    """
```

### 2. Chunk Processing

Each chunk is processed with multiple specialized prompts:

```python
# Topic extraction
topics = llm.complete(TOPIC_EXTRACTION_PROMPT.format(text=chunk))

# Materials science analysis
materials = llm.complete(MATERIALS_SCIENCE_PROMPT.format(text=chunk))

# Findings extraction
findings = llm.complete(FINDINGS_PROMPT.format(text=chunk))
```

### 3. Result Aggregation

Results from all chunks are merged using frequency-based ranking:

```python
def _deduplicate_and_rank(items: list[str]) -> list[str]:
    """
    1. Normalize to lowercase
    2. Count occurrences across chunks
    3. Rank by frequency
    4. Return original casing for top items
    """
```

## Integration Points

### Obsidian

HAL 9000 creates interconnected notes:

```markdown
---
title: "Paper Title"
topics: [magnetic-materials, rare-earth-free-magnets]
---

# Paper Title

## Key Concepts
- [[Concept 1]]
- [[Concept 2]]

## Topics
- [[magnetic-materials|Magnetic Materials]] (primary)
- [[rare-earth-free-magnets|Rare-Earth-Free Magnets]]

## Related Papers
- [[Related Paper 1]]
```

### ADAM Platform

Output format is designed for ADAM's autonomous experiment design:

```json
{
  "context_id": "uuid",
  "research_domain": "materials_science",
  "literature_summary": {
    "papers_analyzed": 50,
    "key_findings": [...],
    "gaps_identified": [...]
  },
  "experiment_suggestions": [
    {
      "hypothesis": "...",
      "methodology": "...",
      "variables": {
        "independent": [...],
        "dependent": [...],
        "controlled": [...]
      },
      "expected_outcomes": [...]
    }
  ],
  "knowledge_graph": {
    "nodes": [...],
    "edges": [...]
  }
}
```

## Performance Considerations

### Chunking Strategy

- **Default chunk size**: 50,000 characters (~12,500 tokens)
- **Overlap**: 1,000 characters to maintain context
- **Break points**: Paragraphs > Sentences > Hard split

### API Usage

- **Max concurrent calls**: 5 (configurable)
- **Rate limiting**: Handled by Anthropic SDK
- **Caching**: Optional result caching to avoid reprocessing

### Database

- **SQLite**: Default, good for single-user scenarios
- **PostgreSQL**: Recommended for team/production use
- **Indexing**: Full-text search on title, abstract, keywords

## Error Handling

### PDF Extraction Errors

```python
try:
    content = pdf_processor.extract_text(path)
except Exception as e:
    logger.error(f"PDF extraction failed: {e}")
    # Continue with next document in batch mode
```

### LLM Errors

```python
try:
    response = self._call_llm(prompt)
    data = self._parse_json_response(response)
except json.JSONDecodeError:
    # Retry with simplified prompt
except anthropic.RateLimitError:
    # Exponential backoff
```

### Classification Errors

```python
if not matching_topics and taxonomy.auto_extend:
    # Create new topic from document analysis
    new_topic = taxonomy.create_topic_from_analysis(analysis)
```

## Extensibility

### Adding New Prompts

```python
# In rlm/prompts.py
NEW_ANALYSIS_PROMPT = """
Analyze the following text for specific aspect:
{text}

Return JSON:
{{"aspect_results": [...]}}
"""
```

### Adding New Cloud Connectors

```python
# In ingest/cloud_connectors/
class DropboxConnector:
    def __init__(self, credentials):
        ...

    def scan(self, folder_path: str) -> Iterator[DiscoveredFile]:
        ...
```

### Custom Taxonomies

Create a new YAML file:

```yaml
taxonomy:
  name: My Research Domain
  topics:
    - name: Topic 1
      slug: topic-1
      keywords: [keyword1, keyword2]
      children:
        - name: Subtopic 1.1
          ...
```

Load it:

```python
taxonomy = Taxonomy.from_yaml("path/to/taxonomy.yaml")
```
