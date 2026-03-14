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
    list_cached_reports, clear_cache
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
def build_trend_pdf(fiscal_year: str, report_key: str, report_meta: dict,
                    category: str, analysis: dict, month_results: dict) -> bytes:
    from modules.pdf_output import generate_pdf

    label = report_meta["label"]
    sections = []

    # Executive Summary
    sections.append({"type": "heading1", "text": "Executive Summary"})
    sections.append({"type": "paragraph", "text": analysis.get("summary", "")})

    # Flags
    flags = analysis.get("flags", [])
    if flags:
        sections.append({"type": "heading2", "text": "Flags & Observations"})
        for flag in flags:
            pri  = flag.get("priority", "medium")
            item = flag.get("item", "")
            obs  = flag.get("observation", "")
            sections.append({"type": "flag", "text": f"<b>{item}:</b> {obs}", "priority": pri})
        sections.append({"type": "spacer", "height": 12})

    # Month-by-month table
    months_in_fy = FISCAL_YEARS.get(fiscal_year, [])
    sections.append({"type": "heading2", "text": "Month-by-Month Summary"})

    if category == "finance":
        headers = ["Month", "Status", "Top Amount", "YTD %", "Text Length"]
        rows = []
        for ym in months_in_fy:
            month_num = ym.split("-")[1]
            month_name = MONTH_LABELS.get(month_num, ym)
            ms = analysis.get("month_summaries", {}).get(month_name, {})
            status   = ms.get("status", "no_data")
            top_amt  = ms.get("top_dollar", "—")
            pct      = ms.get("pct_ytd", "—")
            chars    = str(ms.get("text_length", 0))
            status_lbl = "✅ Extracted" if status == "extracted" else "⚠ No data"
            rows.append([month_name, status_lbl, top_amt, pct, chars])
        sections.append({
            "type": "table",
            "headers": headers,
            "rows": rows,
        })
    else:
        # Director
        all_themes = sorted(analysis.get("themes", {}).keys())
        headers = ["Month", "Status", "Topics Found"]
        rows = []
        for ym in months_in_fy:
            month_num  = ym.split("-")[1]
            month_name = MONTH_LABELS.get(month_num, ym)
            ms = analysis.get("month_summaries", {}).get(month_name, {})
            status = ms.get("status", "no_data")
            topics = ", ".join(ms.get("topics", [])) or "—"
            status_lbl = "✅ Extracted" if status == "extracted" else "⚠ No data"
            rows.append([month_name, status_lbl, topics])
        sections.append({
            "type": "table",
            "headers": headers,
            "rows": rows,
        })

        # Themes table
        if analysis.get("themes"):
            sections.append({"type": "heading2", "text": "Theme Frequency Table"})
            theme_rows = []
            for topic, months in sorted(analysis["themes"].items(), key=lambda x: -len(x[1])):
                theme_rows.append([topic, str(len(months)), ", ".join(months) or "—"])
            sections.append({
                "type": "table",
                "headers": ["Theme", "# Months", "Months Present"],
                "rows": theme_rows,
            })

    # Month detail previews
    sections.append({"type": "pagebreak"})
    sections.append({"type": "heading1", "text": "Document Previews by Month"})
    for ym in months_in_fy:
        month_num  = ym.split("-")[1]
        month_name = MONTH_LABELS.get(month_num, ym)
        text = month_results.get(month_name)
        sections.append({"type": "heading2", "text": month_name})
        if text:
            preview = text[:800].replace("<", "&lt;").replace(">", "&gt;")
            sections.append({"type": "paragraph", "text": preview})
        else:
            sections.append({"type": "callout", "text": "No report data available for this month."})
        sections.append({"type": "rule"})

    return generate_pdf(
        title=f"{label} — School Year Trend",
        subtitle=f"Fiscal Year {fiscal_year}",
        period=f"Generated {datetime.date.today().strftime('%B %d, %Y')}",
        sections=sections,
        authors="BPCSD Board of Education"
    )


