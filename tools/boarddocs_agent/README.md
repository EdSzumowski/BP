# BPCSD BoardDocs Agent

This tool logs into BoardDocs for Broadalbin-Perth CSD, discovers Board meetings, downloads agenda attachments, categorizes documents with local rules, extracts readable text, creates meeting summaries, and maintains indexes under `Meetings/`.

The tool is designed for monthly reuse. It does not hardcode credentials and does not require an external AI API for categorization or summaries.

## Setup

From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
python -m playwright install chromium
```

If your shell does not support the quoted extra syntax, use:

```bash
pip install -e .
pip install pytest
```

## Credentials

Set credentials in your shell or a local `.env` file in the repository root. The `.env` file is ignored by Git.

```bash
BOARDDOCS_USERNAME='your-user-name'
BOARDDOCS_PASSWORD='your-password'
BOARDDOCS_START_DATE='2025-07-01'
BOARDDOCS_OUTPUT_ROOT='Meetings'
```

Never commit credentials, cookies, browser profiles, downloaded session state, or local `.env` files.

## First login

If BoardDocs accepts a direct username/password login, `sync` can authenticate from environment variables. If BoardDocs requires MFA, captcha, or another interactive step, run:

```bash
python -m boarddocs_agent login --headful
```

Complete the login in the browser, then return to the terminal and press Enter. The tool stores only Playwright storage state under `.boarddocs_session/state.json`, which is ignored by Git.

## Monthly run examples

```bash
python -m boarddocs_agent doctor
python -m boarddocs_agent sync --month 2026-05 --headful
python -m boarddocs_agent sync --start-date 2025-07-01
python -m boarddocs_agent sync --meeting-date 2026-05-12 --limit-meetings 1
python -m boarddocs_agent summarize
python -m boarddocs_agent report
```

The first cautious live test should be:

```bash
python -m boarddocs_agent doctor
python -m boarddocs_agent login --headful
python -m boarddocs_agent sync --start-date 2025-07-01 --headful --limit-meetings 2
```

## Output

The default output root is `Meetings/`:

```text
Meetings/
  README.md
  index.json
  manifest.sqlite
  _runs/
    YYYY-MM-DD_HHMMSS_run_report.md
  2025-2026/
    YYYY-MM-DD/
      agenda.md
      metadata.json
      <Category_Folder>/
      summaries/
        summary.md
        extracted_text/
        extracted_documents/
```

Each manifest record tracks meeting date, meeting type, agenda title, agenda item title, document title, source URL, downloaded path, content type, checksum, first download time, last checked time, category, extraction status, and summary path.


## Architecture

The codebase uses a 3-module architecture that preserves the existing CLI commands and output paths.

- downloader module - login/session flow, meeting discovery, strict meeting filtering by date window, agenda attachment downloads, and manifest source updates.
- categorization_extraction module - document category assignment, report-family detection, normalized field extraction, extracted text persistence, and structured per-document JSON outputs linked to document provenance.
- trend_analysis module - cross-month aggregation inputs, financial and narrative trend helpers, top entity summaries, anomaly detection, and trend report generation wrappers.

Backward compatibility is preserved by keeping legacy module entry points and routing them into the new modules.

Downloader orchestration is centralized in `boarddocs_agent/downloader.py` via `DownloaderService`, so the CLI delegates session checks, login, meeting sync flow, and strict date-window filtering without changing command names or output paths.

## Idempotence

The downloader checks the manifest by stable source URL plus meeting date and document title. After download, it computes a SHA-256 checksum. If the same source is already present, the tool updates `last_checked_at` instead of duplicating the file. If a remote file changes and `--force` is used, the new version is saved with a `__v2` style suffix when needed.

## Categorization and summaries

Categorization is rule-based and uses the agenda section, agenda item title, document title, and extracted snippets. Supported categories include finance, budget, personnel, policy, curriculum, special education, facilities, transportation, athletics, technology, communications, contracts, grants, legal/executive session, minutes, board agenda, and other.

Summaries are conservative. If text cannot be extracted or the document meaning is unclear, the generated summary says so instead of guessing.

## Assumptions about BoardDocs

The client uses common BoardDocs patterns seen in BPCSD tooling and BoardDocs pages:

- Meeting lists may be exposed by `BD-GetMeetingsList?open`, `Private?open`, or `Public?open`.
- Agenda details may be retrieved by posting a meeting id to `BD-GetAgenda?open`.
- Agenda item details may be retrieved by posting an item id to `BD-GetItem?open`.
- Agenda item ids are usually uppercase alphanumeric values embedded in HTML attributes such as `id`, `data-id`, `Xtitle`, or `data-title`.
- Attachment links usually contain a document extension, `download`, or attachment-related path text.

BoardDocs deployments vary, so selectors and endpoint assumptions are isolated in `boarddocs_agent/boarddocs_client.py` for focused maintenance.

## Troubleshooting

- If `doctor` reports Playwright browser failures, run `python -m playwright install chromium`.
- If login fails, verify `.env` values and then try `python -m boarddocs_agent login --headful`.
- If meetings are not found, run with `--headful` and confirm the session can see the meeting list.
- If a document fails extraction, install the listed dependencies and run `python -m boarddocs_agent summarize`.
- If BoardDocs markup changes, update the parsing helpers in `boarddocs_agent/boarddocs_client.py` and add a fixture-based test.

## Reviewing and committing output

Review `Meetings/README.md`, `Meetings/index.json`, each meeting `summary.md`, and the latest `_runs/*_run_report.md`. Commit only the downloaded meeting files that you are authorized to store in GitHub. Do not commit `.env`, `.boarddocs_session/`, browser profiles, or other secrets.
