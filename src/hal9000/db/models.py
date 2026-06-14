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
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
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
    __table_args__ = (
        Index("ix_documents_source_identifier", "source_identifier"),
        Index("ix_documents_version_group_key", "version_group_key"),
        Index("ix_documents_normalized_doi", "normalized_doi"),
    )

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

    # Corpus hardening metadata
    source_identifier: Mapped[Optional[str]] = mapped_column(String(512))
    source_version: Mapped[Optional[str]] = mapped_column(String(100), default="v1")
    version_group_key: Mapped[Optional[str]] = mapped_column(String(512))
    is_current_version: Mapped[bool] = mapped_column(Boolean, default=True)
    supersedes_document_id: Mapped[Optional[str]] = mapped_column(String(36))
    refresh_policy: Mapped[str] = mapped_column(String(50), default="manual")
    refresh_interval_days: Mapped[Optional[int]] = mapped_column(Integer)
    last_refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    next_refresh_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    normalized_doi: Mapped[Optional[str]] = mapped_column(String(256))
    citation_key: Mapped[Optional[str]] = mapped_column(String(256))
    normalized_citation: Mapped[Optional[str]] = mapped_column(Text)
    source_quality_score: Mapped[Optional[float]] = mapped_column(Float)
    source_quality_label: Mapped[Optional[str]] = mapped_column(String(50))
    source_quality_json: Mapped[Optional[str]] = mapped_column(Text)

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


class ResearchProject(Base):
    """A shared research workspace for teams, programs, runs, and outputs."""

    __tablename__ = "research_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner: Mapped[Optional[str]] = mapped_column(String(256))
    visibility: Mapped[str] = mapped_column(String(50), default="firm")
    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    programs: Mapped[list["ResearchProgramRecord"]] = relationship(
        "ResearchProgramRecord", back_populates="project"
    )
    runs: Mapped[list["ResearchRun"]] = relationship(
        "ResearchRun", back_populates="project"
    )
    outputs: Mapped[list["ResearchOutput"]] = relationship(
        "ResearchOutput", back_populates="project"
    )
    permissions: Mapped[list["ProjectPermission"]] = relationship(
        "ProjectPermission", back_populates="project"
    )

    def __repr__(self) -> str:
        return f"<ResearchProject(id={self.id}, slug={self.slug})>"


class UserAccount(Base):
    """A firm user known to the HAL research OS."""

    __tablename__ = "user_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(256))
    external_subject: Mapped[Optional[str]] = mapped_column(String(512), unique=True)
    global_role: Mapped[str] = mapped_column(String(50), default="member")
    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    team_memberships: Mapped[list["TeamMembership"]] = relationship(
        "TeamMembership", back_populates="user"
    )

    def __repr__(self) -> str:
        return f"<UserAccount(id={self.id}, email={self.email})>"


class Team(Base):
    """A firm team that can receive project permissions."""

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    slug: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    memberships: Mapped[list["TeamMembership"]] = relationship(
        "TeamMembership", back_populates="team"
    )

    def __repr__(self) -> str:
        return f"<Team(id={self.id}, slug={self.slug})>"


class TeamMembership(Base):
    """A user's membership in a firm team."""

    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_memberships_team_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(String(36), ForeignKey("teams.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user_accounts.id"), nullable=False)

    role: Mapped[str] = mapped_column(String(50), default="member")
    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    team: Mapped["Team"] = relationship("Team", back_populates="memberships")
    user: Mapped["UserAccount"] = relationship("UserAccount", back_populates="team_memberships")

    def __repr__(self) -> str:
        return f"<TeamMembership(id={self.id}, role={self.role})>"


class ProjectPermission(Base):
    """A user or team permission grant on a research project."""

    __tablename__ = "project_permissions"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "principal_type",
            "principal_id",
            name="uq_project_permissions_principal",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_projects.id"), nullable=False
    )

    principal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    principal_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    granted_by: Mapped[Optional[str]] = mapped_column(String(256))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    project: Mapped["ResearchProject"] = relationship(
        "ResearchProject", back_populates="permissions"
    )

    def __repr__(self) -> str:
        return f"<ProjectPermission(id={self.id}, principal={self.principal_type}:{self.principal_id})>"


