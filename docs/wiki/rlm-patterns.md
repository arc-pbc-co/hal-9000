# RLM Patterns Wiki

Understanding the Recursive Language Model patterns used in HAL 9000.

## Background

HAL 9000 implements patterns from the **Recursive Language Models (RLM)** paper for processing large documents with language models. These patterns address fundamental challenges in using LLMs for document analysis.

## The Problem

Traditional LLM approaches struggle with large documents:

1. **Context limits**: Models have finite context windows
2. **Information loss**: Important details get "lost" in long prompts
3. **Cost**: Processing entire documents is expensive
4. **Consistency**: Results vary based on what fits in context

## Core RLM Principles

### 1. Context as Environment

**Traditional approach** (problematic):
```python
# Stuffing entire document into prompt
response = llm.complete(f"""
Analyze this document:
{entire_document_text}

Extract topics and findings.
""")
```

**RLM approach** (HAL 9000):
```python
# Document as external environment
env = {"document": entire_document_text}

# Query specific parts programmatically
chunks = split_into_chunks(env["document"])
results = [analyze_chunk(chunk) for chunk in chunks]
```

The document is treated as an **external variable** that can be accessed programmatically, not as direct prompt content.

### 2. Recursive Decomposition

Large problems are broken into smaller sub-problems:

```
Document (100k chars)
        │
        ▼
┌───────┴───────┐
│   Chunking    │
└───────┬───────┘
        │
   ┌────┼────┐
   ▼    ▼    ▼
Chunk1 Chunk2 Chunk3  (sub-problems)
   │    │    │
   ▼    ▼    ▼
Result1 Result2 Result3
   │    │    │
   └────┼────┘
        ▼
┌───────┴───────┐
│  Aggregation  │
└───────┬───────┘
        ▼
  Final Result
```

Each chunk is processed independently, then results are aggregated.

### 3. Sub-LM Calls

Instead of one large LLM call, make multiple smaller calls:

```python
# Multiple specialized calls per chunk
topics = llm.complete(TOPIC_PROMPT.format(text=chunk))
materials = llm.complete(MATERIALS_PROMPT.format(text=chunk))
findings = llm.complete(FINDINGS_PROMPT.format(text=chunk))
```

Benefits:
- Smaller, focused prompts
- Better specialized outputs
- Easier error handling
- Parallel execution

### 4. REPL-Style Interaction

The system can programmatically query document content:

```python
class DocumentEnvironment:
    def __init__(self, text):
        self.text = text
        self.sections = self.extract_sections()

    def get_section(self, name):
        return self.sections.get(name, "")

    def search(self, query):
        # Return relevant passages
        return find_relevant_text(self.text, query)
```

## HAL 9000 Implementation

### Chunking Strategy

HAL 9000 uses intelligent chunking:

```python
def chunk_text(text, chunk_size=50000, overlap=1000):
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        # Find natural break point
        if end < len(text):
            # Prefer paragraph break
            para_break = text.rfind("\n\n", start, end)
            if para_break > start + chunk_size * 0.5:
                end = para_break

            # Fall back to sentence break
            else:
                sent_break = max(
                    text.rfind(". ", start, end),
                    text.rfind("? ", start, end),
                    text.rfind("! ", start, end)
                )
                if sent_break > start + chunk_size * 0.5:
                    end = sent_break + 1

        chunks.append(text[start:end])
        start = end - overlap  # Overlap for context

    return chunks
```

Key features:
- **Natural breaks**: Split at paragraphs or sentences
- **Overlap**: 1000 chars overlap maintains context
- **Configurable size**: Adjust based on needs

### Processing Pipeline

```python
class RLMProcessor:
    def process_document(self, text):
        # 1. Chunk the document
        chunks = self.chunk_text(text)

        # 2. Process each chunk
        chunk_results = []
        for i, chunk in enumerate(chunks):
            result = self.process_chunk(chunk, i)
            chunk_results.append(result)

        # 3. Aggregate results
        return self.aggregate_results(chunk_results)

    def process_chunk(self, chunk, index):
        # Multiple sub-LM calls
        topics = self.extract_topics(chunk)
        materials = self.extract_materials(chunk)
        findings = self.extract_findings(chunk)

        return ChunkResult(
            chunk_index=index,
            topics=topics,
            materials=materials,
            findings=findings
        )

    def aggregate_results(self, results):
        # Merge and rank by frequency
        all_topics = []
        for r in results:
            all_topics.extend(r.topics)

        ranked_topics = self.rank_by_frequency(all_topics)
        return DocumentAnalysis(topics=ranked_topics, ...)
```

### Aggregation Logic

Results are aggregated using frequency-based ranking:

```python
def aggregate_topics(chunk_results):
    # Collect all topics across chunks
    topic_counts = {}
    for result in chunk_results:
        for topic in result.primary_topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 2  # Primary weight
        for topic in result.secondary_topics:
            topic_counts[topic] = topic_counts.get(topic, 0) + 1  # Secondary weight

    # Rank by frequency
    ranked = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)

    # Split into primary/secondary
    primary = [t for t, c in ranked if c >= threshold]
    secondary = [t for t, c in ranked if c < threshold]

    return primary, secondary
```

## Benefits of RLM in HAL 9000

### 1. Handles Large Documents

- 100+ page papers processed successfully
- No context window limitations
- Consistent quality regardless of length

### 2. Improved Accuracy

- Focused prompts for each task
- Less information competing for attention
- Better extraction of specific details

### 3. Robustness

- Errors in one chunk don't fail entire document
- Redundancy through overlap
- Frequency ranking filters noise

### 4. Efficiency

- Parallel chunk processing possible
- Caching at chunk level
- Targeted re-processing

## Configuration

### Chunk Size

```yaml
processing:
  chunk_size: 50000  # Characters
```

| Size | Use Case |
|------|----------|
| 25,000 | Maximum detail, higher cost |
| 50,000 | Balanced (default) |
| 100,000 | Faster, may miss details |

### Overlap

```python
# In code
chunks = processor.chunk_text(text, overlap=1000)
```

Overlap ensures context continuity between chunks.

## Advanced Usage

### Custom Chunking

```python
from hal9000.ingest import PDFProcessor

processor = PDFProcessor()

# Section-aware chunking
sections = processor.extract_sections(text)
chunks = []
for section_name, section_text in sections.items():
    if len(section_text) > chunk_size:
        chunks.extend(processor.chunk_text(section_text))
    else:
        chunks.append(section_text)
```

### Custom Aggregation

```python
def custom_aggregate(chunk_results):
    # Weight by chunk position
    weights = [1.5 if i == 0 else 1.0 for i in range(len(chunk_results))]

    # First chunk (abstract/intro) weighted higher
    weighted_topics = []
    for result, weight in zip(chunk_results, weights):
        for topic in result.topics:
            weighted_topics.append((topic, weight))

    # Aggregate with weights
    ...
```

## Comparison with Other Approaches

| Approach | Pros | Cons |
|----------|------|------|
| **Full Context** | Simple | Context limits, expensive |
| **Summarization** | Compact | Loses details |
| **RAG** | Flexible | Requires embedding/search |
| **RLM (HAL 9000)** | Complete, accurate | More API calls |

## References

- Recursive Language Models paper
- HAL 9000 implementation: `hal9000/rlm/processor.py`
- Prompts: `hal9000/rlm/prompts.py`
