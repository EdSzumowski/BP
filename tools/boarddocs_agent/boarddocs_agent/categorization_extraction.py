from __future__ import annotations

import json
import re
from pathlib import Path

from .classifier import classify_document
from .extractor import extract_signals, extract_text
from .manifest import Manifest
from .models import AgendaItem, Attachment, DocumentRecord, Meeting
from .summarizer import summarize_text
from .utils import ensure_unique_path, now_stamp, sanitize_filename, sha256_file, slug_category


def detect_report_family(*parts: str | None) -> str:
    text = " ".join(part or "" for part in parts).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    families: list[tuple[str, tuple[str, ...]]] = [
        ("treasurer_report", ("treasurer report", "treasurer", "warrant claims", "claims")),
        ("budget_status", ("budget status", "budget transfer", "fund balance", "tax levy")),
        ("financial_statement", ("financial statement", "revenue", "expense", "general fund")),
        ("personnel_action", ("personnel", "appointment", "resignation", "tenure", "leave of absence")),
        ("policy_update", ("policy", "first reading", "second reading")),
        ("board_minutes", ("minutes", "meeting minute")),
        ("board_agenda", ("board agenda", "agenda")),
    ]
    scores: dict[str, int] = {}
    for family, terms in families:
        score = 0
        for term in terms:
            if term in text:
                score += 3 if " " in term else 1
        if score:
            scores[family] = score
    if not scores:
        return "general_document"
    return max(scores.items(), key=lambda item: item[1])[0]


def normalize_extraction_fields(text: str, extraction_status: str) -> dict[str, str]:
    signals = extract_signals(text) if extraction_status == "ok" and text.strip() else {
        "dates": [], "dollars": [], "people_departments": [], "keywords": []
    }
    return {
        "keywords": ", ".join(signals.get("keywords") or []),
        "dates_mentioned": ", ".join(signals.get("dates") or []),
        "dollar_amounts": ", ".join(signals.get("dollars") or []),
        "people_departments": ", ".join(signals.get("people_departments") or []),
    }


def persist_extracted_outputs(*, meeting_root: Path, downloaded_path: Path, record: DocumentRecord, text: str, normalized_fields: dict[str, str]) -> None:
    artifact_stem = f"{slug_category(record.category)}__{downloaded_path.stem}"
    extracted_path = meeting_root / "summaries" / "extracted_text" / f"{artifact_stem}.txt"
    extracted_path.parent.mkdir(parents=True, exist_ok=True)
    extracted_path.write_text(text, encoding="utf-8")

    structured_root = meeting_root / "summaries" / "extracted_documents"
    structured_root.mkdir(parents=True, exist_ok=True)
    structured_path = structured_root / f"{artifact_stem}.json"
    payload = {
        "provenance": {
            "meeting_date": record.meeting_date,
            "agenda_title": record.agenda_title,
            "agenda_item_title": record.agenda_item_title,
            "document_title": record.document_title,
            "original_url": record.original_url,
            "downloaded_filepath": record.downloaded_filepath,
            "sha256_checksum": record.sha256_checksum,
        },
        "classification": {
            "category": record.category,
            "report_family": detect_report_family(record.source_section, record.agenda_item_title, record.document_title),
        },
        "extraction": {
            "status": record.extraction_status,
            "normalized_fields": normalized_fields,
            "text_path": str(extracted_path),
        },
    }
    structured_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def process_attachment_document(*, client, manifest: Manifest, meeting: Meeting, item: AgendaItem, attachment: Attachment, meeting_root: Path, dry_run: bool = False, force: bool = False) -> tuple[DocumentRecord | None, str]:
    title = attachment.title or attachment.filename or "attachment"
    category = classify_document(item.section, item.title, title)
    filename = sanitize_filename(attachment.filename or title)
    target = meeting_root / slug_category(category) / filename
    existing = manifest.find_by_source(meeting.meeting_date.isoformat(), title, attachment.url)
    timestamp = now_stamp()
    if existing and existing["downloaded_filepath"] and Path(existing["downloaded_filepath"]).exists() and not force:
        return _record_from_existing(existing, timestamp), "already_downloaded"
    if dry_run:
        return None, "dry_run"
    try:
        download_target = ensure_unique_path(target) if target.exists() else target
        downloaded_path, content_type = client.download_attachment(attachment, download_target)
        checksum = sha256_file(downloaded_path)
        same_checksum = manifest.find_by_checksum(checksum)
        status = "downloaded"
        if same_checksum and same_checksum["downloaded_filepath"] != str(downloaded_path):
            downloaded_path.unlink(missing_ok=True)
            downloaded_path = Path(same_checksum["downloaded_filepath"])
            status = "duplicate_checksum"
        text, extraction_status = extract_text(downloaded_path)
        details = summarize_text(title, category, text, extraction_status)
        normalized_fields = normalize_extraction_fields(text, extraction_status)
        details.update(normalized_fields)
        first_downloaded_at = (existing or {}).get("first_downloaded_at") or timestamp
        if same_checksum and same_checksum["first_downloaded_at"] and same_checksum["first_downloaded_at"] < first_downloaded_at:
            first_downloaded_at = same_checksum["first_downloaded_at"]
        record = DocumentRecord(
            meeting_date=meeting.meeting_date.isoformat(),
            meeting_type=meeting.meeting_type,
            agenda_title=meeting.agenda_title,
            agenda_item_title=item.title,
            document_title=title,
            original_url=attachment.url,
            downloaded_filepath=str(downloaded_path),
            content_type=content_type,
            sha256_checksum=sha256_file(downloaded_path),
            first_downloaded_at=first_downloaded_at,
            last_checked_at=timestamp,
            category=category,
            extraction_status=extraction_status,
            summary_path=str(meeting_root / "summaries" / "summary.md"),
            source_section=item.section,
            **details,
        )
        persist_extracted_outputs(
            meeting_root=meeting_root,
            downloaded_path=downloaded_path,
            record=record,
            text=text,
            normalized_fields=normalized_fields,
        )
        manifest.upsert_document(record)
        return record, status
    except Exception as exc:
        return None, f"error:{exc}"


def _record_from_existing(existing, timestamp: str) -> DocumentRecord:
    data = dict(existing)
    data.pop("id", None)
    data.pop("source_key", None)
    data["last_checked_at"] = timestamp
    allowed = DocumentRecord.__dataclass_fields__.keys()
    return DocumentRecord(**{key: data.get(key) for key in allowed})
