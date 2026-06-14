"""Corpus hardening services for document provenance and curation."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from hal9000.db.models import CorpusDedupeReport, Document, ExtractedClaim, utc_now
from hal9000.db.store import ResearchStore


@dataclass(frozen=True)
class CitationNormalization:
    """Normalized citation fields for one document."""

    source_identifier: str
    normalized_doi: str | None
    citation_key: str
    normalized_citation: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


@dataclass(frozen=True)
class SourceQualityAssessment:
    """Source quality score and underlying signals."""

    score: float
    label: str
    signals: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


@dataclass(frozen=True)
class CorpusHardeningResult:
    """Result of hardening one document."""

    document_id: str
    source_identifier: str
    citation_key: str
    source_quality_score: float
    source_quality_label: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


@dataclass(frozen=True)
class DedupeGroup:
    """A group of documents that appear to represent the same source."""

    match_type: str
    match_key: str
    document_ids: list[str]
    titles: list[str | None]
    file_hashes: list[str]
    normalized_dois: list[str | None]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


@dataclass(frozen=True)
class ClaimDedupeGroup:
    """A group of extracted claims that appear semantically duplicated."""

    match_type: str
    match_key: str
    claim_ids: list[str]
    document_ids: list[str]
    run_ids: list[str | None]
    claim_texts: list[str]
    statuses: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


@dataclass(frozen=True)
class SourceRefreshResult:
    """Result of one scheduled source refresh attempt."""

    document_id: str
    status: str
    source_path: str
    previous_file_hash: str | None
    current_file_hash: str | None
    new_document_id: str | None = None
    next_refresh_at: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation."""
        return asdict(self)


