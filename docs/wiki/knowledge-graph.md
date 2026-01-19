# Knowledge Graph Wiki

Understanding the knowledge graph structure in HAL 9000.

## Overview

HAL 9000 builds knowledge graphs to represent relationships between papers, concepts, materials, and methods. These graphs are exported in ADAM context files and can be visualized in Obsidian.

## Graph Structure

### Nodes

Nodes represent entities in the research domain:

```json
{
  "id": "n1",
  "label": "LLZO",
  "type": "material",
  "properties": {
    "formula": "Li7La3Zr2O12",
    "conductivity": "1 mS/cm"
  }
}
```

#### Node Types

| Type | Description | Example |
|------|-------------|---------|
| `paper` | Research paper | "Solid-State Battery Review 2024" |
| `concept` | Abstract concept | "ionic conductivity" |
| `material` | Physical material | "LLZO", "NdFeB" |
| `method` | Technique/method | "spark plasma sintering" |

### Edges

Edges represent relationships between nodes:

```json
{
  "source": "paper-1",
  "target": "material-1",
  "relationship": "studies",
  "weight": 1.0
}
```

#### Relationship Types

| Relationship | Meaning | Example |
|--------------|---------|---------|
| `studies` | Paper studies material | Paper → Material |
| `discusses` | Paper discusses concept | Paper → Concept |
| `uses` | Paper uses method | Paper → Method |
| `related` | General relationship | Concept → Concept |
| `cites` | Paper cites paper | Paper → Paper |
| `synthesizes` | Method produces material | Method → Material |

## Building the Graph

### From Document Analysis

```python
from hal9000.adam import ContextBuilder

builder = ContextBuilder()

# Build graph from analyses
nodes, edges = builder._build_knowledge_graph(analyses)
```

### Graph Construction Logic

```python
def _build_knowledge_graph(self, analyses):
    nodes = []
    edges = []
    node_ids = {}

    def get_or_create_node(label, node_type):
        key = f"{node_type}:{label.lower()}"
        if key not in node_ids:
            node_id = generate_id()
            node_ids[key] = node_id
            nodes.append(KnowledgeGraphNode(
                id=node_id,
                label=label,
                type=node_type
            ))
        return node_ids[key]

    for analysis in analyses:
        # Create paper node
        paper_id = get_or_create_node(analysis.title, "paper")

        # Connect to topics (concepts)
        for topic in analysis.primary_topics[:5]:
            topic_id = get_or_create_node(topic, "concept")
            edges.append(KnowledgeGraphEdge(
                source=paper_id,
                target=topic_id,
                relationship="discusses"
            ))

        # Connect to materials
        for material in analysis.materials[:5]:
            mat_name = material.get("name", str(material))
            mat_id = get_or_create_node(mat_name, "material")
            edges.append(KnowledgeGraphEdge(
                source=paper_id,
                target=mat_id,
                relationship="studies"
            ))

    return nodes, edges
```

## Visualizing the Graph

### In Obsidian

The knowledge graph is implicitly represented through wikilinks:

```markdown
# Paper Note

## Key Concepts
- [[ionic conductivity]]
- [[solid electrolyte]]

## Materials
- [[LLZO]]
- [[LGPS]]

## Related Papers
- [[Other Paper 1]]
- [[Other Paper 2]]
```

Obsidian's Graph View shows these connections visually.

### Export to NetworkX

```python
import networkx as nx
import json

# Load ADAM context
with open("adam_context.json") as f:
    context = json.load(f)

# Build NetworkX graph
G = nx.DiGraph()

# Add nodes
for node in context["knowledge_graph"]["nodes"]:
    G.add_node(
        node["id"],
        label=node["label"],
        type=node["type"],
        **node.get("properties", {})
    )

# Add edges
for edge in context["knowledge_graph"]["edges"]:
    G.add_edge(
        edge["source"],
        edge["target"],
        relationship=edge["relationship"],
        weight=edge.get("weight", 1.0)
    )

# Export
nx.write_gexf(G, "knowledge_graph.gexf")  # For Gephi
nx.write_graphml(G, "knowledge_graph.graphml")  # For yEd
```

### Export to vis.js

