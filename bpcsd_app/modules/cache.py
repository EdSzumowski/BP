"""
cache.py — File-based cache for BPCSD BoardDocs app.

Cache layout under CACHE_DIR:
  text/<report_type>/<meeting_ym>.txt        — extracted PDF text
  agenda/<meeting_id>.html                   — raw agenda HTML
  discovery/meetings.json                    — discovered meeting list
  discovery/structure_<meeting_id>.json      — parsed agenda structure per meeting
  discovery/report_catalog.json             — full cross-meeting report catalog
"""

import os
import json
import time
import hashlib
from pathlib import Path
from datetime import datetime

# Relative to this file so it works anywhere (local, Streamlit Cloud, etc.)
CACHE_DIR = Path(__file__).parent.parent / "cache"


def _ensure(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Report text cache  (extracted PDF text)
# ─────────────────────────────────────────────────────────────────────────────

def _text_path(report_type: str, meeting_ym: str) -> Path:
    return CACHE_DIR / "text" / report_type / f"{meeting_ym}.txt"


def get_cached_text(report_type, meeting_ym, _legacy_item_id=None):
    """Return cached extracted text, or None."""
    p = _text_path(report_type, meeting_ym)
    if p.exists():
        return p.read_text(encoding="utf-8")
    # Legacy fallback: old flat-file names (report_type_meeting_ym_item_id.txt)
    if _legacy_item_id:
        legacy = CACHE_DIR / f"{report_type}_{meeting_ym}_{_legacy_item_id}.txt"
        if legacy.exists():
            return legacy.read_text(encoding="utf-8")
    return None


def save_cached_text(report_type, meeting_ym, _legacy_item_id, text: str):
    """Save extracted text. (legacy_item_id kept for backward compat, ignored here)"""
    p = _ensure(_text_path(report_type, meeting_ym))
    p.write_text(text, encoding="utf-8")


def delete_cached_text(report_type: str, meeting_ym: str) -> bool:
    """Delete a specific cached text entry. Returns True if deleted."""
    p = _text_path(report_type, meeting_ym)
    if p.exists():
        p.unlink()
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Legacy item-ID cache (no longer needed by the two-path boarddocs client,
# but kept so old cached entries aren't broken)
# ─────────────────────────────────────────────────────────────────────────────

def get_cached_item_id(meeting_ym, report_type):
    p = CACHE_DIR / f"itemid_{meeting_ym}_{report_type}.json"
    if p.exists():
        return json.loads(p.read_text()).get("item_id")
    return None


def save_cached_item_id(meeting_ym, report_type, item_id):
    p = CACHE_DIR / f"itemid_{meeting_ym}_{report_type}.json"
    _ensure(p)
    p.write_text(json.dumps({"item_id": item_id}))


# ─────────────────────────────────────────────────────────────────────────────
# Agenda HTML cache
# ─────────────────────────────────────────────────────────────────────────────

def get_cached_agenda(meeting_id: str):
    p = CACHE_DIR / "agenda" / f"{meeting_id}.html"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def save_cached_agenda(meeting_id: str, html: str):
    p = _ensure(CACHE_DIR / "agenda" / f"{meeting_id}.html")
    p.write_text(html, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Discovery cache  (meeting list, agenda structure, report catalog)
# ─────────────────────────────────────────────────────────────────────────────

def get_cached_meetings() -> dict | None:
    """Return {ym: {id, label, type, date}} or None."""
    p = CACHE_DIR / "discovery" / "meetings.json"
    if p.exists():
        data = json.loads(p.read_text())
        return data.get("meetings")
    return None


def save_cached_meetings(meetings: dict):
    p = _ensure(CACHE_DIR / "discovery" / "meetings.json")
    p.write_text(json.dumps({"meetings": meetings, "saved_at": time.time()}, indent=2))


def get_cached_structure(meeting_id: str) -> dict | None:
    """Return parsed agenda structure for one meeting, or None."""
    p = CACHE_DIR / "discovery" / "structure" / f"{meeting_id}.json"
    if p.exists():
        return json.loads(p.read_text())
    return None


def save_cached_structure(meeting_id: str, structure: dict):
    p = _ensure(CACHE_DIR / "discovery" / "structure" / f"{meeting_id}.json")
    p.write_text(json.dumps(structure, indent=2))


def get_report_catalog() -> dict | None:
    """
    Return the full cross-meeting report catalog, or None.
    Format: { report_slug: {label, section, meetings: {ym: {url, filename}}} }
    """
    p = CACHE_DIR / "discovery" / "report_catalog.json"
    if p.exists():
        data = json.loads(p.read_text())
        # Invalidate if older than 12 hours
        if time.time() - data.get("saved_at", 0) < 43200:
            return data.get("catalog")
    return None


def save_report_catalog(catalog: dict):
    p = _ensure(CACHE_DIR / "discovery" / "report_catalog.json")
    p.write_text(json.dumps({"catalog": catalog, "saved_at": time.time()}, indent=2))


# ─────────────────────────────────────────────────────────────────────────────
# Cache inventory  (for the cache management UI)
# ─────────────────────────────────────────────────────────────────────────────

def list_cached_reports():
    """Return set of (report_type, meeting_ym) tuples for the legacy API."""
    cached = set()
    for f in CACHE_DIR.glob("*.txt"):
        parts = f.stem.split("_")
        if len(parts) >= 3:
            cached.add((parts[0], parts[1]))
    # Also new-style
    text_dir = CACHE_DIR / "text"
    if text_dir.exists():
        for rtype_dir in text_dir.iterdir():
            if rtype_dir.is_dir():
                for f in rtype_dir.glob("*.txt"):
                    cached.add((rtype_dir.name, f.stem))
    return cached


def get_cache_inventory() -> list[dict]:
    """
    Return a list of dicts describing every cached text entry:
      {report_type, meeting_ym, path, size_kb, age_hours, modified_ts}
    Sorted newest-first.
    """
    items = []

    # New-style: cache/text/<report_type>/<ym>.txt
    text_dir = CACHE_DIR / "text"
    if text_dir.exists():
        for rtype_dir in text_dir.iterdir():
            if not rtype_dir.is_dir():
                continue
            for f in rtype_dir.glob("*.txt"):
                stat = f.stat()
                items.append({
                    "report_type": rtype_dir.name,
                    "meeting_ym":  f.stem,
                    "path":        str(f),
                    "size_kb":     round(stat.st_size / 1024, 1),
                    "age_hours":   round((time.time() - stat.st_mtime) / 3600, 1),
                    "modified_ts": stat.st_mtime,
                    "style":       "new",
                })

    # Legacy flat files: cache/<report_type>_<ym>_<itemid>.txt
    for f in CACHE_DIR.glob("*.txt"):
        parts = f.stem.split("_")
        if len(parts) >= 3:
            stat = f.stat()
            items.append({
                "report_type": parts[0],
                "meeting_ym":  f"{parts[1]}_{parts[2]}" if len(parts) >= 4 else parts[1],
                "path":        str(f),
                "size_kb":     round(stat.st_size / 1024, 1),
                "age_hours":   round((time.time() - stat.st_mtime) / 3600, 1),
                "modified_ts": stat.st_mtime,
                "style":       "legacy",
            })

    items.sort(key=lambda x: x["modified_ts"], reverse=True)
    return items


def delete_cache_entry(path: str) -> bool:
    """Delete a cache file by its absolute path."""
    p = Path(path)
    if p.exists() and str(p).startswith(str(CACHE_DIR)):
        p.unlink()
        return True
    return False


def get_cache_stats() -> dict:
    """Return summary stats for the cache manager UI."""
    inventory = get_cache_inventory()
    total_size = sum(CACHE_DIR.rglob("*") and [0])  # fallback
    try:
        total_bytes = sum(f.stat().st_size for f in CACHE_DIR.rglob("*") if f.is_file())
    except Exception:
        total_bytes = 0

    catalog = get_report_catalog()
    meetings = get_cached_meetings()

    return {
        "text_entries":    len(inventory),
        "total_size_kb":   round(total_bytes / 1024, 1),
        "meetings_cached": len(meetings) if meetings else 0,
        "catalog_ready":   catalog is not None,
        "inventory":       inventory,
    }


def clear_discovery_cache():
    """Clear only the discovery cache (meetings + catalog), keep text."""
    for p in (CACHE_DIR / "discovery").rglob("*"):
        if p.is_file():
            p.unlink()


def clear_all_cache():
    """Nuke everything."""
    import shutil
    for child in CACHE_DIR.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


# Backward-compat alias
clear_cache = clear_all_cache