class ResearchProgramRecord(Base):
    """A persisted autoresearch-style research program."""

    __tablename__ = "research_programs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_projects.id")
    )

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="0.1")
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[Optional[str]] = mapped_column(String(256))
    domain: Mapped[str] = mapped_column(String(256), default="materials_science")
    tags: Mapped[Optional[str]] = mapped_column(Text)  # JSON list
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, nullable=False)
    source_path: Mapped[Optional[str]] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    project: Mapped[Optional["ResearchProject"]] = relationship(
        "ResearchProject", back_populates="programs"
    )
    runs: Mapped[list["ResearchRun"]] = relationship(
        "ResearchRun", back_populates="program"
    )

    def __repr__(self) -> str:
        return f"<ResearchProgramRecord(id={self.id}, name={self.name})>"


class ResearchRun(Base):
    """A bounded execution of a research program."""

    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_projects.id")
    )
    program_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_programs.id")
    )

    status: Mapped[str] = mapped_column(String(50), default="queued")
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    initiated_by: Mapped[Optional[str]] = mapped_column(String(256))
    budget_json: Mapped[Optional[str]] = mapped_column(Text)
    tool_policy_json: Mapped[Optional[str]] = mapped_column(Text)
    run_log_path: Mapped[Optional[str]] = mapped_column(String(1024))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    project: Mapped[Optional["ResearchProject"]] = relationship(
        "ResearchProject", back_populates="runs"
    )
    program: Mapped[Optional["ResearchProgramRecord"]] = relationship(
        "ResearchProgramRecord", back_populates="runs"
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="run"
    )
    claims: Mapped[list["ExtractedClaim"]] = relationship(
        "ExtractedClaim", back_populates="run"
    )
    outputs: Mapped[list["ResearchOutput"]] = relationship(
        "ResearchOutput", back_populates="run"
    )
    events: Mapped[list["ResearchRunEvent"]] = relationship(
        "ResearchRunEvent",
        back_populates="run",
        order_by="ResearchRunEvent.sequence",
    )
    tool_calls: Mapped[list["ResearchToolCall"]] = relationship(
        "ResearchToolCall",
        back_populates="run",
        order_by="ResearchToolCall.sequence",
    )

    def __repr__(self) -> str:
        return f"<ResearchRun(id={self.id}, status={self.status})>"


class ResearchRunEvent(Base):
    """Append-only event log entry for a research run."""

    __tablename__ = "research_run_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"), nullable=False)

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text)
    actor: Mapped[Optional[str]] = mapped_column(String(256))
    payload_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    run: Mapped["ResearchRun"] = relationship(
        "ResearchRun", back_populates="events"
    )

    def __repr__(self) -> str:
        return f"<ResearchRunEvent(id={self.id}, run_id={self.run_id}, sequence={self.sequence})>"


class ResearchToolCall(Base):
    """Durable accounting record for a worker tool invocation."""

    __tablename__ = "research_tool_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_runs.id"), nullable=False)

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="started")
    actor: Mapped[Optional[str]] = mapped_column(String(256))
    input_json: Mapped[Optional[str]] = mapped_column(Text)
    output_json: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    run: Mapped["ResearchRun"] = relationship("ResearchRun", back_populates="tool_calls")

    def __repr__(self) -> str:
        return f"<ResearchToolCall(id={self.id}, tool={self.tool_name}, status={self.status})>"


class DocumentChunk(Base):
    """A canonical chunk of a document used for retrieval and extraction."""

    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False)
    run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("research_runs.id"))

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    char_start: Mapped[Optional[int]] = mapped_column(Integer)
    char_end: Mapped[Optional[int]] = mapped_column(Integer)
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_ref: Mapped[Optional[str]] = mapped_column(String(1024))
    extraction_metadata: Mapped[Optional[str]] = mapped_column(Text)  # JSON

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    document: Mapped["Document"] = relationship("Document", backref="chunks")
    run: Mapped[Optional["ResearchRun"]] = relationship(
        "ResearchRun", back_populates="chunks"
    )
    claims: Mapped[list["ExtractedClaim"]] = relationship(
        "ExtractedClaim", back_populates="chunk"
    )
    embeddings: Mapped[list["ChunkEmbedding"]] = relationship(
        "ChunkEmbedding",
        back_populates="chunk",
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, index={self.chunk_index})>"


