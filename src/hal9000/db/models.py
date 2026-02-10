"""Database models for HAL 9000."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


# Association table for document-topic many-to-many relationship
document_topics = Table(
    "document_topics",
    Base.metadata,
    Column("document_id", String(36), ForeignKey("documents.id"), primary_key=True),
    Column("topic_id", String(36), ForeignKey("topics.id"), primary_key=True),
    Column("confidence", Float, default=1.0),
    Column("created_at", DateTime, default=utc_now),
)


# Association table for document relationships (citations, related papers)
document_relations = Table(
    "document_relations",
    Base.metadata,
    Column("source_id", String(36), ForeignKey("documents.id"), primary_key=True),
    Column("target_id", String(36), ForeignKey("documents.id"), primary_key=True),
    Column("relation_type", String(50)),  # "cites", "related", "extends", etc.
    Column("confidence", Float, default=1.0),
    Column("created_at", DateTime, default=utc_now),
)


class Document(Base):
    """Represents a processed research document (PDF)."""

    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Source information
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="local")  # local, gdrive, etc.
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # SHA-256

    # Metadata
    title: Mapped[Optional[str]] = mapped_column(String(512))
    authors: Mapped[Optional[str]] = mapped_column(Text)  # JSON list
    year: Mapped[Optional[int]] = mapped_column(Integer)
    doi: Mapped[Optional[str]] = mapped_column(String(256))
    abstract: Mapped[Optional[str]] = mapped_column(Text)

    # Processing results
    summary: Mapped[Optional[str]] = mapped_column(Text)
    key_concepts: Mapped[Optional[str]] = mapped_column(Text)  # JSON list
    methodology: Mapped[Optional[str]] = mapped_column(Text)
    findings: Mapped[Optional[str]] = mapped_column(Text)

    # Content
    full_text: Mapped[Optional[str]] = mapped_column(Text)
    page_count: Mapped[Optional[int]] = mapped_column(Integer)

    # Processing status
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, processing, completed, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Obsidian integration
    obsidian_note_path: Mapped[Optional[str]] = mapped_column(String(1024))

    # ADAM context
    adam_context_id: Mapped[Optional[str]] = mapped_column(String(36))

    # Acquisition metadata
    acquisition_source: Mapped[Optional[str]] = mapped_column(String(50))  # Provider name
    acquisition_query: Mapped[Optional[str]] = mapped_column(String(512))  # Original search topic

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    topics: Mapped[list["Topic"]] = relationship(
        "Topic", secondary=document_topics, back_populates="documents"
    )

    def __repr__(self) -> str:
        return f"<Document(id={self.id}, title={self.title})>"


class Topic(Base):
    """Represents a topic in the taxonomy."""

    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Topic hierarchy
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    parent_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("topics.id"))

    # Metadata
    level: Mapped[int] = mapped_column(Integer, default=0)  # Depth in taxonomy tree
    is_auto_generated: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    # Relationships
    documents: Mapped[list["Document"]] = relationship(
        "Document", secondary=document_topics, back_populates="topics"
    )
    parent: Mapped[Optional["Topic"]] = relationship(
        "Topic", remote_side=[id], backref="children"
    )

    def __repr__(self) -> str:
        return f"<Topic(id={self.id}, name={self.name})>"


class ProcessingJob(Base):
    """Tracks document processing jobs."""

    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False)

    # Job details
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ingest, process, categorize, etc.
    status: Mapped[str] = mapped_column(String(50), default="pending")

    # Progress tracking
    total_chunks: Mapped[Optional[int]] = mapped_column(Integer)
    processed_chunks: Mapped[int] = mapped_column(Integer, default=0)

    # Results and errors
    result: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    def __repr__(self) -> str:
        return f"<ProcessingJob(id={self.id}, type={self.job_type}, status={self.status})>"


class ADAMContext(Base):
    """Represents an ADAM research context."""

    __tablename__ = "adam_contexts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Context metadata
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    research_domain: Mapped[str] = mapped_column(String(256), default="materials_science")
    topic_focus: Mapped[Optional[str]] = mapped_column(String(256))

    # Content (JSON)
    literature_summary: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    experiment_suggestions: Mapped[Optional[str]] = mapped_column(Text)  # JSON
    knowledge_graph: Mapped[Optional[str]] = mapped_column(Text)  # JSON

    # Statistics
    papers_analyzed: Mapped[int] = mapped_column(Integer, default=0)

    # Export
    output_path: Mapped[Optional[str]] = mapped_column(String(1024))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    def __repr__(self) -> str:
        return f"<ADAMContext(id={self.id}, name={self.name})>"


class GatewaySession(Base):
    """Persisted gateway session for session continuity across restarts."""

    __tablename__ = "gateway_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Session metadata
    channel: Mapped[str] = mapped_column(String(50), default="websocket")
    user_id: Mapped[Optional[str]] = mapped_column(String(256))

    # Session state (JSON fields)
    context: Mapped[Optional[str]] = mapped_column(Text)  # JSON: ResearchContext
    conversation_history: Mapped[Optional[str]] = mapped_column(Text)  # JSON list
    active_tools: Mapped[Optional[str]] = mapped_column(Text)  # JSON list

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_active: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    def __repr__(self) -> str:
        return f"<GatewaySession(id={self.id}, channel={self.channel})>"


class AcquisitionRecord(Base):
    """Tracks paper acquisition attempts and status."""

    __tablename__ = "acquisition_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Search metadata
    search_topic: Mapped[str] = mapped_column(String(512), nullable=False)
    search_query: Mapped[Optional[str]] = mapped_column(Text)  # Expanded query used
    session_id: Mapped[Optional[str]] = mapped_column(String(36))  # Links records from same session
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    # Paper identification
    title: Mapped[Optional[str]] = mapped_column(String(512))
    external_id: Mapped[Optional[str]] = mapped_column(String(256))  # Provider's ID
    doi: Mapped[Optional[str]] = mapped_column(String(256))
    arxiv_id: Mapped[Optional[str]] = mapped_column(String(50))

    # Download status
    status: Mapped[str] = mapped_column(String(50), default="pending")
    # Status values: pending, searching, downloading, downloaded, processing, completed, failed, duplicate

    source_url: Mapped[Optional[str]] = mapped_column(String(1024))
    local_path: Mapped[Optional[str]] = mapped_column(String(1024))
    file_hash: Mapped[Optional[str]] = mapped_column(String(64))

    # Relevance scoring
    relevance_score: Mapped[Optional[float]] = mapped_column(Float)

    # Link to processed document
    document_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("documents.id"))

    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationship
    document: Mapped[Optional["Document"]] = relationship("Document", backref="acquisition_record")

    def __repr__(self) -> str:
        return f"<AcquisitionRecord(id={self.id}, topic={self.search_topic[:30]}, status={self.status})>"


# Convenience alias for backwards compatibility
DocumentTopic = document_topics


def normalize_database_url(database_url: str) -> str:
    """Normalize database URLs for local filesystem compatibility.

    For sqlite paths, expand `~` and normalize relative paths to absolute paths.
    """
    url = make_url(database_url)
    if url.drivername != "sqlite":
        return database_url

    database = url.database
    if not database or database == ":memory:":
        return database_url

    normalized_path = Path(database).expanduser()
    if not normalized_path.is_absolute():
        normalized_path = normalized_path.resolve()

    normalized_url = url.set(database=str(normalized_path))
    return normalized_url.render_as_string(hide_password=False)


def init_db(database_url: str = "sqlite:///./hal9000.db") -> tuple:
    """Initialize the database and return engine and session factory."""
    from sqlalchemy.orm import sessionmaker

    normalized_url = normalize_database_url(database_url)
    engine = create_engine(normalized_url, echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    return engine, session_factory


def get_session(database_url: str = "sqlite:///./hal9000.db") -> Session:
    """Get a new database session."""
    _, session_factory = init_db(database_url)
    return session_factory()  # type: ignore[no-any-return]
