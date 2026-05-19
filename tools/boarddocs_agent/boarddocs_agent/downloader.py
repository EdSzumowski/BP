from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path

from .boarddocs_client import BoardDocsClient
from .categorization_extraction import process_attachment_document
from .manifest import Manifest
from .models import DocumentRecord, Meeting, RunStats
from .reporting import regenerate_indexes, write_run_report
from .utils import now_stamp


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
            record, status = process_attachment_document(
                client=client,
                manifest=manifest,
                meeting=meeting,
                item=item,
                attachment=attachment,
                meeting_root=root,
                dry_run=dry_run,
                force=force,
            )
            timestamp = now_stamp()
            if status == "already_downloaded" and record is not None:
                stats.documents_skipped += 1
                reason = f"{record.document_title}: already downloaded"
                stats.skipped.append(reason)
                skipped.append(reason)
                manifest.upsert_document(_record_from_existing(manifest.find_by_source(record.meeting_date, record.document_title, record.original_url), timestamp))
                meeting_records.append(record)
            elif status == "dry_run":
                stats.documents_skipped += 1
                skipped.append(f"{attachment.title or attachment.filename or 'attachment'}: dry run")
            elif status == "duplicate_checksum" and record is not None:
                stats.documents_skipped += 1
                stats.skipped.append(f"{record.document_title}: duplicate checksum")
                meeting_records.append(record)
            elif status == "downloaded" and record is not None:
                stats.documents_downloaded += 1
                stats.downloaded.append(record.downloaded_filepath)
                meeting_records.append(record)
                if record.extraction_status != "ok":
                    msg = f"{record.document_title}: {record.extraction_status}"
                    stats.extraction_failures.append(msg)
                    warnings.append(msg)
            elif status.startswith("error:"):
                msg = f"{attachment.title or attachment.filename or 'attachment'}: {status[6:]}"
                stats.extraction_failures.append(msg)
                warnings.append(msg)
    if not dry_run:
        from .summarizer import write_meeting_summary
        write_meeting_summary(meeting, meeting_records, skipped, warnings, root / "summaries" / "summary.md")


def _record_from_existing(existing, timestamp: str) -> DocumentRecord:
    data = dict(existing or {})
    data.pop("id", None)
    data.pop("source_key", None)
    data["last_checked_at"] = timestamp
    allowed = DocumentRecord.__dataclass_fields__.keys()
    return DocumentRecord(**{key: data.get(key) for key in allowed})
