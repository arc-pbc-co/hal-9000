"""Compliance checks for source PDFs and generated summaries."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from hal9000.db.models import Document, ResearchOutput, utc_now

OPEN_LICENSE_MARKERS = (
    "cc-by",
    "cc by",
    "cc0",
    "creative commons",
    "open access",
    "public domain",
    "arxiv",
)
RESTRICTED_RIGHTS_MARKERS = (
    "all rights reserved",
    "copyright",
    "copyrighted",
    "closed",
    "licensed",
    "publisher pdf",
    "restricted",
)
SUMMARY_OUTPUT_MARKERS = (
    "summary",
    "brief",
    "literature",
    "review",
    "adam_context",
    "context",
)


@dataclass(frozen=True)
class ComplianceIssue:
    """One compliance finding for a source or generated artifact."""

    code: str
    severity: str
    target_type: str
    target_id: str
    title: str
    message: str
    action_required: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the finding for CLI/API output."""
        return {
            "code": self.code,
            "severity": self.severity,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "title": self.title,
            "message": self.message,
            "action_required": self.action_required,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class ComplianceReport:
    """Compliance report across source PDFs and generated summaries."""

    generated_at: str
    issues: list[ComplianceIssue]
    checked: dict[str, int]

    @property
    def issue_count(self) -> int:
        """Return the number of findings."""
        return len(self.issues)

    @property
    def high_count(self) -> int:
        """Return the number of high severity findings."""
        return sum(1 for issue in self.issues if issue.severity == "high")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report for CLI/API output."""
        return {
            "generated_at": self.generated_at,
            "issue_count": self.issue_count,
            "high_count": self.high_count,
            "checked": dict(self.checked),
            "issues": [issue.to_dict() for issue in self.issues],
        }


class ResearchComplianceService:
    """Run conservative compliance checks over HAL research assets."""

    def __init__(self, session: Session):
        """Initialize with a shared-store session."""
        self.session = session

    def check(self) -> ComplianceReport:
        """Return a compliance report without mutating records."""
        documents = self.session.query(Document).all()
        outputs = self.session.query(ResearchOutput).all()
        issues: list[ComplianceIssue] = []
        for document in documents:
            issue = self._document_issue(document)
            if issue is not None:
                issues.append(issue)
        for output in outputs:
            issue = self._output_issue(output)
            if issue is not None:
                issues.append(issue)
        issues.sort(key=lambda issue: (_severity_rank(issue.severity), issue.code, issue.title))
        return ComplianceReport(
            generated_at=utc_now().isoformat().replace("+00:00", "Z"),
            issues=issues,
            checked={"documents": len(documents), "outputs": len(outputs)},
        )

    def _document_issue(self, document: Document) -> ComplianceIssue | None:
        metadata = _json_or_none(document.source_quality_json)
        if not _looks_like_pdf(document):
            return None
        if _is_reviewed_or_allowed(metadata):
            return None
        title = document.title or document.source_path
        if _is_restricted(metadata):
            return ComplianceIssue(
                code="copyrighted_pdf_review_required",
                severity="high",
                target_type="document",
                target_id=document.id,
                title=title,
                message="PDF/source metadata indicates restricted or copyrighted rights.",
                action_required="Record rights review, license basis, or legal hold before broad sharing.",
                evidence=_compact_evidence(metadata, source_type=document.source_type),
            )
        if not _has_open_license(metadata):
            return ComplianceIssue(
                code="pdf_rights_metadata_missing",
                severity="medium",
                target_type="document",
                target_id=document.id,
                title=title,
                message="PDF/source artifact has no open-license or rights-review metadata.",
                action_required="Add open-access/license metadata or mark the document as compliance reviewed.",
                evidence=_compact_evidence(metadata, source_type=document.source_type),
            )
        return None

    def _output_issue(self, output: ResearchOutput) -> ComplianceIssue | None:
        if not _looks_like_generated_summary(output):
            return None
        metadata = _json_or_none(output.source_json)
        if _is_reviewed_or_allowed(metadata):
            return None
        title = output.title or output.output_type
        if _uses_restricted_source(metadata):
            return ComplianceIssue(
                code="generated_summary_copyright_source_review_required",
                severity="high",
                target_type="output",
                target_id=output.id,
                title=title,
                message="Generated summary metadata indicates restricted source material.",
                action_required="Review summary length, quotation use, citations, and sharing scope before promotion.",
                evidence=_compact_evidence(metadata, output_type=output.output_type),
            )
        if not _has_summary_provenance(metadata):
            return ComplianceIssue(
                code="generated_summary_missing_provenance",
                severity="medium",
                target_type="output",
                target_id=output.id,
                title=title,
                message="Generated summary lacks source provenance metadata.",
                action_required="Attach cited claims, source documents, or evidence links before promotion.",
                evidence={"output_type": output.output_type, "format": output.format},
            )
        return None


def _looks_like_pdf(document: Document) -> bool:
    source_path = (document.source_path or "").lower()
    source_type = (document.source_type or "").lower()
    return (
        source_path.endswith(".pdf")
        or "pdf" in source_type
        or source_type in {"local", "downloaded", "object_store"}
    )


def _looks_like_generated_summary(output: ResearchOutput) -> bool:
    haystack = f"{output.output_type} {output.title} {output.format}".lower()
    return bool((output.content or "").strip()) and any(
        marker in haystack for marker in SUMMARY_OUTPUT_MARKERS
    )


def _is_reviewed_or_allowed(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    for key in ("compliance_reviewed", "rights_reviewed", "allowed_use", "open_access"):
        if metadata.get(key) is True:
            return True
    return False


def _is_restricted(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    for key in ("copyrighted", "restricted", "publisher_pdf", "all_rights_reserved"):
        if metadata.get(key) is True:
            return True
    rights_text = " ".join(
        str(metadata.get(key) or "")
        for key in ("license", "rights", "rights_status", "source_quality_label")
    ).lower()
    return any(marker in rights_text for marker in RESTRICTED_RIGHTS_MARKERS)


def _uses_restricted_source(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    for key in (
        "copyrighted_pdf",
        "derived_from_copyrighted_pdf",
        "uses_restricted_source",
        "publisher_pdf_source",
    ):
        if metadata.get(key) is True:
            return True
    return _is_restricted(metadata)


def _has_open_license(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    rights_text = " ".join(
        str(metadata.get(key) or "") for key in ("license", "rights", "rights_status")
    ).lower()
    return any(marker in rights_text for marker in OPEN_LICENSE_MARKERS)


def _has_summary_provenance(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    for key in (
        "claim_ids",
        "claims",
        "citations",
        "document_ids",
        "documents",
        "evidence_links",
        "source_documents",
    ):
        value = metadata.get(key)
        if isinstance(value, list) and value:
            return True
        if isinstance(value, dict) and value:
            return True
    return False


def _compact_evidence(metadata: Any, **extra: Any) -> dict[str, Any]:
    evidence = dict(extra)
    if isinstance(metadata, dict):
        for key in (
            "license",
            "rights",
            "rights_status",
            "source_quality_label",
            "copyrighted",
            "restricted",
            "publisher_pdf",
        ):
            if key in metadata:
                evidence[key] = metadata[key]
    return evidence


def _json_or_none(raw_value: str | None) -> Any:
    if not raw_value:
        return None
    try:
        return json.loads(raw_value)
    except json.JSONDecodeError:
        return None


def _severity_rank(severity: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(severity, 3)
