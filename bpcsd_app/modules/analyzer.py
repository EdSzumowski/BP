"""
analyzer.py — Rich analysis engine for BPCSD reports.

Finance reports  → Parse the structured ledger tables line-by-line;
                   extract totals, collection rates, and flags.
Director reports → Extract actual narrative content: specific numbers,
                   sports results, programs, achievements, concerns.
Both             → Support trend analysis and year-over-year comparison.
"""

import re
from collections import defaultdict


# ─────────────────────────────────────────────────────────────────────────────
# Shared utilities
# ─────────────────────────────────────────────────────────────────────────────

def _parse_dollar(s):
    """'1,234,567.89' or '-1,234.56' → float."""
    try:
        return float(str(s).strip().replace(",", "").replace("$", "").replace("(", "-").replace(")", ""))
    except (ValueError, AttributeError):
        return 0.0


def _fmt_dollar(v, show_cents=False):
    """float → '$1,234,567' or '($1,234,567)' for negatives."""
    if v is None:
        return "—"
    neg = v < 0
    fmt = f"${abs(v):,.2f}" if show_cents else f"${abs(v):,.0f}"
    return f"({fmt})" if neg else fmt


def _fmt_pct(v):
    if v is None:
        return "—"
    return f"{v:.1f}%"


def _delta_str(old, new):
    """Return a formatted delta like '+$123,456 (+5.2%)'."""
    if old is None or new is None or old == 0:
        return ""
    delta = new - old
    pct = delta / abs(old) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{_fmt_dollar(delta)} ({sign}{pct:.1f}%)"


# ─────────────────────────────────────────────────────────────────────────────
# Revenue Status (and similar structured financial reports) parser
# ─────────────────────────────────────────────────────────────────────────────

# The Revenue Status report format (from pdfplumber text extraction):
# A 1001 PROPERTY TAXES 15,300,000.00 119,822.22 15,419,822.22 14,401,666.17 1,018,156.05
#
# Columns: Account | Description | Budget | Adjustments | Revised Budget | Revenue Earned | Unearned Revenue

_ACCOUNT_LINE = re.compile(
    r"(A\s+\d{4}(?:\.[A-Z0-9])?)\s+"          # Account code
    r"([A-Z][A-Z0-9 &\'/\-\.]+?)\s+"           # Description (all caps)
    r"([\-\d,]+\.\d{2})\s+"                     # Budget
    r"([\-\d,]+\.\d{2})\s+"                     # Adjustments
    r"([\-\d,]+\.\d{2})\s+"                     # Revised Budget
    r"([\-\d,]+\.\d{2})\s+"                     # Revenue Earned
    r"([\-\d,]+\.\d{2})"                         # Unearned Revenue
)

_TOTAL_LINE = re.compile(
    # Matches "A Totals:", "Grand Totals:", "Total Revenue", etc.
    r"(?:A\s+Totals|Grand\s+Totals|Total\s+Revenue)\s*:?\s+"
    r"([\d,]+\.\d{2})\s+"
    r"([\-\d,]+\.\d{2})\s+"
    r"([\d,]+\.\d{2})\s+"
    r"([\d,]+\.\d{2})\s+"
    r"([\-\d,]+\.\d{2})",
    re.I
)

_DATE_HEADER = re.compile(r"From\s+([\d/]+)\s+To\s+([\d/]+)")


def parse_revenue_status(text):
    """
    Parse Revenue Status Report text.
    Returns (items_list, totals_dict, date_range_str).

    items_list: [{account, description, budget, adjustments, revised_budget,
                  earned, unearned, pct_collected}, ...]
    totals_dict: {budget, adjustments, revised_budget, earned, unearned, pct_collected}
    """
    if not text:
        return [], {}, ""

    date_m = _DATE_HEADER.search(text)
    date_range = date_m.group(0) if date_m else ""

    # Totals
    totals = {}
    tm = _TOTAL_LINE.search(text)
    if tm:
        totals = {
            "budget":         _parse_dollar(tm.group(1)),
            "adjustments":    _parse_dollar(tm.group(2)),
            "revised_budget": _parse_dollar(tm.group(3)),
            "earned":         _parse_dollar(tm.group(4)),
            "unearned":       _parse_dollar(tm.group(5)),
        }
        if totals.get("revised_budget"):
            totals["pct_collected"] = totals["earned"] / totals["revised_budget"] * 100
        else:
            totals["pct_collected"] = None

    # Line items
    items = []
    for m in _ACCOUNT_LINE.finditer(text):
        acc      = re.sub(r"\s+", " ", m.group(1)).strip()
        desc     = re.sub(r"\s+", " ", m.group(2)).strip().rstrip("-").strip()
        budget   = _parse_dollar(m.group(3))
        adj      = _parse_dollar(m.group(4))
        rev_bud  = _parse_dollar(m.group(5))
        earned   = _parse_dollar(m.group(6))
        unearned = _parse_dollar(m.group(7))
        pct      = (earned / rev_bud * 100) if rev_bud else None
        items.append({
            "account": acc, "description": desc,
            "budget": budget, "adjustments": adj,
            "revised_budget": rev_bud,
            "earned": earned, "unearned": unearned,
            "pct_collected": pct,
        })

    return items, totals, date_range


