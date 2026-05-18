from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import DocumentRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_date TEXT NOT NULL,
    meeting_type TEXT NOT NULL,
    agenda_title TEXT NOT NULL,
    agenda_item_title TEXT NOT NULL,
    document_title TEXT NOT NULL,
    original_url TEXT,
    downloaded_filepath TEXT,
    content_type TEXT,
    sha256_checksum TEXT,
    first_downloaded_at TEXT,
    last_checked_at TEXT NOT NULL,
    category TEXT NOT NULL,
    extraction_status TEXT NOT NULL,
    summary_path TEXT,
    source_key TEXT NOT NULL,
    source_section TEXT,
    short_summary TEXT,
    importance TEXT,
    importance_reason TEXT,
    keywords TEXT,
    dates_mentioned TEXT,
    dollar_amounts TEXT,
    people_departments TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_source ON documents(source_key);
CREATE INDEX IF NOT EXISTS idx_documents_meeting ON documents(meeting_date, meeting_type);
CREATE INDEX IF NOT EXISTS idx_documents_checksum ON documents(sha256_checksum);
"""


class Manifest:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert_document(self, record: DocumentRecord) -> int:
        existing = self.find_by_source(record.meeting_date, record.document_title, record.original_url)
        values = record.as_dict()
        values["source_key"] = source_key(record.meeting_date, record.document_title, record.original_url)
        if existing:
            if not values.get("first_downloaded_at"):
                values["first_downloaded_at"] = existing["first_downloaded_at"]
            assignments = ", ".join(f"{key} = :{key}" for key in values)
            values["id"] = existing["id"]
            self.conn.execute(f"UPDATE documents SET {assignments} WHERE id = :id", values)
            self.conn.commit()
            return int(existing["id"])
        columns = ", ".join(values)
        placeholders = ", ".join(f":{key}" for key in values)
        cursor = self.conn.execute(f"INSERT INTO documents ({columns}) VALUES ({placeholders})", values)
        self.conn.commit()
        return int(cursor.lastrowid)

    def find_by_source(self, meeting_date: str, document_title: str, original_url: str | None) -> sqlite3.Row | None:
        cursor = self.conn.execute(
            """
            SELECT * FROM documents
            WHERE source_key = ?
            LIMIT 1
            """,
            (source_key(meeting_date, document_title, original_url),),
        )
        return cursor.fetchone()

    def find_by_checksum(self, checksum: str) -> sqlite3.Row | None:
        cursor = self.conn.execute("SELECT * FROM documents WHERE sha256_checksum = ? LIMIT 1", (checksum,))
        return cursor.fetchone()

    def all_documents(self) -> list[dict]:
        cursor = self.conn.execute("SELECT * FROM documents ORDER BY meeting_date DESC, category, document_title")
        return [dict(row) for row in cursor.fetchall()]

    def documents_for_meeting(self, meeting_date: str) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT * FROM documents WHERE meeting_date = ? ORDER BY category, document_title",
            (meeting_date,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def export_json(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"documents": self.all_documents()}, indent=2, sort_keys=True), encoding="utf-8")


def open_manifest(output_root: Path) -> Manifest:
    return Manifest(output_root / "manifest.sqlite")



def source_key(meeting_date: str, document_title: str, original_url: str | None) -> str:
    return f"{meeting_date}|{document_title}|{original_url or ''}"
