from __future__ import annotations

from pathlib import Path

from .classifier import classify_document
from .extractor import extract_text
from .manifest import Manifest
from .models import DocumentRecord
from .summarizer import summarize_text
from .utils import now_stamp, sha256_file


def summarize_existing_downloads(output_root: Path, manifest: Manifest) -> int:
    count = 0
    for row in manifest.all_documents():
        filepath = row.get("downloaded_filepath")
        if not filepath or not Path(filepath).exists():
            continue
        path = Path(filepath)
        text, status = extract_text(path)
        extracted_path = path.parents[1] / "summaries" / "extracted_text" / f"{path.stem}.txt" if len(path.parents) > 1 else output_root / "summaries" / "extracted_text" / f"{path.stem}.txt"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text(text, encoding="utf-8")
        category = row.get("category") or classify_document(row.get("source_section"), row.get("agenda_item_title"), row.get("document_title"), text[:1000])
        details = summarize_text(row["document_title"], category, text, status)
        allowed = DocumentRecord.__dataclass_fields__.keys()
        data = {key: row.get(key) for key in allowed}
        data.update(details)
        data.update({
            "category": category,
            "extraction_status": status,
            "sha256_checksum": sha256_file(path),
            "last_checked_at": now_stamp(),
        })
        manifest.upsert_document(DocumentRecord(**data))
        count += 1
    return count
