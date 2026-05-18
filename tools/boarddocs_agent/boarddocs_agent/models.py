from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Attachment:
    title: str
    url: str | None = None
    filename: str | None = None
    content_type: str | None = None


@dataclass(slots=True)
class AgendaItem:
    item_id: str | None
    title: str
    section: str | None = None
    body: str | None = None
    attachments: list[Attachment] = field(default_factory=list)


@dataclass(slots=True)
class Meeting:
    meeting_id: str | None
    meeting_date: date
    meeting_type: str
    agenda_title: str
    url: str | None = None
    agenda_html: str | None = None
    agenda_items: list[AgendaItem] = field(default_factory=list)

    @property
    def school_year(self) -> str:
        start = self.meeting_date.year if self.meeting_date.month >= 7 else self.meeting_date.year - 1
        return f"{start}-{start + 1}"


@dataclass(slots=True)
class DocumentRecord:
    meeting_date: str
    meeting_type: str
    agenda_title: str
    agenda_item_title: str
    document_title: str
    original_url: str | None
    downloaded_filepath: str | None
    content_type: str | None
    sha256_checksum: str | None
    first_downloaded_at: str | None
    last_checked_at: str
    category: str
    extraction_status: str
    summary_path: str | None
    source_section: str | None = None
    short_summary: str | None = None
    importance: str | None = None
    importance_reason: str | None = None
    keywords: str | None = None
    dates_mentioned: str | None = None
    dollar_amounts: str | None = None
    people_departments: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            field_name: getattr(self, field_name)
            for field_name in self.__dataclass_fields__
        }


@dataclass(slots=True)
class RunStats:
    meetings_found: int = 0
    meetings_processed: int = 0
    documents_downloaded: int = 0
    documents_skipped: int = 0
    extraction_failures: list[str] = field(default_factory=list)
    login_navigation_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    downloaded: list[str] = field(default_factory=list)
    run_report_path: Path | None = None