class ChunkEmbedding(Base):
    """Embedding metadata and portable vector payload for a document chunk."""

    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "chunk_id",
            "embedding_provider",
            "embedding_model",
            name="uq_chunk_embeddings_chunk_provider_model",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    chunk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_chunks.id"), nullable=False
    )

    embedding_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(256), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    vector_uri: Mapped[Optional[str]] = mapped_column(String(1024))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    chunk: Mapped["DocumentChunk"] = relationship("DocumentChunk", back_populates="embeddings")

    def __repr__(self) -> str:
        return (
            "<ChunkEmbedding("
            f"id={self.id}, chunk_id={self.chunk_id}, provider={self.embedding_provider}, "
            f"model={self.embedding_model}, dim={self.embedding_dim}"
            ")>"
        )


class ExtractedClaim(Base):
    """A source-backed claim extracted from a document or research run."""

    __tablename__ = "extracted_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("documents.id"), nullable=False)
    chunk_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("document_chunks.id"))
    run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("research_runs.id"))

    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(100), default="finding")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_text: Mapped[Optional[str]] = mapped_column(Text)
    normalized_subject: Mapped[Optional[str]] = mapped_column(String(512))
    normalized_predicate: Mapped[Optional[str]] = mapped_column(String(256))
    normalized_object: Mapped[Optional[str]] = mapped_column(String(512))
    provenance_json: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="staged")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    document: Mapped["Document"] = relationship("Document", backref="claims")
    chunk: Mapped[Optional["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="claims"
    )
    run: Mapped[Optional["ResearchRun"]] = relationship(
        "ResearchRun", back_populates="claims"
    )
    evidence_links: Mapped[list["EvidenceLink"]] = relationship(
        "EvidenceLink", back_populates="claim"
    )

    def __repr__(self) -> str:
        return f"<ExtractedClaim(id={self.id}, type={self.claim_type}, status={self.status})>"


class EvidenceLink(Base):
    """A precise evidence pointer supporting an extracted claim."""

    __tablename__ = "evidence_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    claim_id: Mapped[str] = mapped_column(String(36), ForeignKey("extracted_claims.id"), nullable=False)
    document_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("documents.id"))
    chunk_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("document_chunks.id"))

    source_url: Mapped[Optional[str]] = mapped_column(String(1024))
    quote: Mapped[Optional[str]] = mapped_column(Text)
    locator: Mapped[Optional[str]] = mapped_column(String(256))
    evidence_type: Mapped[str] = mapped_column(String(100), default="source_excerpt")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    claim: Mapped["ExtractedClaim"] = relationship(
        "ExtractedClaim", back_populates="evidence_links"
    )
    document: Mapped[Optional["Document"]] = relationship("Document", backref="evidence_links")
    chunk: Mapped[Optional["DocumentChunk"]] = relationship("DocumentChunk", backref="evidence_links")

    def __repr__(self) -> str:
        return f"<EvidenceLink(id={self.id}, claim_id={self.claim_id})>"


class ResearchOutput(Base):
    """A generated research artifact staged for review or promotion."""

    __tablename__ = "research_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_projects.id")
    )
    run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("research_runs.id"))

    output_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="staged")
    format: Mapped[str] = mapped_column(String(50), default="markdown")
    content: Mapped[Optional[str]] = mapped_column(Text)
    artifact_uri: Mapped[Optional[str]] = mapped_column(String(1024))
    source_json: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(256))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    project: Mapped[Optional["ResearchProject"]] = relationship(
        "ResearchProject", back_populates="outputs"
    )
    run: Mapped[Optional["ResearchRun"]] = relationship(
        "ResearchRun", back_populates="outputs"
    )
    review_decisions: Mapped[list["ReviewDecision"]] = relationship(
        "ReviewDecision", back_populates="output"
    )
    versions: Mapped[list["ResearchOutputVersion"]] = relationship(
        "ResearchOutputVersion",
        back_populates="output",
        order_by="ResearchOutputVersion.version_number",
    )

    def __repr__(self) -> str:
        return f"<ResearchOutput(id={self.id}, type={self.output_type}, status={self.status})>"


