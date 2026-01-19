# Database API Reference

Module: `hal9000.db`

SQLAlchemy database models and utilities.

## Functions

### init_db

```python
def init_db(database_url: str) -> tuple[Engine, sessionmaker]
```

Initialize database connection and create tables.

**Parameters**:
- `database_url`: SQLAlchemy database URL

**Returns**: Tuple of (Engine, SessionLocal factory)

**Example**:
```python
from hal9000.db.models import init_db

engine, SessionLocal = init_db("sqlite:///./hal9000.db")
session = SessionLocal()
```

### get_session

```python
def get_session(database_url: str) -> Session
```

Convenience function to get a new session.

**Parameters**:
- `database_url`: SQLAlchemy database URL

**Returns**: New Session instance

---

## Models

### Document

Represents a processed document.

```python
from hal9000.db.models import Document

doc = Document(
    source_path="/path/to/paper.pdf",
    source_type="local",
    title="Paper Title",
    authors='["Author 1", "Author 2"]',
    year=2024
)
session.add(doc)
session.commit()
```

#### Columns

| Column | Type | Description |
|--------|------|-------------|
| `id` | `Integer` | Primary key |
| `source_path` | `String` | Original file path |
| `source_type` | `String` | Source type (local/gdrive) |
| `file_hash` | `String` | SHA-256 hash |
| `title` | `String` | Document title |
| `authors` | `Text` | Authors (JSON array) |
| `year` | `Integer` | Publication year |
| `doi` | `String` | DOI identifier |
| `arxiv_id` | `String` | arXiv ID |
| `abstract` | `Text` | Abstract text |
| `summary` | `Text` | AI-generated summary |
| `key_concepts` | `Text` | Key concepts (JSON) |
| `methodology` | `Text` | Methodology summary |
| `findings` | `Text` | Key findings (JSON) |
| `full_text` | `Text` | Full text (truncated) |
| `page_count` | `Integer` | Number of pages |
| `status` | `String` | Processing status |
| `note_path` | `String` | Obsidian note path |
| `adam_context_id` | `String` | Related ADAM context |
| `created_at` | `DateTime` | Creation time |
| `updated_at` | `DateTime` | Last update time |
| `processed_at` | `DateTime` | Processing completion time |

#### Relationships

| Relationship | Type | Description |
|--------------|------|-------------|
| `topics` | `list[Topic]` | Associated topics |
| `related_documents` | `list[Document]` | Related documents |

#### Status Values

| Status | Description |
|--------|-------------|
| `pending` | Not yet processed |
| `processing` | Currently processing |
| `completed` | Successfully processed |
| `failed` | Processing failed |

---

### Topic

Represents a topic in the taxonomy.

```python
from hal9000.db.models import Topic

topic = Topic(
    name="Rare-Earth-Free Magnets",
    slug="rare-earth-free-magnets",
    description="Permanent magnets without rare-earth elements",
    keywords='["Fe16N2", "MnAl"]',
    level=1
)
```

#### Columns

| Column | Type | Description |
|--------|------|-------------|
| `id` | `Integer` | Primary key |
| `name` | `String` | Display name |
| `slug` | `String` | URL-safe identifier |
| `description` | `Text` | Topic description |
| `keywords` | `Text` | Keywords (JSON array) |
| `parent_id` | `Integer` | Parent topic FK |
| `level` | `Integer` | Hierarchy level |
| `auto_generated` | `Boolean` | Auto-created flag |
| `created_at` | `DateTime` | Creation time |

#### Relationships

| Relationship | Type | Description |
|--------------|------|-------------|
| `parent` | `Topic` | Parent topic |
| `children` | `list[Topic]` | Child topics |
| `documents` | `list[Document]` | Documents in topic |

---

### ProcessingJob

Track document processing jobs.

```python
from hal9000.db.models import ProcessingJob

job = ProcessingJob(
    document_id=1,
    status="processing",
    total_chunks=5
)
```

#### Columns

| Column | Type | Description |
|--------|------|-------------|
| `id` | `Integer` | Primary key |
| `document_id` | `Integer` | Document FK |
| `status` | `String` | Job status |
| `total_chunks` | `Integer` | Total chunks |
| `processed_chunks` | `Integer` | Completed chunks |
| `result` | `Text` | Result (JSON) |
| `error` | `Text` | Error message |
| `created_at` | `DateTime` | Creation time |
| `started_at` | `DateTime` | Start time |
| `completed_at` | `DateTime` | Completion time |

