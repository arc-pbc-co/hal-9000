# ADAM Platform Integration Guide

HAL 9000 generates research contexts compatible with the [ADAM Platform](https://github.com/arc-pbc-co/adam-platform) for autonomous materials discovery and experimental design.

## Overview

The ADAM (Autonomous Discovery of Advanced Materials) Platform uses AI to design and execute materials science experiments. HAL 9000 provides the literature-based research context that informs ADAM's experimental decisions.

### Integration Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Research PDFs  │────▶│    HAL 9000     │────▶│  ADAM Platform  │
│                 │     │  (Context Gen)  │     │ (Experiments)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

1. **HAL 9000** processes research papers
2. **Generates** structured research context (JSON)
3. **ADAM** uses context for experiment design

## Generating ADAM Contexts

### Basic Usage

```bash
hal batch ~/Papers --context-name "my_research"
```

This:
1. Processes all PDFs in the directory
2. Aggregates findings across papers
3. Builds a knowledge graph
4. Generates experiment suggestions
5. Exports ADAM-compatible JSON

### Options

```bash
hal batch [PATHS] [OPTIONS]

Options:
  -n, --limit INTEGER       Maximum PDFs to process (default: 10)
  -c, --context-name TEXT   Name for ADAM context (default: research_context)
  -o, --output-dir PATH     Output directory (default: ./adam_contexts)
```

### Examples

```bash
# Process 50 papers on battery research
hal batch ~/Papers/Batteries --limit 50 --context-name "solid_state_batteries"

# Process from multiple directories
hal batch ~/Papers/Magnets ~/Papers/Synthesis --limit 30 --context-name "magnetic_materials"

# Custom output location
hal batch ~/Papers --output-dir ~/ADAM/contexts --context-name "catalysis_review"
```

## Context Structure

### Full JSON Schema

```json
{
  "context_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "name": "solid_state_batteries",
  "description": "Research context for solid-state electrolytes. Based on analysis of 50 papers. Key materials: LLZO, LGPS, Li3PS4. Includes 5 experiment suggestions.",
  "research_domain": "materials_science",
  "topic_focus": "solid-state-batteries",

  "literature_summary": {
    "papers_analyzed": 50,
    "key_findings": [
      "LLZO garnet electrolytes achieve ionic conductivity of 1 mS/cm at room temperature",
      "Sulfide electrolytes show higher conductivity but poor air stability",
      "Interface resistance remains primary challenge for practical applications"
    ],
    "methodologies": [
      "Solid-state synthesis via ball milling and sintering",
      "Electrochemical impedance spectroscopy for conductivity",
      "XRD and Raman for phase identification"
    ],
    "gaps_identified": [
      "Limited understanding of grain boundary resistance",
      "Lack of scalable synthesis methods",
      "Need for better cathode-electrolyte interfaces"
    ],
    "open_questions": [
      "Can sulfide electrolytes be stabilized in air?",
      "What dopants optimize LLZO conductivity?"
    ]
  },

  "experiment_suggestions": [
    {
      "hypothesis": "Al-doped LLZO will show improved ionic conductivity compared to undoped LLZO",
      "methodology": "Synthesize Li7-xAlxLa3Zr2O12 (x = 0, 0.1, 0.2, 0.3) via solid-state reaction. Characterize with XRD, SEM, EIS.",
      "variables": {
        "independent": ["Al doping level (x)"],
        "dependent": ["Ionic conductivity", "Activation energy"],
        "controlled": ["Sintering temperature", "Particle size"]
      },
      "expected_outcomes": [
        "Optimal conductivity at x = 0.2-0.25",
        "Cubic phase stabilization with Al doping"
      ],
      "rationale": "Literature shows Al stabilizes cubic LLZO and creates Li vacancies for improved conduction.",
      "priority": "high",
      "confidence_score": 0.85
    }
  ],

  "knowledge_graph": {
    "nodes": [
      {
        "id": "n1",
        "label": "LLZO",
        "type": "material",
        "properties": {
          "formula": "Li7La3Zr2O12",
          "conductivity": "1 mS/cm"
        }
      },
      {
        "id": "n2",
        "label": "Solid-State Batteries Review 2024",
        "type": "paper",
        "properties": {}
      },
      {
        "id": "n3",
        "label": "ionic conductivity",
        "type": "concept",
        "properties": {}
      }
    ],
    "edges": [
      {
        "source": "n2",
        "target": "n1",
        "relationship": "studies",
        "weight": 1.0
      },
      {
        "source": "n2",
        "target": "n3",
        "relationship": "discusses",
        "weight": 1.0
      }
    ]
  },

  "materials_of_interest": [
    "LLZO",
    "LGPS",
    "Li3PS4",
    "NASICON",
    "polymer electrolyte"
  ],

  "recommended_characterization": [
    "XRD",
    "EIS",
    "SEM",
    "Raman",
    "DSC"
  ],

  "source_documents": [
    "Solid-State Batteries Review 2024",
    "LLZO Synthesis Optimization",
    "Sulfide Electrolyte Stability Study"
  ],

  "metadata": {
    "created_at": "2024-01-15T10:30:00",
    "updated_at": "2024-01-15T10:30:00",
    "version": "1.0",
    "generator": "HAL9000"
  }
}
```

### Key Sections

#### Literature Summary

Aggregated findings from all processed papers:

| Field | Description |
|-------|-------------|
| `papers_analyzed` | Number of papers processed |
| `key_findings` | Important results from literature |
| `methodologies` | Common experimental methods |
| `gaps_identified` | Research gaps for exploration |
| `open_questions` | Unanswered questions |

#### Experiment Suggestions

AI-generated experiment proposals:

| Field | Description |
|-------|-------------|
| `hypothesis` | Testable hypothesis |
| `methodology` | Proposed experimental approach |
| `variables` | Independent, dependent, controlled |
| `expected_outcomes` | Predicted results |
| `rationale` | Literature-based justification |
| `priority` | high/medium/low |
| `confidence_score` | 0.0-1.0 confidence |

#### Knowledge Graph

Network representation of papers, materials, and concepts:

- **Nodes**: Papers, materials, concepts, methods
- **Edges**: Relationships (studies, discusses, cites, related)
- **Weights**: Connection strength

## Configuration

### ADAM Settings

```yaml
hal9000:
  adam:
    enabled: true
    output_path: ./adam_contexts
    default_domain: materials_science
    api_url: null      # Future: ADAM Platform API
    api_key: null      # Future: ADAM Platform API key
```

### Research Domains

The `default_domain` affects prompt tuning:

| Domain | Focus |
|--------|-------|
| `materials_science` | Materials synthesis, characterization |
| `chemistry` | Chemical reactions, synthesis |
| `physics` | Physical properties, phenomena |

## Using Contexts with ADAM

### Manual Import

1. Generate context with HAL 9000
2. Copy JSON file to ADAM Platform input
3. Load context in ADAM's experiment designer

### API Integration (Future)

```yaml
hal9000:
  adam:
    api_url: https://api.adam-platform.com
    api_key: your-api-key
```

When configured, HAL 9000 will:
- Push contexts directly to ADAM
- Receive experiment results
- Update literature analysis

## Experiment Suggestion Quality

### Confidence Scores

| Score | Meaning |
|-------|---------|
| 0.8-1.0 | Strong literature support, clear hypothesis |
| 0.6-0.8 | Good support, some uncertainty |
| 0.4-0.6 | Moderate support, needs validation |
| 0.0-0.4 | Limited support, exploratory |

### Improving Suggestions

1. **More papers**: Process more relevant literature
2. **Focused topics**: Use specific directories by topic
3. **Recent papers**: Prioritize recent publications

```bash
# Better: Focused context
hal batch ~/Papers/LLZO_Electrolytes --limit 30 --context-name "llzo_optimization"

# Less ideal: Mixed topics
hal batch ~/Papers --limit 30 --context-name "general"
```

## Knowledge Graph Usage

### Visualization

Export the graph for visualization tools:

```python
import json
import networkx as nx

# Load context
with open("adam_context_xxx.json") as f:
    context = json.load(f)

# Build NetworkX graph
G = nx.DiGraph()
for node in context["knowledge_graph"]["nodes"]:
    G.add_node(node["id"], **node)
for edge in context["knowledge_graph"]["edges"]:
    G.add_edge(edge["source"], edge["target"], **edge)

# Export to various formats
nx.write_gexf(G, "knowledge_graph.gexf")  # For Gephi
nx.write_graphml(G, "knowledge_graph.graphml")  # For yEd
```

### Analysis

```python
# Find most connected materials
materials = [n for n in G.nodes if G.nodes[n]["type"] == "material"]
centrality = nx.degree_centrality(G)
top_materials = sorted(materials, key=lambda n: centrality[n], reverse=True)
```

## Programmatic Access

### Generate Context in Code

```python
from hal9000.adam import ContextBuilder
from hal9000.rlm import RLMProcessor

# Initialize
processor = RLMProcessor()
builder = ContextBuilder(processor=processor)

# Process documents
analyses = []
for pdf_path in pdf_files:
    content = pdf_processor.extract_text(pdf_path)
    analysis = processor.process_document(content.full_text)
    analyses.append(analysis)

# Build context
context = builder.build_context(
    analyses,
    name="my_context",
    topic_focus="solid-state-batteries",
    generate_experiments=True
)

# Save
context.save(Path("./adam_contexts/my_context.json"))
```

### Access Context Data

```python
from pathlib import Path
import json

# Load context
with open("adam_context_xxx.json") as f:
    data = json.load(f)

# Access fields
print(f"Papers analyzed: {data['literature_summary']['papers_analyzed']}")
print(f"Key findings: {len(data['literature_summary']['key_findings'])}")
print(f"Experiments suggested: {len(data['experiment_suggestions'])}")

# Get experiment hypotheses
for exp in data["experiment_suggestions"]:
    print(f"- {exp['hypothesis']} (confidence: {exp['confidence_score']})")
```

## Best Practices

### 1. Organize Papers by Topic

```
Papers/
├── Solid-State-Batteries/
│   ├── LLZO/
│   ├── Sulfides/
│   └── Polymer/
├── Magnetic-Materials/
│   ├── Rare-Earth/
│   └── Rare-Earth-Free/
└── Catalysis/
```

### 2. Generate Focused Contexts

```bash
# Generate per-topic contexts
hal batch ~/Papers/LLZO --context-name "llzo_research"
hal batch ~/Papers/Sulfides --context-name "sulfide_research"
```

### 3. Update Regularly

Re-run batch processing as new papers are added:

```bash
# Weekly update
hal batch ~/Papers/Solid-State-Batteries --context-name "batteries_$(date +%Y%m%d)"
```

### 4. Review Experiment Suggestions

Before using in ADAM:
- Verify hypotheses make scientific sense
- Check methodology feasibility
- Validate against recent literature

## Troubleshooting

### Empty Experiment Suggestions

**Cause**: Not enough literature or too diverse topics

**Solution**:
- Process more papers (increase `--limit`)
- Use more focused paper collections
- Check API key is valid

### Low Confidence Scores

**Cause**: Insufficient supporting literature

**Solution**:
- Add more papers on the specific topic
- Ensure papers are relevant to the topic focus

### Missing Materials

**Cause**: Materials not recognized in text

**Solution**:
- Check PDFs are text-based (not scanned images)
- Verify materials are mentioned in abstracts/text
- Consider adding OCR support for scanned papers

### Knowledge Graph Too Sparse

**Cause**: Few connections between papers

**Solution**:
- Process papers from related research areas
- Include review papers that cite multiple sources
- Increase the number of processed papers
