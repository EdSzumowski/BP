"""
BPCSD Board Report Analysis — Streamlit Application
Broadalbin-Perth Central School District
"""

import sys
import os
from pathlib import Path

# Ensure modules directory is on the path (works locally and on Streamlit Cloud)
APP_DIR = Path(__file__).parent
sys.path.insert(0, str(APP_DIR))

import streamlit as st
import datetime
import time

from modules.registry import (
    REPORT_TYPES, KNOWN_MEETINGS, FISCAL_YEARS, MONTH_LABELS,
    get_report_category, get_report_meta
)
from modules.cache import (
    get_cached_text, save_cached_text,
    get_cached_item_id, save_cached_item_id,
    list_cached_reports, clear_cache, clear_all_cache,
    get_cache_inventory, get_cache_stats,
    delete_cache_entry, clear_discovery_cache,
    get_report_catalog, save_report_catalog,
    get_cached_meetings, save_cached_meetings,
)

# ── No hardcoded or stored credentials ───────────────────────────────────────
# Authentication is handled entirely by BoardDocs. Users log in with their own
# BoardDocs account. The app never stores or embeds any credentials.
# No Streamlit secrets are required for this app.

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🏫 BPCSD Board Analysis",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #1a2744 0%, #2d4a8c 100%);
        padding: 1.5rem 2rem;
        border-radius: 10px;
        margin-bottom: 1.5rem;
        color: white;
    }
    .main-header h1 { color: white; margin: 0; font-size: 2rem; }
    .main-header p  { color: #adc8ff; margin: 0.3rem 0 0; font-size: 1rem; }

    .summary-card {
        background: #f0f4ff;
        border-left: 4px solid #1a2744;
        padding: 1rem 1.2rem;
        border-radius: 6px;
        margin: 1rem 0;
    }
    .flag-high   { color: #b91c1c; font-weight: bold; }
    .flag-medium { color: #b45309; font-weight: bold; }
    .flag-low    { color: #166534; font-weight: bold; }

    .month-card {
        border: 1px solid #e0e6f0;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        margin: 0.4rem 0;
        background: #fafbff;
    }
    .status-cached  { color: #166534; }
    .status-missing { color: #b45309; }

    div[data-testid="stExpander"] { border: 1px solid #d0d8ee; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Helper: get/build client ──────────────────────────────────────────────────
def _check_boarddocs_auth():
    """
    Show a BoardDocs login screen before any app content is visible.
    Returns True once the user has successfully authenticated.
    BoardDocs itself is the only authentication gate — no app-level password needed.
    """
    if st.session_state.get("app_authenticated"):
        return True

    # Login screen
    st.markdown("""
    <div class="main-header">
        <h1>🏫 BPCSD Board Analysis</h1>
        <p>Broadalbin-Perth Central School District — Board Report Intelligence</p>
    </div>""", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Sign in with your BoardDocs account")
        st.caption("Use the same username and password you use on boarddocs.com")
        username = st.text_input("Username", key="login_user", autocomplete="username")
        password = st.text_input("Password", type="password", key="login_pass",
                                  autocomplete="current-password")
        if st.button("Sign In →", use_container_width=True, type="primary"):
            if not username or not password:
                st.error("Please enter both username and password.")
            else:
                with st.spinner("Authenticating with BoardDocs…"):
                    try:
                        from modules.boarddocs import BoardDocsClient
                        client = BoardDocsClient(username, password)
                        # Success — store everything in session
                        st.session_state["app_authenticated"] = True
                        st.session_state["username"] = username
                        st.session_state["password"] = password
                        st.session_state[f"client_{username}"] = client
                        st.rerun()
                    except Exception as e:
                        st.error(f"Sign-in failed — please check your credentials. ({e})")
        st.markdown("---")
        st.caption("🔒 Your credentials are sent directly to BoardDocs and are never stored by this app.")
    return False


def get_client(username, password):
    """Return a BoardDocsClient, using session cache if already authenticated."""
    key = f"client_{username}"
    if key in st.session_state and st.session_state[key] is not None:
        return st.session_state[key]
    from modules.boarddocs import BoardDocsClient
    client = BoardDocsClient(username, password)
    st.session_state[key] = client
    return client


def invalidate_client(username):
    key = f"client_{username}"
    st.session_state.pop(key, None)


# ── Helper: find meeting key for a YYYY-MM ────────────────────────────────────
def find_meeting_key(ym: str):
    """Find KNOWN_MEETINGS key for a year-month string (exact or with suffix)."""
    if ym in KNOWN_MEETINGS:
        return ym
    # Check variants like "2025-07-reorg"
    for k in KNOWN_MEETINGS:
        if k.startswith(ym):
            return k
    return None


# ── Helper: fetch + extract one report ───────────────────────────────────────
def fetch_report(client, meeting_ym: str, report_key: str, report_meta: dict,
                 status_placeholder, category: str = "director"):
    """
    Fetch and extract text for one report at one meeting.
    Strategy differs by category:
      finance  → Finance Committee item → attachment filename fuzzy match
      director → Director's own agenda item → first PDF attachment
    Returns (text_or_None, status_str)
    """
    meeting_key = find_meeting_key(meeting_ym)
    if not meeting_key:
        return None, "Meeting not yet registered"

    meeting_info = KNOWN_MEETINGS[meeting_key]
    meeting_id   = meeting_info["id"]
    search_terms = report_meta["search"]
    label        = report_meta["label"]

    # Cache key: use report_key + meeting_ym (no item_id needed for finance path)
    cache_id = f"{category}_{meeting_ym}"
    cached_text = get_cached_text(report_key, meeting_ym, cache_id)
    if cached_text:
        return cached_text, "✅ cached"

    try:
        if category == "finance":
            # ── Finance path: attachment on Finance Committee item ────────────
            status_placeholder.info(
                f"📎 Searching Finance Committee attachments for '{label}' "
                f"in {meeting_info['label']}…")
            url, result = client.find_finance_attachment(meeting_id, search_terms)
            if url is None:
                return None, f"Not found — {result}"
            fname = result  # result is filename when url is not None
            status_placeholder.info(f"⬇️ Downloading {fname}…")

        else:
            # ── Director path: find agenda item by title ──────────────────────
            status_placeholder.info(
                f"🔍 Finding '{label}' agenda item in {meeting_info['label']}…")
            url, result = client.find_director_attachment(meeting_id, search_terms)
            if url is None:
                return None, f"Not found — {result}"
            fname = result
            status_placeholder.info(f"⬇️ Downloading {fname}…")

        pdf_bytes = client.download_file(url)
        status_placeholder.info(f"📄 Extracting text from {fname}…")
        from modules.extractor import extract_text_from_pdf_bytes
        text = extract_text_from_pdf_bytes(pdf_bytes)

        save_cached_text(report_key, meeting_ym, cache_id, text)
        return text, f"fetched ({fname})"

    except Exception as e:
        return None, f"Error: {e}"

        status_placeholder.info(f"📄 Extracting text from {fname}…")
        from modules.extractor import extract_text_from_pdf_bytes
        text = extract_text_from_pdf_bytes(pdf_bytes)

        save_cached_text(report_key, meeting_ym, item_id, text)
        return text, "fetched"

    except Exception as e:
        return None, f"Error: {e}"


# ── Helper: build PDF for trend analysis ─────────────────────────────────────
def _safe(text):
    """Escape HTML special chars for PDF paragraphs."""
    return str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_trend_pdf(fiscal_year: str, report_key: str, report_meta: dict,
                    category: str, analysis: dict, month_results: dict) -> bytes:
    from modules.pdf_output import generate_pdf

    label = report_meta["label"]
    sections = []
    months_in_fy = FISCAL_YEARS.get(fiscal_year, [])

    # ── Executive Summary ─────────────────────────────────────────────────────
    sections.append({"type": "heading1", "text": "Executive Summary"})
    sections.append({"type": "paragraph", "text": _safe(analysis.get("summary", ""))})

    # ── Flags ──────────────────────────────────────────────────────────────────
    flags = analysis.get("flags", [])
    if flags:
        sections.append({"type": "heading2", "text": "Flags &amp; Observations"})
        for flag in flags:
            pri = flag.get("priority", "medium")
            sections.append({
                "type": "flag",
                "text": f"<b>{_safe(flag.get('item',''))}:</b> {_safe(flag.get('observation',''))}",
                "priority": pri
            })
        sections.append({"type": "spacer", "height": 8})

    # ── Finance: collection rate table + full line-item breakdown ─────────────
    if category == "finance":
        ct = analysis.get("collection_table", [])
        if ct:
            sections.append({"type": "heading2", "text": "YTD Collection Rate by Month"})
            headers = ["Month", "YTD Earned", "Revised Budget", "% Collected", "Period Covered"]
            rows = [[
                r["month"],
                f"${r['earned']:,.0f}",
                f"${r['budget']:,.0f}",
                f"{r['pct']:.1f}%",
                r.get("date_range", "—"),
            ] for r in ct]
            sections.append({
                "type": "table", "headers": headers, "rows": rows,
                "col_widths": [2.8*28.35, 2.5*28.35, 2.5*28.35, 1.8*28.35, 3.0*28.35]
            })

        # Notable items (top earners in most recent month)
        notable = analysis.get("notable_items", [])
        if notable:
            sections.append({"type": "heading2", "text": "Top Revenue Sources (Most Recent Month)"})
            n_headers = ["Account", "Description", "Earned", "% of Budget"]
            n_rows = [[
                it["account"],
                it["description"][:45],
                f"${it['earned']:,.0f}",
                f"{it['pct_collected']:.1f}%" if it["pct_collected"] is not None else "—",
            ] for it in notable]
            sections.append({"type": "table", "headers": n_headers, "rows": n_rows})

        # Line-item trend table (all accounts across all months)
        line_items = analysis.get("line_items", {})
        ct_months = [r["month"] for r in ct]
        if line_items and ct_months:
            sections.append({"type": "pagebreak"})
            sections.append({"type": "heading1", "text": "Line-Item Revenue Trend"})
            sections.append({"type": "paragraph",
                "text": "YTD Revenue Earned per account code across the school year. "
                        "Percentages show collection rate vs. revised budget."})

            li_headers = ["Account", "Description"] + ct_months
            li_rows = []
            for acc, data in sorted(line_items.items()):
                desc = data["description"][:35]
                row = [acc, desc]
                for m in ct_months:
                    md = data["monthly"].get(m)
                    if md:
                        pct_s = f" ({md['pct']:.0f}%)" if md["pct"] is not None else ""
                        row.append(f"${md['earned']:,.0f}{pct_s}")
                    else:
                        row.append("—")
                li_rows.append(row)
            col_w = [1.6*28.35, 3.5*28.35] + [1.8*28.35]*len(ct_months)
            sections.append({"type": "table", "headers": li_headers, "rows": li_rows,
                              "col_widths": col_w})

    # ── Director: month-by-month topic grid + per-month narratives ────────────
    else:
        sections.append({"type": "heading2", "text": "Month-by-Month Overview"})
        m_headers = ["Month", "Status", "Key Topics"]
        m_rows = []
        for ym in months_in_fy:
            month_name = MONTH_LABELS.get(ym.split("-")[1], ym)
            ms = analysis.get("month_summaries", {}).get(month_name, {})
            if ms.get("status") == "extracted":
                topics = ", ".join(ms.get("topics", [])) or "—"
                m_rows.append([month_name, "✅", topics])
            else:
                m_rows.append([month_name, "—", "No data"])
        sections.append({"type": "table", "headers": m_headers, "rows": m_rows})

        # Theme frequency
        themes = analysis.get("themes", {})
        if themes:
            sections.append({"type": "heading2", "text": "Theme Frequency"})
            t_rows = [[t, str(len(m)), ", ".join(m) or "—"]
                      for t, m in sorted(themes.items(), key=lambda x: -len(x[1])) if m]
            if t_rows:
                sections.append({"type": "table",
                    "headers": ["Theme", "# Months", "Months Present"],
                    "rows": t_rows})

        # Per-month narrative detail
        sections.append({"type": "pagebreak"})
        sections.append({"type": "heading1", "text": "Month-by-Month Detail"})
        for ym in months_in_fy:
            month_name = MONTH_LABELS.get(ym.split("-")[1], ym)
            ms = analysis.get("month_summaries", {}).get(month_name, {})
            sections.append({"type": "heading2", "text": month_name})
            if ms.get("status") != "extracted":
                sections.append({"type": "callout", "text": "No report data for this month."})
                continue

            # Lead paragraph (first real sentences from the report)
            lead = ms.get("lead", "")
            if lead:
                sections.append({"type": "paragraph", "text": _safe(lead)})

            # Numeric facts extracted
            facts = ms.get("facts", [])
            if facts:
                sections.append({"type": "heading3", "text": "Key Statistics"})
                for fact in facts[:8]:
                    sections.append({"type": "bullet", "text": _safe(fact[:200])})

            # Topic-specific quotes
            topic_content = ms.get("topic_content", {})
            for topic, sents in list(topic_content.items())[:6]:
                if sents:
                    sections.append({"type": "heading3", "text": topic})
                    for s in sents[:2]:
                        sections.append({"type": "bullet", "text": _safe(s)})
            sections.append({"type": "rule"})

    return generate_pdf(
        title=f"{label} — School Year Trend",
        subtitle=f"Fiscal Year {fiscal_year}",
        period=f"Generated {datetime.date.today().strftime('%B %d, %Y')}",
        sections=sections,
        authors="BPCSD Board of Education"
    )


def build_yoy_pdf(report_key: str, report_meta: dict, month_str: str,
                  analysis: dict, category: str = "finance") -> bytes:
    from modules.pdf_output import generate_pdf

    label = report_meta["label"]
    sections = []

    sections.append({"type": "heading1", "text": "Year-over-Year Summary"})
    sections.append({"type": "paragraph", "text": _safe(analysis.get("summary", ""))})

    flags = analysis.get("flags", [])
    if flags:
        sections.append({"type": "heading2", "text": "Key Findings"})
        for flag in flags:
            pri = flag.get("priority", "medium")
            sections.append({
                "type": "flag",
                "text": "<b>" + _safe(flag.get("item","")) + ":</b> " + _safe(flag.get("observation","")),
                "priority": pri
            })
        sections.append({"type": "spacer", "height": 8})

    if category == "finance":
        totals_rows = analysis.get("totals_rows", [])
        if totals_rows:
            sections.append({"type": "heading2", "text": "Overall Totals Comparison"})
            headers = ["Fiscal Year", "Period Covered", "YTD Earned", "Revised Budget", "% Collected"]
            rows = [[
                r["year"],
                r.get("date_range", "—"),
                "${:,.0f}".format(r["earned"]),
                "${:,.0f}".format(r["budget"]),
                "{:.1f}%".format(r["pct"]),
            ] for r in totals_rows]
            sections.append({"type": "table", "headers": headers, "rows": rows})

        line_comparison = analysis.get("line_comparison", [])
        years = analysis.get("years", [])
        avail_years = [y for y in years if analysis.get("year_summaries", {}).get(y, {}).get("status") == "extracted"]
        if line_comparison and avail_years:
            sections.append({"type": "pagebreak"})
            sections.append({"type": "heading1", "text": "Line-Item Comparison"})
            sections.append({"type": "paragraph",
                "text": "Revenue Earned per account code, compared across fiscal years at the same calendar point."})
            li_headers = ["Account", "Description"] + avail_years
            li_rows = []
            for row in line_comparison:
                if not row["years"]:
                    continue
                r = [row["account"], row["description"][:35]]
                for fy in avail_years:
                    yd = row["years"].get(fy)
                    if yd:
                        pct_s = " ({:.0f}%)".format(yd["pct"]) if yd["pct"] is not None else ""
                        r.append("${:,.0f}{}".format(yd["earned"], pct_s))
                    else:
                        r.append("—")
                li_rows.append(r)
            col_w = [1.6*28.35, 3.5*28.35] + [2.5*28.35]*len(avail_years)
            sections.append({"type": "table", "headers": li_headers, "rows": li_rows,
                              "col_widths": col_w})
    else:
        year_summaries = analysis.get("year_summaries", {})
        for fy in analysis.get("years", []):
            ys = year_summaries.get(fy, {})
            sections.append({"type": "heading2", "text": "Fiscal Year " + fy})
            if ys.get("status") != "extracted":
                sections.append({"type": "callout", "text": "No data for this year."})
                continue
            lead = ys.get("lead", "")
            if lead:
                sections.append({"type": "paragraph", "text": _safe(lead)})
            facts = ys.get("facts", [])
            if facts:
                sections.append({"type": "heading3", "text": "Key Statistics"})
                for fact in facts[:6]:
                    sections.append({"type": "bullet", "text": _safe(fact[:200])})
            topic_content = ys.get("topic_content", {})
            for topic, sents in list(topic_content.items())[:6]:
                if sents:
                    sections.append({"type": "heading3", "text": topic})
                    for s in sents[:2]:
                        sections.append({"type": "bullet", "text": _safe(s)})
            sections.append({"type": "rule"})

    return generate_pdf(
        title=label + " — Year-over-Year",
        subtitle="Month: " + month_str,
        period="Generated " + __import__("datetime").date.today().strftime("%B %d, %Y"),
        sections=sections,
        authors="BPCSD Board of Education"
    )

# ── Build flat report lookup ──────────────────────────────────────────────────
ALL_REPORTS = {}   # key → (category, meta)
for cat_key, cat_val in REPORT_TYPES.items():
    for rpt_key, rpt_meta in cat_val["reports"].items():
        ALL_REPORTS[rpt_key] = (cat_key, rpt_meta)


# ═══════════════════════════════════════════════════════════════════════════════
#  BOARDDOCS LOGIN GATE — must pass before any app content is shown
# ═══════════════════════════════════════════════════════════════════════════════
if not _check_boarddocs_auth():
    st.stop()

# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🏫 BPCSD Board Analysis")
    st.markdown("*Broadalbin-Perth Central School District*")
    st.divider()

    # ── Session info ─────────────────────────────────────────────────────────
    signed_in_as = st.session_state.get("username", "")
    st.caption(f"✅ Signed in as **{signed_in_as}**")
    if st.button("🚪 Sign Out", use_container_width=True):
        for key in list(st.session_state.keys()):
            st.session_state.pop(key, None)
        st.rerun()

    st.divider()

    # ── Mode selector ─────────────────────────────────────────────────────────
    mode = st.radio(
        "Mode",
        ["📈 School Year Trend", "📊 Year-over-Year",
         "🔍 Discover Reports", "💬 Chat with Reports", "🗑 Cache Manager"],
        label_visibility="collapsed"
    )

    st.divider()

    # ── LLM API key (shown for Chat mode, stored in session) ─────────────────
    if mode == "💬 Chat with Reports":
        st.markdown("**AI Provider Key**")
        st.caption(
            "Get a free Gemini key at [aistudio.google.com](https://aistudio.google.com) "
            "or use an OpenAI/Anthropic key."
        )
        api_key_input = st.text_input(
            "API Key", type="password",
            value=st.session_state.get("llm_api_key", ""),
            placeholder="AIza... or sk-...",
            key="api_key_field"
        )
        if api_key_input and api_key_input != st.session_state.get("llm_api_key", ""):
            st.session_state["llm_api_key"] = api_key_input
            st.session_state.pop("llm_client_ok", None)  # force re-validation

        if st.session_state.get("llm_api_key"):
            if not st.session_state.get("llm_client_ok"):
                with st.spinner("Validating key…"):
                    try:
                        from modules.llm_chat import LLMClient
                        client_llm = LLMClient.from_key(st.session_state["llm_api_key"])
                        st.session_state["llm_client_ok"] = True
                        st.session_state["llm_provider_label"] = client_llm.provider_label
                        st.session_state["llm_model"] = client_llm.model
                    except Exception as e:
                        st.session_state["llm_client_ok"] = False
                        st.session_state["llm_key_error"] = str(e)

            if st.session_state.get("llm_client_ok"):
                st.success(f"✅ {st.session_state.get('llm_provider_label')} ({st.session_state.get('llm_model')})")
            else:
                st.error(st.session_state.get("llm_key_error", "Invalid key"))

        st.divider()

    # ── SCHOOL YEAR TREND SIDEBAR ─────────────────────────────────────────────
    if mode == "📈 School Year Trend":
        fy_options = list(FISCAL_YEARS.keys())
        fiscal_year = st.selectbox("📅 Fiscal Year", fy_options, index=0)
        months_in_fy = FISCAL_YEARS.get(fiscal_year, [])
        cached_set = list_cached_reports()

        with st.expander("💰 Finance Reports", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("All", key="sel_all_fin", use_container_width=True):
                    for k in REPORT_TYPES["finance"]["reports"]:
                        st.session_state[f"fin_{k}"] = True
            with col2:
                if st.button("None", key="clr_all_fin", use_container_width=True):
                    for k in REPORT_TYPES["finance"]["reports"]:
                        st.session_state[f"fin_{k}"] = False
            fin_selected = {}
            for rpt_key, rpt_meta in REPORT_TYPES["finance"]["reports"].items():
                cached_months = sum(
                    1 for ym in months_in_fy
                    if get_cached_text(rpt_key, ym) is not None
                )
                badge = f" ✅{cached_months}" if cached_months else ""
                fin_selected[rpt_key] = st.checkbox(
                    f"{rpt_meta['label']}{badge}", key=f"fin_{rpt_key}",
                    value=st.session_state.get(f"fin_{rpt_key}", False)
                )

        with st.expander("📋 Director Reports", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("All", key="sel_all_dir", use_container_width=True):
                    for k in REPORT_TYPES["director"]["reports"]:
                        st.session_state[f"dir_{k}"] = True
            with col2:
                if st.button("None", key="clr_all_dir", use_container_width=True):
                    for k in REPORT_TYPES["director"]["reports"]:
                        st.session_state[f"dir_{k}"] = False
            dir_selected = {}
            for rpt_key, rpt_meta in REPORT_TYPES["director"]["reports"].items():
                cached_months = sum(
                    1 for ym in months_in_fy
                    if get_cached_text(rpt_key, ym) is not None
                )
                badge = f" ✅{cached_months}" if cached_months else ""
                dir_selected[rpt_key] = st.checkbox(
                    f"{rpt_meta['label']}{badge}", key=f"dir_{rpt_key}",
                    value=st.session_state.get(f"dir_{rpt_key}", False)
                )

        selected_reports = {
            **{k: ("finance", REPORT_TYPES["finance"]["reports"][k])
               for k, v in fin_selected.items() if v},
            **{k: ("director", REPORT_TYPES["director"]["reports"][k])
               for k, v in dir_selected.items() if v},
        }
        n_sel = len(selected_reports)
        n_mo  = len(months_in_fy)
        st.caption(f"{n_sel} report(s) × {n_mo} months = up to {n_sel * n_mo} fetches")
        run_trend = st.button("🚀 Run Analysis", disabled=(n_sel == 0),
                               type="primary", use_container_width=True)

    # ── YoY SIDEBAR ───────────────────────────────────────────────────────────
    elif mode == "📊 Year-over-Year":
        rpt_options = {}
        for cat_key, cat_val in REPORT_TYPES.items():
            for rpt_key, rpt_meta in cat_val["reports"].items():
                rpt_options[rpt_key] = f"{cat_val['label']} › {rpt_meta['label']}"

        yoy_report_key = st.selectbox(
            "Report Type", options=list(rpt_options.keys()),
            format_func=lambda k: rpt_options[k]
        )
        yoy_category, yoy_report_meta = ALL_REPORTS[yoy_report_key]

        month_keys   = list(MONTH_LABELS.keys())
        month_labels_list = [MONTH_LABELS[m] for m in month_keys]
        yoy_month_idx = st.selectbox(
            "Month", options=range(len(month_keys)),
            format_func=lambda i: month_labels_list[i]
        )
        yoy_month_num = month_keys[yoy_month_idx]
        yoy_month_str = month_labels_list[yoy_month_idx]

        st.markdown("**Fiscal Years to Compare**")
        yoy_years_selected = {}
        for fy in FISCAL_YEARS:
            yoy_years_selected[fy] = st.checkbox(f"FY {fy}", key=f"yoy_{fy}", value=True)

        run_yoy = st.button("🚀 Run Comparison", type="primary",
                             use_container_width=True,
                             disabled=not any(yoy_years_selected.values()))

    # ── DISCOVER REPORTS SIDEBAR ──────────────────────────────────────────────
    elif mode == "🔍 Discover Reports":
        st.markdown("**Discovery Options**")
        disc_refresh = st.checkbox("Force refresh (ignore cache)", value=False)
        run_discovery = st.button("🔍 Run Discovery", type="primary",
                                   use_container_width=True)
        st.caption(
            "Discovery scans every meeting agenda, collects all attachments, "
            "and clusters them by report type. Takes 2–5 min for a full year."
        )

        catalog = get_report_catalog()
        if catalog:
            from modules.discovery import get_catalog_months, get_catalog_fiscal_years
            n_sections = len(catalog)
            all_types  = sum(len(v) for v in catalog.values())
            all_months = get_catalog_months(catalog)
            st.success(
                f"✅ Catalog: {n_sections} sections, {all_types} report types, "
                f"{len(all_months)} meetings covered"
            )

    # ── CHAT SIDEBAR ──────────────────────────────────────────────────────────
    elif mode == "💬 Chat with Reports":
        st.markdown("**Load Reports into Context**")
        chat_fy = st.selectbox("Fiscal Year", list(FISCAL_YEARS.keys()), key="chat_fy")

        # Which report types to load
        st.markdown("**Include:**")
        chat_reports = {}
        for cat_key, cat_val in REPORT_TYPES.items():
            for rpt_key, rpt_meta in cat_val["reports"].items():
                has_cache = any(
                    get_cached_text(rpt_key, ym) for ym in FISCAL_YEARS.get(chat_fy, [])
                )
                if has_cache:
                    chat_reports[rpt_key] = st.checkbox(
                        rpt_meta["label"], key=f"chat_{rpt_key}", value=False
                    )

        if not chat_reports:
            st.caption("No cached reports found for this fiscal year. "
                        "Run a trend analysis first to populate the cache.")

        load_chat = st.button("📚 Load into Context", type="primary",
                               use_container_width=True,
                               disabled=not any(chat_reports.values()))
        if st.button("🗑 Clear Chat History", use_container_width=True):
            st.session_state.pop("chat_history", None)
            st.session_state.pop("chat_context_docs", None)

    # ── CACHE MANAGER SIDEBAR ─────────────────────────────────────────────────
    elif mode == "🗑 Cache Manager":
        stats = get_cache_stats()
        st.metric("Cached text files", stats["text_entries"])
        st.metric("Total cache size", f"{stats['total_size_kb']} KB")
        st.metric("Meetings catalog", "✅ Ready" if stats["catalog_ready"] else "⚠️ Not built")

        if st.button("🗑 Clear ALL Cache", use_container_width=True):
            clear_all_cache()
            st.success("All cache cleared!")
            st.rerun()
        if st.button("🗑 Clear Discovery Only", use_container_width=True):
            clear_discovery_cache()
            st.success("Discovery cache cleared — text cache kept.")
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN PANEL
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div class="main-header">
    <h1>🏫 BPCSD Board Report Analysis</h1>
    <p>Broadalbin-Perth Central School District · Board of Education</p>
</div>
""", unsafe_allow_html=True)


# ── Welcome / idle state ─────────────────────────────────────────────────────
if "last_results" not in st.session_state:
    st.markdown("""
    ### Welcome to the BPCSD Board Analysis Tool

    This application retrieves and analyzes board reports directly from **BoardDocs**.

    ---

    #### 📈 School Year Trend
    1. Select a **Fiscal Year** (July–June)
    2. Check the **Finance** or **Director** reports you want to analyze
    3. Click **Generate Analysis**
    4. Download the resulting **PDF** report

    #### 📊 Year-over-Year Comparison
    1. Pick a **Report Type** and **Month**
    2. Select which **fiscal years** to compare
    3. Click **Generate Comparison**
    4. Download the **side-by-side PDF**

    ---

    #### Pipeline Overview

    | Step | Description |
    |------|-------------|
    | 🔐 Auth | Authenticate with BoardDocs using your credentials |
    | 🔍 Discover | Find the agenda item for each meeting |
    | ⬇️ Download | Retrieve the attached PDF file |
    | 📄 Extract | Pull text from the PDF via pdfplumber |
    | 🧠 Analyze | Identify themes, flags, and key figures |
    | 📊 Report | Generate a professional PDF for download |

    > **Tip:** Extracted reports are cached locally. Re-running the same analysis is instant.
    """)


# ═══════════════════════════════════════════════════════════════════════════════
#  SCHOOL YEAR TREND — RUN
# ═══════════════════════════════════════════════════════════════════════════════
if mode == "📈 School Year Trend" and run_trend:
    st.session_state.pop("last_results", None)

    months_in_fy = FISCAL_YEARS.get(fiscal_year, [])
    total_tasks  = len(selected_reports) * len(months_in_fy)

    st.markdown(f"### 📈 School Year Trend — FY {fiscal_year}")
    st.markdown(f"Analyzing **{len(selected_reports)}** report type(s) across **{len(months_in_fy)}** months…")

    prog_bar    = st.progress(0)
    status_msg  = st.empty()
    results_all = {}   # report_key → {month_name: text}

    # Authenticate
    try:
        with st.spinner("Authenticating with BoardDocs…"):
            client = get_client(st.session_state["username"], st.session_state["password"])
    except Exception as e:
        st.error(f"❌ Authentication failed: {e}")
        st.stop()

    task_done = 0

    for rpt_key, (category, rpt_meta) in selected_reports.items():
        month_results = {}

        for ym in months_in_fy:
            parts      = ym.split("-")
            year_part  = parts[0]
            month_part = parts[1]
            month_name = MONTH_LABELS.get(month_part, ym)

            text, status = fetch_report(client, ym, rpt_key, rpt_meta, status_msg,
                                           category=category)
            month_results[month_name] = text

            task_done += 1
            prog_bar.progress(task_done / total_tasks)

        results_all[rpt_key] = month_results

    prog_bar.progress(1.0)
    status_msg.success("✅ All reports processed!")

    # ── Display results per report type ──────────────────────────────────────
    st.divider()
    pdf_results = {}

    for rpt_key, month_results in results_all.items():
        category, rpt_meta = selected_reports[rpt_key]
        label = rpt_meta["label"]

        st.markdown(f"### {label}")

        # Analyze
        if category == "finance":
            from modules.analyzer import analyze_finance_trend
            analysis = analyze_finance_trend(month_results)
        else:
            from modules.analyzer import analyze_director_trend
            analysis = analyze_director_trend(month_results)

        # Summary card
        st.markdown(f"""
        <div class="summary-card">
            <strong>Summary:</strong> {analysis.get('summary','')}
        </div>
        """, unsafe_allow_html=True)

        # Flags
        flags = analysis.get("flags", [])
        if flags:
            st.markdown("**Flags & Observations**")
            for flag in flags:
                pri  = flag.get("priority", "medium")
                item = flag.get("item", "")
                obs  = flag.get("observation", "")
                icon = "🔴" if pri == "high" else ("🟡" if pri == "medium" else "🟢")
                cls  = f"flag-{pri}"
                st.markdown(f'<span class="{cls}">{icon} <b>{item}</b></span> — {obs}',
                            unsafe_allow_html=True)

        if category == "finance":
            # Collection rate table
            ct = analysis.get("collection_table", [])
            if ct:
                st.markdown("**YTD Collection Rate by Month**")
                import pandas as pd
                ct_df = pd.DataFrame([{
                    "Month":          r["month"],
                    "YTD Earned":     f"${r['earned']:,.0f}",
                    "Revised Budget": f"${r['budget']:,.0f}",
                    "% Collected":    f"{r['pct']:.1f}%",
                    "Period":         r.get("date_range",""),
                } for r in ct])
                st.dataframe(ct_df, use_container_width=True, hide_index=True)

            # Notable items (top earners)
            notable = analysis.get("notable_items", [])
            if notable:
                with st.expander("📊 Top Revenue Sources (Most Recent Month)"):
                    n_df = pd.DataFrame([{
                        "Account":    it["account"],
                        "Description": it["description"][:50],
                        "YTD Earned": f"${it['earned']:,.0f}",
                        "% of Budget": f"{it['pct_collected']:.1f}%" if it["pct_collected"] is not None else "—",
                    } for it in notable])
                    st.dataframe(n_df, use_container_width=True, hide_index=True)

            # Full line-item trend (all accounts × all months)
            line_items = analysis.get("line_items", {})
            ct_months = [r["month"] for r in ct]
            if line_items and ct_months:
                with st.expander("📈 Full Line-Item Revenue Trend (All Accounts × All Months)"):
                    li_rows = []
                    for acc, data in sorted(line_items.items()):
                        row = {"Account": acc, "Description": data["description"][:40]}
                        for m in ct_months:
                            md = data["monthly"].get(m)
                            if md:
                                pct_s = f" ({md['pct']:.0f}%)" if md["pct"] is not None else ""
                                row[m] = f"${md['earned']:,.0f}{pct_s}"
                            else:
                                row[m] = "—"
                        li_rows.append(row)
                    if li_rows:
                        st.dataframe(pd.DataFrame(li_rows), use_container_width=True, hide_index=True)

        else:
            # Director: month-by-month detail with real content
            months_in_fy_order = FISCAL_YEARS.get(fiscal_year, [])
            import pandas as pd

            # Theme summary table
            themes = analysis.get("themes", {})
            if themes:
                with st.expander("📊 Theme Frequency Table"):
                    t_rows = [{"Theme": t, "Months": len(m), "Present In": ", ".join(m)}
                              for t, m in sorted(themes.items(), key=lambda x: -len(x[1])) if m]
                    if t_rows:
                        st.dataframe(pd.DataFrame(t_rows), use_container_width=True, hide_index=True)

            # Per-month rich detail
            for ym in months_in_fy_order:
                month_name = MONTH_LABELS.get(ym.split("-")[1], ym)
                ms = analysis.get("month_summaries", {}).get(month_name, {})
                if ms.get("status") != "extracted":
                    continue
                with st.expander(f"📄 {month_name}"):
                    lead = ms.get("lead","")
                    if lead:
                        st.markdown(f"*{lead}*")
                    facts = ms.get("facts",[])
                    if facts:
                        st.markdown("**Key Numbers & Statistics**")
                        for fact in facts[:8]:
                            st.markdown(f"- {fact[:200]}")
                    topic_content = ms.get("topic_content",{})
                    if topic_content:
                        st.markdown("**Topics Covered**")
                        for topic, sents in topic_content.items():
                            if sents:
                                st.markdown(f"**{topic}**")
                                for s in sents[:2]:
                                    st.caption(s[:250])

        # Generate PDF
        with st.spinner(f"Generating PDF for {label}…"):
            try:
                pdf_bytes = build_trend_pdf(
                    fiscal_year, rpt_key, rpt_meta, category, analysis, month_results
                )
                pdf_results[rpt_key] = pdf_bytes
                st.download_button(
                    label=f"📄 Download PDF — {label}",
                    data=pdf_bytes,
                    file_name=f"BPCSD_{rpt_key}_{fiscal_year}_trend.pdf",
                    mime="application/pdf",
                    key=f"dl_{rpt_key}"
                )
            except Exception as e:
                st.error(f"PDF generation failed: {e}")

        st.divider()

    st.session_state["last_results"] = pdf_results
    st.success("🎉 Analysis complete!")


# ═══════════════════════════════════════════════════════════════════════════════
#  YEAR-OVER-YEAR — RUN
# ═══════════════════════════════════════════════════════════════════════════════
if mode == "📊 Year-over-Year" and run_yoy:
    st.session_state.pop("last_results", None)

    selected_fy = [fy for fy, v in yoy_years_selected.items() if v]

    st.markdown(f"### 📊 Year-over-Year — {yoy_report_meta['label']} ({yoy_month_str})")
    st.markdown(f"Comparing **{len(selected_fy)}** fiscal year(s)…")

    prog_bar   = st.progress(0)
    status_msg = st.empty()

    # Authenticate
    try:
        with st.spinner("Authenticating with BoardDocs…"):
            client = get_client(st.session_state["username"], st.session_state["password"])
    except Exception as e:
        st.error(f"❌ Authentication failed: {e}")
        st.stop()

    reports_by_year = {}

    for i, fy in enumerate(selected_fy):
        # Find the YYYY-MM for this fiscal year + selected month
        months_in_fy = FISCAL_YEARS.get(fy, [])
        ym_match = None
        for ym in months_in_fy:
            if ym.endswith(f"-{yoy_month_num}"):
                ym_match = ym
                break

        if ym_match is None:
            reports_by_year[fy] = None
            status_msg.warning(f"Month {yoy_month_str} not found in FY {fy}")
        else:
            text, status = fetch_report(
                client, ym_match, yoy_report_key, yoy_report_meta, status_msg,
                category=get_report_category(yoy_report_key)
            )
            reports_by_year[fy] = text or ""
            status_msg.info(f"FY {fy}: {status}")

        prog_bar.progress((i + 1) / len(selected_fy))

    prog_bar.progress(1.0)
    status_msg.success("✅ All years processed!")

    # Analyze — pass category so the right parser is used
    from modules.analyzer import analyze_yoy
    analysis = analyze_yoy(
        reports_by_year, yoy_report_meta["label"],
        report_category=yoy_category
    )

    st.divider()
    st.markdown(f"""
    <div class="summary-card">
        <strong>Summary:</strong> {analysis.get('summary','')}
    </div>
    """, unsafe_allow_html=True)

    for flag in analysis.get("flags", []):
        pri  = flag.get("priority","medium")
        icon = "\U0001f534" if pri=="high" else ("\U0001f7e1" if pri=="medium" else "\U0001f7e2")
        cls  = f"flag-{pri}"
        st.markdown(
            f'<span class="{cls}">{icon} <b>{flag["item"]}</b></span> — {flag["observation"]}',
            unsafe_allow_html=True)

    import pandas as pd
    if yoy_category == "finance":
        totals_rows = analysis.get("totals_rows", [])
        if totals_rows:
            st.markdown("**Overall Totals Comparison**")
            t_df = pd.DataFrame([{
                "Fiscal Year":    r["year"],
                "Period":         r.get("date_range",""),
                "YTD Earned":     "${:,.0f}".format(r["earned"]),
                "Revised Budget": "${:,.0f}".format(r["budget"]),
                "% Collected":    "{:.1f}%".format(r["pct"]),
            } for r in totals_rows])
            st.dataframe(t_df, use_container_width=True, hide_index=True)

        line_comparison = analysis.get("line_comparison", [])
        years_avail = [y for y in analysis.get("years",[])
                       if analysis.get("year_summaries",{}).get(y,{}).get("status")=="extracted"]
        if line_comparison and years_avail:
            with st.expander("\U0001f4c8 Line-Item Comparison (All Accounts)"):
                li_rows = []
                for row in line_comparison:
                    if not row["years"]:
                        continue
                    r = {"Account": row["account"], "Description": row["description"][:40]}
                    for fy in years_avail:
                        yd = row["years"].get(fy)
                        if yd:
                            pct_s = " ({:.0f}%)".format(yd["pct"]) if yd["pct"] is not None else ""
                            r[fy] = "${:,.0f}{}".format(yd["earned"], pct_s)
                        else:
                            r[fy] = "—"
                    li_rows.append(r)
                if li_rows:
                    st.dataframe(pd.DataFrame(li_rows), use_container_width=True, hide_index=True)
    else:
        year_summaries = analysis.get("year_summaries", {})
        for fy in analysis.get("years", []):
            ys = year_summaries.get(fy, {})
            with st.expander(f"\U0001f4c4 FY {fy}"):
                if ys.get("status") != "extracted":
                    st.caption("No data available.")
                    continue
                lead = ys.get("lead","")
                if lead:
                    st.markdown(f"*{lead}*")
                facts = ys.get("facts",[])
                if facts:
                    st.markdown("**Key Numbers & Statistics**")
                    for fact in facts[:8]:
                        st.markdown(f"- {fact[:200]}")
                topic_content = ys.get("topic_content",{})
                if topic_content:
                    st.markdown("**Topics Covered**")
                    for topic, sents in topic_content.items():
                        if sents:
                            st.markdown(f"**{topic}**")
                            for s in sents[:2]:
                                st.caption(s[:250])

    # Previews
    for yr, text in reports_by_year.items():
        with st.expander(f"📄 FY {yr} — Preview"):
            if text:
                st.text_area(
                    label=yr,
                    value=text[:800] + ("…" if len(text) > 800 else ""),
                    height=150,
                    label_visibility="collapsed",
                    key=f"yoy_prev_{yr}"
                )
            else:
                st.caption("No data available.")

    # PDF download
    with st.spinner("Generating comparison PDF…"):
        try:
            pdf_bytes = build_yoy_pdf(
                yoy_report_key, yoy_report_meta,
                yoy_month_str, analysis
            )
            st.download_button(
                label="📄 Download Year-over-Year PDF",
                data=pdf_bytes,
                file_name=f"BPCSD_{yoy_report_key}_{yoy_month_num}_YoY.pdf",
                mime="application/pdf",
                key="dl_yoy"
            )
        except Exception as e:
            st.error(f"PDF generation failed: {e}")

    st.success("🎉 Comparison complete!")


# ═══════════════════════════════════════════════════════════════════════════════
#  DISCOVERY MODE
# ═══════════════════════════════════════════════════════════════════════════════
if mode == "🔍 Discover Reports":
    st.markdown("## 🔍 Report Discovery")
    st.markdown(
        "Scans every meeting agenda in BoardDocs, collects all attachments, "
        "and automatically clusters them by report type across all years."
    )

    catalog = None if disc_refresh else get_report_catalog()

    if run_discovery or (catalog is None and not run_discovery):
        if run_discovery:
            # Full discovery run
            from modules.discovery import discover_all_meetings, build_report_catalog
            from modules.cache import save_cached_meetings

            st.info("🔍 Discovering meetings…")
            prog = st.progress(0.0)
            status_disc = st.empty()

            meetings = discover_all_meetings(client)
            save_cached_meetings(meetings)
            status_disc.success(f"✅ Found {len(meetings)} meetings")

            def disc_progress(i, total, msg):
                prog.progress(i / max(total, 1))
                status_disc.info(msg)

            status_disc.info(f"📂 Scanning {len(meetings)} meeting agendas for attachments…")
            catalog = build_report_catalog(client, meetings, disc_progress)
            save_report_catalog(catalog)
            prog.progress(1.0)
            status_disc.success(f"✅ Discovery complete! Found {sum(len(v) for v in catalog.values())} report types across {len(catalog)} sections.")

    if catalog:
        from modules.discovery import get_catalog_months, get_catalog_fiscal_years
        import pandas as pd

        all_months = sorted(get_catalog_months(catalog))
        fiscal_years_disc = get_catalog_fiscal_years(catalog)

        # Fiscal year filter for grid
        fy_filter = st.selectbox("Filter by Fiscal Year", ["All"] + fiscal_years_disc,
                                  key="disc_fy_filter")

        def _in_fy(ym, fy):
            if fy == "All":
                return True
            yr, mo = int(ym[:4]), int(ym[5:7])
            fy_start_yr = int(fy[:4])
            return (yr == fy_start_yr and mo >= 7) or (yr == fy_start_yr + 1 and mo <= 6)

        filtered_months = [m for m in all_months if _in_fy(m, fy_filter)]

        for section_name, section_reports in sorted(catalog.items()):
            st.markdown(f"### {section_name}")
            grid_rows = []
            for slug, rpt_data in sorted(section_reports.items()):
                row = {"Report": rpt_data["label"]}
                for ym in filtered_months:
                    mo = MONTH_LABELS.get(ym.split("-")[1], ym)
                    yr = ym[:4]
                    col_label = f"{mo[:3]} {yr[2:]}"
                    mtg = rpt_data["meetings"].get(ym)
                    if mtg:
                        cached = get_cached_text(slug, ym) is not None
                        row[col_label] = "✅" if cached else "📄"
                    else:
                        row[col_label] = "—"
                grid_rows.append(row)

            if grid_rows:
                df_grid = pd.DataFrame(grid_rows).set_index("Report")
                st.dataframe(df_grid, use_container_width=True)

        st.caption("✅ = cached (text extracted) | 📄 = available (not yet cached) | — = no report")

        # Download report from grid
        st.markdown("---")
        st.markdown("### Fetch a Specific Report")
        col_sec, col_rpt, col_mo = st.columns(3)
        with col_sec:
            fetch_section = st.selectbox("Section", list(catalog.keys()), key="fetch_sec")
        with col_rpt:
            rpts_in_sec = catalog.get(fetch_section, {})
            fetch_slug  = st.selectbox("Report", list(rpts_in_sec.keys()),
                                        format_func=lambda s: rpts_in_sec[s]["label"],
                                        key="fetch_rpt")
        with col_mo:
            avail_months = list(catalog.get(fetch_section, {}).get(fetch_slug, {}).get("meetings", {}).keys())
            fetch_ym = st.selectbox("Meeting Month", avail_months, key="fetch_ym")

        if st.button("⬇️ Fetch & Extract", type="primary"):
            mtg_info = catalog[fetch_section][fetch_slug]["meetings"].get(fetch_ym, {})
            url = mtg_info.get("url")
            if url:
                with st.spinner(f"Downloading {mtg_info.get('filename','report')}…"):
                    try:
                        pdf_bytes = client.download_file(url)
                        from modules.extractor import extract_text_from_pdf_bytes
                        text = extract_text_from_pdf_bytes(pdf_bytes)
                        save_cached_text(fetch_slug, fetch_ym, None, text)
                        st.success(f"✅ Extracted {len(text):,} chars → cached as {fetch_slug}/{fetch_ym}")
                        st.text_area("Preview", text[:800], height=200)
                    except Exception as e:
                        st.error(f"Failed: {e}")
            else:
                st.warning("No URL found for this report.")

    elif not run_discovery:
        st.info("Click **Run Discovery** in the sidebar to scan all available meetings and reports.")


# ═══════════════════════════════════════════════════════════════════════════════
#  CHAT MODE
# ═══════════════════════════════════════════════════════════════════════════════
if mode == "💬 Chat with Reports":
    st.markdown("## 💬 Chat with Board Reports")

    if not st.session_state.get("llm_api_key"):
        st.warning("Enter your AI API key in the sidebar to enable chat.")
        st.markdown("""
        **How to get a free Gemini API key:**
        1. Go to [aistudio.google.com](https://aistudio.google.com)
        2. Sign in with your Google account
        3. Click **Get API key** → **Create API key**
        4. Paste it in the sidebar

        The free tier supports ~1,500 requests/day with a 1M-token context window — more than enough for a full year of board reports.
        """)
        st.stop()

    if not st.session_state.get("llm_client_ok"):
        st.error("API key validation failed. Check the key in the sidebar.")
        st.stop()

    # Load context docs when button pressed
    if load_chat and any(chat_reports.values()):
        context_docs = {}
        months_in_chat_fy = FISCAL_YEARS.get(chat_fy, [])
        for rpt_key, selected in chat_reports.items():
            if not selected:
                continue
            cat_key = get_report_category(rpt_key)
            rpt_meta = REPORT_TYPES[cat_key]["reports"][rpt_key]
            for ym in months_in_chat_fy:
                text = get_cached_text(rpt_key, ym)
                if text:
                    mo_name = MONTH_LABELS.get(ym.split("-")[1], ym)
                    doc_title = f"{rpt_meta['label']} — {mo_name} {ym[:4]}"
                    context_docs[doc_title] = text
        st.session_state["chat_context_docs"] = context_docs
        st.session_state["chat_history"] = []
        total_chars = sum(len(v) for v in context_docs.values())
        st.success(f"✅ Loaded {len(context_docs)} report(s) into context ({total_chars:,} chars)")

    context_docs = st.session_state.get("chat_context_docs", {})
    if not context_docs:
        st.info("Select reports and click **Load into Context** in the sidebar to begin chatting.")
        st.stop()

    # Show what's loaded
    with st.expander(f"📚 Context: {len(context_docs)} report(s) loaded"):
        for title in context_docs:
            st.caption(f"• {title} ({len(context_docs[title]):,} chars)")

    # Chat interface
    chat_history = st.session_state.get("chat_history", [])
    for msg in chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if question := st.chat_input("Ask a question about the loaded reports…"):
        chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    from modules.llm_chat import LLMClient
                    llm = LLMClient.from_key(st.session_state["llm_api_key"])
                    answer = llm.chat(
                        context_docs=context_docs,
                        history=chat_history[:-1],  # exclude the just-appended question
                        question=question,
                    )
                    st.markdown(answer)
                    chat_history.append({"role": "assistant", "content": answer})
                except Exception as e:
                    err = f"Error communicating with AI: {e}"
                    st.error(err)
                    chat_history.append({"role": "assistant", "content": err})

        st.session_state["chat_history"] = chat_history


# ═══════════════════════════════════════════════════════════════════════════════
#  CACHE MANAGER MODE
# ═══════════════════════════════════════════════════════════════════════════════
if mode == "🗑 Cache Manager":
    st.markdown("## 🗑 Cache Manager")
    st.markdown("View, selectively delete, or bulk-clear cached report text.")

    import pandas as pd
    inventory = get_cache_inventory()

    if not inventory:
        st.info("Cache is empty — run some analyses to populate it.")
    else:
        # Group by report type for display
        grouped = {}
        for item in inventory:
            rt = item["report_type"]
            grouped.setdefault(rt, []).append(item)

        for rt, items in sorted(grouped.items()):
            with st.expander(f"**{rt}** — {len(items)} cached month(s)"):
                for item in items:
                    col_a, col_b, col_c = st.columns([3, 1, 1])
                    with col_a:
                        st.caption(
                            f"{item['meeting_ym']} — {item['size_kb']} KB — "
                            f"{item['age_hours']:.0f}h ago"
                        )
                    with col_b:
                        pass  # spacer
                    with col_c:
                        btn_key = f"del_{item['path']}"
                        if st.button("Delete", key=btn_key, use_container_width=True):
                            delete_cache_entry(item["path"])
                            st.success(f"Deleted {item['meeting_ym']}")
                            st.rerun()

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑 Clear All Text Cache", use_container_width=True, type="secondary"):
            clear_all_cache()
            st.success("All cache cleared!")
            st.rerun()
    with col2:
        if st.button("🗑 Clear Discovery Only", use_container_width=True, type="secondary"):
            clear_discovery_cache()
            st.success("Discovery cache cleared.")
            st.rerun()

