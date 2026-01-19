# ADAM API Reference

Module: `hal9000.adam`

ADAM Platform research context generation.

## Classes

### ContextBuilder

Build ADAM research contexts from document analyses.

```python
from hal9000.adam import ContextBuilder
from hal9000.rlm import RLMProcessor

processor = RLMProcessor()
builder = ContextBuilder(processor=processor)

context = builder.build_context(analyses, name="my_research")
```

#### Constructor

```python
def __init__(
    self,
    processor: Optional[RLMProcessor] = None,
    default_domain: str = "materials_science"
)
```

**Parameters**:
- `processor`: RLMProcessor for experiment generation (creates new if None)
- `default_domain`: Default research domain

#### Methods

##### build_context

```python
def build_context(
    self,
    analyses: list[DocumentAnalysis],
    name: str,
    topic_focus: Optional[str] = None,
    generate_experiments: bool = True
) -> ADAMResearchContext
```

Build a research context from document analyses.

**Parameters**:
- `analyses`: List of DocumentAnalysis objects
- `name`: Context name
- `topic_focus`: Specific topic focus (auto-inferred if None)
- `generate_experiments`: Generate experiment suggestions

**Returns**: `ADAMResearchContext`

**Example**:
```python
context = builder.build_context(
    analyses,
    name="solid_state_batteries",
    topic_focus="LLZO electrolytes",
    generate_experiments=True
)

print(f"Papers analyzed: {context.literature_summary.papers_analyzed}")
print(f"Experiments: {len(context.experiment_suggestions)}")
```

##### save_context

```python
def save_context(
    self,
    context: ADAMResearchContext,
    output_dir: Path
) -> Path
```

Save context to JSON file.

**Parameters**:
- `context`: Context to save
- `output_dir`: Output directory

**Returns**: Path to saved file

**Example**:
```python
output_path = builder.save_context(context, Path("./contexts"))
print(f"Saved to: {output_path}")
```

---

### ADAMResearchContext

Complete research context for ADAM Platform.

```python
from hal9000.adam import ADAMResearchContext
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `context_id` | `str` | UUID identifier |
| `name` | `str` | Context name |
| `description` | `str` | Generated description |
| `research_domain` | `str` | Research domain |
| `topic_focus` | `str` | Main topic focus |
| `literature_summary` | `LiteratureSummary` | Aggregated findings |
| `experiment_suggestions` | `list[ExperimentSuggestion]` | Suggested experiments |
| `nodes` | `list[KnowledgeGraphNode]` | Graph nodes |
| `edges` | `list[KnowledgeGraphEdge]` | Graph edges |
| `materials_of_interest` | `list[str]` | Key materials |
| `recommended_characterization` | `list[str]` | Recommended techniques |
| `source_documents` | `list[str]` | Source paper titles |
| `created_at` | `str` | Creation timestamp |
| `updated_at` | `str` | Update timestamp |

#### Methods

##### to_dict

```python
def to_dict(self) -> dict
```

Convert to dictionary for JSON export.

##### to_json

```python
def to_json(self, indent: int = 2) -> str
```

Convert to JSON string.

##### save

```python
def save(self, path: Path) -> None
```

Save to JSON file.

---

### LiteratureSummary

Summary of analyzed literature.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `papers_analyzed` | `int` | Number of papers |
| `key_findings` | `list[str]` | Important findings |
| `methodologies` | `list[str]` | Common methods |
| `gaps_identified` | `list[str]` | Research gaps |
| `open_questions` | `list[str]` | Open questions |

---

### ExperimentSuggestion

AI-generated experiment suggestion.

```python
from hal9000.adam import ExperimentSuggestion

suggestion = ExperimentSuggestion(
    hypothesis="Al-doped LLZO shows improved conductivity",
    methodology="Solid-state synthesis with varying Al content",
    variables={
        "independent": ["Al doping level"],
        "dependent": ["Ionic conductivity"],
        "controlled": ["Sintering temperature"]
    },
    expected_outcomes=["Optimal conductivity at x=0.2"],
    rationale="Literature shows Al stabilizes cubic phase",
    priority="high",
    confidence_score=0.85
)
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `hypothesis` | `str` | Testable hypothesis |
| `methodology` | `str` | Proposed methods |
| `variables` | `dict` | Experimental variables |
| `expected_outcomes` | `list[str]` | Predicted results |
| `rationale` | `str` | Literature-based justification |
| `priority` | `str` | Priority level (high/medium/low) |
| `confidence_score` | `float` | Confidence (0.0-1.0) |

