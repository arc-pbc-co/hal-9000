"""Figure and table reference extraction helpers for HAL research outputs."""

from __future__ import annotations

import re
from typing import Any

CAPTION_PATTERN = re.compile(
    r"(?im)\b(?P<kind>fig(?:ure)?|table)\s*"
    r"(?P<number>[A-Za-z0-9][A-Za-z0-9.\-]*)"
    r"(?:\s*[:.\-]\s*|\s+)"
    r"(?P<caption>[^\n]{8,600})"
)


def extract_media_references_from_text(
    text: str,
    *,
    document_id: str | None = None,
    chunk_id: str | None = None,
    claim_id: str | None = None,
    char_offset: int = 0,
) -> list[dict[str, Any]]:
    """Extract simple structured figure/table captions from source text."""
    references = []
    for match in CAPTION_PATTERN.finditer(text or ""):
        kind = _canonical_kind(match.group("kind"))
        label = f"{kind.title()} {match.group('number').strip().rstrip('.')}"
        caption = _clean_caption(match.group("caption"))
        references.append(
            normalize_media_reference(
                {
                    "kind": kind,
                    "label": label,
                    "caption": caption,
                    "char_start": char_offset + match.start(),
                    "char_end": char_offset + match.end(),
                },
                document_id=document_id,
                chunk_id=chunk_id,
                claim_id=claim_id,
            )
        )
    return dedupe_media_references(references)


def normalize_media_reference(
    raw: Any,
    *,
    kind: str | None = None,
    document_id: str | None = None,
    chunk_id: str | None = None,
    claim_id: str | None = None,
    citation_marker: str | None = None,
) -> dict[str, Any] | None:
    """Normalize a figure/table payload from text, chunk metadata, or provenance."""
    if isinstance(raw, str):
        payload: dict[str, Any] = {"label": raw, "caption": raw}
    elif isinstance(raw, dict):
        payload = dict(raw)
    else:
        return None

    normalized_kind = _canonical_kind(
        str(payload.get("kind") or payload.get("type") or kind or _kind_from_label(payload))
    )
    label = str(payload.get("label") or payload.get("id") or payload.get("title") or normalized_kind).strip()
    caption = _clean_caption(
        str(
            payload.get("caption")
            or payload.get("description")
            or payload.get("title")
            or label
        )
    )
    table_data = payload.get("table_data") or payload.get("rows")
    normalized = {
        "kind": normalized_kind,
        "label": label,
        "caption": caption,
        "description": caption,
        "document_id": payload.get("document_id") or document_id,
        "chunk_id": payload.get("chunk_id") or chunk_id,
        "claim_id": payload.get("claim_id") or claim_id,
        "page": _optional_int(payload.get("page")),
        "locator": payload.get("locator"),
        "source_url": payload.get("source_url") or payload.get("url"),
        "artifact_uri": payload.get("artifact_uri"),
        "char_start": _optional_int(payload.get("char_start")),
        "char_end": _optional_int(payload.get("char_end")),
        "citation_marker": payload.get("citation_marker") or citation_marker,
        "row_count": _row_count(table_data),
        "column_count": _column_count(table_data),
    }
    return {key: value for key, value in normalized.items() if value is not None}


def split_media_references(references: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Return references grouped under `figures` and `tables` metadata keys."""
    grouped = {"figures": [], "tables": []}
    for reference in dedupe_media_references(references):
        key = "tables" if reference.get("kind") == "table" else "figures"
        grouped[key].append(reference)
    return grouped


def dedupe_media_references(references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate figure/table references while preserving order."""
    seen = set()
    deduped = []
    for reference in references:
        key = (
            reference.get("kind"),
            _casefold(reference.get("label")),
            reference.get("document_id"),
            reference.get("chunk_id"),
            _casefold(reference.get("caption") or reference.get("description")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(reference)
    return deduped


def _canonical_kind(value: str) -> str:
    normalized = value.strip().lower().rstrip(".")
    if normalized.startswith("fig"):
        return "figure"
    return "table" if normalized == "table" else normalized or "figure"


def _kind_from_label(payload: dict[str, Any]) -> str:
    label = str(payload.get("label") or payload.get("id") or payload.get("title") or "").lower()
    return "table" if label.startswith("table") else "figure"


def _clean_caption(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().rstrip()


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _row_count(value: Any) -> int | None:
    return len(value) if isinstance(value, list) else None


def _column_count(value: Any) -> int | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    return len(first) if isinstance(first, list) else None


def _casefold(value: Any) -> str | None:
    return str(value).casefold().strip() if value is not None else None
