import os
import json
import hashlib
from pathlib import Path

# Use a path relative to this file so it works anywhere (local, Streamlit Cloud, etc.)
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def cache_key(*parts):
    return hashlib.md5("_".join(str(p) for p in parts).encode()).hexdigest()[:12]


def get_cached_text(report_type, meeting_ym, item_id):
    p = CACHE_DIR / f"{report_type}_{meeting_ym}_{item_id}.txt"
    if p.exists():
        return p.read_text()
    return None


def save_cached_text(report_type, meeting_ym, item_id, text):
    p = CACHE_DIR / f"{report_type}_{meeting_ym}_{item_id}.txt"
    p.write_text(text)


def get_cached_item_id(meeting_ym, report_type):
    p = CACHE_DIR / f"itemid_{meeting_ym}_{report_type}.json"
    if p.exists():
        return json.loads(p.read_text()).get("item_id")
    return None


def save_cached_item_id(meeting_ym, report_type, item_id):
    p = CACHE_DIR / f"itemid_{meeting_ym}_{report_type}.json"
    p.write_text(json.dumps({"item_id": item_id}))


def list_cached_reports():
    """Return set of (report_type, meeting_ym) tuples that are cached."""
    cached = set()
    for f in CACHE_DIR.glob("*.txt"):
        parts = f.stem.split("_")
        if len(parts) >= 3:
            cached.add((parts[0], parts[1]))
    return cached


def get_cached_agenda(meeting_id):
    """Cache raw agenda HTML to avoid repeated fetches."""
    p = CACHE_DIR / f"agenda_{meeting_id}.html"
    if p.exists():
        return p.read_text()
    return None


def save_cached_agenda(meeting_id, html):
    p = CACHE_DIR / f"agenda_{meeting_id}.html"
    p.write_text(html)


def clear_cache():
    """Clear all cached files."""
    for f in CACHE_DIR.glob("*"):
        f.unlink()