class CorpusHardeningService:
    """Normalize document identity, source quality, refresh policy, and dedupe reports."""

    def __init__(self, store: ResearchStore):
        """Initialize with the shared research store."""
        self.store = store
        self.session = store.session

    def harden_document(
        self,
        document: Document,
        refresh_policy: str = "manual",
        refresh_interval_days: int | None = None,
        source_version: str | None = None,
    ) -> CorpusHardeningResult:
        """Apply stable citation, version, refresh, and source quality metadata."""
        citation = normalize_citation(document)
        quality = assess_source_quality(document)
        now = utc_now()

        document.source_identifier = citation.source_identifier
        document.normalized_doi = citation.normalized_doi
        document.citation_key = citation.citation_key
        document.normalized_citation = citation.normalized_citation
        document.source_quality_score = quality.score
        document.source_quality_label = quality.label
        document.source_quality_json = json.dumps(quality.signals, sort_keys=True)
        document.version_group_key = document.version_group_key or citation.source_identifier
        document.source_version = source_version or document.source_version or "v1"
        document.is_current_version = True
        document.refresh_policy = _normalize_refresh_policy(refresh_policy)
        document.refresh_interval_days = refresh_interval_days
        document.last_refreshed_at = now
        document.next_refresh_at = (
            now + timedelta(days=refresh_interval_days)
            if document.refresh_policy == "interval" and refresh_interval_days
            else None
        )
        self.session.flush()

        return CorpusHardeningResult(
            document_id=document.id,
            source_identifier=citation.source_identifier,
            citation_key=citation.citation_key,
            source_quality_score=quality.score,
            source_quality_label=quality.label,
        )

    def harden_documents(
        self,
        limit: int | None = None,
        refresh_policy: str = "manual",
        refresh_interval_days: int | None = None,
    ) -> list[CorpusHardeningResult]:
        """Apply hardening metadata to recent documents."""
        query = self.session.query(Document).order_by(Document.created_at.desc())
        if limit is not None:
            query = query.limit(max(1, limit))
        return [
            self.harden_document(
                document,
                refresh_policy=refresh_policy,
                refresh_interval_days=refresh_interval_days,
            )
            for document in query.all()
        ]

    def register_new_version(
        self,
        previous_document: Document,
        new_document: Document,
        source_version: str,
        refresh_policy: str | None = None,
        refresh_interval_days: int | None = None,
    ) -> CorpusHardeningResult:
        """Mark a new document as the current version of a previous source."""
        previous_document.is_current_version = False
        version_group_key = (
            previous_document.version_group_key
            or previous_document.source_identifier
            or normalize_citation(previous_document).source_identifier
        )
        previous_document.version_group_key = version_group_key
        new_document.supersedes_document_id = previous_document.id
        new_document.version_group_key = version_group_key
        result = self.harden_document(
            new_document,
            refresh_policy=refresh_policy or previous_document.refresh_policy,
            refresh_interval_days=refresh_interval_days
            if refresh_interval_days is not None
            else previous_document.refresh_interval_days,
            source_version=source_version,
        )
        new_document.version_group_key = version_group_key
        self.session.flush()
        return result

    def due_source_documents(
        self,
        limit: int | None = None,
        now: datetime | None = None,
    ) -> list[Document]:
        """Return current interval-refresh documents due for scheduled source checks."""
        now = now or utc_now()
        query = (
            self.session.query(Document)
            .filter(Document.refresh_policy == "interval")
            .filter(Document.is_current_version.is_(True))
            .filter(Document.next_refresh_at.is_not(None))
            .filter(Document.next_refresh_at <= now)
            .order_by(Document.next_refresh_at.asc(), Document.created_at.asc())
        )
        if limit is not None:
            query = query.limit(max(1, limit))
        return query.all()

    def execute_scheduled_refresh(
        self,
        limit: int | None = None,
        refreshed_by: str | None = None,
        now: datetime | None = None,
    ) -> list[SourceRefreshResult]:
        """Execute due source refresh checks and advance each document's refresh window."""
        now = now or utc_now()
        return [
            self.refresh_source_document(document, refreshed_by=refreshed_by, now=now)
            for document in self.due_source_documents(limit=limit, now=now)
        ]

    def refresh_source_document(
        self,
        document: Document,
        refreshed_by: str | None = None,
        now: datetime | None = None,
    ) -> SourceRefreshResult:
        """Refresh one source according to its policy and local source evidence."""
        now = now or utc_now()
        if document.refresh_policy != "interval":
            return SourceRefreshResult(
                document_id=document.id,
                status="skipped",
                source_path=document.source_path,
                previous_file_hash=document.file_hash,
                current_file_hash=None,
                next_refresh_at=_isoformat(document.next_refresh_at),
                message="Document refresh_policy is not interval.",
            )

        current_hash = _local_file_hash(document.source_path)
        if current_hash is None:
            _advance_refresh_window(document, now)
            self.session.flush()
            return SourceRefreshResult(
                document_id=document.id,
                status="checked_unavailable",
                source_path=document.source_path,
                previous_file_hash=document.file_hash,
                current_file_hash=None,
                next_refresh_at=_isoformat(document.next_refresh_at),
                message="Source is not a readable local file; refreshed scheduling metadata only.",
            )

        if current_hash == document.file_hash:
            self.harden_document(
                document,
                refresh_policy=document.refresh_policy,
                refresh_interval_days=document.refresh_interval_days,
                source_version=document.source_version,
            )
            return SourceRefreshResult(
                document_id=document.id,
                status="unchanged",
                source_path=document.source_path,
                previous_file_hash=document.file_hash,
                current_file_hash=current_hash,
                next_refresh_at=_isoformat(document.next_refresh_at),
                message="Local source hash is unchanged.",
            )

        new_document = _new_document_version_from_refresh(document, current_hash)
        self.session.add(new_document)
        self.session.flush()
        self.register_new_version(
            document,
            new_document,
            source_version=_next_source_version(document.source_version),
            refresh_policy=document.refresh_policy,
            refresh_interval_days=document.refresh_interval_days,
        )
        _advance_refresh_window(document, now)
        document.updated_at = now
        self.session.flush()
        return SourceRefreshResult(
            document_id=document.id,
            status="new_version_detected",
            source_path=document.source_path,
            previous_file_hash=document.file_hash,
            current_file_hash=current_hash,
            new_document_id=new_document.id,
            next_refresh_at=_isoformat(new_document.next_refresh_at),
            message=f"Source changed; created pending document version. Refreshed by {refreshed_by or 'system'}.",
        )

    def create_dedupe_report(
        self,
        created_by: str | None = None,
        scope: str = "all_documents",
    ) -> CorpusDedupeReport:
        """Persist a duplicate-source report over the current document corpus."""
        documents = self.session.query(Document).order_by(Document.created_at).all()
        groups = build_dedupe_groups(documents)
        duplicate_document_ids = {
            document_id for group in groups for document_id in group.document_ids
        }
        payload = {
            "scope": scope,
            "duplicate_group_count": len(groups),
            "duplicate_document_count": len(duplicate_document_ids),
            "groups": [group.to_dict() for group in groups],
        }
        report = CorpusDedupeReport(
            report_type="document_duplicates",
            scope=scope,
            duplicate_group_count=len(groups),
            duplicate_document_count=len(duplicate_document_ids),
            report_json=json.dumps(payload, sort_keys=True),
            created_by=created_by,
        )
        self.session.add(report)
        self.session.flush()
        return report

    def create_claim_dedupe_report(
        self,
        created_by: str | None = None,
        scope: str = "all_claims",
        run_id: str | None = None,
    ) -> CorpusDedupeReport:
        """Persist a duplicate-claim report over extracted claims."""
        query = self.session.query(ExtractedClaim).order_by(ExtractedClaim.created_at)
        if run_id:
            query = query.filter(ExtractedClaim.run_id == run_id)
            scope = f"run:{run_id}"
        claims = query.all()
        groups = build_claim_dedupe_groups(claims)
        duplicate_claim_ids = {claim_id for group in groups for claim_id in group.claim_ids}
        payload = {
            "scope": scope,
            "run_id": run_id,
            "duplicate_group_count": len(groups),
            "duplicate_claim_count": len(duplicate_claim_ids),
            "groups": [group.to_dict() for group in groups],
        }
        report = CorpusDedupeReport(
            report_type="claim_duplicates",
            scope=scope,
            duplicate_group_count=len(groups),
            duplicate_document_count=len(duplicate_claim_ids),
            report_json=json.dumps(payload, sort_keys=True),
            created_by=created_by,
        )
        self.session.add(report)
        self.session.flush()
        return report