# ─────────────────────────────────────────────────────────────────────────────
# Finance trend analysis
# ─────────────────────────────────────────────────────────────────────────────

def analyze_finance_trend(month_texts: dict) -> dict:
    """
    Full multi-month finance trend analysis.
    month_texts: {month_name: extracted_text}

    Returns:
        summary, flags, collection_table, line_items, month_summaries,
        notable_items, raw_months
    """
    # Parse every month
    parsed = {}
    for month, text in month_texts.items():
        if not text:
            parsed[month] = None
            continue
        items, totals, date_range = parse_revenue_status(text)
        parsed[month] = {
            "items": items, "totals": totals,
            "date_range": date_range, "text": text,
        }

    available_months = [m for m, v in parsed.items() if v is not None]
    missing_months   = [m for m, v in parsed.items() if v is None]

    # ── Collection rate table ─────────────────────────────────────────────────
    collection_table = []
    for month in available_months:
        t = parsed[month]["totals"]
        if not t:
            continue
        collection_table.append({
            "month":   month,
            "budget":  t.get("revised_budget", 0),
            "earned":  t.get("earned", 0),
            "pct":     t.get("pct_collected"),
            "date_range": parsed[month]["date_range"],
        })

    # ── Line-item cross-month tracking ────────────────────────────────────────
    # Gather all unique accounts and their data per month
    all_accounts = {}  # account → description
    for month in available_months:
        for item in parsed[month]["items"]:
            if item["account"] not in all_accounts:
                all_accounts[item["account"]] = item["description"]

    line_items = {}  # account → {description, monthly: {month: {earned, pct, budget}}}
    for acc, desc in all_accounts.items():
        monthly = {}
        for month in available_months:
            match = next((i for i in parsed[month]["items"] if i["account"] == acc), None)
            if match:
                monthly[month] = {
                    "earned":  match["earned"],
                    "pct":     match["pct_collected"],
                    "budget":  match["revised_budget"],
                    "unearned": match["unearned"],
                }
        line_items[acc] = {"description": desc, "monthly": monthly}

    # ── Flags ─────────────────────────────────────────────────────────────────
    flags = []

    if missing_months:
        flags.append({"priority": "medium", "item": "Missing Reports",
                      "observation": f"No data for: {', '.join(missing_months)}"})

    # Collection rate trend
    if len(collection_table) >= 2:
        rates = [r["pct"] for r in collection_table if r["pct"] is not None]
        if len(rates) >= 2:
            first_r = collection_table[0]
            last_r  = collection_table[-1]
            # Check pace vs prior periods
            if last_r["pct"] is not None and first_r["pct"] is not None:
                pace_change = last_r["pct"] - first_r["pct"]
                # Compare to expected linear pace
                pass

    # Per-line anomalies
    for acc, data in line_items.items():
        desc    = data["description"]
        monthly = data["monthly"]
        months  = list(monthly.keys())
        if not months:
            continue

        last_m   = months[-1]
        last_d   = monthly[last_m]
        earned   = last_d["earned"]
        pct      = last_d["pct"]
        budget   = last_d["budget"]

        # Over-budget (>115%) with meaningful amount
        if pct and pct > 115 and earned > 25_000:
            flags.append({
                "priority": "high",
                "item": f"{acc} — {desc}",
                "observation": (
                    f"Over budget: {_fmt_pct(pct)} collected as of {last_m} "
                    f"({_fmt_dollar(earned)} earned vs {_fmt_dollar(budget)} budget)."
                )
            })
        # Unbudgeted but significant
        elif budget == 0 and earned > 50_000:
            flags.append({
                "priority": "high",
                "item": f"{acc} — {desc}",
                "observation": (
                    f"UNBUDGETED: {_fmt_dollar(earned)} received with no budget allocation."
                )
            })

        # Large single-month jump (not just cumulative growth)
        if len(months) >= 2:
            prev_m = months[-2]
            prev_e = monthly[prev_m]["earned"]
            jump   = earned - prev_e
            if prev_e > 0 and jump > prev_e and jump > 150_000:
                flags.append({
                    "priority": "medium",
                    "item": f"{acc} — {desc}",
                    "observation": (
                        f"Large receipt jump {prev_m}→{last_m}: "
                        f"{_fmt_dollar(prev_e)} → {_fmt_dollar(earned)} "
                        f"(+{_fmt_dollar(jump)} in a single period)."
                    )
                })

        # Consistently lagging: <30% at or after mid-year (flag if latest ≥ Oct)
        LATE_MONTHS = {"November", "December", "January", "February",
                       "March", "April", "May", "June"}
        if last_m in LATE_MONTHS and pct is not None and pct < 30 and budget > 100_000:
            flags.append({
                "priority": "medium",
                "item": f"{acc} — {desc}",
                "observation": (
                    f"Low collection rate in {last_m}: only {_fmt_pct(pct)} of "
                    f"{_fmt_dollar(budget)} budget collected. "
                    f"May indicate delayed payments or unearned allocation."
                )
            })

    # Sort: high first
    priority_order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: priority_order.get(f["priority"], 3))

    # ── Notable items ─────────────────────────────────────────────────────────
    # Top earners and top laggards in most recent month
    notable_items = []
    if available_months:
        last_month = available_months[-1]
        items_last = parsed[last_month]["items"]
        # Sort by earned descending
        by_earned = sorted(items_last, key=lambda i: i["earned"], reverse=True)
        notable_items = by_earned[:10]  # top 10 earners

    # ── Summary narrative ─────────────────────────────────────────────────────
    if collection_table:
        first = collection_table[0]
        last  = collection_table[-1]
        budget_str  = _fmt_dollar(last["budget"])
        earned_str  = _fmt_dollar(last["earned"])
        pct_str     = _fmt_pct(last["pct"])
        first_pct   = _fmt_pct(first["pct"])
        summary = (
            f"Analysis spans {len(available_months)} months of data "
            f"({first['month']} through {last['month']}). "
            f"As of {last['month']}, the district has collected {earned_str} "
            f"against a {budget_str} revised budget ({pct_str} collection rate). "
            f"Collection rate has moved from {first_pct} at the start of the tracked period "
            f"to {pct_str} at the latest report."
        )
    else:
        summary = f"Finance data extracted from {len(available_months)} months."

    # Build month_summaries (used by app.py display and PDF builder)
    month_summaries = {}
    for month in month_texts.keys():
        if parsed.get(month) is None:
            month_summaries[month] = {"status": "no_data"}
            continue
        t = parsed[month]["totals"]
        month_summaries[month] = {
            "status":       "extracted",
            "text_length":  len(parsed[month]["text"]),
            "budget":       t.get("revised_budget"),
            "earned":       t.get("earned"),
            "pct":          t.get("pct_collected"),
            "date_range":   parsed[month]["date_range"],
            "item_count":   len(parsed[month]["items"]),
        }

    return {
        "summary":          summary,
        "flags":            flags,
        "collection_table": collection_table,
        "line_items":       line_items,
        "notable_items":    notable_items,
        "month_summaries":  month_summaries,
        "raw_months":       month_texts,
        "parsed":           parsed,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Director (narrative) report analysis
# ─────────────────────────────────────────────────────────────────────────────

# Numbers/stats typically found in director reports
_NUMBER_PATTERNS = [
    (r"(\d[\d,]*)\s+student.?athletes?",    "Student athletes"),
    (r"(\d[\d,]*)\s+students?\s+(?:who\s+)?(?:participated?|registered?|enrolled?|attended?)", "Students participating"),
    (r"(\d[\d,]*)\s+(?:players?|kids?|children|participants?)", "Participants"),
    (r"(\d+)\s*[-–]\s*(\d+)\s+(?:league\s+)?record",          "Win-loss record"),
    (r"\$[\d,]+(?:\.\d{2})?",                                  "Dollar amount"),
    (r"(\d[\d,]*)\s+(?:class(?:rooms?)?|section)",             "Classes/sections"),
    (r"(\d+(?:\.\d+)?)\s*%",                                   "Percentage"),
]

_TOPIC_KEYWORDS = {
    "Sports / Athletics": [
        r"\bsport\b", r"\bsectional\b", r"\bvarsity\b", r"\bJV\b", r"\bmodified\b",
        r"\bseason\b", r"\bleague\b", r"\bgame\b", r"\bmatch\b", r"\btournament\b",
        r"\bchampionship\b", r"\bcoach\b", r"\bathlet", r"\bpool\b",
    ],
    "Academics / Assessment": [
        r"\bacadem\b", r"\bassessment\b", r"\bbenchmark\b", r"\biReady\b",
        r"\bstate test\b", r"\bELA\b", r"\bmath\b", r"\bNYS\b", r"\bgrades?\b",
        r"\bGPA\b", r"\bapprenticeship\b", r"\bhonor roll\b",
    ],
    "Enrollment": [
        r"\benroll\b", r"\bregistration\b", r"\bPreK\b", r"\bkindergarten\b",
        r"\bstudent count\b", r"\bheadcount\b",
    ],
    "Clubs / Student Life": [
        r"\bclub\b", r"\bstudent council\b", r"\bleadership\b", r"\bhomecoming\b",
        r"\bdance\b", r"\bprom\b", r"\bNational Honor\b", r"\bNHS\b",
    ],
    "PBIS / Culture": [
        r"\bPBIS\b", r"\bCore Connect\b", r"\bPatriot Buck\b", r"\bpep rally\b",
        r"\bculture\b", r"\bclimate\b", r"\bwellness\b",
    ],
    "Community / Fundraising": [
        r"\bPTO\b", r"\bfundrais\b", r"\bdonat\b", r"\bcommunity\b",
        r"\bSpecial Olympics\b", r"\bcharity\b", r"\braised\b",
    ],
    "Safety / Facilities": [
        r"\bsafety\b", r"\bdrill\b", r"\blockdown\b", r"\bfire drill\b",
        r"\bsecurit\b", r"\bconstruction\b", r"\brenovation\b",
        r"\bplayground\b", r"\bfacility\b",
    ],
    "Summer Program": [
        r"\bsummer\b", r"\bcamp\b", r"\bESY\b", r"\bProject Summer\b",
    ],
    "Professional Development": [
        r"\bprofessional development\b", r"\bPD day\b", r"\btraining\b",
        r"\bworkshop\b", r"\bconference\b",
    ],
    "Technology": [
        r"\btechnolog\b", r"\bChromebook\b", r"\bdevice\b", r"\b1:1\b",
        r"\bdigital\b", r"\bcomputer\b",
    ],
    "Drama / Arts": [
        r"\bdrama\b", r"\bconcert\b", r"\bmusical\b", r"\bperformance\b",
        r"\bband\b", r"\bchorus\b", r"\bsshow\b",
    ],
    "Special Education": [
        r"\bIEP\b", r"\bspecial ed\b", r"\b504\b", r"\bCPSE\b", r"\bCSE\b",
        r"\binclusion\b", r"\bparaprofessional\b",
    ],
    "New Program / Initiative": [
        r"\bnew program\b", r"\bnew initiative\b", r"\bnewly added\b",
        r"\bfirst time\b", r"\bintroducing\b", r"\bbrand new\b", r"\blaunched?\b",
    ],
}


def _extract_sentences_matching(text, pattern):
    """Return up to 3 content sentences from text that match the pattern."""
    SKIP_PAT = re.compile(
        r"^\s*(?:TO:|FROM:|RE:|DATE:|[A-Za-z.\s]+@[a-z]+\.[a-z]+)", re.I
    )
    results = []
    for sent in re.split(r"(?<=[.!?])\s+|\n(?=[A-Z])", text):
        sent = sent.strip()
        if len(sent) < 25:
            continue
        if SKIP_PAT.match(sent):
            continue
        if re.search(pattern, sent, re.I):
            results.append(sent[:250])
        if len(results) >= 3:
            break
    return results


def _extract_numbers_with_context(text):
    """Pull out specific numeric facts from the report."""
    facts = []
    # Student/athlete counts
    for m in re.finditer(r"(\d[\d,]*)\s+(student.?athlete|student|player|participant|athlete)", text, re.I):
        context = text[max(0, m.start() - 30): m.end() + 80].strip()
        context = re.sub(r"\s+", " ", context)
        facts.append(f"{m.group(1)} {m.group(2).lower()}s — {context}")
    # Win-loss records
    for m in re.finditer(r"(\d+)\s*[-–]\s*(\d+)\s+(league\s+)?record", text, re.I):
        context = text[max(0, m.start() - 50): m.end() + 60].strip()
        context = re.sub(r"\s+", " ", context)
        facts.append(f"Record {m.group(1)}-{m.group(2)} — {context}")
    # Dollar amounts
    for m in re.finditer(r"\$([\d,]+(?:\.\d{2})?)", text):
        context = text[max(0, m.start() - 40): m.end() + 80].strip()
        context = re.sub(r"\s+", " ", context)
        if len(context) > 15:
            facts.append(f"${m.group(1)} — {context}")
    return facts[:12]  # cap at 12 facts


def _build_topic_summaries(text):
    """For each topic found, return up to 2 illustrative sentences."""
    topic_data = {}
    for topic, patterns in _TOPIC_KEYWORDS.items():
        found_sentences = []
        for pat in patterns:
            if re.search(pat, text, re.I):
                sents = _extract_sentences_matching(text, pat)
                found_sentences.extend(sents)
        if found_sentences:
            # Deduplicate
            seen = set()
            unique = []
            for s in found_sentences:
                key = s[:60]
                if key not in seen:
                    seen.add(key)
                    unique.append(s)
            topic_data[topic] = unique[:2]
    return topic_data


def _first_n_sentences(text, n=3):
    """Return first n non-trivial content sentences from text, skipping header/byline lines."""
    # Skip the typical BoardDocs header: name, email, TO/FROM/RE/DATE lines
    SKIP_PAT = re.compile(
        r"^\s*(?:TO:|FROM:|RE:|DATE:|Director|Superintendent|Principal|"
        r"[A-Za-z.\s]+@[a-z]+\.[a-z]+|Board of Education|BOE Report|"
        r"Director'?s? Report)\b",
        re.I
    )
    sents = []
    for sent in re.split(r"(?<=[.!?])\s+|\n", text):
        sent = sent.strip()
        if len(sent) < 40:
            continue
        if SKIP_PAT.match(sent):
            continue
        sents.append(sent)
        if len(sents) >= n:
            break
    return " ".join(sents)


def analyze_director_trend(month_texts: dict) -> dict:
    """
    Rich analysis of director/narrative reports across months.
    Extracts actual content rather than counting keyword presence.
    """
    month_summaries = {}
    all_topic_months = defaultdict(list)

    for month, text in month_texts.items():
        if not text:
            month_summaries[month] = {"status": "no_data", "topics": [], "facts": [], "topic_content": {}}
            continue

        topic_content = _build_topic_summaries(text)
        facts         = _extract_numbers_with_context(text)
        topics_found  = list(topic_content.keys())

        for t in topics_found:
            all_topic_months[t].append(month)

        month_summaries[month] = {
            "status":        "extracted",
            "text_length":   len(text),
            "topics":        topics_found,
            "topic_content": topic_content,
            "facts":         facts,
            "lead":          _first_n_sentences(text, 3),
            "preview":       text[:500],
        }

    available = [m for m, v in month_summaries.items() if v["status"] == "extracted"]
    missing   = [m for m, v in month_summaries.items() if v["status"] == "no_data"]

    # ── Flags ──────────────────────────────────────────────────────────────────
    flags = []
    if missing and len(missing) < len(month_texts):
        flags.append({
            "priority": "medium", "item": "Missing Reports",
            "observation": f"No reports found for: {', '.join(missing)}"
        })

    # Director change flag: if 2+ consecutive months have a different name in the header
    director_names = []
    for month in available:
        text = month_texts.get(month, "")
        # Name usually appears in first 200 chars
        name_m = re.search(r"^([A-Z][a-z\-]+(?: [A-Z][a-z\-]+){1,3})", text[:200])
        if name_m:
            director_names.append((month, name_m.group(1)))

    unique_directors = list(dict.fromkeys(n for _, n in director_names))
    if len(unique_directors) > 1:
        flags.append({
            "priority": "medium", "item": "Director Change Detected",
            "observation": (
                f"Reports appear under different names across the year: "
                + "; ".join(f"{m}: {n}" for m, n in director_names[:6])
            )
        })

    # Recurring themes (3+ months)
    n_avail = max(len(available), 1)
    for topic, months in sorted(all_topic_months.items(), key=lambda x: -len(x[1])):
        if len(months) >= 3:
            flags.append({
                "priority": "low", "item": f"Recurring: {topic}",
                "observation": f"Appears in {len(months)}/{n_avail} months: {', '.join(months)}"
            })

    # Themes that disappeared (present early, absent late)
    if len(available) >= 4:
        first_half = set(available[:len(available) // 2])
        second_half = set(available[len(available) // 2:])
        for topic, months in all_topic_months.items():
            months_set = set(months)
            if months_set & first_half and not months_set & second_half:
                flags.append({
                    "priority": "low", "item": f"Dropped Off: {topic}",
                    "observation": (
                        f"Present in early months ({', '.join(sorted(months_set & first_half))}) "
                        f"but not seen in later months."
                    )
                })

    # Coverage and momentum flags
    coverage_ratio = (len(available) / len(month_texts)) if month_texts else 0
    if month_texts and coverage_ratio < 0.6:
        flags.append({
            "priority": "high", "item": "Low Report Coverage",
            "observation": (
                f"Only {len(available)} of {len(month_texts)} months have report text. "
                "Trend conclusions are directional only until more months are available."
            )
        })

    # High-signal change detection using extracted fact counts and topic counts.
    if len(available) >= 2:
        first_m, last_m = available[0], available[-1]
        first = month_summaries[first_m]
        last = month_summaries[last_m]
        first_facts = len(first.get("facts", []))
        last_facts = len(last.get("facts", []))
        first_topics = len(first.get("topics", []))
        last_topics = len(last.get("topics", []))

        if last_facts >= first_facts + 6:
            flags.append({
                "priority": "low", "item": "Detail Level Increased",
                "observation": (
                    f"The latest report ({last_m}) includes substantially more numeric/detail statements "
                    f"than early-year reporting ({first_m}) ({last_facts} vs {first_facts})."
                )
            })
        elif first_facts >= last_facts + 6:
            flags.append({
                "priority": "medium", "item": "Detail Level Declined",
                "observation": (
                    f"The latest report ({last_m}) includes fewer concrete numeric/detail statements "
                    f"than early-year reporting ({first_m}) ({last_facts} vs {first_facts})."
                )
            })

        if abs(last_topics - first_topics) >= 4:
            direction = "broadened" if last_topics > first_topics else "narrowed"
            flags.append({
                "priority": "low", "item": "Topic Breadth Shift",
                "observation": (
                    f"Topic coverage has {direction} from {first_topics} themes in {first_m} "
                    f"to {last_topics} themes in {last_m}."
                )
            })

    # ── Summary ────────────────────────────────────────────────────────────────
    top_topics = sorted(all_topic_months.items(), key=lambda x: -len(x[1]))[:5]
    top_str = ", ".join(f"{t} ({len(m)})" for t, m in top_topics) if top_topics else "none"
    summary = (
        f"Director reports analyzed across {len(available)} months "
        f"({len(available) + len(missing)} total in fiscal year, {coverage_ratio:.0%} coverage). "
        f"Top recurring themes: {top_str}."
    )

    return {
        "summary":          summary,
        "flags":            flags,
        "themes":           dict(all_topic_months),
        "month_summaries":  month_summaries,
        "raw_months":       month_texts,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Year-over-year comparison
# ─────────────────────────────────────────────────────────────────────────────

def analyze_yoy(reports_by_year: dict, report_type: str,
                report_category: str = "finance") -> dict:
    """
    Year-over-year comparison of the same report across multiple fiscal years.
    reports_by_year: {"2024-25": text, "2025-26": text, ...}
    report_category: "finance" or "director"
    """
    if report_category == "finance":
        return _analyze_finance_yoy(reports_by_year, report_type)
    else:
        return _analyze_director_yoy(reports_by_year, report_type)


def _analyze_finance_yoy(reports_by_year: dict, report_type: str) -> dict:
    """Side-by-side financial comparison across fiscal years (same calendar month)."""
    parsed_years = {}
    for fy, text in reports_by_year.items():
        if not text:
            parsed_years[fy] = None
            continue
        items, totals, date_range = parse_revenue_status(text)
        parsed_years[fy] = {"items": items, "totals": totals, "date_range": date_range}

    years    = sorted(parsed_years.keys())
    avail    = [y for y in years if parsed_years[y] is not None]
    missing  = [y for y in years if parsed_years[y] is None]

    # ── Overall totals table ─────────────────────────────────────────────────
    totals_rows = []
    for fy in avail:
        t = parsed_years[fy]["totals"]
        totals_rows.append({
            "year":   fy,
            "budget": t.get("revised_budget"),
            "earned": t.get("earned"),
            "pct":    t.get("pct_collected"),
            "date_range": parsed_years[fy]["date_range"],
        })

    # ── Line-by-line comparison ───────────────────────────────────────────────
    # Gather all accounts
    all_accounts = {}
    for fy in avail:
        for item in parsed_years[fy]["items"]:
            all_accounts.setdefault(item["account"], item["description"])

    line_comparison = []
    for acc, desc in all_accounts.items():
        row = {"account": acc, "description": desc, "years": {}}
        for fy in avail:
            match = next((i for i in parsed_years[fy]["items"] if i["account"] == acc), None)
            if match:
                row["years"][fy] = {
                    "earned":  match["earned"],
                    "pct":     match["pct_collected"],
                    "budget":  match["revised_budget"],
                }
        line_comparison.append(row)

    # ── Flags ──────────────────────────────────────────────────────────────────
    flags = []
    if missing:
        flags.append({"priority": "medium", "item": "Missing Year Data",
                      "observation": f"No data found for: {', '.join(missing)}"})

    if len(avail) >= 2:
        prev_fy, curr_fy = avail[-2], avail[-1]
        prev_t = parsed_years[prev_fy]["totals"]
        curr_t = parsed_years[curr_fy]["totals"]

        # Overall budget change
        if prev_t.get("revised_budget") and curr_t.get("revised_budget"):
            bd = curr_t["revised_budget"] - prev_t["revised_budget"]
            bp = bd / prev_t["revised_budget"] * 100
            sign = "+" if bd >= 0 else ""
            flags.append({
                "priority": "low", "item": "Budget Change",
                "observation": (
                    f"Total budget: {_fmt_dollar(prev_t['revised_budget'])} ({prev_fy}) → "
                    f"{_fmt_dollar(curr_t['revised_budget'])} ({curr_fy}) "
                    f"({sign}{_fmt_dollar(bd)}, {sign}{bp:.1f}%)"
                )
            })

        # Collection rate vs same period last year
        if prev_t.get("pct_collected") and curr_t.get("pct_collected"):
            pp = curr_t["pct_collected"] - prev_t["pct_collected"]
            sign = "+" if pp >= 0 else ""
            trend = "ahead of" if pp > 1 else ("behind" if pp < -1 else "on par with")
            flags.append({
                "priority": "low", "item": "Collection Rate vs Prior Year",
                "observation": (
                    f"YTD collection at same calendar point: "
                    f"{_fmt_pct(prev_t['pct_collected'])} ({prev_fy}) → "
                    f"{_fmt_pct(curr_t['pct_collected'])} ({curr_fy}) — "
                    f"currently {trend} the prior year pace ({sign}{pp:.1f} pp)."
                )
            })

        # Line items with large year-over-year changes
        for row in line_comparison:
            if prev_fy in row["years"] and curr_fy in row["years"]:
                prev_e = row["years"][prev_fy]["earned"]
                curr_e = row["years"][curr_fy]["earned"]
                if prev_e > 0:
                    yoy_change = (curr_e - prev_e) / abs(prev_e) * 100
                    delta = curr_e - prev_e
                    if abs(yoy_change) > 50 and abs(delta) > 100_000:
                        direction = "increase" if delta > 0 else "decrease"
                        flags.append({
                            "priority": "medium",
                            "item": f"{row['account']} — {row['description']}",
                            "observation": (
                                f"Large year-over-year {direction}: "
                                f"{_fmt_dollar(prev_e)} ({prev_fy}) → {_fmt_dollar(curr_e)} ({curr_fy}) "
                                f"({'+' if delta > 0 else ''}{_fmt_dollar(delta)}, "
                                f"{'+' if yoy_change > 0 else ''}{yoy_change:.0f}%)"
                            )
                        })
            elif curr_fy in row["years"] and prev_fy not in row["years"]:
                # New line item this year
                curr_e = row["years"][curr_fy]["earned"]
                curr_b = row["years"][curr_fy]["budget"]
                if curr_e > 50_000 or curr_b > 50_000:
                    flags.append({
                        "priority": "medium",
                        "item": f"{row['account']} — {row['description']}",
                        "observation": (
                            f"New line item in {curr_fy} (not present in {prev_fy}): "
                            f"Budget {_fmt_dollar(curr_b)}, earned {_fmt_dollar(curr_e)}."
                        )
                    })

    priority_order = {"high": 0, "medium": 1, "low": 2}
    flags.sort(key=lambda f: priority_order.get(f["priority"], 3))

    # ── Summary ─────────────────────────────────────────────────────────────────
    if len(totals_rows) >= 2:
        prev = totals_rows[-2]
        curr = totals_rows[-1]
        summary = (
            f"Year-over-year comparison of {report_type} at the same calendar month. "
            f"In {prev['year']}, YTD revenue was {_fmt_dollar(prev['earned'])} "
            f"({_fmt_pct(prev['pct'])} of {_fmt_dollar(prev['budget'])} budget). "
            f"In {curr['year']}, YTD revenue is {_fmt_dollar(curr['earned'])} "
            f"({_fmt_pct(curr['pct'])} of {_fmt_dollar(curr['budget'])} budget) — "
            f"a year-over-year change of {_delta_str(prev['earned'], curr['earned'])}."
        )
    else:
        summary = f"Year-over-year analysis of {report_type}. {len(avail)} year(s) with data."

    # Build year_summaries for backward-compat with app.py display
    year_summaries = {}
    for fy in years:
        if parsed_years.get(fy):
            t = parsed_years[fy]["totals"]
            year_summaries[fy] = {
                "status":    "extracted",
                "budget":    t.get("revised_budget"),
                "earned":    t.get("earned"),
                "pct":       t.get("pct_collected"),
                "date_range": parsed_years[fy]["date_range"],
                "item_count": len(parsed_years[fy]["items"]),
            }
        else:
            year_summaries[fy] = {"status": "no_data"}

    return {
        "summary":          summary,
        "flags":            flags,
        "years":            years,
        "totals_rows":      totals_rows,
        "line_comparison":  line_comparison,
        "year_summaries":   year_summaries,
        "raw_years":        reports_by_year,
    }


def _analyze_director_yoy(reports_by_year: dict, report_type: str) -> dict:
    """Year-over-year comparison for narrative director reports."""
    years   = sorted(reports_by_year.keys())
    avail   = [y for y in years if reports_by_year.get(y)]
    missing = [y for y in years if not reports_by_year.get(y)]

    year_summaries = {}
    all_topics_by_year = {}

    for fy, text in reports_by_year.items():
        if not text:
            year_summaries[fy] = {"status": "no_data"}
            continue
        topic_content = _build_topic_summaries(text)
        facts = _extract_numbers_with_context(text)
        all_topics_by_year[fy] = set(topic_content.keys())
        year_summaries[fy] = {
            "status":        "extracted",
            "topics":        list(topic_content.keys()),
            "topic_content": topic_content,
            "facts":         facts,
            "lead":          _first_n_sentences(text, 4),
            "text_length":   len(text),
        }

    # Compare topics: new topics, dropped topics
    flags = []
    if missing:
        flags.append({"priority": "medium", "item": "Missing Year Data",
                      "observation": f"No data for: {', '.join(missing)}"})

    if len(avail) >= 2:
        prev_fy, curr_fy = avail[-2], avail[-1]
        prev_topics = all_topics_by_year.get(prev_fy, set())
        curr_topics = all_topics_by_year.get(curr_fy, set())
        new_topics  = curr_topics - prev_topics
        gone_topics = prev_topics - curr_topics
        shared_topics = prev_topics & curr_topics
        if new_topics:
            flags.append({"priority": "low", "item": f"New Topics in {curr_fy}",
                          "observation": f"Topics not seen in {prev_fy}: {', '.join(sorted(new_topics))}"})
        if gone_topics:
            flags.append({"priority": "low", "item": f"Topics Absent in {curr_fy}",
                          "observation": f"Topics present in {prev_fy} but absent in {curr_fy}: {', '.join(sorted(gone_topics))}"})

        continuity = (len(shared_topics) / max(len(prev_topics | curr_topics), 1)) * 100
        flags.append({
            "priority": "low", "item": "Topic Continuity",
            "observation": (
                f"{len(shared_topics)} topics are shared between {prev_fy} and {curr_fy} "
                f"({continuity:.0f}% continuity)."
            )
        })

        prev_fact_count = len(year_summaries.get(prev_fy, {}).get("facts", []))
        curr_fact_count = len(year_summaries.get(curr_fy, {}).get("facts", []))
        if abs(curr_fact_count - prev_fact_count) >= 6:
            direction = "more" if curr_fact_count > prev_fact_count else "fewer"
            pri = "medium" if curr_fact_count < prev_fact_count else "low"
            flags.append({
                "priority": pri,
                "item": "Evidence Density Shift",
                "observation": (
                    f"{curr_fy} includes {direction} extracted numeric/detail statements than {prev_fy} "
                    f"({curr_fact_count} vs {prev_fact_count})."
                )
            })

    summary = (
        f"Year-over-year comparison of {report_type} at the same calendar month "
        f"across {len(avail)} year(s)."
    )
    return {
        "summary":        summary,
        "flags":          flags,
        "years":          years,
        "year_summaries": year_summaries,
        "raw_years":      reports_by_year,
    }
