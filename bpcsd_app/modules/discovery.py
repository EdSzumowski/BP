"""
discovery.py — Meeting and report discovery for the BPCSD BoardDocs app.

Discovery pipeline:
1. discover_all_meetings(client)
   → Scrapes the BoardDocs meeting list; returns {ym: {id, label, date, type}}

2. discover_agenda_structure(client, meeting_id)
   → Parses the full agenda into sections with their child items and attachments
   → Returns {section_title: [{item_id, item_title, files: [{url, filename}]}]}

3. build_report_catalog(client, meetings, progress_callback)
   → Runs steps 1-2 for all meetings, then clusters attachments by normalized name
   → Returns the full cross-meeting catalog organized by section → report type → month

Smart clustering:
   "Revenue Status Report December 2024.pdf"  ─┐
   "Revenue Status, October 2025.pdf"          ─┤─→ slug: "revenue_status"
   "Revenue Status Report Jan 2026.pdf"        ─┘

   "NYCLASS Collateral Report December 2024"   ─┐
   "NYCLASS October 2025.pdf"                  ─┴─→ slug: "nyclass"
"""

import re
import time
from collections import defaultdict

# Month names used in filename normalization
_MONTHS = {
    "january":"01","february":"02","march":"03","april":"04",
    "may":"05","june":"06","july":"07","august":"08",
    "september":"09","october":"10","november":"11","december":"12",
    "jan":"01","feb":"02","mar":"03","apr":"04","jun":"06",
    "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12",
}

# Words to strip before clustering (noise words)
_NOISE = {
    "report","boe","board","bpcsd","broadalbin","perth","csd","status","monthly",
    "the","of","from","and","for","by","to","a","an","in","at","on","–","—","-",
    "update","summary","review","memo","meeting","agenda","committee",
}