class ResearchOutputVersion(Base):
    """A point-in-time version of a generated research output."""

    __tablename__ = "research_output_versions"
    __table_args__ = (
        UniqueConstraint(
            "output_id",
            "version_number",
            name="uq_research_output_versions_output_number",
        ),
        Index("ix_research_output_versions_output", "output_id", "version_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    output_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_outputs.id"), nullable=False)

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    artifact_uri: Mapped[Optional[str]] = mapped_column(String(1024))
    source_json: Mapped[Optional[str]] = mapped_column(Text)
    change_summary: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    output: Mapped["ResearchOutput"] = relationship("ResearchOutput", back_populates="versions")

    def __repr__(self) -> str:
        return (
            "<ResearchOutputVersion("
            f"id={self.id}, output_id={self.output_id}, version={self.version_number}"
            ")>"
        )


class ReviewDecision(Base):
    """A human or policy decision on a staged research output."""

    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    output_id: Mapped[str] = mapped_column(String(36), ForeignKey("research_outputs.id"), nullable=False)

    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    reviewer: Mapped[Optional[str]] = mapped_column(String(256))
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    output: Mapped["ResearchOutput"] = relationship(
        "ResearchOutput", back_populates="review_decisions"
    )

    def __repr__(self) -> str:
        return f"<ReviewDecision(id={self.id}, decision={self.decision})>"


class ReviewAnnotation(Base):
    """A reviewer comment or annotation on a research output or claim."""

    __tablename__ = "review_annotations"
    __table_args__ = (
        Index("ix_review_annotations_target", "target_type", "target_id"),
        Index("ix_review_annotations_run_status", "run_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_projects.id")
    )
    run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("research_runs.id"))
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    author_user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("user_accounts.id"))
    author_email: Mapped[Optional[str]] = mapped_column(String(320))
    annotation_type: Mapped[str] = mapped_column(String(50), default="comment")
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="open")
    resolved_by: Mapped[Optional[str]] = mapped_column(String(320))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    project: Mapped[Optional["ResearchProject"]] = relationship("ResearchProject")
    run: Mapped[Optional["ResearchRun"]] = relationship("ResearchRun")
    author: Mapped[Optional["UserAccount"]] = relationship("UserAccount")

    def __repr__(self) -> str:
        return f"<ReviewAnnotation(id={self.id}, target={self.target_type}:{self.target_id})>"


class CorpusDedupeReport(Base):
    """A persisted duplicate-source report for corpus curation."""

    __tablename__ = "corpus_dedupe_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    report_type: Mapped[str] = mapped_column(String(100), default="document_duplicates")
    scope: Mapped[str] = mapped_column(String(256), default="all_documents")
    duplicate_group_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_document_count: Mapped[int] = mapped_column(Integer, default=0)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    def __repr__(self) -> str:
        return (
            "<CorpusDedupeReport("
            f"id={self.id}, groups={self.duplicate_group_count}, "
            f"documents={self.duplicate_document_count}"
            ")>"
        )


class ResearchGraphEdge(Base):
    """A typed knowledge-graph relationship between research entities."""

    __tablename__ = "research_graph_edges"
    __table_args__ = (
        Index("ix_research_graph_edges_source", "source_type", "source_id"),
        Index("ix_research_graph_edges_target", "target_type", "target_id"),
        Index("ix_research_graph_edges_relationship", "relationship_type"),
        Index("ix_research_graph_edges_project_run", "project_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_projects.id")
    )
    run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("research_runs.id"))

    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False)

    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    project: Mapped[Optional["ResearchProject"]] = relationship("ResearchProject")
    run: Mapped[Optional["ResearchRun"]] = relationship("ResearchRun")

    def __repr__(self) -> str:
        return (
            "<ResearchGraphEdge("
            f"id={self.id}, {self.source_type}:{self.source_id} "
            f"{self.relationship_type} {self.target_type}:{self.target_id}"
            ")>"
        )