def build_yoy_pdf(report_key: str, report_meta: dict, month_str: str,
                  analysis: dict) -> bytes:
    from modules.pdf_output import generate_pdf

    label = report_meta["label"]
    sections = []

    sections.append({"type": "heading1", "text": "Year-over-Year Summary"})
    sections.append({"type": "paragraph", "text": analysis.get("summary", "")})

    flags = analysis.get("flags", [])
    if flags:
        sections.append({"type": "heading2", "text": "Flags"})
        for flag in flags:
            pri  = flag.get("priority", "medium")
            item = flag.get("item", "")
            obs  = flag.get("observation", "")
            sections.append({"type": "flag", "text": f"<b>{item}:</b> {obs}", "priority": pri})

    # Year comparison table
    sections.append({"type": "heading2", "text": "Year Comparison"})
    year_summaries = analysis.get("year_summaries", {})
    headers = ["Fiscal Year", "Status", "Document Length", "Preview"]
    rows = []
    for yr in analysis.get("years", []):
        ys     = year_summaries.get(yr, {})
        status = "✅ Extracted" if ys.get("status") == "extracted" else "⚠ No data"
        chars  = str(ys.get("text_length", 0))
        preview= (ys.get("preview","")[:120] + "…") if ys.get("preview") else "—"
        preview = preview.replace("<","&lt;").replace(">","&gt;")
        rows.append([yr, status, chars, preview])
    sections.append({"type": "table", "headers": headers, "rows": rows})

    # Full previews per year
    sections.append({"type": "pagebreak"})
    sections.append({"type": "heading1", "text": "Document Previews by Year"})
    for yr, text in analysis.get("raw_years", {}).items():
        sections.append({"type": "heading2", "text": f"Fiscal Year {yr}"})
        if text:
            preview = text[:800].replace("<","&lt;").replace(">","&gt;")
            sections.append({"type": "paragraph", "text": preview})
        else:
            sections.append({"type": "callout", "text": "No report data available for this year."})
        sections.append({"type": "rule"})

    return generate_pdf(
        title=f"{label} — Year-over-Year",
        subtitle=f"Month: {month_str}",
        period=f"Generated {datetime.date.today().strftime('%B %d, %Y')}",
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
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🗑 Clear Cache", use_container_width=True):
            clear_cache()
            st.success("Cache cleared!")
    with col_b:
        if st.button("🚪 Sign Out", use_container_width=True):
            for key in ["app_authenticated", "username", "password"]:
                st.session_state.pop(key, None)
            # Remove any stored clients
            for key in list(st.session_state.keys()):
                if key.startswith("client_"):
                    st.session_state.pop(key, None)
            st.rerun()

    st.divider()

    # ── Mode selector ────────────────────────────────────────────────────────
    mode = st.radio(
        "Analysis Mode",
        ["📈 School Year Trend", "📊 Year-over-Year Comparison"],
        label_visibility="collapsed"
    )

    st.divider()

    # ── Cache status helper ───────────────────────────────────────────────────
    cached_set = list_cached_reports()

    # ── SCHOOL YEAR TREND SIDEBAR ────────────────────────────────────────────
    if mode == "📈 School Year Trend":
        fy_options = list(FISCAL_YEARS.keys())
        fiscal_year = st.selectbox("📅 Fiscal Year", fy_options, index=0)

        months_in_fy = FISCAL_YEARS.get(fiscal_year, [])

        # Finance Reports
        with st.expander("💰 Finance Reports", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Select All", key="sel_all_fin", use_container_width=True):
                    for k in REPORT_TYPES["finance"]["reports"]:
                        st.session_state[f"fin_{k}"] = True
            with col2:
                if st.button("Clear All", key="clr_all_fin", use_container_width=True):
                    for k in REPORT_TYPES["finance"]["reports"]:
                        st.session_state[f"fin_{k}"] = False

            fin_selected = {}
            for rpt_key, rpt_meta in REPORT_TYPES["finance"]["reports"].items():
                cached_months = sum(
                    1 for ym in months_in_fy
                    if (rpt_key, ym.split("-")[0] + "-" + ym.split("-")[1]) in cached_set
                )
                cache_badge = f" ✅{cached_months}" if cached_months else ""
                val = st.checkbox(
                    f"{rpt_meta['label']}{cache_badge}",
                    key=f"fin_{rpt_key}",
                    value=st.session_state.get(f"fin_{rpt_key}", False)
                )
                fin_selected[rpt_key] = val

        # Director Reports
        with st.expander("📋 Director Reports", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Select All", key="sel_all_dir", use_container_width=True):
                    for k in REPORT_TYPES["director"]["reports"]:
                        st.session_state[f"dir_{k}"] = True
            with col2:
                if st.button("Clear All", key="clr_all_dir", use_container_width=True):
                    for k in REPORT_TYPES["director"]["reports"]:
                        st.session_state[f"dir_{k}"] = False

            dir_selected = {}
            for rpt_key, rpt_meta in REPORT_TYPES["director"]["reports"].items():
                cached_months = sum(
                    1 for ym in months_in_fy
                    if (rpt_key, ym.split("-")[0] + "-" + ym.split("-")[1]) in cached_set
                )
                cache_badge = f" ✅{cached_months}" if cached_months else ""
                val = st.checkbox(
                    f"{rpt_meta['label']}{cache_badge}",
                    key=f"dir_{rpt_key}",
                    value=st.session_state.get(f"dir_{rpt_key}", False)
                )
                dir_selected[rpt_key] = val

        selected_reports = {
            **{k: ("finance", REPORT_TYPES["finance"]["reports"][k])
               for k, v in fin_selected.items() if v},
            **{k: ("director", REPORT_TYPES["director"]["reports"][k])
               for k, v in dir_selected.items() if v},
        }

        n_selected = len(selected_reports)
        n_months   = len(months_in_fy)
        st.caption(f"{n_selected} report type(s) × {n_months} months = up to {n_selected * n_months} fetches")

        run_trend = st.button(
            "🚀 Generate Analysis",
            disabled=(n_selected == 0),
            type="primary",
            use_container_width=True
        )

    # ── YoY COMPARISON SIDEBAR ───────────────────────────────────────────────
    else:
        # Flat list of all report types
        rpt_options = {}
        for cat_key, cat_val in REPORT_TYPES.items():
            for rpt_key, rpt_meta in cat_val["reports"].items():
                rpt_options[rpt_key] = f"{cat_val['label']} › {rpt_meta['label']}"

        yoy_report_key = st.selectbox(
            "Report Type",
            options=list(rpt_options.keys()),
            format_func=lambda k: rpt_options[k]
        )
        yoy_category, yoy_report_meta = ALL_REPORTS[yoy_report_key]

        month_keys   = list(MONTH_LABELS.keys())
        month_labels = [MONTH_LABELS[m] for m in month_keys]
        yoy_month_idx = st.selectbox(
            "Month",
            options=range(len(month_keys)),
            format_func=lambda i: month_labels[i]
        )
        yoy_month_num = month_keys[yoy_month_idx]
        yoy_month_str = month_labels[yoy_month_idx]

        st.markdown("**Fiscal Years to Compare**")
        yoy_years_selected = {}
        for fy in FISCAL_YEARS:
            yoy_years_selected[fy] = st.checkbox(f"FY {fy}", key=f"yoy_{fy}", value=True)

        run_yoy = st.button(
            "🚀 Generate Comparison",
            type="primary",
            use_container_width=True,
            disabled=not any(yoy_years_selected.values())
        )


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
            # Map month name → text
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
                st.markdown(
                    f'<span class="{cls}">{icon} {item}:</span> {obs}',
                    unsafe_allow_html=True
                )

        # Month-by-month table
        months_in_fy_order = FISCAL_YEARS.get(fiscal_year, [])
        table_data = []
        for ym in months_in_fy_order:
            month_num  = ym.split("-")[1]
            month_name = MONTH_LABELS.get(month_num, ym)
            ms = analysis.get("month_summaries", {}).get(month_name, {})
            status = ms.get("status", "no_data")
            status_icon = "✅" if status == "extracted" else "⚠️"

            row = {"Month": month_name, "Status": status_icon}

            if category == "finance":
                row["Top Amount"] = ms.get("top_dollar", "—")
                row["YTD %"]      = ms.get("pct_ytd", "—")
                row["Length"]     = ms.get("text_length", 0)
            else:
                row["Topics"] = ", ".join(ms.get("topics", [])) or "—"
                row["Length"] = ms.get("text_length", 0)

            table_data.append(row)

        if table_data:
            import pandas as pd
            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Director: themes
        if category == "director" and analysis.get("themes"):
            with st.expander("📊 Theme Frequency Table"):
                theme_rows = [
                    {"Theme": t, "Months Present": len(m), "Details": ", ".join(m)}
                    for t, m in sorted(analysis["themes"].items(), key=lambda x: -len(x[1]))
                    if m
                ]
                if theme_rows:
                    st.dataframe(pd.DataFrame(theme_rows), use_container_width=True, hide_index=True)

        # Month previews
        with st.expander("📄 Document Previews"):
            for ym in months_in_fy_order:
                month_num  = ym.split("-")[1]
                month_name = MONTH_LABELS.get(month_num, ym)
                text = month_results.get(month_name)
                if text:
                    st.markdown(f"**{month_name}** — {len(text):,} chars")
                    st.text_area(
                        label=month_name,
                        value=text[:600] + ("…" if len(text) > 600 else ""),
                        height=100,
                        label_visibility="collapsed",
                        key=f"prev_{rpt_key}_{ym}"
                    )
                else:
                    st.caption(f"**{month_name}** — No data")

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
if mode == "📊 Year-over-Year Comparison" and run_yoy:
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

    # Analyze
    from modules.analyzer import analyze_yoy
    analysis = analyze_yoy(reports_by_year, yoy_report_meta["label"])

    st.divider()
    st.markdown(f"""
    <div class="summary-card">
        <strong>Summary:</strong> {analysis.get('summary','')}
    </div>
    """, unsafe_allow_html=True)

    # Flags
    for flag in analysis.get("flags", []):
        pri  = flag.get("priority","medium")
        icon = "🔴" if pri=="high" else ("🟡" if pri=="medium" else "🟢")
        st.markdown(f'{icon} **{flag["item"]}:** {flag["observation"]}')

    # Year comparison table
    import pandas as pd
    yr_table = []
    for yr, ys in analysis.get("year_summaries", {}).items():
        yr_table.append({
            "Fiscal Year": yr,
            "Status": "✅ Extracted" if ys.get("status")=="extracted" else "⚠️ No data",
            "Chars": ys.get("text_length", 0),
            "Preview": ys.get("preview","")[:120]
        })
    if yr_table:
        st.dataframe(pd.DataFrame(yr_table), use_container_width=True, hide_index=True)

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
