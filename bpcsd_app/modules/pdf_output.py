# PermissionError patch for /app directory (must run before reportlab imports)
def _patch_os():
    import os

    class _EmptyResult:
        def __enter__(self): return iter([])
        def __exit__(self, *a): pass
        def __iter__(self): return iter([])

    _orig_scandir = os.scandir
    def safe_scandir(path='.'):
        try:
            return _orig_scandir(path)
        except PermissionError:
            return _EmptyResult()
    os.scandir = safe_scandir

    _orig_listdir = os.listdir
    def safe_listdir(path='.'):
        try:
            return _orig_listdir(path)
        except PermissionError:
            return []
    os.listdir = safe_listdir

_patch_os()

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
import io

# Color palette
NAVY       = colors.HexColor("#1a2744")
LIGHT_BLUE = colors.HexColor("#f0f4ff")
ALT_ROW    = colors.HexColor("#f4f6fb")
AMBER      = colors.HexColor("#b45309")
RED_C      = colors.HexColor("#b91c1c")
GREEN_C    = colors.HexColor("#166534")
BORDER_GREY= colors.HexColor("#dddddd")


def build_styles():
    styles = getSampleStyleSheet()
    custom = {
        "H1": ParagraphStyle(
            "H1", fontSize=18, textColor=NAVY,
            spaceAfter=8, spaceBefore=16, fontName="Helvetica-Bold"
        ),
        "H2": ParagraphStyle(
            "H2", fontSize=13, textColor=NAVY,
            spaceAfter=6, spaceBefore=12, fontName="Helvetica-Bold"
        ),
        "H3": ParagraphStyle(
            "H3", fontSize=11, textColor=NAVY,
            spaceAfter=4, spaceBefore=8, fontName="Helvetica-Bold"
        ),
        "Body": ParagraphStyle(
            "Body", fontSize=10, spaceAfter=6, leading=14, alignment=TA_JUSTIFY
        ),
        "Bullet": ParagraphStyle(
            "Bullet", fontSize=10, spaceAfter=3, leftIndent=16, leading=13
        ),
        "Small": ParagraphStyle(
            "Small", fontSize=8, textColor=colors.grey, spaceAfter=4
        ),
        "Callout": ParagraphStyle(
            "Callout", fontSize=9.5, backColor=LIGHT_BLUE,
            leftIndent=12, rightIndent=12, spaceBefore=6, spaceAfter=6,
            leading=14, borderPadding=6
        ),
        "FlagHigh": ParagraphStyle(
            "FlagHigh", fontSize=10, textColor=RED_C, fontName="Helvetica-Bold"
        ),
        "FlagMed": ParagraphStyle(
            "FlagMed", fontSize=10, textColor=AMBER, fontName="Helvetica-Bold"
        ),
        "FlagLow": ParagraphStyle(
            "FlagLow", fontSize=10, textColor=GREEN_C, fontName="Helvetica-Bold"
        ),
        "Cover": ParagraphStyle(
            "Cover", fontSize=11, textColor=colors.white,
            alignment=TA_CENTER, leading=18
        ),
        "CoverTitle": ParagraphStyle(
            "CoverTitle", fontSize=24, textColor=colors.white,
            fontName="Helvetica-Bold", alignment=TA_CENTER, leading=30
        ),
    }
    merged = {k: styles[k] for k in styles.byName}
    merged.update(custom)
    return merged


def make_table(headers, rows, col_widths=None):
    data = [headers] + rows
    if col_widths is None:
        w = (A4[0] - 4 * cm) / max(len(headers), 1)
        col_widths = [w] * len(headers)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND",    (0, 0), (-1, 0),  NAVY),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER_GREY),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, ALT_ROW]),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(style))
    return t


def cover_page(title, subtitle, period, authors="", district="Broadalbin-Perth CSD"):
    """Return flowables for a cover page."""
    s = build_styles()
    author_html = (
        f'<br/><br/><font size="10" color="#adc8ff">{authors}</font>'
        if authors else ""
    )
    cover_data = [[Paragraph(
        f'<font color="white"><b>{district}</b></font><br/><br/>'
        f'<font size="22" color="white"><b>{title}</b></font><br/><br/>'
        f'<font size="13" color="#adc8ff">{subtitle}</font><br/><br/>'
        f'<font size="11" color="#adc8ff">{period}</font>'
        + author_html,
        s["Cover"]
    )]]
    cover_tbl = Table(cover_data, colWidths=[A4[0] - 2 * cm])
    cover_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), NAVY),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 80),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 80),
        ("LEFTPADDING",  (0, 0), (-1, -1), 40),
        ("RIGHTPADDING", (0, 0), (-1, -1), 40),
    ]))
    return [cover_tbl, PageBreak()]


def generate_pdf(title, subtitle, period, sections, authors=""):
    """
    Generate a PDF and return bytes.

    sections: list of dicts with keys:
      - type: "heading1"|"heading2"|"heading3"|"paragraph"|"bullet"|"table"|
               "rule"|"callout"|"flag"|"spacer"|"pagebreak"
      - text: str (for non-table types)
      - headers: list (for table)
      - rows: list of lists (for table)
      - col_widths: list (for table, optional)
      - priority: "high"|"medium"|"low" (for flag)
      - height: int (for spacer, default 8)
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm
    )
    s = build_styles()
    story = cover_page(title, subtitle, period, authors)

    TH_STYLE = ParagraphStyle("TH", fontSize=9, textColor=colors.white, fontName="Helvetica-Bold")
    TD_STYLE = ParagraphStyle("TD", fontSize=9, leading=12)

    for sec in sections:
        t    = sec.get("type", "paragraph")
        text = sec.get("text", "")

        if t == "heading1":
            story.append(Paragraph(text, s["H1"]))
            story.append(HRFlowable(width="100%", thickness=1.5, color=NAVY))
            story.append(Spacer(1, 4))
        elif t == "heading2":
            story.append(Paragraph(text, s["H2"]))
        elif t == "heading3":
            story.append(Paragraph(text, s["H3"]))
        elif t == "paragraph":
            if text:
                story.append(Paragraph(text, s["Body"]))
        elif t == "bullet":
            if text:
                story.append(Paragraph(f"• {text}", s["Bullet"]))
        elif t == "callout":
            if text:
                story.append(Paragraph(text, s["Callout"]))
        elif t == "rule":
            story.append(HRFlowable(
                width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=8
            ))
        elif t == "flag":
            priority = sec.get("priority", "medium")
            icon = "[!!]" if priority == "high" else ("[!]" if priority == "medium" else "[→]")
            sty  = s["FlagHigh"] if priority == "high" else (s["FlagMed"] if priority == "medium" else s["FlagLow"])
            if text:
                story.append(Paragraph(f"{icon} {text}", sty))
        elif t == "table":
            headers    = sec.get("headers", [])
            rows       = sec.get("rows", [])
            col_widths = sec.get("col_widths", None)
            if headers and rows:
                story.append(make_table(
                    [Paragraph(h, TH_STYLE) for h in headers],
                    [[Paragraph(str(c), TD_STYLE) for c in row] for row in rows],
                    col_widths
                ))
                story.append(Spacer(1, 6))
        elif t == "spacer":
            story.append(Spacer(1, sec.get("height", 8)))
        elif t == "pagebreak":
            story.append(PageBreak())

    doc.build(story)
    return buf.getvalue()
