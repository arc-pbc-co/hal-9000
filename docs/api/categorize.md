# Categorize API Reference

Module: `hal9000.categorize`

Topic taxonomy and document classification.

## Classes

### Taxonomy

Hierarchical topic structure for classification.

```python
from hal9000.categorize import Taxonomy
from hal9000.categorize.taxonomy import create_materials_science_taxonomy

# Load built-in taxonomy
taxonomy = create_materials_science_taxonomy()

# Or load from YAML
taxonomy = Taxonomy.from_yaml("config/my_taxonomy.yaml")
```

#### Class Methods

##### from_yaml

```python
@classmethod
def from_yaml(cls, path: Path) -> "Taxonomy"
```

Load taxonomy from YAML file.

**Parameters**:
- `path`: Path to YAML file

**Returns**: `Taxonomy` instance

##### create_materials_science_taxonomy

```python
def create_materials_science_taxonomy() -> Taxonomy
```

Create the built-in Materials Science taxonomy.

**Returns**: Pre-configured `Taxonomy`

#### Instance Methods

##### get_topic

```python
def get_topic(self, slug: str) -> Optional[TopicNode]
```

Get topic by slug.

**Parameters**:
- `slug`: Topic slug (e.g., "rare-earth-free-magnets")

**Returns**: `TopicNode` or `None`

##### get_topics_at_level

```python
def get_topics_at_level(self, level: int) -> list[TopicNode]
```

Get all topics at a specific hierarchy level.

**Parameters**:
- `level`: Hierarchy level (0 = root)

**Returns**: List of topics at that level

##### find_topics_by_keyword

```python
def find_topics_by_keyword(self, keyword: str) -> list[TopicNode]
```

Find topics matching a keyword.

**Parameters**:
- `keyword`: Keyword to search

**Returns**: List of matching topics

##### add_topic

```python
def add_topic(
    self,
    name: str,
    parent_slug: Optional[str] = None,
    keywords: list[str] = None
) -> TopicNode
```

Add a new topic to the taxonomy.

**Parameters**:
- `name`: Topic display name
- `parent_slug`: Parent topic slug (None for root)
- `keywords`: Topic keywords

**Returns**: Created `TopicNode`

##### save

```python
def save(self, path: Path) -> None
```

Save taxonomy to YAML file.

**Parameters**:
- `path`: Output file path

---

### TopicNode

A node in the topic hierarchy.

```python
from hal9000.categorize import TopicNode

topic = TopicNode(
    name="Solid-State Batteries",
    slug="solid-state-batteries",
    description="All-solid-state battery technologies",
    keywords=["solid electrolyte", "LLZO", "sulfide"]
)
```

#### Constructor

```python
def __init__(
    self,
    name: str,
    slug: str,
    description: str = "",
    keywords: list[str] = None,
    parent: Optional["TopicNode"] = None
)
```

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Display name |
| `slug` | `str` | URL-safe identifier |
| `description` | `str` | Topic description |
| `keywords` | `list[str]` | Matching keywords |
| `parent` | `Optional[TopicNode]` | Parent topic |
| `children` | `list[TopicNode]` | Child topics |
| `level` | `int` | Hierarchy level (computed) |
| `auto_generated` | `bool` | Auto-created flag |

#### Properties

##### full_path

```python
@property
def full_path(self) -> str
```

Get full path from root (e.g., "magnetic-materials/rare-earth-free-magnets").

##### ancestors

```python
@property
def ancestors(self) -> list[TopicNode]
```

Get list of ancestor topics.

#### Methods

##### add_child

```python
def add_child(self, child: "TopicNode") -> None
```

Add a child topic.

##### matches_keywords

```python
def matches_keywords(self, keywords: list[str]) -> float
```

Calculate match score against keywords.

**Parameters**:
- `keywords`: Keywords to match

**Returns**: Match score (0.0 to 1.0)

---

### Classifier

Classify documents using the taxonomy.

```python
from hal9000.categorize import Classifier

classifier = Classifier(
    taxonomy,
    confidence_threshold=0.6,
    auto_extend=True
)
```

#### Constructor

```python
def __init__(
    self,
    taxonomy: Taxonomy,
    confidence_threshold: float = 0.6,
    auto_extend: bool = True
)
```

