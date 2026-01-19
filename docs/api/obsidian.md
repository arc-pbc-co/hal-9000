# Obsidian API Reference

Module: `hal9000.obsidian`

Obsidian vault management and note generation.

## Classes

### VaultManager

Manage an Obsidian vault.

```python
from hal9000.obsidian import VaultManager

vault = VaultManager(Path("~/ObsidianVault/Research"))
vault.initialize()
```

#### Constructor

```python
def __init__(
    self,
    vault_path: Path,
    config: Optional[VaultConfig] = None
)
```

**Parameters**:
- `vault_path`: Path to vault directory
- `config`: Optional vault configuration

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `vault_path` | `Path` | Vault root directory |
| `config` | `VaultConfig` | Vault configuration |

#### Methods

##### initialize

```python
def initialize(self) -> None
```

Initialize vault structure and configuration.

Creates:
- Folder structure (Papers, Concepts, Topics, Canvas, Templates)
- Obsidian configuration files
- Default templates
- Index note

**Example**:
```python
vault = VaultManager(Path("~/MyVault"))
vault.initialize()
# Vault is now ready for use
```

##### get_paper_path

```python
def get_paper_path(self, title: str) -> Path
```

Get path for a paper note.

**Parameters**:
- `title`: Paper title

**Returns**: Full path to paper note

##### get_concept_path

```python
def get_concept_path(self, concept: str) -> Path
```

Get path for a concept note.

**Parameters**:
- `concept`: Concept name

**Returns**: Full path to concept note

##### get_topic_path

```python
def get_topic_path(self, slug: str) -> Path
```

Get path for a topic note.

**Parameters**:
- `slug`: Topic slug

**Returns**: Full path to topic note

##### create_wikilink

```python
def create_wikilink(
    self,
    target: str,
    display: Optional[str] = None
) -> str
```

Create an Obsidian wikilink.

**Parameters**:
- `target`: Link target
- `display`: Optional display text

**Returns**: Wikilink string (e.g., `[[target|display]]`)

**Example**:
```python
link = vault.create_wikilink("rare-earth-free-magnets", "Rare-Earth-Free Magnets")
# Returns: [[rare-earth-free-magnets|Rare-Earth-Free Magnets]]
```

##### get_vault_stats

```python
def get_vault_stats(self) -> dict
```

Get vault statistics.

**Returns**: Dict with:
- `papers`: Number of paper notes
- `concepts`: Number of concept notes
- `topics`: Number of topic notes

---

### VaultConfig

Configuration for vault structure.

```python
from hal9000.obsidian import VaultConfig

config = VaultConfig(
    papers_folder="Papers",
    concepts_folder="Concepts",
    topics_folder="Topics"
)
```

#### Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `papers_folder` | `str` | `"Papers"` | Paper notes folder |
| `concepts_folder` | `str` | `"Concepts"` | Concept notes folder |
| `topics_folder` | `str` | `"Topics"` | Topic notes folder |
| `canvas_folder` | `str` | `"Canvas"` | Canvas files folder |
| `templates_folder` | `str` | `"Templates"` | Templates folder |

---

### NoteGenerator

Generate Obsidian notes from document analysis.

```python
from hal9000.obsidian import NoteGenerator

generator = NoteGenerator(vault)
note = generator.generate_paper_note(document, metadata, analysis, classification)
generator.write_note(note)
```

#### Constructor

```python
def __init__(self, vault: VaultManager)
```

**Parameters**:
- `vault`: VaultManager instance

#### Methods

##### generate_paper_note

```python
def generate_paper_note(
    self,
    document: Document,
    metadata: DocumentMetadata,
    analysis: DocumentAnalysis,
    classification: ClassificationResult
) -> NoteContent
```

Generate a paper note.

**Parameters**:
- `document`: Database document record
- `metadata`: Extracted metadata
- `analysis`: RLM analysis
- `classification`: Topic classification

**Returns**: `NoteContent` ready to write

**Example**:
```python
note = generator.generate_paper_note(
    document, metadata, analysis, classification
)
print(note.content[:500])  # Preview
generator.write_note(note)
```

##### generate_concept_note