def normalize_citation(document: Document) -> CitationNormalization:
    """Build stable source identity and citation strings from document metadata."""
    normalized_doi = _normalize_doi(document.doi)
    authors = _authors(document.authors)
    first_author = _last_name(authors[0]) if authors else "unknown"
    year = str(document.year) if document.year else "nd"
    title = _clean_title(document.title) or "Untitled source"
    title_slug = _slug(title, max_words=4)
    citation_key = "-".join(part for part in [first_author.lower(), year, title_slug] if part)
    source_identifier = _source_identifier(document, normalized_doi, title)
    author_text = ", ".join(authors) if authors else "Unknown author"
    doi_text = f" DOI: {normalized_doi}." if normalized_doi else ""
    normalized_citation = f"{author_text} ({year}). {title}.{doi_text}".strip()
    return CitationNormalization(
        source_identifier=source_identifier,
        normalized_doi=normalized_doi,
        citation_key=citation_key,
        normalized_citation=normalized_citation,
    )


def assess_source_quality(document: Document) -> SourceQualityAssessment:
    """Score source quality from available metadata and extracted content signals."""
    signals = {
        "has_doi": bool(_normalize_doi(document.doi)),
        "has_title": bool(_clean_title(document.title)),
        "has_authors": bool(_authors(document.authors)),
        "has_year": document.year is not None,
        "has_abstract": bool((document.abstract or "").strip()),
        "has_full_text": bool((document.full_text or "").strip()),
        "completed_processing": document.status == "completed",
    }
    weights = {
        "has_doi": 0.22,
        "has_title": 0.16,
        "has_authors": 0.14,
        "has_year": 0.10,
        "has_abstract": 0.12,
        "has_full_text": 0.16,
        "completed_processing": 0.10,
    }
    score = round(sum(weights[key] for key, present in signals.items() if present), 3)
    if score >= 0.75:
        label = "high"
    elif score >= 0.45:
        label = "medium"
    else:
        label = "low"
    return SourceQualityAssessment(score=score, label=label, signals=signals)


