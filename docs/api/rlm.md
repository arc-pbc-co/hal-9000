# RLM API Reference

Module: `hal9000.rlm`

Recursive Language Model processing for intelligent document analysis.

## Classes

### RLMProcessor

Core processor implementing RLM patterns for document analysis.

```python
from hal9000.rlm import RLMProcessor

processor = RLMProcessor(
    model="claude-sonnet-4-20250514",
    chunk_size=50000
)
analysis = processor.process_document(text)
```

#### Constructor

```python
def __init__(
    self,
    model: str = "claude-sonnet-4-20250514",
    chunk_size: int = 50000,
    max_concurrent: int = 5
)
```

**Parameters**:
- `model`: Claude model to use
- `chunk_size`: Characters per chunk
- `max_concurrent`: Max concurrent API calls

#### Methods

##### process_document

```python
def process_document(
    self,
    text: str,
    domain: str = "materials_science",
    include_materials_analysis: bool = True
) -> DocumentAnalysis
```

Process a full document through the RLM pipeline.

**Parameters**:
- `text`: Full document text
- `domain`: Research domain for prompt tuning
- `include_materials_analysis`: Include materials-specific analysis

**Returns**: `DocumentAnalysis` with complete analysis

**Example**:
```python
analysis = processor.process_document(
    content.full_text,
    domain="materials_science"
)

print(f"Title: {analysis.title}")
print(f"Topics: {analysis.primary_topics}")
print(f"Summary: {analysis.summary}")
```

##### process_chunk

```python
def _process_chunk(
    self,
    chunk: str,
    chunk_index: int,
    domain: str,
    include_materials: bool
) -> ChunkResult
```

Process a single chunk (internal method).

**Parameters**:
- `chunk`: Text chunk
- `chunk_index`: Index of this chunk
- `domain`: Research domain
- `include_materials`: Include materials analysis

**Returns**: `ChunkResult` with chunk-level analysis

---

### DocumentAnalysis

Dataclass containing complete document analysis.

```python
from hal9000.rlm import DocumentAnalysis
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `title` | `str` | Extracted/inferred title |
| `summary` | `str` | AI-generated summary |
| `primary_topics` | `list[str]` | Main topics |
| `secondary_topics` | `list[str]` | Secondary topics |
| `keywords` | `list[str]` | Key terms |
| `key_findings` | `list[str]` | Important findings |
| `materials` | `list[dict]` | Materials information |
| `methodology_summary` | `str` | Methods summary |
| `potential_applications` | `list[str]` | Applications |
| `adam_relevance` | `str` | ADAM Platform relevance |
| `chunk_count` | `int` | Number of chunks processed |
| `processing_stats` | `dict` | Processing statistics |

#### Methods

##### to_dict

```python
def to_dict(self) -> dict
```

Convert to dictionary for JSON serialization.

**Example**:
```python
import json
print(json.dumps(analysis.to_dict(), indent=2))
```

---

### ChunkResult

Dataclass for single chunk analysis.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `chunk_index` | `int` | Chunk position |
| `primary_topics` | `list[str]` | Topics in chunk |
| `secondary_topics` | `list[str]` | Secondary topics |
| `keywords` | `list[str]` | Keywords found |
| `key_findings` | `list[str]` | Findings in chunk |
| `materials` | `list[dict]` | Materials mentioned |
| `methodology_notes` | `str` | Method notes |
| `error` | `Optional[str]` | Error if failed |

---

## Prompt Templates

Module: `hal9000.rlm.prompts`

### Available Prompts

| Prompt | Purpose |
|--------|---------|
| `SYSTEM_PROMPT` | System context for Claude |
| `TOPIC_EXTRACTION_PROMPT` | Extract topics and keywords |
| `MATERIALS_SCIENCE_PROMPT` | Materials-specific analysis |
| `FINDINGS_PROMPT` | Extract key findings |
| `METHODOLOGY_PROMPT` | Extract methods |
| `SUMMARY_PROMPT` | Generate summary |
| `AGGREGATION_PROMPT` | Aggregate chunk results |
| `ADAM_CONTEXT_PROMPT` | Generate ADAM context |
| `HYPOTHESIS_PROMPT` | Generate hypotheses |

### format_prompt

```python
def format_prompt(template: str, **kwargs) -> str
```

Format a prompt template with variables.

**Parameters**:
- `template`: Prompt template string
- `**kwargs`: Variables to substitute

**Returns**: Formatted prompt string

**Example**:
```python
from hal9000.rlm.prompts import TOPIC_EXTRACTION_PROMPT, format_prompt