class ResearchCollection(Base):
    """A named project collection of research entities."""

    __tablename__ = "research_collections"
    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_research_collections_project_slug"),
        Index("ix_research_collections_project", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_projects.id"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_email: Mapped[Optional[str]] = mapped_column(String(320))
    visibility: Mapped[str] = mapped_column(String(50), default="project")
    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    project: Mapped["ResearchProject"] = relationship("ResearchProject")
    items: Mapped[list["ResearchCollectionItem"]] = relationship(
        "ResearchCollectionItem",
        back_populates="collection",
        order_by="ResearchCollectionItem.created_at",
    )

    def __repr__(self) -> str:
        return f"<ResearchCollection(id={self.id}, slug={self.slug})>"


class ResearchCollectionItem(Base):
    """One entity saved into a research collection."""

    __tablename__ = "research_collection_items"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "target_type",
            "target_id",
            name="uq_research_collection_items_target",
        ),
        Index("ix_research_collection_items_target", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    collection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_collections.id"), nullable=False
    )

    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    added_by: Mapped[Optional[str]] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    collection: Mapped["ResearchCollection"] = relationship(
        "ResearchCollection", back_populates="items"
    )

    def __repr__(self) -> str:
        return f"<ResearchCollectionItem(id={self.id}, target={self.target_type}:{self.target_id})>"


class SavedSearch(Base):
    """A reusable project search definition."""

    __tablename__ = "saved_searches"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_saved_searches_project_name"),
        Index("ix_saved_searches_project", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_projects.id"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[str] = mapped_column(String(50), default="memory")
    filters_json: Mapped[Optional[str]] = mapped_column(Text)
    owner_email: Mapped[Optional[str]] = mapped_column(String(320))
    visibility: Mapped[str] = mapped_column(String(50), default="project")
    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    project: Mapped["ResearchProject"] = relationship("ResearchProject")

    def __repr__(self) -> str:
        return f"<SavedSearch(id={self.id}, name={self.name})>"


class SharedProjectView(Base):
    """A saved project dashboard/review/list view."""

    __tablename__ = "shared_project_views"
    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_shared_project_views_project_slug"),
        Index("ix_shared_project_views_project", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_projects.id"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(256), nullable=False)
    view_type: Mapped[str] = mapped_column(String(50), default="dashboard")
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    owner_email: Mapped[Optional[str]] = mapped_column(String(320))
    visibility: Mapped[str] = mapped_column(String(50), default="project")
    status: Mapped[str] = mapped_column(String(50), default="active")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    project: Mapped["ResearchProject"] = relationship("ResearchProject")

    def __repr__(self) -> str:
        return f"<SharedProjectView(id={self.id}, slug={self.slug})>"


class ResearchNotification(Base):
    """A queued or delivered collaboration notification."""

    __tablename__ = "research_notifications"
    __table_args__ = (
        Index("ix_research_notifications_recipient_status", "recipient_email", "status"),
        Index("ix_research_notifications_project_run", "project_id", "run_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_projects.id")
    )
    run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("research_runs.id"))

    recipient_email: Mapped[Optional[str]] = mapped_column(String(320))
    channel: Mapped[str] = mapped_column(String(50), default="in_app")
    notification_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    payload_json: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    project: Mapped[Optional["ResearchProject"]] = relationship("ResearchProject")
    run: Mapped[Optional["ResearchRun"]] = relationship("ResearchRun")

    def __repr__(self) -> str:
        return f"<ResearchNotification(id={self.id}, type={self.notification_type})>"


class ResearchAuditEvent(Base):
    """An auditable collaboration or review event."""

    __tablename__ = "research_audit_events"
    __table_args__ = (
        Index("ix_research_audit_events_project_run", "project_id", "run_id"),
        Index("ix_research_audit_events_target", "target_type", "target_id"),
        Index("ix_research_audit_events_action", "action"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("research_projects.id")
    )
    run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("research_runs.id"))

    actor_email: Mapped[Optional[str]] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[str] = mapped_column(String(512), nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    project: Mapped[Optional["ResearchProject"]] = relationship("ResearchProject")
    run: Mapped[Optional["ResearchRun"]] = relationship("ResearchRun")

    def __repr__(self) -> str:
        return f"<ResearchAuditEvent(id={self.id}, action={self.action})>"


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