**Parameters**:
- `taxonomy`: Taxonomy to use
- `confidence_threshold`: Min confidence for primary topics
- `auto_extend`: Create new topics for unmatched documents

#### Methods

##### classify

```python
def classify(self, analysis: DocumentAnalysis) -> ClassificationResult
```

Classify a document based on its analysis.

**Parameters**:
- `analysis`: DocumentAnalysis from RLM processing

**Returns**: `ClassificationResult`

**Example**:
```python
result = classifier.classify(analysis)

print(f"Primary topics: {[t.name for t in result.primary_topics]}")
print(f"Secondary topics: {[t.name for t in result.secondary_topics]}")
print(f"Folder path: {result.suggested_folder_path}")
```

##### classify_keywords

```python
def classify_keywords(self, keywords: list[str]) -> ClassificationResult
```

Classify based on keywords only.

**Parameters**:
- `keywords`: List of keywords

**Returns**: `ClassificationResult`

---

### ClassificationResult

Result of document classification.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `primary_topics` | `list[TopicNode]` | Main topics (confidence ≥ threshold) |
| `secondary_topics` | `list[TopicNode]` | Secondary topics |
| `all_topics` | `list[TopicNode]` | All matched topics |
| `confidence_scores` | `dict[str, float]` | Scores by topic slug |
| `suggested_folder_path` | `str` | Recommended folder path |
| `auto_extended` | `bool` | Whether new topics were created |
| `topic_slugs` | `list[str]` | All topic slugs |

---

### FolderOrganizer

Organize documents into folders by topic.

```python
from hal9000.categorize import FolderOrganizer

organizer = FolderOrganizer(
    base_path=Path("./organized_papers"),
    use_symlinks=True
)
```

#### Constructor

```python
def __init__(
    self,
    base_path: Path,
    use_symlinks: bool = True
)
```

**Parameters**:
- `base_path`: Root folder for organization
- `use_symlinks`: Create symlinks instead of copies

#### Methods

##### organize_document

```python
def organize_document(
    self,
    document_path: Path,
    classification: ClassificationResult
) -> Path
```

Organize a document into the folder structure.

**Parameters**:
- `document_path`: Path to document
- `classification`: Classification result

**Returns**: Path to organized document

##### create_folder_structure

```python
def create_folder_structure(self, taxonomy: Taxonomy) -> None
```

Create full folder structure from taxonomy.

**Parameters**:
- `taxonomy`: Taxonomy to create folders for

---

## Usage Examples

### Basic Classification

```python
from hal9000.categorize import Classifier
from hal9000.categorize.taxonomy import create_materials_science_taxonomy

# Load taxonomy and create classifier
taxonomy = create_materials_science_taxonomy()
classifier = Classifier(taxonomy)

# Classify a document
result = classifier.classify(document_analysis)

# Access results
for topic in result.primary_topics:
    score = result.confidence_scores[topic.slug]
    print(f"{topic.name}: {score:.2f}")

print(f"Suggested path: {result.suggested_folder_path}")
```

### Custom Taxonomy

```python
from hal9000.categorize import Taxonomy, TopicNode

# Create taxonomy
taxonomy = Taxonomy(name="My Research")

# Add topics
energy = taxonomy.add_topic("Energy", keywords=["energy", "power"])
solar = taxonomy.add_topic(
    "Solar Energy",
    parent_slug="energy",
    keywords=["solar", "photovoltaic", "PV"]
)

# Save
taxonomy.save(Path("my_taxonomy.yaml"))
```

### Organize Files

```python
from pathlib import Path
from hal9000.categorize import FolderOrganizer

organizer = FolderOrganizer(Path("./papers_by_topic"))

# Create folder structure
organizer.create_folder_structure(taxonomy)

# Organize a document
organized_path = organizer.organize_document(
    Path("paper.pdf"),
    classification_result
)

print(f"Organized to: {organized_path}")
```

### Query Taxonomy

```python
# Find topics by keyword
battery_topics = taxonomy.find_topics_by_keyword("battery")
for topic in battery_topics:
    print(f"{topic.name} ({topic.full_path})")

# Get topic hierarchy
topic = taxonomy.get_topic("solid-state-batteries")
print(f"Parent: {topic.parent.name}")
print(f"Level: {topic.level}")
print(f"Keywords: {topic.keywords}")
```