```python
def generate_concept_note(
    self,
    concept_name: str,
    definition: Optional[str] = None,
    related_papers: Optional[list[str]] = None,
    related_concepts: Optional[list[str]] = None
) -> NoteContent
```

Generate a concept note.

**Parameters**:
- `concept_name`: Name of the concept
- `definition`: Optional definition
- `related_papers`: Paper titles discussing this concept
- `related_concepts`: Related concept names

**Returns**: `NoteContent`

##### generate_topic_note

```python
def generate_topic_note(
    self,
    topic_name: str,
    topic_slug: str,
    description: Optional[str] = None,
    parent_topic: Optional[str] = None,
    subtopics: Optional[list[str]] = None,
    papers: Optional[list[str]] = None
) -> NoteContent
```

Generate a topic note.

**Parameters**:
- `topic_name`: Display name
- `topic_slug`: URL-safe slug
- `description`: Topic description
- `parent_topic`: Parent topic name
- `subtopics`: Child topic names
- `papers`: Paper titles in this topic

**Returns**: `NoteContent`

##### write_note

```python
def write_note(
    self,
    note: NoteContent,
    overwrite: bool = False
) -> bool
```

Write a note to the vault.

**Parameters**:
- `note`: Note to write
- `overwrite`: Overwrite existing notes

**Returns**: `True` if written successfully

##### update_note_links

```python
def update_note_links(
    self,
    note_path: Path,
    links_to_add: list[str],
    section: str = "Related Papers"
) -> bool
```

Add links to an existing note.

**Parameters**:
- `note_path`: Path to note
- `links_to_add`: Wikilinks to add
- `section`: Section to add links to

**Returns**: `True` if updated successfully

---

### NoteContent

Dataclass for generated note content.

#### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `path` | `Path` | Full path to note file |
| `content` | `str` | Note content (markdown) |
| `frontmatter` | `dict` | YAML frontmatter data |

---

## Usage Examples

### Initialize and Use Vault

```python
from pathlib import Path
from hal9000.obsidian import VaultManager, NoteGenerator

# Initialize vault
vault = VaultManager(Path("~/ObsidianVault/Research"))
vault.initialize()

# Create note generator
generator = NoteGenerator(vault)

# Generate and write paper note
note = generator.generate_paper_note(
    document, metadata, analysis, classification
)
generator.write_note(note)

# Check stats
stats = vault.get_vault_stats()
print(f"Papers: {stats['papers']}")
```

### Create Concept Notes

```python
# Generate concept note
concept_note = generator.generate_concept_note(
    concept_name="Fe16N2",
    definition="Iron nitride with giant saturation magnetization",
    related_papers=[
        "Novel Fe16N2 Synthesis",
        "Iron Nitride Magnets Review"
    ],
    related_concepts=["iron nitride", "permanent magnet"]
)

generator.write_note(concept_note)
```

### Create Topic Hierarchy

```python
# Generate parent topic
parent_note = generator.generate_topic_note(
    topic_name="Magnetic Materials",
    topic_slug="magnetic-materials",
    description="Research on magnetic properties",
    subtopics=["Rare-Earth Magnets", "Rare-Earth-Free Magnets"]
)

# Generate child topic
child_note = generator.generate_topic_note(
    topic_name="Rare-Earth-Free Magnets",
    topic_slug="rare-earth-free-magnets",
    description="Permanent magnets without rare-earth elements",
    parent_topic="Magnetic Materials",
    papers=["Novel Fe16N2 Synthesis", "MnAl Magnets Study"]
)

generator.write_note(parent_note)
generator.write_note(child_note)
```

### Update Existing Notes

```python
# Add related papers to a concept note
generator.update_note_links(
    vault.get_concept_path("Fe16N2"),
    links_to_add=["[[New Fe16N2 Paper]]"],
    section="Papers Discussing This Concept"
)
```

### Custom Note Structure

```python
# Access frontmatter for custom processing
note = generator.generate_paper_note(...)

# Modify frontmatter
note.frontmatter["custom_field"] = "value"

# Regenerate content with modified frontmatter
from hal9000.obsidian.notes import NoteGenerator
content = generator._format_frontmatter(note.frontmatter)
content += note.content.split("---\n", 2)[2]  # Keep body

# Write modified note
with open(note.path, "w") as f:
    f.write(content)
```
