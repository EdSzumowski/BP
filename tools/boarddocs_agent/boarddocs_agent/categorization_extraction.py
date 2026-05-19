from __future__ import annotations

from pathlib import Path

from .classifier import classify_document
from .extractor import extract_text
from .manifest import Manifest
from .models import AgendaAttachment, AgendaItem, DocumentRecord, Meeting
from .summarizer import summarize_text
from .utils import ensure_unique_path, now_stamp, sanitize_filename, sha256_file, slug_category


def process_attachment_document(*, client, manifest: Manifest, meeting: Meeting, item: AgendaItem, attachment: AgendaAttachment, meeting_root: Path, dry_run: bool = False, force: bool = False) -> tuple[DocumentRecord | None, str]:
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
        extracted_path = meeting_root / "summaries" / "extracted_text" / f"{downloaded_path.stem}.txt"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text(text, encoding="utf-8")
        details = summarize_text(title, category, text, extraction_status)
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
