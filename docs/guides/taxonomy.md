# Taxonomy Guide

HAL 9000 uses a hierarchical topic taxonomy to classify research papers. This guide explains the taxonomy system and how to customize it.

## Overview

The taxonomy is a tree structure of topics:

```
Materials Science
├── Magnetic Materials
│   ├── Rare-Earth Magnets
│   ├── Rare-Earth-Free Magnets
│   ├── Soft Magnetic Materials
│   └── Spintronics
├── Energy Storage
│   ├── Solid-State Batteries
│   ├── Lithium-Ion Batteries
│   └── ...
└── ...
```

Each document can be classified into multiple topics (multi-label classification).

## Default Taxonomy

HAL 9000 includes a comprehensive Materials Science taxonomy:

### Main Categories

| Category | Description | Subtopics |
|----------|-------------|-----------|
| **Magnetic Materials** | Magnetic properties and applications | 4 subtopics |
| **Energy Storage** | Batteries and capacitors | 4 subtopics |
| **Catalysis** | Catalytic processes | 3 subtopics |
| **Thin Films & Coatings** | Deposition technologies | 3 subtopics |
| **Nanomaterials** | Nanoscale materials | 3 subtopics |
| **Characterization** | Analysis techniques | 4 subtopics |
| **Computational Materials** | Simulation and ML | 3 subtopics |
| **Synthesis & Processing** | Manufacturing methods | 3 subtopics |

### Complete Taxonomy

See `config/materials_science_taxonomy.yaml` for the full taxonomy with 48+ topics.

## Topic Structure

Each topic has:

```yaml
- name: Rare-Earth-Free Magnets
  slug: rare-earth-free-magnets
  description: Permanent magnets without rare-earth elements
  keywords:
    - rare-earth-free
    - iron nitride
    - Fe16N2
    - MnAl
    - MnBi
    - alnico
    - ferrite magnet
  children:
    - name: Iron Nitrides
      slug: iron-nitrides
      ...
```

| Field | Description |
|-------|-------------|
| `name` | Display name |
| `slug` | URL-safe identifier |
| `description` | Topic description |
| `keywords` | Terms for matching |
| `children` | Subtopics |

## Classification Process

### 1. Keyword Matching

The classifier matches document keywords against topic keywords:

```python
# Document has keywords: ["Fe16N2", "permanent magnet", "iron nitride"]
# Topic "rare-earth-free-magnets" has keywords: ["Fe16N2", "iron nitride", ...]
# Match score: 2/3 keywords = 0.67
```

### 2. Confidence Scoring

- **Primary topics**: Confidence ≥ 0.6
- **Secondary topics**: Confidence ≥ 0.3

### 3. Hierarchy Traversal

When a subtopic matches, its parents are also included:

```
Document matches "rare-earth-free-magnets"
→ Also tagged with "magnetic-materials" (parent)
```

## Customizing the Taxonomy

### Edit the YAML File

Modify `config/materials_science_taxonomy.yaml`:

```yaml
taxonomy:
  name: Materials Science
  version: "1.1"  # Update version

  topics:
    # Add a new top-level topic
    - name: Polymers
      slug: polymers
      description: Polymer materials research
      keywords:
        - polymer
        - plastic
        - macromolecule
      children:
        - name: Conducting Polymers
          slug: conducting-polymers
          keywords:
            - conducting polymer
            - PEDOT
            - polyaniline
```

### Add Topics Programmatically

```python
from hal9000.categorize import Taxonomy, TopicNode

# Load existing taxonomy
taxonomy = Taxonomy.from_yaml("config/materials_science_taxonomy.yaml")

# Create new topic
new_topic = TopicNode(
    name="Perovskites",
    slug="perovskites",
    description="Perovskite materials for solar cells and LEDs",
    keywords=["perovskite", "ABX3", "methylammonium", "solar cell"]
)

# Add as child of existing topic
nanomaterials = taxonomy.get_topic("nanomaterials")
nanomaterials.add_child(new_topic)

# Save updated taxonomy
taxonomy.save("config/materials_science_taxonomy.yaml")
```

### Auto-Extension

When enabled, HAL 9000 creates new topics for unclassified documents:

```yaml
hal9000:
  taxonomy:
    auto_extend: true
```

Auto-created topics:
- Are marked with `auto_generated: true`
- Use keywords from the document
- Are added at the root level initially

## Creating a Custom Taxonomy

### For a Different Domain

Create a new YAML file:

```yaml
# config/chemistry_taxonomy.yaml
taxonomy:
  name: Chemistry
  version: "1.0"

  topics:
    - name: Organic Chemistry
      slug: organic-chemistry
      description: Carbon-based compounds
      keywords:
        - organic
        - synthesis
        - reaction
      children:
        - name: Natural Products
          slug: natural-products
          keywords:
            - natural product
            - alkaloid
            - terpene
        - name: Medicinal Chemistry
          slug: medicinal-chemistry
          keywords:
            - drug
            - pharmaceutical
            - medicinal

    - name: Inorganic Chemistry
      slug: inorganic-chemistry
      description: Non-carbon compounds
      keywords:
        - inorganic
        - metal complex
        - coordination
```