# Known section title patterns → canonical section key
_SECTION_MAP = [
    (r"finance.?committee",          "Finance Committee"),
    (r"superintendent",              "Report from the Superintendent"),
    (r"elementary.?school",          "Elementary School"),
    (r"secondary.?school|high.?school", "Secondary School"),
    (r"middle.?school",              "Middle School"),
    (r"special.?education",          "Special Education"),
    (r"athletics|health.*phys",      "Athletics & Health"),
    (r"technology",                  "Technology"),
    (r"business.?office",            "Business Office"),
    (r"communications",              "Communications"),
    (r"curriculum",                  "Curriculum"),
    (r"transportation|building",     "Transportation & Buildings"),
    (r"public.?comment",             "Public Comment"),
    (r"consent.?agenda",             "Consent Agenda"),
    (r"new.?business",               "New Business"),
    (r"old.?business",               "Old Business"),
    (r"executive.?session",          "Executive Session"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Discover all meetings
# ─────────────────────────────────────────────────────────────────────────────

def discover_all_meetings(client) -> dict:
    """
    Scrape the BoardDocs meeting list and return:
      { "YYYY-MM": {"id": "...", "label": "...", "date": "YYYY-MM-DD", "type": "regular|reorg|special"} }

    Strategy: BoardDocs exposes a meeting-picker dropdown in the private/edit view.
    We also try the BD-GetMeetingsList endpoint (returns empty on some boards,
    but worth trying). Falls back to known-IDs registry.
    """
    import urllib.request
    import urllib.parse

    meetings = {}

    def _merge(parsed: dict):
        """Merge parsed meetings without clobbering same-month special/reorg meetings."""
        for key, val in parsed.items():
            if key not in meetings:
                meetings[key] = val
                continue

            # Prefer richer labels and preserve unique IDs by adding suffixes.
            existing = meetings[key]
            if existing.get("id") == val.get("id"):
                if len(str(val.get("label", ""))) > len(str(existing.get("label", ""))):
                    meetings[key] = val
                continue

            mtype = val.get("type", "regular")
            candidate = f"{key}-{mtype}"
            i = 2
            while candidate in meetings and meetings[candidate].get("id") != val.get("id"):
                candidate = f"{key}-{mtype}{i}"
                i += 1
            meetings[candidate] = val

    # Try the hidden dropdown used during initial discovery
    # The board's agenda edit page lists all meetings in a <select>
    try:
        req = urllib.request.Request(
            "https://go.boarddocs.com/ny/bpcsd/Board.nsf/BD-GetMeetingsList?open",
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "text/html,*/*",
                "User-Agent": "Mozilla/5.0",
            }
        )
        r = client.opener.open(req, timeout=20)
        html = r.read().decode("utf-8", errors="replace")
        parsed = _parse_meetings_list(html)
        if parsed:
            _merge(parsed)
    except Exception:
        pass

    # Also try the private page which has a meeting selector form
    try:
        req = urllib.request.Request(
            "https://go.boarddocs.com/ny/bpcsd/Board.nsf/Private?open",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        r = client.opener.open(req, timeout=20)
        html = r.read().decode("utf-8", errors="replace")
        parsed = _parse_meetings_list(html)
        if parsed:
            _merge(parsed)
    except Exception:
        pass

    # Try the public meeting selector
    try:
        req = urllib.request.Request(
            "https://go.boarddocs.com/ny/bpcsd/Board.nsf/Public?open",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        r = client.opener.open(req, timeout=20)
        html = r.read().decode("utf-8", errors="replace")
        parsed = _parse_meetings_list(html)
        if parsed:
            _merge(parsed)
    except Exception:
        pass

    # Probe year-specific meeting list variants used by some BoardDocs installs.
    # This improves discovery coverage when default pages only show one year.
    current_year = time.gmtime().tm_year
    for year in range(current_year - 15, current_year + 3):
        probes = [
            ("GET", f"https://go.boarddocs.com/ny/bpcsd/Board.nsf/BD-GetMeetingsList?open&year={year}", None),
            ("GET", f"https://go.boarddocs.com/ny/bpcsd/Board.nsf/BD-GetMeetingsList?open&schoolyear={year}", None),
            ("GET", f"https://go.boarddocs.com/ny/bpcsd/Board.nsf/BD-GetMeetingList?open&year={year}", None),
            ("POST", f"https://go.boarddocs.com/ny/bpcsd/Board.nsf/BD-GetMeetingsList?open", {"year": str(year)}),
            ("POST", f"https://go.boarddocs.com/ny/bpcsd/Board.nsf/BD-GetMeetingsList?open", {"schoolYear": str(year)}),
            ("POST", f"https://go.boarddocs.com/ny/bpcsd/Board.nsf/BD-GetMeetingsList?open", {"schoolyear": str(year)}),
            ("POST", f"https://go.boarddocs.com/ny/bpcsd/Board.nsf/BD-GetMeetingList?open", {"year": str(year)}),
        ]
        for method, url, body in probes:
            try:
                req = urllib.request.Request(
                    url,
                    data=(urllib.parse.urlencode(body).encode() if body else None),
                    headers={
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "text/html,*/*",
                        "User-Agent": "Mozilla/5.0",
                    },
                    method=method,
                )
                r = client.opener.open(req, timeout=20)
                html = r.read().decode("utf-8", errors="replace")
                parsed = _parse_meetings_list(html)
                if parsed:
                    _merge(parsed)
            except Exception:
                continue

    # Seed with known-good IDs so discovery doesn't start from zero
    from modules.registry import KNOWN_MEETINGS
    for ym, info in KNOWN_MEETINGS.items():
        if ym not in meetings:
            _merge({ym: {
                "id":    info["id"],
                "label": info["label"],
                "date":  _ym_to_date(ym),
                "type":  info.get("type", "regular"),
            }})

    return dict(sorted(meetings.items()))


def _parse_meetings_list(html: str) -> dict:
    """
    Extract meeting IDs from HTML that might contain:
      <option value="DCCNK760440C">January 27, 2025 - Regular</option>
      or JSON-like meeting data blocks.
    """
    meetings = {}

    def _insert(ym: str, mtype: str, value: dict):
        key = _meeting_key(ym, mtype, meetings)
        if key in meetings and meetings[key].get("id") != value.get("id"):
            key = _meeting_key(ym, f"{mtype}2", meetings)
        meetings[key] = value

    # Pattern 1: <option value="ID">label</option>
    for m in re.finditer(
        r'value="([A-Z0-9]{10,16})"[^>]*>\s*([^<]{10,80}?)\s*</option>',
        html, re.I
    ):
        mid, label = m.group(1), m.group(2).strip()
        ym = _label_to_ym(label)
        if ym:
            mtype = "reorg" if "reorg" in label.lower() else (
                "special" if "special" in label.lower() else "regular")
            _insert(ym, mtype, {"id": mid, "label": label,
                                "date": _ym_to_date(ym), "type": mtype})

    # Pattern 2: data-meetingid="..." data-date="YYYY-MM-DD"
    for m in re.finditer(
        r'data-meetingid="([A-Z0-9]{10,16})"[^>]*data-date="(\d{4}-\d{2}-\d{2})"',
        html, re.I
    ):
        mid, date = m.group(1), m.group(2)
        ym = date[:7]  # YYYY-MM
        _insert(ym, "regular", {"id": mid, "label": date, "date": date, "type": "regular"})

    # Pattern 3: JSON array [{id: "...", date: "..."}]
    for m in re.finditer(r'"id"\s*:\s*"([A-Z0-9]{10,16})"[^}]*?"date"\s*:\s*"(\d{4}-\d{2}-\d{2})"',
                          html, re.I):
        mid, date = m.group(1), m.group(2)
        ym = date[:7]
        _insert(ym, "regular", {"id": mid, "label": date, "date": date, "type": "regular"})

    # Pattern 4: JSON with m/d/YYYY dates
    for m in re.finditer(r'"id"\s*:\s*"([A-Z0-9]{10,16})"[^}]*?"date"\s*:\s*"(\d{1,2}/\d{1,2}/\d{4})"',
                         html, re.I):
        mid, date = m.group(1), m.group(2)
        mm, _dd, yyyy = date.split("/")
        ym = f"{yyyy}-{int(mm):02d}"
        _insert(ym, "regular", {
            "id": mid,
            "label": date,
            "date": f"{yyyy}-{int(mm):02d}-01",
            "type": "regular"
        })

    return meetings


def _label_to_ym(label: str) -> str | None:
    """'January 27, 2025 - Regular' → '2025-01'"""
    m = re.search(
        r'(January|February|March|April|May|June|July|August|September|October|November|December)'
        r'\s+\d{1,2},?\s+(\d{4})',
        label, re.I
    )
    if m:
        mon = _MONTHS.get(m.group(1).lower(), "01")
        yr = m.group(2)
        return f"{yr}-{mon}"
    # YYYY-MM-DD
    m2 = re.search(r'(\d{4})-(\d{2})-\d{2}', label)
    if m2:
        return f"{m2.group(1)}-{m2.group(2)}"
    return None


def _meeting_key(ym: str, mtype: str, existing: dict) -> str:
    """Return stable key; append suffix for non-regular meetings in same month."""
    if ym not in existing:
        return ym
    if mtype == "regular" and ym in existing:
        return ym

    key = f"{ym}-{mtype}"
    i = 2
    while key in existing:
        key = f"{ym}-{mtype}{i}"
        i += 1
    return key


def _ym_to_date(ym: str) -> str:
    """'2025-01' → '2025-01-01'"""
    return f"{ym}-01" if re.match(r'\d{4}-\d{2}$', ym) else ym


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Parse agenda structure for one meeting
# ─────────────────────────────────────────────────────────────────────────────

def discover_agenda_structure(client, meeting_id: str) -> dict:
    """
    Fetch the agenda for one meeting and return its full section → items → files structure.

    Returns:
    {
      "Finance Committee": {
        "section_id": "DCCNL6604528",
        "items": [
          {"item_id": "...", "title": "...", "files": [{"url": "...", "filename": "..."}]}
        ]
      },
      ...
    }
    """
    from modules.cache import get_cached_agenda, save_cached_agenda

    html = get_cached_agenda(meeting_id)
    if not html:
        html = client.get_agenda(meeting_id)
        save_cached_agenda(meeting_id, html)

    # Parse all items (id, title, indent level) from the agenda HTML
    # BoardDocs uses "level" or "indent" attributes to indicate hierarchy
    raw_items = _parse_agenda_with_levels(html)
    structure = _group_into_sections(raw_items)

    return structure


def _parse_agenda_with_levels(html: str) -> list:
    """
    Return list of {item_id, title, level} from agenda HTML.
    Handles both attribute orderings and level/indent attributes.
    """
    items = []
    seen = set()

    # Try to extract level/indent information
    # Pattern: <li class="level-1" id="..." Xtitle="...">
    # or: <div class="agenda-item level2" data-id="..." data-title="...">
    # or: <tr id="ID" Xtitle="TITLE" Xlevel="1" ...>
    # Fall back to position-based inference if no level attr

    combined_pattern = re.compile(
        r'(?:'
        # With Xlevel
        r'id="([A-Z0-9]{10,16})"[^>]*?Xtitle="([^"]*)"[^>]*?(?:Xlevel|level)="(\d+)"'
        r'|'
        r'(?:Xlevel|level)="(\d+)"[^>]*?id="([A-Z0-9]{10,16})"[^>]*?Xtitle="([^"]*)"'
        r'|'
        # Without level (fall back to order)
        r'id="([A-Z0-9]{10,16})"[^>]*?Xtitle="([^"]*)"'
        r'|'
        r'Xtitle="([^"]*)"[^>]*?id="([A-Z0-9]{10,16})"'
        r')',
        re.I
    )

    for m in combined_pattern.finditer(html):
        g = m.groups()
        if g[0] and g[1]:  # id before Xtitle, with level
            iid, title, level = g[0], g[1], int(g[2] or 1)
        elif g[4] and g[5]:  # level before id
            iid, title, level = g[4], g[5], int(g[3] or 1)
        elif g[6] and g[7]:  # no level, id before Xtitle
            iid, title, level = g[6], g[7], None
        elif g[8] and g[9]:  # no level, Xtitle before id
            iid, title, level = g[9], g[8], None
        else:
            continue

        if iid in seen:
            continue
        seen.add(iid)
        items.append({"item_id": iid, "title": title.strip(), "level": level})

    return items


def _group_into_sections(raw_items: list) -> dict:
    """
    Heuristically group items into sections.
    Items whose title matches a known section pattern are section headers;
    the rest are child items until the next section.
    """
    sections = {}
    current_section = "General"

    for item in raw_items:
        title = item["title"]
        level = item.get("level")
        # Check if this item is a section header
        canonical = _canonicalize_section(title, level)
        if canonical:
            current_section = canonical
            if current_section not in sections:
                sections[current_section] = {"section_id": item["item_id"], "items": []}
        else:
            # It's a child item
            if current_section not in sections:
                sections[current_section] = {"section_id": None, "items": []}
            sections[current_section]["items"].append({
                "item_id": item["item_id"],
                "title":   title,
                "files":   [],  # filled in during catalog build
            })

    # Remove sections with no items (headers only)
    return {k: v for k, v in sections.items() if v["items"]}


def _canonicalize_section(title: str, level: int | None = None) -> str | None:
    """Return canonical section name if title looks like a section header, else None."""
    if level is not None and level >= 2:
        return None

    # Skip long, code-heavy agenda items that are likely reports/motions, not sections.
    if len(title) > 70:
        return None
    if re.search(r"\b\d{3,}\b", title):
        return None

    t = title.lower()
    for pattern, canonical in _SECTION_MAP:
        if re.search(pattern, t):
            return canonical
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Normalize filenames and cluster into report types
# ─────────────────────────────────────────────────────────────────────────────

def normalize_filename(filename: str) -> tuple[str, str | None]:
    """
    Strip dates, months, years, and noise words from a PDF filename.
    Returns (slug, detected_data_ym) where slug is a short lowercase identifier.

    Examples:
      "Revenue Status Report December 2024.pdf"  → ("revenue_status", "2024-12")
      "NYCLASS October 2025.pdf"                 → ("nyclass", "2025-10")
      "M & T Collateral, October 2025.pdf"       → ("mt_collateral", "2025-10")
    """
    # Remove extension
    name = re.sub(r'\.pdf$', '', filename, flags=re.I).strip()

    # Detect data month/year in the filename
    data_ym = None
    month_m = re.search(
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December'
        r'|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b\s*,?\s*(\d{4})\b',
        name, re.I
    )
    if month_m:
        mon_str = month_m.group(1).lower()
        mon_num = _MONTHS.get(mon_str, "01")
        data_ym = f"{month_m.group(2)}-{mon_num}"

    # Strip dates, month names, years from the name
    name = re.sub(
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December'
        r'|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b',
        '', name, flags=re.I
    )
    name = re.sub(r'\b(20\d{2}|19\d{2})\b', '', name)
    name = re.sub(r'\b\d{1,2}\b', '', name)  # stray day numbers

    # Lowercase, strip punctuation, strip noise words
    name = re.sub(r'[^a-z0-9\s]', ' ', name.lower())
    words = [w for w in name.split() if w and w not in _NOISE]

    slug = "_".join(words[:4]) if words else "unknown"
    return slug, data_ym


def _similarity(a: str, b: str) -> float:
    """Simple word-overlap similarity between two slugs."""
    wa = set(a.split("_"))
    wb = set(b.split("_"))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def cluster_filenames(filenames: list[str], threshold: float = 0.5) -> dict[str, list[str]]:
    """
    Group filenames into clusters by normalized slug similarity.
    Returns {canonical_slug: [filename, ...]}
    """
    slug_map = {}
    for fn in filenames:
        slug, _ = normalize_filename(fn)
        slug_map[fn] = slug

    clusters = {}  # canonical_slug → [filename]
    slug_to_canonical = {}

    for fn, slug in slug_map.items():
        # Find best matching existing cluster
        best_match = None
        best_score = 0.0
        for canon in clusters:
            score = _similarity(slug, canon)
            if score > best_score:
                best_score = score
                best_match = canon

        if best_match and best_score >= threshold:
            clusters[best_match].append(fn)
        else:
            clusters[slug] = [fn]

    return clusters


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Full catalog build
# ─────────────────────────────────────────────────────────────────────────────

def build_report_catalog(client, meetings: dict,
                          progress_callback=None) -> dict:
    """
    For every meeting, discover its agenda structure and collect all attachments.
    Then cluster attachments by normalized filename across all meetings.

    Returns catalog:
    {
      "Finance Committee": {
        "revenue_status": {
          "label":    "Revenue Status",
          "section":  "Finance Committee",
          "meetings": {
            "2025-01": {"url": "...", "filename": "...", "data_ym": "2024-12"},
            ...
          }
        },
        ...
      },
      "Report from the Superintendent": { ... },
      ...
    }
    """
    from modules.cache import get_cached_structure, save_cached_structure

    # Phase 1: collect all (section, filename, url, ym) tuples
    all_files = []  # [{section, item_title, filename, url, meeting_ym}]
    total = len(meetings)

    for i, (ym, info) in enumerate(sorted(meetings.items())):
        if progress_callback:
            progress_callback(i, total, f"Scanning {info.get('label', ym)}…")

        mid = info["id"]

        # Try cache first
        structure = get_cached_structure(mid)
        if not structure:
            try:
                structure = discover_agenda_structure(client, mid)
                save_cached_structure(mid, structure)
            except Exception as e:
                structure = {}

        # Collect files — for Finance Committee, hit BD-GetPublicFiles on the section item
        for section_name, sec_data in structure.items():
            for item in sec_data.get("items", []):
                item_id = item["item_id"]
                item_title = item["title"]

                # Get files for this item
                try:
                    files = client.get_item_files(item_id)
                    for url, filename in files:
                        _, data_ym = normalize_filename(filename)
                        all_files.append({
                            "section":     section_name,
                            "item_title":  item_title,
                            "filename":    filename,
                            "url":         url,
                            "meeting_ym":  ym,
                            "data_ym":     data_ym or ym,
                        })
                except Exception:
                    pass

                time.sleep(0.1)  # be polite

        # Special-case: Finance Committee section_id itself may have files
        for section_name, sec_data in structure.items():
            if "finance" in section_name.lower() and sec_data.get("section_id"):
                try:
                    files = client.get_item_files(sec_data["section_id"])
                    for url, filename in files:
                        _, data_ym = normalize_filename(filename)
                        all_files.append({
                            "section":     section_name,
                            "item_title":  "Finance Committee",
                            "filename":    filename,
                            "url":         url,
                            "meeting_ym":  ym,
                            "data_ym":     data_ym or ym,
                        })
                except Exception:
                    pass

    if progress_callback:
        progress_callback(total, total, "Clustering report types…")

    # Phase 2: cluster by section + normalized slug
    # Group files by section first
    by_section = defaultdict(list)
    for f in all_files:
        by_section[f["section"]].append(f)

    catalog = {}
    for section, files in by_section.items():
        section_catalog = {}

        # Cluster filenames within this section
        filenames = [f["filename"] for f in files]
        clusters = cluster_filenames(filenames)

        for slug, clustered_fnames in clusters.items():
            # Representative label: longest common non-noise prefix
            label = _make_label(clustered_fnames)
            meeting_data = {}

            for f in files:
                if f["filename"] in clustered_fnames:
                    meeting_ym = f["meeting_ym"]
                    # If multiple files match same slug in same meeting, keep largest
                    if meeting_ym not in meeting_data:
                        meeting_data[meeting_ym] = f
                    # else keep existing

            if meeting_data:
                section_catalog[slug] = {
                    "label":    label,
                    "section":  section,
                    "meetings": {ym: {"url": d["url"], "filename": d["filename"],
                                      "data_ym": d["data_ym"], "item_title": d["item_title"]}
                                  for ym, d in meeting_data.items()},
                }

        if section_catalog:
            catalog[section] = section_catalog

    return catalog


def _make_label(filenames: list[str]) -> str:
    """Derive a human-readable label from a cluster of filenames."""
    # Use the normalized slug words from the longest filename
    longest = max(filenames, key=len)
    slug, _ = normalize_filename(longest)
    words = [w.capitalize() for w in slug.split("_") if w]
    return " ".join(words) if words else longest[:40]


# ─────────────────────────────────────────────────────────────────────────────
# Catalog helpers (used by app.py)
# ─────────────────────────────────────────────────────────────────────────────

def get_catalog_months(catalog: dict) -> list[str]:
    """Return all unique meeting_ym values across the catalog, sorted."""
    months = set()
    for section in catalog.values():
        for report in section.values():
            months.update(report.get("meetings", {}).keys())
    return sorted(months)


def get_catalog_fiscal_years(catalog: dict) -> list[str]:
    """Infer fiscal years (Jul-Jun) from catalog months."""
    months = get_catalog_months(catalog)
    fiscal_years = set()
    for ym in months:
        yr, mo = int(ym[:4]), int(ym[5:7])
        if mo >= 7:
            fiscal_years.add(f"{yr}-{str(yr+1)[2:]}")
        else:
            fiscal_years.add(f"{yr-1}-{str(yr)[2:]}")
    return sorted(fiscal_years, reverse=True)
