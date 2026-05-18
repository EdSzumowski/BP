from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .extractor import extract_signals
from .models import DocumentRecord, Meeting


def summarize_text(title: str, category: str, text: str, extraction_status: str) -> dict[str, str]:
    if extraction_status != "ok" or not text.strip():
        return {
            "short_summary": f"Text extraction was not available for {title}; content was not interpreted.",
            "importance": "Low",
            "importance_reason": "The tool could not inspect the document text.",
            "keywords": "",
            "dates_mentioned": "",
            "dollar_amounts": "",
            "people_departments": "",
        }
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text.strip()))
    useful = [sentence for sentence in sentences if len(sentence) > 40][:2]
    summary = " ".join(useful)[:700] or text.strip()[:500]
    signals = extract_signals(text)
    importance = "High" if category in {"Business and Finance", "Budget", "Personnel", "Policy", "Contracts, Agreements, and MOUs", "Legal/Executive Session"} else "Medium"
    if len(text) < 500 and not signals["dollars"]:
        importance = "Low"
    reason = f"Classified as {category}."
    if signals["dollars"]:
        reason += " Dollar amounts were detected."
    return {
        "short_summary": summary,
        "importance": importance,
        "importance_reason": reason,
        "keywords": ", ".join(signals["keywords"]),
        "dates_mentioned": ", ".join(signals["dates"]),
        "dollar_amounts": ", ".join(signals["dollars"]),
        "people_departments": ", ".join(signals["people_departments"]),
    }


def write_meeting_summary(meeting: Meeting, documents: list[DocumentRecord], skipped: list[str], warnings: list[str], path: Path) -> None:
    categories = Counter(doc.category for doc in documents)
    def section_for(category: str) -> list[DocumentRecord]:
        return [doc for doc in documents if doc.category == category]

    lines = [
        f"# {meeting.meeting_date.isoformat()} - {meeting.meeting_type}",
        "",
        f"Agenda title: {meeting.agenda_title}",
        "",
        "## Documents downloaded",
    ]
    if documents:
        for doc in documents:
            lines.append(f"- {doc.document_title} - {doc.category} - {doc.extraction_status}")
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Documents skipped and why"])
    lines.extend([f"- {item}" for item in skipped] or ["- None recorded."])
    lines.extend(["", "## Categories found"])
    lines.extend([f"- {category}: {count}" for category, count in sorted(categories.items())] or ["- None recorded."])
    lines.extend(["", "## Notable topics"])
    notable = [doc for doc in documents if doc.importance in {"High", "Medium"}]
    lines.extend([f"- {doc.document_title}: {doc.short_summary or 'No summary available.'}" for doc in notable[:12]] or ["- No notable topics identified from extracted text."])

    category_sections = [
        ("Action items or board decisions", ("Board Agenda", "Minutes")),
        ("Finance/budget items", ("Business and Finance", "Budget", "Claims/Audits/Treasurer")),
        ("Personnel items", ("Personnel",)),
        ("Policy items", ("Policy",)),
        ("Contracts/agreements", ("Contracts, Agreements, and MOUs",)),
    ]
    for heading, cats in category_sections:
        lines.extend(["", f"## {heading}"])
        rows = [doc for cat in cats for doc in section_for(cat)]
        lines.extend([f"- {doc.document_title}: {doc.short_summary or 'No readable summary.'}" for doc in rows] or ["- None identified."])

    lines.extend(["", "## Missing or inaccessible documents"])
    missing = [doc for doc in documents if doc.extraction_status != "ok"]
    lines.extend([f"- {doc.document_title}: {doc.extraction_status}" for doc in missing] or ["- None recorded."])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {warning}" for warning in warnings] or ["- None recorded."])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
