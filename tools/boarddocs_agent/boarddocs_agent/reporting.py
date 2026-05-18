from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .manifest import Manifest
from .models import RunStats


def regenerate_indexes(output_root: Path, manifest: Manifest) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    docs = manifest.all_documents()
    index = {"documents": docs}
    (output_root / "index.json").write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")

    by_meeting: dict[str, list[dict]] = defaultdict(list)
    for doc in docs:
        by_meeting[doc["meeting_date"]].append(doc)
    lines = ["# BoardDocs Meeting Index", "", "Generated from the local manifest database.", ""]
    if not by_meeting:
        lines.append("No meeting documents have been indexed yet.")
    for meeting_date in sorted(by_meeting, reverse=True):
        meeting_docs = by_meeting[meeting_date]
        first = meeting_docs[0]
        lines.extend([f"## {meeting_date} - {first['meeting_type']}", ""])
        categories = sorted({doc["category"] for doc in meeting_docs})
        lines.append(f"Categories: {', '.join(categories)}")
        lines.append("")
        for doc in meeting_docs:
            path = doc.get("downloaded_filepath") or "not downloaded"
            lines.append(f"- {doc['document_title']} - {doc['category']} - {path}")
        lines.append("")
    (output_root / "README.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_run_report(output_root: Path, stats: RunStats) -> Path:
    from .utils import run_stamp

    runs = output_root / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    path = runs / f"{run_stamp()}_run_report.md"
    lines = [
        "# BoardDocs Sync Run Report",
        "",
        f"- Meetings found: {stats.meetings_found}",
        f"- Meetings processed: {stats.meetings_processed}",
        f"- Documents downloaded: {stats.documents_downloaded}",
        f"- Documents skipped: {stats.documents_skipped}",
        "",
        "## Downloaded",
    ]
    lines.extend([f"- {item}" for item in stats.downloaded] or ["- None"])
    lines.extend(["", "## Skipped"])
    lines.extend([f"- {item}" for item in stats.skipped] or ["- None"])
    lines.extend(["", "## Extraction failures"])
    lines.extend([f"- {item}" for item in stats.extraction_failures] or ["- None"])
    lines.extend(["", "## Login/navigation failures"])
    lines.extend([f"- {item}" for item in stats.login_navigation_failures] or ["- None"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {item}" for item in stats.warnings] or ["- None"])
    lines.extend(["", "## Next suggested action"])
    if stats.login_navigation_failures:
        lines.append("- Run `python -m boarddocs_agent login --headful` and complete any interactive challenge.")
    elif stats.extraction_failures:
        lines.append("- Review failed files and rerun `python -m boarddocs_agent summarize` after installing optional extractors if needed.")
    else:
        lines.append("- Review Meetings/README.md and commit desired meeting artifacts.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    stats.run_report_path = path
    return path
