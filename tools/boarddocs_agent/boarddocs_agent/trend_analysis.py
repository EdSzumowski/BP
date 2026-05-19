from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .manifest import Manifest
from .reporting import regenerate_indexes
from .utils import slug_category

FINANCE_FAMILY_HINTS = (
    "treasurer",
    "budget",
    "financial",
    "cash_disbursement",
    "claims_audit",
    "warrant",
    "fund",
)


def aggregate_documents(manifest: Manifest) -> list[dict]:
    return manifest.all_documents()


def _month_key(meeting_date: str | None) -> str:
    if not meeting_date:
        return "unknown"
    try:
        parsed = date.fromisoformat(meeting_date)
        return f"{parsed.year:04d}-{parsed.month:02d}"
    except ValueError:
        return "unknown"


def _split_csv(field: str | None) -> list[str]:
    if not field:
        return []
    return [item.strip() for item in field.split(",") if item.strip()]


def _safe_float(value: str) -> float | None:
    cleaned = re.sub(r"[^0-9.\-]", "", value)
    if cleaned in {"", ".", "-", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _read_structured_output(doc: dict) -> dict:
    path = doc.get("downloaded_filepath")
    if not path:
        return {}
    downloaded = Path(path)
    structured = downloaded.parent.parent / "summaries" / "extracted_documents"
    if not structured.exists():
        return {}
    target = structured / f"{slug_category(doc.get('category') or 'other')}__{downloaded.stem}.json"
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}


def aggregate_cross_month(manifest: Manifest) -> dict[str, dict]:
    monthly: dict[str, dict] = defaultdict(lambda: {
        "documents": 0,
        "families": Counter(),
        "categories": Counter(),
        "amount_total": 0.0,
        "amount_count": 0,
        "narrative_keywords": Counter(),
        "records": [],
    })
    for doc in aggregate_documents(manifest):
        month = _month_key(doc.get("meeting_date"))
        entry = monthly[month]
        entry["documents"] += 1
        entry["categories"][doc.get("category") or "Other"] += 1

        structured = _read_structured_output(doc)
        family = (((structured.get("classification") or {}).get("report_family")) or "general_document")
        entry["families"][family] += 1

        normalized = ((structured.get("extraction") or {}).get("normalized_fields")) or {}
        dollars = _split_csv(normalized.get("dollar_amounts") or doc.get("dollar_amounts"))
        for item in dollars:
            amount = _safe_float(item)
            if amount is not None:
                entry["amount_total"] += amount
                entry["amount_count"] += 1

        keywords = _split_csv(normalized.get("keywords") or doc.get("keywords"))
        for kw in keywords[:25]:
            entry["narrative_keywords"][kw.lower()] += 1

        entry["records"].append({
            "meeting_date": doc.get("meeting_date"),
            "document_title": doc.get("document_title"),
            "category": doc.get("category"),
            "report_family": family,
            "source": {
                "document": doc.get("downloaded_filepath"),
                "field_source": str((structured.get("extraction") or {}).get("text_path") or ""),
            },
        })
    return dict(monthly)


def detect_financial_trends(monthly: dict[str, dict]) -> list[dict]:
    months = sorted(monthly)
    trends: list[dict] = []
    for prev, curr in zip(months, months[1:]):
        p = monthly[prev]
        c = monthly[curr]
        prev_avg = (p["amount_total"] / p["amount_count"]) if p["amount_count"] else 0.0
        curr_avg = (c["amount_total"] / c["amount_count"]) if c["amount_count"] else 0.0
        change = curr_avg - prev_avg
        finance_prev = sum(count for fam, count in p["families"].items() if any(h in fam for h in FINANCE_FAMILY_HINTS))
        finance_curr = sum(count for fam, count in c["families"].items() if any(h in fam for h in FINANCE_FAMILY_HINTS))
        trends.append({
            "from": prev,
            "to": curr,
            "avg_amount_change": round(change, 2),
            "finance_docs_change": finance_curr - finance_prev,
            "stable": abs(change) < 100 and (finance_curr - finance_prev) == 0,
        })
    return trends


def detect_narrative_trends(monthly: dict[str, dict], top_n: int = 8) -> list[dict]:
    months = sorted(monthly)
    narrative: list[dict] = []
    for prev, curr in zip(months, months[1:]):
        prev_kw = monthly[prev]["narrative_keywords"]
        curr_kw = monthly[curr]["narrative_keywords"]
        rising = [kw for kw, _ in (curr_kw - prev_kw).most_common(top_n)]
        fading = [kw for kw, _ in (prev_kw - curr_kw).most_common(top_n)]
        stable = [kw for kw, _ in (curr_kw & prev_kw).most_common(top_n)]
        narrative.append({"from": prev, "to": curr, "rising": rising, "fading": fading, "stable": stable})
    return narrative


def top_entities(manifest: Manifest, top_n: int = 10) -> list[tuple[str, int]]:
    counter = Counter()
    for doc in aggregate_documents(manifest):
        structured = _read_structured_output(doc)
        normalized = ((structured.get("extraction") or {}).get("normalized_fields")) or {}
        names = _split_csv(normalized.get("people_departments") or doc.get("people_departments"))
        for name in names:
            counter[name] += 1
    if not counter:
        counter.update(doc.get("category") or "Other" for doc in aggregate_documents(manifest))
    return counter.most_common(top_n)


def detect_anomalies(manifest: Manifest) -> list[dict]:
    issues: list[dict] = []
    monthly = aggregate_cross_month(manifest)
    months = sorted(monthly)
    for idx, month in enumerate(months):
        doc_count = monthly[month]["documents"]
        if idx > 0:
            prev = monthly[months[idx - 1]]["documents"]
            if prev and (doc_count > prev * 2 or doc_count < prev / 2):
                issues.append({
                    "type": "volume_shift",
                    "month": month,
                    "explanation": f"Document volume changed from {prev} to {doc_count}",
                    "sources": monthly[month]["records"][:5],
                })
    for doc in aggregate_documents(manifest):
        if not doc.get("downloaded_filepath"):
            issues.append({
                "type": "missing_file",
                "month": _month_key(doc.get("meeting_date")),
                "explanation": "Document is missing downloaded filepath",
                "sources": [{"meeting_date": doc.get("meeting_date"), "document_title": doc.get("document_title"), "field": "downloaded_filepath"}],
            })
        if doc.get("extraction_status") not in (None, "ok"):
            issues.append({
                "type": "extraction_issue",
                "month": _month_key(doc.get("meeting_date")),
                "explanation": f"Extraction status is {doc.get('extraction_status')}",
                "sources": [{"meeting_date": doc.get("meeting_date"), "document_title": doc.get("document_title"), "field": "extraction_status"}],
            })
    return issues


def generate_trend_report(output_root: Path, manifest: Manifest) -> None:
    regenerate_indexes(output_root, manifest)
    monthly = aggregate_cross_month(manifest)
    trend = {
        "cross_month": monthly,
        "financial_trends": detect_financial_trends(monthly),
        "narrative_trends": detect_narrative_trends(monthly),
        "top_entities": top_entities(manifest),
        "anomalies": detect_anomalies(manifest),
    }
    (output_root / "trend_report.json").write_text(json.dumps(trend, indent=2, sort_keys=True), encoding="utf-8")