```python
import json

def export_to_visjs(context):
    nodes = []
    edges = []

    # Color by type
    colors = {
        "paper": "#97C2FC",
        "material": "#FB7E81",
        "concept": "#7BE141",
        "method": "#FFA807"
    }

    for node in context["knowledge_graph"]["nodes"]:
        nodes.append({
            "id": node["id"],
            "label": node["label"],
            "color": colors.get(node["type"], "#CCCCCC"),
            "title": f"{node['type']}: {node['label']}"
        })

    for edge in context["knowledge_graph"]["edges"]:
        edges.append({
            "from": edge["source"],
            "to": edge["target"],
            "label": edge["relationship"],
            "arrows": "to"
        })

    return {"nodes": nodes, "edges": edges}

# Save for vis.js
data = export_to_visjs(context)
with open("graph_visjs.json", "w") as f:
    json.dump(data, f)
```

## Graph Analysis

### Centrality Analysis

```python
import networkx as nx

# Degree centrality - most connected nodes
centrality = nx.degree_centrality(G)
top_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:10]

print("Most central nodes:")
for node_id, score in top_nodes:
    label = G.nodes[node_id]["label"]
    print(f"  {label}: {score:.3f}")
```

### Find Key Materials

```python
# Materials connected to most papers
material_nodes = [n for n in G.nodes if G.nodes[n]["type"] == "material"]

material_connections = {}
for mat in material_nodes:
    papers = [n for n in G.predecessors(mat)
              if G.nodes[n]["type"] == "paper"]
    material_connections[mat] = len(papers)

top_materials = sorted(
    material_connections.items(),
    key=lambda x: x[1],
    reverse=True
)

print("Most studied materials:")
for mat_id, count in top_materials[:10]:
    label = G.nodes[mat_id]["label"]
    print(f"  {label}: {count} papers")
```

### Community Detection

```python
from networkx.algorithms import community

# Convert to undirected for community detection
G_undirected = G.to_undirected()

# Find communities
communities = community.louvain_communities(G_undirected)

print(f"Found {len(communities)} communities")
for i, comm in enumerate(communities):
    labels = [G.nodes[n]["label"] for n in list(comm)[:5]]
    print(f"Community {i}: {', '.join(labels)}...")
```

## Graph in ADAM Context

### Structure

```json
{
  "knowledge_graph": {
    "nodes": [
      {
        "id": "n1",
        "label": "LLZO",
        "type": "material",
        "properties": {
          "formula": "Li7La3Zr2O12"
        }
      },
      {
        "id": "n2",
        "label": "Solid-State Battery Review",
        "type": "paper",
        "properties": {}
      }
    ],
    "edges": [
      {
        "source": "n2",
        "target": "n1",
        "relationship": "studies",
        "weight": 1.0
      }
    ]
  }
}
```

### Usage in ADAM

The knowledge graph helps ADAM Platform:

1. **Identify relationships** between materials and properties
2. **Find research gaps** - materials not well connected
3. **Suggest experiments** based on graph structure
4. **Track provenance** - which papers support which claims

## Best Practices

### 1. Consistent Naming

Use consistent labels for the same entity:
- "LLZO" not "Li7La3Zr2O12" and "LLZO" mixed
- "solid electrolyte" not "solid-electrolyte" and "solid electrolyte"

### 2. Appropriate Granularity

- Too fine: Every chemical formula as separate node
- Too coarse: "battery materials" as single node
- Right level: Specific materials (LLZO, LGPS) with properties

### 3. Weight Meaningful Edges

```python
# Weight by mention frequency
edge_weight = mention_count / total_mentions

# Or by confidence
edge_weight = analysis_confidence
```

### 4. Include Properties

```python
node = KnowledgeGraphNode(
    id="mat-1",
    label="LLZO",
    type="material",
    properties={
        "formula": "Li7La3Zr2O12",
        "ionic_conductivity": "1 mS/cm",
        "stability": "air-stable"
    }
)
```

## Limitations

1. **Extraction quality** depends on RLM analysis
2. **No semantic similarity** - purely structural
3. **Static snapshot** - doesn't track temporal evolution
4. **Single domain** - Materials Science focused
