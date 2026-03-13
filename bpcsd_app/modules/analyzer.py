import re
import collections


def analyze_finance_trend(month_texts: dict) -> dict:
    """
    Analyze a dict of {month_label: text} for finance reports.
    Returns structured analysis with:
    - summary: str (narrative summary)
    - flags: list of {"priority": "high|medium|low", "item": str, "observation": str}
    - month_summaries: dict with per-month status
    - raw_months: dict (passthrough)
    """
    results = {
        "summary": "",
        "flags": [],
        "month_summaries": {},
        "raw_months": month_texts,
        "table_rows": []
    }

    DOLLAR_PAT = re.compile(r'\$[\d,]+(?:\.\d+)?')
    PCT_PAT    = re.compile(r'(\d{1,3}(?:\.\d+)?)\s*%')

    for month, text in month_texts.items():
        if not text:
            results["month_summaries"][month] = {"status": "no_data", "text_length": 0}
            continue

        # Extract dollar amounts and percentages
        dollars  = DOLLAR_PAT.findall(text)
        percents = PCT_PAT.findall(text)

        # Try to pick out largest dollar figure as "earned/total"
        def parse_dollar(s):
            try:
                return float(s.replace("$","").replace(",",""))
            except Exception:
                return 0.0

        dollar_vals = sorted([parse_dollar(d) for d in dollars], reverse=True)
        top_dollar  = f"${dollar_vals[0]:,.0f}" if dollar_vals else "—"

        # Look for percentage that looks like YTD %
        pct_val = "—"
        for p in percents:
            v = float(p)
            if 10 <= v <= 120:   # reasonable YTD range
                pct_val = f"{v:.1f}%"
                break

        results["month_summaries"][month] = {
            "status": "extracted",
            "text_length": len(text),
            "preview": text[:300],
            "top_dollar": top_dollar,
            "pct_ytd": pct_val,
        }
        results["table_rows"].append({
            "month": month,
            "top_amount": top_dollar,
            "pct_ytd": pct_val,
            "chars": len(text)
        })

    # Generate summary
    available = [m for m, s in results["month_summaries"].items() if s.get("status") == "extracted"]
    missing   = [m for m, s in results["month_summaries"].items() if s.get("status") == "no_data"]

    results["summary"] = (
        f"Finance report analysis covers {len(available)} month(s) with extracted data. "
        f"{len(missing)} month(s) had no data."
    )
    if missing:
        results["flags"].append({
            "priority": "medium",
            "item": "Missing Reports",
            "observation": f"No reports found for: {', '.join(missing)}"
        })

    return results


def analyze_director_trend(month_texts: dict) -> dict:
    """
    Analyze a dict of {month_label: text} for director (narrative) reports.
    Returns structured analysis covering themes, recurring topics, and flags.
    """
    results = {
        "summary": "",
        "flags": [],
        "themes": {},
        "month_summaries": {},
        "raw_months": month_texts
    }

    # Common topic patterns to track
    TOPIC_PATTERNS = {
        "Academics / Assessment": [r"academ", r"assessment", r"benchmark", r"iReady", r"NYS", r"state test"],
        "PBIS":                   [r"PBIS", r"Core Connect", r"Patriot Buck", r"pep rally"],
        "PTO":                    [r"PTO", r"fundrais"],
        "Safety":                 [r"safety", r"drill", r"lockdown", r"Centegix", r"evacuation", r"deputy"],
        "Summer Program":         [r"summer", r"Project Summer", r"ESY"],
        "Capital Project":        [r"capital", r"playground", r"gymnasium", r"gym"],
        "Enrollment":             [r"enroll", r"PreK", r"kindergarten.*first day"],
        "Drama / Arts":           [r"drama", r"concert", r"musical"],
        "Student Recognition":    [r"student council", r"leadership"],
        "Staff / Professional Dev":[r"professional development", r"PD day", r"staff training"],
        "Technology":             [r"technology", r"Chromebook", r"device", r"1:1"],
        "Special Education":      [r"IEP", r"special ed", r"504"],
    }

    for month, text in month_texts.items():
        if not text:
            results["month_summaries"][month] = {"status": "no_data", "topics": []}
            continue

        topics_found = []
        for topic, patterns in TOPIC_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, text, re.I):
                    topics_found.append(topic)
                    break

        results["month_summaries"][month] = {
            "status": "extracted",
            "text_length": len(text),
            "topics": topics_found,
            "preview": text[:400]
        }

    # Build theme presence table
    for topic in TOPIC_PATTERNS:
        months_with_topic = [
            m for m, s in results["month_summaries"].items()
            if topic in s.get("topics", [])
        ]
        results["themes"][topic] = months_with_topic

    # Flags
    available = [m for m, s in results["month_summaries"].items() if s.get("status") == "extracted"]
    missing   = [m for m, s in results["month_summaries"].items() if s.get("status") == "no_data"]

    if missing:
        results["flags"].append({
            "priority": "medium",
            "item": "Missing Reports",
            "observation": f"No reports found for: {', '.join(missing)}"
        })

    # Flag recurring themes (appear ≥ half the available months)
    n = max(len(available), 1)
    for topic, months in results["themes"].items():
        if len(months) >= max(2, n // 2):
            results["flags"].append({
                "priority": "low",
                "item": f"Recurring Theme: {topic}",
                "observation": f"Appears in {len(months)} of {n} months: {', '.join(months)}"
            })

    results["summary"] = (
        f"Director report analysis across {len(available)} month(s). "
        f"{len(results['themes'])} topic categories tracked."
    )
    return results


def analyze_yoy(reports_by_year: dict, report_type: str) -> dict:
    """
    Year-over-year comparison.
    reports_by_year: { "2024-25": text, "2025-26": text, ... }
    Returns structured comparison.
    """
    DOLLAR_PAT = re.compile(r'\$[\d,]+(?:\.\d+)?')

    year_summaries = {}
    for yr, text in reports_by_year.items():
        if not text:
            year_summaries[yr] = {"text_length": 0, "preview": "", "status": "no_data"}
            continue
        dollars = DOLLAR_PAT.findall(text)
        year_summaries[yr] = {
            "text_length": len(text),
            "preview": text[:300],
            "status": "extracted",
            "dollar_count": len(dollars),
        }

    flags = []
    missing = [yr for yr, s in year_summaries.items() if s.get("status") == "no_data"]
    if missing:
        flags.append({
            "priority": "medium",
            "item": "Missing Year Data",
            "observation": f"No data for: {', '.join(missing)}"
        })

    return {
        "summary": f"Year-over-year comparison of '{report_type}' across {len(reports_by_year)} year(s).",
        "years": list(reports_by_year.keys()),
        "flags": flags,
        "year_summaries": year_summaries,
        "raw_years": reports_by_year
    }