---

### KnowledgeGraphNode

Node in the knowledge graph.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `str` | Unique identifier |
| `label` | `str` | Display label |
| `type` | `str` | Node type (paper/concept/material/method) |
| `properties` | `dict` | Additional properties |

---

### KnowledgeGraphEdge

Edge in the knowledge graph.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `source` | `str` | Source node ID |
| `target` | `str` | Target node ID |
| `relationship` | `str` | Relationship type |
| `weight` | `float` | Edge weight (default 1.0) |

---

## Usage Examples

### Build Context from Analyses

```python
from hal9000.adam import ContextBuilder
from hal9000.rlm import RLMProcessor
from hal9000.ingest import PDFProcessor

# Process documents
processor = PDFProcessor()
rlm = RLMProcessor()

analyses = []
for pdf_path in pdf_files:
    content = processor.extract_text(pdf_path)
    analysis = rlm.process_document(content.full_text)
    analyses.append(analysis)

# Build context
builder = ContextBuilder(processor=rlm)
context = builder.build_context(
    analyses,
    name="battery_research",
    generate_experiments=True
)

# Save
context.save(Path("./context.json"))
```

### Access Context Data

```python
# Literature summary
summary = context.literature_summary
print(f"Analyzed {summary.papers_analyzed} papers")
print(f"Key findings: {len(summary.key_findings)}")

for finding in summary.key_findings[:5]:
    print(f"  - {finding}")

# Experiment suggestions
for exp in context.experiment_suggestions:
    print(f"\nHypothesis: {exp.hypothesis}")
    print(f"Confidence: {exp.confidence_score}")
    print(f"Priority: {exp.priority}")
```

### Work with Knowledge Graph

```python
# Access graph data
nodes = context.nodes
edges = context.edges

# Find material nodes
materials = [n for n in nodes if n.type == "material"]
print(f"Materials: {[m.label for m in materials]}")

# Find paper relationships
paper_edges = [e for e in edges if e.relationship == "studies"]
print(f"Paper-material relationships: {len(paper_edges)}")

# Export to NetworkX
import networkx as nx

G = nx.DiGraph()
for node in nodes:
    G.add_node(node.id, label=node.label, type=node.type)
for edge in edges:
    G.add_edge(edge.source, edge.target, relationship=edge.relationship)
```

### Custom Context Generation

```python
from hal9000.adam import (
    ADAMResearchContext,
    LiteratureSummary,
    ExperimentSuggestion,
    KnowledgeGraphNode,
    KnowledgeGraphEdge
)

# Create custom context
context = ADAMResearchContext(
    name="custom_research",
    research_domain="chemistry",
    topic_focus="organic synthesis"
)

# Add literature summary
context.literature_summary = LiteratureSummary(
    papers_analyzed=10,
    key_findings=["Finding 1", "Finding 2"],
    methodologies=["Method 1"],
    gaps_identified=["Gap 1"]
)

# Add custom experiment
context.experiment_suggestions.append(
    ExperimentSuggestion(
        hypothesis="My hypothesis",
        methodology="My method",
        priority="high",
        confidence_score=0.7
    )
)

# Add graph nodes
context.nodes.append(
    KnowledgeGraphNode(
        id="n1",
        label="My Material",
        type="material"
    )
)

# Save
context.save(Path("./custom_context.json"))
```

### Load and Modify Context

```python
import json
from pathlib import Path

# Load existing context
with open("context.json") as f:
    data = json.load(f)

# Modify
data["name"] = "updated_name"
data["experiment_suggestions"].append({
    "hypothesis": "New experiment",
    "methodology": "New method",
    "priority": "medium",
    "confidence_score": 0.6
})

# Save
with open("context_updated.json", "w") as f:
    json.dump(data, f, indent=2)
```