def build_dedupe_groups(documents: list[Document]) -> list[DedupeGroup]:
    """Group likely duplicate documents by exact hash, DOI, and title/year fingerprint."""
    buckets: dict[tuple[str, str], list[Document]] = defaultdict(list)
    for document in documents:
        if document.file_hash:
            buckets[("file_hash", document.file_hash.lower())].append(document)
        normalized_doi = document.normalized_doi or _normalize_doi(document.doi)
        if normalized_doi:
            buckets[("doi", normalized_doi)].append(document)
        title_key = _title_year_key(document)
        if title_key:
            buckets[("title_year", title_key)].append(document)

    groups = []
    seen: set[tuple[str, str]] = set()
    for (match_type, match_key), bucket_documents in sorted(buckets.items()):
        unique_documents = _unique_documents(bucket_documents)
        if len(unique_documents) < 2:
            continue
        identity = (match_type, match_key)
        if identity in seen:
            continue
        seen.add(identity)
        groups.append(
            DedupeGroup(
                match_type=match_type,
                match_key=match_key,
                document_ids=[document.id for document in unique_documents],
                titles=[document.title for document in unique_documents],
                file_hashes=[document.file_hash for document in unique_documents],
                normalized_dois=[
                    document.normalized_doi or _normalize_doi(document.doi)
                    for document in unique_documents
                ],
            )
        )
    return groups


def build_claim_dedupe_groups(claims: list[ExtractedClaim]) -> list[ClaimDedupeGroup]:
    """Group likely duplicate claims by normalized text and structured triples."""
    buckets: dict[tuple[str, str], list[ExtractedClaim]] = defaultdict(list)
    for claim in claims:
        text_key = _claim_text_key(claim.claim_text)
        if text_key:
            buckets[("claim_text", text_key)].append(claim)
        triple_key = _claim_triple_key(claim)
        if triple_key:
            buckets[("claim_triple", triple_key)].append(claim)

    groups = []
    seen: set[tuple[str, str]] = set()
    for (match_type, match_key), bucket_claims in sorted(buckets.items()):
        unique_claims = _unique_claims(bucket_claims)
        if len(unique_claims) < 2:
            continue
        identity = (match_type, match_key)
        if identity in seen:
            continue
        seen.add(identity)
        groups.append(
            ClaimDedupeGroup(
                match_type=match_type,
                match_key=match_key,
                claim_ids=[claim.id for claim in unique_claims],
                document_ids=[claim.document_id for claim in unique_claims],
                run_ids=[claim.run_id for claim in unique_claims],
                claim_texts=[claim.claim_text for claim in unique_claims],
                statuses=[claim.status for claim in unique_claims],
            )
        )
    return groups


def report_payload(report: CorpusDedupeReport) -> dict[str, Any]:
    """Return a JSON-friendly persisted dedupe report payload."""
    payload = json.loads(report.report_json)
    payload["id"] = report.id
    payload["report_type"] = report.report_type
    payload["created_by"] = report.created_by
    payload["created_at"] = report.created_at.isoformat() if report.created_at else None
    return payload


def _normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    normalized = re.sub(r"^https?://(dx\.)?doi\.org/", "", normalized)
    normalized = re.sub(r"^doi:\s*", "", normalized)
    normalized = normalized.strip().rstrip(".")
    return normalized or None


