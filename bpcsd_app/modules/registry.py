# Report series definitions
REPORT_TYPES = {
    "finance": {
        "label": "Finance Reports",
        "reports": {
            "revenue_status":       {"label": "Revenue Status",         "search": ["Revenue Status"]},
            "appropriation_status": {"label": "Appropriation Status",   "search": ["GF Appropriation Status", "Appropriation Status"]},
            "treasurer":            {"label": "Treasurer's Report",      "search": ["BOE Treasurers Report", "Treasurer"]},
            "cash_disbursement":    {"label": "Cash Disbursement",       "search": ["Cash Disbursement"]},
            "cash_receipts":        {"label": "Cash Receipts",           "search": ["Cash Receipt"]},
            "journal_entries":      {"label": "Journal Entries",         "search": ["Journal Entry"]},
            "claims_audit":         {"label": "Claims Audit",            "search": ["Claim"]},
            "nyclass":              {"label": "NYCLASS",                  "search": ["NYCLASS"]},
            "mt_collateral":        {"label": "M&T Collateral",          "search": ["M&T Collateral", "MT Collateral"]},
        }
    },
    "director": {
        "label": "Director Reports",
        "reports": {
            "elementary":    {"label": "Elementary School",  "search": ["Elementary School Report", "BOE Elementary"]},
            "middle":        {"label": "Middle School",      "search": ["Middle School BOE Report", "BOE Middle School"]},
            "secondary":     {"label": "High School",        "search": ["BOE Secondary School", "Secondary School Report"]},
            "special_ed":    {"label": "Special Education",  "search": ["BOE Special Education", "Special Education Report"]},
            "athletics":     {"label": "Athletics & Health", "search": ["BOE Athletics", "Athletics and Health"]},
            "technology":    {"label": "Technology",         "search": ["BOE Technology", "Technology Report"]},
            "business":      {"label": "Business Office",    "search": ["BOE Business Office", "Business Office Report"]},
            "communications":{"label": "Communications",     "search": ["Communications Department", "Communications Report"]},
        }
    }
}

# Known meeting IDs — school year runs Jul 1 – Jun 30
# Format: { "YYYY-MM": { "id": "...", "label": "...", "type": "regular|reorg|special" } }
KNOWN_MEETINGS = {
    # FY 2024-25 (Jul 2024 – Jun 2025)
    "2025-01": {"id": "DCCNK760440C", "label": "Jan 27, 2025", "type": "regular"},
    "2025-02": {"id": "DDLGYA45DAD9", "label": "Feb 24, 2025", "type": "regular"},
    "2025-03": {"id": "DE9JEH4CD463", "label": "Mar 17, 2025", "type": "regular"},
    "2025-04": {"id": "DF4FZJ418E1D", "label": "Apr 10, 2025", "type": "regular"},
    "2025-05": {"id": "DG2MV95D0CDE", "label": "May 19, 2025", "type": "regular"},
    "2025-06": {"id": "DHDHRB49B8E4", "label": "Jun 16, 2025", "type": "regular"},
    "2025-07-reorg": {"id": "DHQQUP6AE746", "label": "Jul 1, 2025 (Reorg)", "type": "reorg"},
    "2025-08": {"id": "DJMFDT3EAAF0", "label": "Aug 18, 2025", "type": "regular"},
    "2025-09": {"id": "DKXLF3564988", "label": "Sep 15, 2025", "type": "regular"},
    "2025-10": {"id": "DM2PNT657C10", "label": "Oct 20, 2025", "type": "regular"},
    "2025-11-special": {"id": "DMWPJP64E0A2", "label": "Nov 3, 2025 (Special)", "type": "special"},
    "2025-12": {"id": "DMXNCD5F443C", "label": "Dec 2, 2025", "type": "regular"},
    "2026-01": {"id": "DPGGXD45ECF0", "label": "Jan 26, 2026", "type": "regular"},
    "2026-02": {"id": "DR7KNB52A978", "label": "Feb 23, 2026", "type": "regular"},
}

# Fiscal years: label → list of YYYY-MM keys in Jul→Jun order
FISCAL_YEARS = {
    "2024-25": ["2024-07","2024-08","2024-09","2024-10","2024-11","2024-12",
                "2025-01","2025-02","2025-03","2025-04","2025-05","2025-06"],
    "2025-26": ["2025-07","2025-08","2025-09","2025-10","2025-11","2025-12",
                "2026-01","2026-02","2026-03","2026-04","2026-05","2026-06"],
}

MONTH_LABELS = {
    "01": "January",  "02": "February", "03": "March",    "04": "April",
    "05": "May",      "06": "June",     "07": "July",     "08": "August",
    "09": "September","10": "October",  "11": "November", "12": "December"
}
