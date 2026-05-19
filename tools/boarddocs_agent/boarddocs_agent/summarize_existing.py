from __future__ import annotations

from datetime import date
from pathlib import Path

from .manifest import Manifest



def summarize_existing_downloads(output_root: Path, manifest: Manifest) -> int:
    from .categorization_extraction import process_attachment_document
    from .models import AgendaItem, Attachment, Meeting

    count = 0
    for row in manifest.all_documents():
        filepath = row.get("downloaded_filepath")
        if not filepath or not Path(filepath).exists():
            continue
        meeting = Meeting(row.get("meeting_id"), date.fromisoformat(row["meeting_date"]), row["meeting_type"], row["agenda_title"])
        item = AgendaItem(row.get("agenda_item_id"), row.get("agenda_item_title") or "", row.get("source_section") or "")
        attachment = Attachment(
            title=row.get("document_title") or "",
            url=row.get("original_url") or "",
            filename=Path(filepath).name,
        )
        process_attachment_document(
            client=_LocalFileClient(Path(filepath), row.get("content_type") or "application/octet-stream"),
            manifest=manifest,
            meeting=meeting,
            item=item,
            attachment=attachment,
            meeting_root=Path(filepath).parents[1] if len(Path(filepath).parents) > 1 else output_root,
            dry_run=False,
            force=True,
        )
        count += 1
    return count


class _LocalFileClient:
    def __init__(self, path: Path, content_type: str):
        self.path = path
        self.content_type = content_type

    def download_attachment(self, _attachment, target: Path):
        if target != self.path:
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(self.path.read_bytes())
            return target, self.content_type
        return self.path, self.content_type
