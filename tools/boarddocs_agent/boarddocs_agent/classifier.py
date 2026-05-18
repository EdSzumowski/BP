from __future__ import annotations

import re

CATEGORIES = [
    "Board Agenda",
    "Minutes",
    "Superintendent Reports",
    "Business and Finance",
    "Budget",
    "Claims/Audits/Treasurer",
    "Personnel",
    "Policy",
    "Curriculum and Instruction",
    "Special Education",
    "Facilities and Operations",
    "Transportation",
    "Athletics and Extracurricular",
    "Technology",
    "Communications/Public Comment",
    "Contracts, Agreements, and MOUs",
    "Grants, State, and Federal Programs",
    "Legal/Executive Session",
    "Other",
]

_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Minutes", ("minutes", "meeting minute")),
    ("Board Agenda", ("agenda", "board agenda")),
    ("Superintendent Reports", ("superintendent", "district update")),
    ("Claims/Audits/Treasurer", ("claim", "warrant", "treasurer", "audit", "extraclassroom", "extra classroom")),
    ("Budget", ("budget", "tax levy", "appropriation", "fund balance")),
    ("Business and Finance", ("finance", "financial", "revenue", "expense", "purchase", "bid", "cafeteria", "fund")),
    ("Personnel", ("personnel", "appointment", "resignation", "tenure", "probationary", "substitute", "leave of absence", "civil service")),
    ("Policy", ("policy", "policies", "first reading", "second reading")),
    ("Curriculum and Instruction", ("curriculum", "instruction", "assessment", "academic", "program", "professional development")),
    ("Special Education", ("special education", "cse", "cpse", "iep", "student services")),
    ("Facilities and Operations", ("facilities", "operations", "building", "capital project", "maintenance", "construction")),
    ("Transportation", ("transportation", "bus", "vehicle", "fleet")),
    ("Athletics and Extracurricular", ("athletic", "sports", "extracurricular", "club", "coach")),
    ("Technology", ("technology", "cyber", "software", "hardware", "network", "device")),
    ("Communications/Public Comment", ("public comment", "communication", "correspondence", "hearing")),
    ("Contracts, Agreements, and MOUs", ("contract", "agreement", "mou", "memorandum of understanding", "lease", "settlement")),
    ("Grants, State, and Federal Programs", ("grant", "state aid", "federal", "title i", "idea", "arp", "esser")),
    ("Legal/Executive Session", ("executive session", "legal", "litigation", "attorney", "collective bargaining")),
]


def classify_document(*parts: str | None) -> str:
    text = " ".join(part or "" for part in parts).lower()
    text = re.sub(r"[^a-z0-9$%\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    scores: dict[str, int] = {}
    for category, terms in _RULES:
        score = 0
        for term in terms:
            if term in text:
                score += 3 if " " in term else 1
        if score:
            scores[category] = score
    if not scores:
        return "Other"
    return max(scores.items(), key=lambda item: item[1])[0]
