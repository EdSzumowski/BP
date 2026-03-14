"""
Registry of report types and known meeting IDs for BPCSD BoardDocs analysis.

CRITICAL STRUCTURE NOTE (confirmed by live API inspection):
- Finance reports are NOT separate agenda items.
  They are FILE ATTACHMENTS to a single "Finance Committee" agenda item.
  The app must use find_finance_attachment() — not an Xtitle search.
- Director reports each have their own agenda item (Xtitle search works).
"""

REPORT_TYPES = {
    "finance": {
        "label": "Finance Reports",
        "reports": {
            # Search terms matched against ATTACHMENT FILENAMES (fuzzy)
            "revenue_status":       {"label": "Revenue Status",         "search": ["Revenue Status"]},
            "appropriation_status": {"label": "Appropriation Status",   "search": ["Appropriation Status", "GF Appropriation"]},
            "treasurer":            {"label": "Treasurer's Report",      "search": ["Treasurers Report", "Treasurer"]},
            "cash_disbursement":    {"label": "Cash Disbursement",       "search": ["Cash Disbursement"]},
            "cash_receipts":        {"label": "Cash Receipts",           "search": ["Cash Receipt"]},
            "journal_entries":      {"label": "Journal Entries",         "search": ["Journal Entry", "Journal Entries"]},
            "claims_audit":         {"label": "Claims Audit",            "search": ["Claim"]},
            # M&T: name varies — "M&T Collateral" and "M & T Collateral" both appear
            "mt_collateral":        {"label": "M&T Collateral",          "search": ["M&T Collateral", "M & T Collateral", "MT Collateral"]},
            # NYCLASS: appears as "NYCLASS Collateral Report" and "NYCLASS October 2025"
            "nyclass":              {"label": "NYCLASS",                  "search": ["NYCLASS", "NY CLASS"]},
        }
    },
    "director": {
        "label": "Director Reports",
        "reports": {
            # Search terms matched against AGENDA ITEM XTITLE (fuzzy)
            # Actual titles confirmed from live Jan 2025 agenda:
            # 'Report - Elementary School Report January 2025'
            # 'Report - Secondary School Report January 2025'
            # 'Report - Transportation and Building Report January 2025'
            # 'Report - Special Education Report January 2025'
            # 'Report - Health, Physical Education, Athletics and Nursing Report January 2025'
            # 'Report - Communications Report January 2025'
            # 'Report - Technology Report Jan 2025'
            # 'Report - Business Office Report January 2025'
            # 'Report - Curriculum BOE Report January 2025'
            "elementary":    {"label": "Elementary School",       "search": ["Elementary School Report", "Elementary School"]},
            "secondary":     {"label": "High School / Secondary", "search": ["Secondary School Report", "Secondary School"]},
            "special_ed":    {"label": "Special Education",       "search": ["Special Education Report", "Special Education"]},
            # Note: actual title is "Health, Physical Education, Athletics and Nursing"
            "athletics":     {"label": "Athletics & Health",      "search": ["Athletics and Nursing", "Athletics", "Physical Education"]},
            "technology":    {"label": "Technology",              "search": ["Technology Report", "Technology BOE", "Technology"]},
            "business":      {"label": "Business Office",         "search": ["Business Office Report", "Business Office"]},
            "communications":{"label": "Communications",          "search": ["Communications Report", "Communications Department", "Communications"]},
            "curriculum":    {"label": "Curriculum",              "search": ["Curriculum BOE Report", "Curriculum Report", "Curriculum"]},
            "transportation":{"label": "Transportation & Buildings","search": ["Transportation and Building", "Transportation"]},
            # Middle School — separate from Secondary at some districts; may not exist at BPCSD
            "middle":        {"label": "Middle School",           "search": ["Middle School BOE", "Middle School Report", "Middle School"]},
        }
    }
}


def get_report_category(report_key):
    """Return 'finance' or 'director' for a given report_key."""
    for cat_key, cat in REPORT_TYPES.items():
        if report_key in cat["reports"]:
            return cat_key
    return "director"


def get_report_meta(report_key):
    """Return (category, meta_dict) for a report_key, or (None, None)."""
    for cat_key, cat in REPORT_TYPES.items():
        if report_key in cat["reports"]:
            return cat_key, cat["reports"][report_key]
    return None, None


# ── Meeting IDs ───────────────────────────────────────────────────────────────
# Format: { "YYYY-MM": { "id": "...", "label": "...", "type": "regular|reorg|special" } }
# School year runs July 1 – June 30.
KNOWN_MEETINGS = {
    # FY 2024-25 meetings (the Jul 2024 reorg and Aug-Dec 2024 regular meetings
    # are not yet registered — add them once their IDs are discovered)
    "2025-01": {"id": "DCCNK760440C", "label": "Jan 27, 2025",          "type": "regular"},
    "2025-02": {"id": "DDLGYA45DAD9", "label": "Feb 24, 2025",          "type": "regular"},
    "2025-03": {"id": "DE9JEH4CD463", "label": "Mar 17, 2025",          "type": "regular"},
    "2025-04": {"id": "DF4FZJ418E1D", "label": "Apr 10, 2025",          "type": "regular"},
    "2025-05": {"id": "DG2MV95D0CDE", "label": "May 19, 2025",          "type": "regular"},
    "2025-06": {"id": "DHDHRB49B8E4", "label": "Jun 16, 2025",          "type": "regular"},
    "2025-07": {"id": "DHQQUP6AE746", "label": "Jul 1, 2025 (Reorg)",   "type": "reorg"},
    "2025-08": {"id": "DJMFDT3EAAF0", "label": "Aug 18, 2025",          "type": "regular"},
    "2025-09": {"id": "DKXLF3564988", "label": "Sep 15, 2025",          "type": "regular"},
    "2025-10": {"id": "DM2PNT657C10", "label": "Oct 20, 2025",          "type": "regular"},
    "2025-11": {"id": "DMWPJP64E0A2", "label": "Nov 3, 2025 (Special)", "type": "special"},
    "2025-12": {"id": "DMXNCD5F443C", "label": "Dec 2, 2025",           "type": "regular"},
    "2026-01": {"id": "DPGGXD45ECF0", "label": "Jan 26, 2026",          "type": "regular"},
    "2026-02": {"id": "DR7KNB52A978", "label": "Feb 23, 2026",          "type": "regular"},
}

# Fiscal years: label → ordered list of YYYY-MM keys (Jul → Jun)
FISCAL_YEARS = {
    "2024-25": [
        "2024-07", "2024-08", "2024-09", "2024-10", "2024-11", "2024-12",
        "2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06",
    ],
    "2025-26": [
        "2025-07", "2025-08", "2025-09", "2025-10", "2025-11", "2025-12",
        "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06",
    ],
}

MONTH_LABELS = {
    "01": "January", "02": "February", "03": "March",    "04": "April",
    "05": "May",     "06": "June",     "07": "July",     "08": "August",
    "09": "September","10": "October", "11": "November", "12": "December",
}
