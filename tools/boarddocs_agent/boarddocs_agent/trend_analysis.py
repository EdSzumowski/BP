from __future__ import annotations

from collections import Counter
from pathlib import Path

from .manifest import Manifest
from .reporting import regenerate_indexes


def aggregate_documents(manifest: Manifest) -> list[dict]:
    return manifest.all_documents()


def top_entities(manifest: Manifest, top_n: int = 10) -> list[tuple[str, int]]:
    docs = aggregate_documents(manifest)
    counts = Counter(doc.get("category") or "Other" for doc in docs)
    return counts.most_common(top_n)


def detect_anomalies(manifest: Manifest) -> list[str]:
    issues: list[str] = []
    for doc in aggregate_documents(manifest):
        if not doc.get("downloaded_filepath"):
            issues.append(f"{doc.get('meeting_date')}: {doc.get('document_title')} missing downloaded filepath")
        if doc.get("extraction_status") not in (None, "ok"):
            issues.append(f"{doc.get('meeting_date')}: {doc.get('document_title')} extraction={doc.get('extraction_status')}")
    return issues


def generate_trend_report(output_root: Path, manifest: Manifest) -> None:
    regenerate_indexes(output_root, manifest)