---

### ADAMContext

Store generated ADAM contexts.

```python
from hal9000.db.models import ADAMContext

ctx = ADAMContext(
    name="battery_research",
    research_domain="materials_science",
    topic_focus="solid-state-batteries"
)
```

#### Columns

| Column | Type | Description |
|--------|------|-------------|
| `id` | `String` | UUID primary key |
| `name` | `String` | Context name |
| `research_domain` | `String` | Research domain |
| `topic_focus` | `String` | Topic focus |
| `literature_summary` | `Text` | Summary (JSON) |
| `experiment_suggestions` | `Text` | Suggestions (JSON) |
| `knowledge_graph` | `Text` | Graph data (JSON) |
| `output_path` | `String` | Export file path |
| `created_at` | `DateTime` | Creation time |
| `updated_at` | `DateTime` | Update time |

---

## Association Tables

### document_topics

Many-to-many relationship between documents and topics.

| Column | Type | Description |
|--------|------|-------------|
| `document_id` | `Integer` | Document FK |
| `topic_id` | `Integer` | Topic FK |
| `confidence` | `Float` | Classification confidence |
| `is_primary` | `Boolean` | Primary topic flag |

### document_relations

Self-referential many-to-many for document relationships.

| Column | Type | Description |
|--------|------|-------------|
| `source_id` | `Integer` | Source document FK |
| `target_id` | `Integer` | Target document FK |
| `relationship_type` | `String` | Relationship type |
| `confidence` | `Float` | Confidence score |

#### Relationship Types

| Type | Description |
|------|-------------|
| `cites` | Source cites target |
| `related` | Documents are related |
| `extends` | Source extends target |

---

## Usage Examples

### Basic CRUD Operations

```python
from hal9000.db.models import init_db, Document, Topic

# Initialize
engine, SessionLocal = init_db("sqlite:///./hal9000.db")
session = SessionLocal()

# Create document
doc = Document(
    source_path="/path/to/paper.pdf",
    source_type="local",
    title="My Paper",
    status="completed"
)
session.add(doc)
session.commit()

# Query documents
docs = session.query(Document).filter(
    Document.status == "completed"
).all()

# Update
doc.summary = "New summary"
session.commit()

# Delete
session.delete(doc)
session.commit()

session.close()
```

### Query with Relationships

```python
# Get document with topics
doc = session.query(Document).filter(
    Document.id == 1
).first()

for topic in doc.topics:
    print(f"Topic: {topic.name}")

# Query documents by topic
topic = session.query(Topic).filter(
    Topic.slug == "solid-state-batteries"
).first()

for doc in topic.documents:
    print(f"Document: {doc.title}")
```

### Topic Hierarchy

```python
# Get topic with children
topic = session.query(Topic).filter(
    Topic.slug == "energy-storage"
).first()

print(f"Parent: {topic.name}")
for child in topic.children:
    print(f"  Child: {child.name}")

# Get parent
if topic.parent:
    print(f"Parent of {topic.name}: {topic.parent.name}")
```

### Document Relations

```python
from sqlalchemy import and_

# Add citation relationship
from hal9000.db.models import document_relations

session.execute(
    document_relations.insert().values(
        source_id=1,
        target_id=2,
        relationship_type="cites",
        confidence=0.95
    )
)
session.commit()

# Query citations
stmt = session.query(Document).join(
    document_relations,
    Document.id == document_relations.c.target_id
).filter(
    document_relations.c.source_id == 1,
    document_relations.c.relationship_type == "cites"
)

for cited_doc in stmt.all():
    print(f"Cites: {cited_doc.title}")
```

### Batch Operations

```python
# Bulk insert
documents = [
    Document(source_path=f"/path/{i}.pdf", source_type="local")
    for i in range(100)
]
session.bulk_save_objects(documents)
session.commit()

# Bulk update
session.query(Document).filter(
    Document.status == "pending"
).update({"status": "processing"})
session.commit()
```

### Statistics Queries

```python
from sqlalchemy import func

# Count by status
counts = session.query(
    Document.status,
    func.count(Document.id)
).group_by(Document.status).all()

for status, count in counts:
    print(f"{status}: {count}")

# Documents per topic
topic_counts = session.query(
    Topic.name,
    func.count(Document.id)
).join(Topic.documents).group_by(Topic.name).all()
```