prompt = format_prompt(
    TOPIC_EXTRACTION_PROMPT,
    text=chunk_text,
    domain="materials_science"
)
```

---

## RLM Processing Pipeline

### Overview

```
Document Text
     │
     ▼
┌─────────────┐
│   Chunking  │  Split at paragraph/sentence boundaries
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────┐
│  Process Each Chunk                  │
│  ├── Topic Extraction               │
│  ├── Materials Analysis (optional)  │
│  └── Findings Extraction            │
└──────┬──────────────────────────────┘
       │
       ▼
┌─────────────┐
│ Aggregation │  Merge results, rank by frequency
└──────┬──────┘
       │
       ▼
DocumentAnalysis
```

### Chunking Strategy

1. Target chunk size: 50,000 characters (~12,500 tokens)
2. Overlap: 1,000 characters for context continuity
3. Break points (in order of preference):
   - Double newlines (paragraph boundaries)
   - Single newlines
   - Sentence endings (. ? !)
   - Hard split at chunk_size + overlap

### Aggregation Logic

Results from all chunks are aggregated:

1. **Topics**: Ranked by frequency across chunks
2. **Keywords**: Deduplicated, ranked by occurrence
3. **Findings**: Collected and deduplicated
4. **Materials**: Merged, properties combined
5. **Summary**: Generated from aggregated data

---

## Usage Examples

### Basic Document Processing

```python
from hal9000.rlm import RLMProcessor

processor = RLMProcessor()

# Process document
analysis = processor.process_document(document_text)

# Access results
print(f"Title: {analysis.title}")
print(f"Summary: {analysis.summary}")
print(f"Topics: {', '.join(analysis.primary_topics)}")
print(f"Keywords: {', '.join(analysis.keywords[:10])}")
print(f"Chunks processed: {analysis.chunk_count}")
```

### Custom Configuration

```python
processor = RLMProcessor(
    model="claude-sonnet-4-20250514",  # or "claude-3-haiku-20240307"
    chunk_size=25000,        # Smaller chunks for more detail
    max_concurrent=10        # More parallel calls
)

analysis = processor.process_document(
    text,
    domain="chemistry",  # Different domain
    include_materials_analysis=False  # Skip materials
)
```

### Access Processing Statistics

```python
analysis = processor.process_document(text)

stats = analysis.processing_stats
print(f"Total chunks: {stats['total_chunks']}")
print(f"Successful: {stats['successful_chunks']}")
print(f"Failed: {stats['failed_chunks']}")
print(f"Total API calls: {stats['api_calls']}")
```

### Handle Large Documents

```python
# For very large documents, increase chunk size
processor = RLMProcessor(chunk_size=100000)

# Or process in batches
from hal9000.ingest import PDFProcessor

pdf_processor = PDFProcessor()
chunks = pdf_processor.chunk_text(text, chunk_size=50000)

print(f"Document split into {len(chunks)} chunks")

# Process with progress
for i, chunk in enumerate(chunks):
    print(f"Processing chunk {i+1}/{len(chunks)}")
    # RLMProcessor handles this internally
```

### Custom Prompts

```python
from hal9000.rlm.prompts import format_prompt

# Define custom prompt
CUSTOM_PROMPT = """
Analyze this text for electrochemistry concepts:
{text}

Return JSON:
{{
    "electrochemical_systems": [...],
    "reactions": [...],
    "potentials": [...]
}}
"""

# Use with processor
prompt = format_prompt(CUSTOM_PROMPT, text=chunk)
# response = processor._call_llm(prompt)
```