Configure HAL 9000 to use it:

```yaml
hal9000:
  taxonomy:
    base_file: ./config/chemistry_taxonomy.yaml
```

### Best Practices

1. **Hierarchical depth**: 2-3 levels work best
2. **Keyword coverage**: 5-10 keywords per topic
3. **Specificity**: More specific keywords rank higher
4. **Overlap handling**: Some overlap is OK (multi-label)

## Viewing Classification Results

### In CLI Output

```
⠋ Classifying document...
  Categories: magnetic-materials/rare-earth-free-magnets
```

### In JSON Output

```json
{
  "classification": {
    "topics": ["magnetic-materials", "rare-earth-free-magnets"],
    "folder_path": "magnetic-materials/rare-earth-free-magnets"
  }
}
```

### In Obsidian Notes

```yaml
---
topics:
  - Magnetic Materials
  - Rare-Earth-Free Magnets
---
```

## Taxonomy API

### Loading a Taxonomy

```python
from hal9000.categorize import Taxonomy

# From YAML file
taxonomy = Taxonomy.from_yaml("config/materials_science_taxonomy.yaml")

# Built-in Materials Science taxonomy
from hal9000.categorize.taxonomy import create_materials_science_taxonomy
taxonomy = create_materials_science_taxonomy()
```

### Querying Topics

```python
# Get topic by slug
topic = taxonomy.get_topic("rare-earth-free-magnets")

# Get all topics at a level
level_1_topics = taxonomy.get_topics_at_level(1)

# Search topics by keyword
matches = taxonomy.find_topics_by_keyword("battery")
```

### Topic Properties

```python
topic = taxonomy.get_topic("rare-earth-free-magnets")

print(topic.name)        # "Rare-Earth-Free Magnets"
print(topic.slug)        # "rare-earth-free-magnets"
print(topic.level)       # 1 (child of root)
print(topic.parent.name) # "Magnetic Materials"
print(topic.keywords)    # ["rare-earth-free", "iron nitride", ...]
print(topic.children)    # [] (no children)
print(topic.full_path)   # "magnetic-materials/rare-earth-free-magnets"
```

### Classification

```python
from hal9000.categorize import Classifier

classifier = Classifier(taxonomy)

# Classify a document analysis
result = classifier.classify(document_analysis)

print(result.primary_topics)      # [TopicNode, ...]
print(result.secondary_topics)    # [TopicNode, ...]
print(result.confidence_scores)   # {"topic-slug": 0.85, ...}
print(result.suggested_folder_path)  # "magnetic-materials/rare-earth-free-magnets"
```

## Folder Organization

### Automatic Organization

The `FolderOrganizer` creates folder structures matching the taxonomy:

```python
from hal9000.categorize import FolderOrganizer

organizer = FolderOrganizer(base_path=Path("./organized_papers"))

# Organize a document
organizer.organize_document(
    document_path=Path("paper.pdf"),
    classification=classification_result
)
```

Result:
```
organized_papers/
└── magnetic-materials/
    └── rare-earth-free-magnets/
        └── paper.pdf  (symlink or copy)
```

### Configuration

```yaml
hal9000:
  categorize:
    create_folders: true
    use_symlinks: true  # Link instead of copy
    folder_base: ./organized_papers
```

## Troubleshooting

### Documents Not Classified

**Symptoms**: Documents assigned to root or no topics

**Solutions**:
1. Check document has extractable text
2. Verify keywords match taxonomy
3. Lower confidence threshold
4. Enable auto-extend for new topics

### Wrong Classification

**Symptoms**: Documents in incorrect topics

**Solutions**:
1. Add more specific keywords to correct topic
2. Remove ambiguous keywords
3. Check for keyword conflicts between topics

### Missing Topics

**Symptoms**: Relevant topic not in taxonomy

**Solutions**:
1. Add topic to YAML file
2. Enable auto-extend
3. Create custom taxonomy

## Example: Extending for Batteries

Add detailed battery subtopics:

```yaml
- name: Energy Storage
  slug: energy-storage
  children:
    - name: Solid-State Batteries
      slug: solid-state-batteries
      keywords:
        - solid state battery
        - solid electrolyte
      children:
        # New detailed subtopics
        - name: Oxide Electrolytes
          slug: oxide-electrolytes
          keywords:
            - LLZO
            - garnet
            - NASICON
            - oxide electrolyte
        - name: Sulfide Electrolytes
          slug: sulfide-electrolytes
          keywords:
            - sulfide electrolyte
            - Li6PS5Cl
            - argyrodite
            - LGPS
        - name: Polymer Electrolytes
          slug: polymer-electrolytes
          keywords:
            - polymer electrolyte
            - PEO
            - gel polymer
```
