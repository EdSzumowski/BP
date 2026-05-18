from __future__ import annotations

import shutil
from dataclasses import asdict
from datetime import date
from pathlib import Path

from .boarddocs_client import BoardDocsClient
from .classifier import classify_document
from .extractor import extract_text
from .manifest import Manifest
from .models import DocumentRecord, Meeting, RunStats
from .reporting import regenerate_indexes, write_run_report
from .summarizer import summarize_text, write_meeting_summary
from .utils import ensure_unique_path, now_stamp, sanitize_filename, sha256_file, slug_category


def meeting_dir(output_root: Path, meeting: Meeting) -> Path:
    return output_root / meeting.school_year / meeting.meeting_date.isoformat()


def write_agenda_files(root: Path, meeting: Meeting) -> None:
    root.mkdir(parents=True, exist_ok=True)
    lines = [f"# {meeting.agenda_title}", "", f"Date: {meeting.meeting_date.isoformat()}", f"Type: {meeting.meeting_type}", "", "## Agenda Items"]
    for item in meeting.agenda_items:
        section = f" [{item.section}]" if item.section else ""
        lines.append(f"- {item.title}{section}")
        for att in item.attachments:
            lines.append(f"  - Attachment: {att.title}")
    (root / "agenda.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    metadata = {
        "meeting_id": meeting.meeting_id,
        "meeting_date": meeting.meeting_date.isoformat(),
        "meeting_type": meeting.meeting_type,
        "agenda_title": meeting.agenda_title,
        "agenda_items": [
            {"id": item.item_id, "title": item.title, "section": item.section, "attachments": [asdict(att) for att in item.attachments]}
            for item in meeting.agenda_items
        ],
    }
    import json
    (root / "metadata.json").write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")


def sync_meetings(client: BoardDocsClient, manifest: Manifest, output_root: Path, start_date: date, end_date: date, dry_run: bool = False, force: bool = False, limit_meetings: int | None = None) -> RunStats:
    stats = RunStats()
    meetings = client.discover_meetings(start_date, end_date)
    stats.meetings_found = len(meetings)
    if limit_meetings:
        meetings = meetings[:limit_meetings]
    for meeting in meetings:
        try:
            process_meeting(client, manifest, output_root, meeting, stats, dry_run=dry_run, force=force)
            stats.meetings_processed += 1
        except Exception as exc:
            stats.login_navigation_failures.append(f"{meeting.meeting_date}: {exc}")
    regenerate_indexes(output_root, manifest)
    write_run_report(output_root, stats)
    return stats


def process_meeting(client: BoardDocsClient, manifest: Manifest, output_root: Path, meeting: Meeting, stats: RunStats, dry_run: bool = False, force: bool = False) -> None:
    meeting = client.load_agenda(meeting)
    root = meeting_dir(output_root, meeting)
    if not dry_run:
        write_agenda_files(root, meeting)
    meeting_records: list[DocumentRecord] = []
    skipped: list[str] = []
    warnings: list[str] = []
    for item in meeting.agenda_items:
        for attachment in item.attachments:
            title = attachment.title or attachment.filename or "attachment"
            category = classify_document(item.section, item.title, title)
            filename = sanitize_filename(attachment.filename or title)
            target = root / slug_category(category) / filename
            existing = manifest.find_by_source(meeting.meeting_date.isoformat(), title, attachment.url)
            timestamp = now_stamp()
            if existing and existing["downloaded_filepath"] and Path(existing["downloaded_filepath"]).exists() and not force:
                stats.documents_skipped += 1
                reason = f"{title}: already downloaded"
                stats.skipped.append(reason)
                skipped.append(reason)
                record = _record_from_existing(existing, timestamp)
                manifest.upsert_document(record)
                meeting_records.append(record)
                continue
            if dry_run:
                stats.documents_skipped += 1
                skipped.append(f"{title}: dry run")
                continue
            try:
                download_target = ensure_unique_path(target) if target.exists() else target
                downloaded_path, content_type = client.download_attachment(attachment, download_target)
                checksum = sha256_file(downloaded_path)
                same_checksum = manifest.find_by_checksum(checksum)
                if same_checksum and same_checksum["downloaded_filepath"] != str(downloaded_path):
                    downloaded_path.unlink(missing_ok=True)
                    downloaded_path = Path(same_checksum["downloaded_filepath"])
                    stats.documents_skipped += 1
                    stats.skipped.append(f"{title}: duplicate checksum")
                elif existing and existing["sha256_checksum"] and existing["sha256_checksum"] != checksum:
                    stats.documents_downloaded += 1
                    stats.downloaded.append(str(downloaded_path))
                else:
                    stats.documents_downloaded += 1
                    stats.downloaded.append(str(downloaded_path))
                text, extraction_status = extract_text(downloaded_path)
                extracted_path = root / "summaries" / "extracted_text" / f"{downloaded_path.stem}.txt"
                extracted_path.parent.mkdir(parents=True, exist_ok=True)
                extracted_path.write_text(text, encoding="utf-8")
                if extraction_status != "ok":
                    stats.extraction_failures.append(f"{title}: {extraction_status}")
                    warnings.append(f"{title}: {extraction_status}")
                details = summarize_text(title, category, text, extraction_status)
                # Preserve the earliest first_downloaded_at across source and checksum matches
                _fda = existing["first_downloaded_at"] if existing else None
                if same_checksum and same_checksum["first_downloaded_at"]:
                    _sc_fda = same_checksum["first_downloaded_at"]
                    if not _fda or _sc_fda < _fda:
                        _fda = _sc_fda
                first_downloaded_at = _fda or timestamp
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
                    summary_path=str(root / "summaries" / "summary.md"),
                    source_section=item.section,
                    **details,
                )
                manifest.upsert_document(record)
                meeting_records.append(record)
            except Exception as exc:
                message = f"{title}: {exc}"
                stats.extraction_failures.append(message)
                warnings.append(message)
    if not dry_run:
        write_meeting_summary(meeting, meeting_records, skipped, warnings, root / "summaries" / "summary.md")


def _record_from_existing(existing, timestamp: str) -> DocumentRecord:
    data = dict(existing)
    data.pop("id", None)
    data.pop("source_key", None)
    data["last_checked_at"] = timestamp
    allowed = DocumentRecord.__dataclass_fields__.keys()
    return DocumentRecord(**{key: data.get(key) for key in allowed})