def _authors(value: str | None) -> list[str]:
    if not value:
        return []
    raw = value.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw
    if isinstance(parsed, list):
        return [str(author).strip() for author in parsed if str(author).strip()]
    return [author.strip() for author in re.split(r";|\band\b", str(parsed)) if author.strip()]


def _last_name(author: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9\s-]", "", author).strip()
    if "," in author:
        return _slug(author.split(",", 1)[0], max_words=1) or "unknown"
    parts = cleaned.split()
    return _slug(parts[-1], max_words=1) if parts else "unknown"


def _clean_title(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized or None


def _slug(value: str, max_words: int = 6) -> str:
    words = re.findall(r"[a-z0-9]+", value.lower())
    return "-".join(words[:max_words])


def _source_identifier(document: Document, normalized_doi: str | None, title: str) -> str:
    if normalized_doi:
        return f"doi:{normalized_doi}"
    if document.file_hash:
        return f"sha256:{document.file_hash.lower()}"
    fingerprint = hashlib.sha256(
        f"{title.lower()}|{document.year or ''}|{document.source_path}".encode()
    ).hexdigest()
    return f"fingerprint:{fingerprint}"


def _title_year_key(document: Document) -> str | None:
    title = _clean_title(document.title)
    if not title:
        return None
    return f"{_slug(title, max_words=12)}|{document.year or 'nd'}"


def _unique_documents(documents: list[Document]) -> list[Document]:
    seen = set()
    unique = []
    for document in documents:
        if document.id in seen:
            continue
        seen.add(document.id)
        unique.append(document)
    return unique


def _unique_claims(claims: list[ExtractedClaim]) -> list[ExtractedClaim]:
    seen = set()
    unique = []
    for claim in claims:
        if claim.id in seen:
            continue
        seen.add(claim.id)
        unique.append(claim)
    return unique


def _claim_text_key(value: str | None) -> str | None:
    if not value:
        return None
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return " ".join(tokens) or None


def _claim_triple_key(claim: ExtractedClaim) -> str | None:
    parts = [
        _claim_text_key(claim.normalized_subject),
        _claim_text_key(claim.normalized_predicate),
        _claim_text_key(claim.normalized_object),
    ]
    if not all(parts):
        return None
    return "|".join(str(part) for part in parts)


def _local_file_hash(source_path: str | None) -> str | None:
    if not source_path:
        return None
    path = Path(source_path).expanduser()
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _new_document_version_from_refresh(document: Document, file_hash: str) -> Document:
    return Document(
        source_path=document.source_path,
        source_type=document.source_type,
        file_hash=file_hash,
        title=document.title,
        authors=document.authors,
        year=document.year,
        doi=document.doi,
        abstract=document.abstract,
        key_concepts=document.key_concepts,
        methodology=document.methodology,
        acquisition_source=document.acquisition_source,
        acquisition_query=document.acquisition_query,
        status="pending",
        source_identifier=document.source_identifier,
        source_version=_next_source_version(document.source_version),
        version_group_key=document.version_group_key,
        refresh_policy=document.refresh_policy,
        refresh_interval_days=document.refresh_interval_days,
        normalized_doi=document.normalized_doi,
        citation_key=document.citation_key,
        normalized_citation=document.normalized_citation,
    )


def _next_source_version(value: str | None) -> str:
    if not value:
        return "v2"
    match = re.fullmatch(r"v?(\d+)", value.strip().lower())
    if match:
        return f"v{int(match.group(1)) + 1}"
    return f"{value}-refresh"


def _advance_refresh_window(document: Document, now: datetime) -> None:
    document.last_refreshed_at = now
    document.next_refresh_at = (
        now + timedelta(days=document.refresh_interval_days)
        if document.refresh_policy == "interval" and document.refresh_interval_days
        else None
    )


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _normalize_refresh_policy(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_")
    if normalized not in {"manual", "interval", "never"}:
        raise ValueError("refresh_policy must be manual, interval, or never")
    return normalized
