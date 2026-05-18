from __future__ import annotations

import importlib.util
import os
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .boarddocs_client import BoardDocsClient, BrowserConfig, SESSION_STATE
from .manifest import open_manifest
from .processor import sync_meetings
from .reporting import regenerate_indexes
from .summarize_existing import summarize_existing_downloads
from .utils import load_dotenv, month_bounds, parse_date

app = typer.Typer(help="Download, categorize, summarize, and index BPCSD BoardDocs meeting materials.")
console = Console()


def _settings(output_root: str | None = None) -> tuple[str | None, str | None, Path]:
    load_dotenv()
    username = os.getenv("BOARDDOCS_USERNAME")
    password = os.getenv("BOARDDOCS_PASSWORD")
    root = Path(output_root or os.getenv("BOARDDOCS_OUTPUT_ROOT", "Meetings"))
    return username, password, root


def _date_range(start_date: str | None, end_date: str | None, month: str | None, meeting_date: str | None) -> tuple[date, date]:
    if sum(bool(value) for value in (month, meeting_date)) > 1:
        raise typer.BadParameter("Use only one of --month or --meeting-date.")
    if month:
        return month_bounds(month)
    if meeting_date:
        parsed = parse_date(meeting_date)
        return parsed, parsed
    start = parse_date(start_date or os.getenv("BOARDDOCS_START_DATE", "2025-07-01"))
    end = parse_date(end_date) if end_date else date.today()
    if end < start:
        raise typer.BadParameter("End date must be on or after start date.")
    return start, end


@app.command()
def login(
    headful: bool = typer.Option(True, "--headful/--headless", help="Show the browser for MFA/captcha or manual login."),
) -> None:
    """Open BoardDocs, authenticate, and save ignored local browser state."""
    username, password, _root = _settings()
    with BoardDocsClient(BrowserConfig(headful=headful)) as client:
        client.login(username, password, interactive=headful or not (username and password))
    console.print(f"[green]Saved local session state to {SESSION_STATE}[/green]")


@app.command()
def sync(
    start_date: Optional[str] = typer.Option(None, help="Start date, default BOARDDOCS_START_DATE or 2025-07-01."),
    end_date: Optional[str] = typer.Option(None, help="End date, default today."),
    month: Optional[str] = typer.Option(None, help="Limit to a YYYY-MM month."),
    meeting_date: Optional[str] = typer.Option(None, help="Limit to one YYYY-MM-DD meeting date."),
    output_root: str = typer.Option("Meetings", help="Output folder."),
    headful: bool = typer.Option(False, help="Show the browser."),
    dry_run: bool = typer.Option(False, help="Discover and plan without writing downloads."),
    force: bool = typer.Option(False, help="Re-download known source documents."),
    limit_meetings: Optional[int] = typer.Option(None, help="Process at most N meetings."),
) -> None:
    """Download and process BoardDocs meetings."""
    username, password, root = _settings(output_root)
    start, end = _date_range(start_date, end_date, month, meeting_date)
    manifest = open_manifest(root)
    try:
        with BoardDocsClient(BrowserConfig(headful=headful)) as client:
            client.login(username, password, interactive=headful and not SESSION_STATE.exists())
            stats = sync_meetings(client, manifest, root, start, end, dry_run=dry_run, force=force, limit_meetings=limit_meetings)
    finally:
        manifest.close()
    console.print(f"[green]Processed {stats.meetings_processed}/{stats.meetings_found} meetings.[/green]")
    if stats.run_report_path:
        console.print(f"Run report: {stats.run_report_path}")


@app.command()
def report(output_root: str = typer.Option("Meetings", help="Output folder.")) -> None:
    """Regenerate Meetings/README.md and Meetings/index.json from the manifest."""
    _username, _password, root = _settings(output_root)
    manifest = open_manifest(root)
    try:
        regenerate_indexes(root, manifest)
    finally:
        manifest.close()
    console.print(f"[green]Regenerated {root / 'README.md'} and {root / 'index.json'}[/green]")


@app.command()
def summarize(output_root: str = typer.Option("Meetings", help="Output folder.")) -> None:
    """Re-run extraction and summaries for already downloaded files."""
    _username, _password, root = _settings(output_root)
    manifest = open_manifest(root)
    try:
        count = summarize_existing_downloads(root, manifest)
        regenerate_indexes(root, manifest)
    finally:
        manifest.close()
    console.print(f"[green]Updated summaries for {count} documents.[/green]")


@app.command()
def doctor(output_root: str = typer.Option("Meetings", help="Output folder.")) -> None:
    """Check local dependencies, Playwright installation, env vars, and write access."""
    username, password, root = _settings(output_root)
    table = Table(title="BoardDocs Agent Doctor")
    table.add_column("Check")
    table.add_column("Status")
    packages = ["playwright", "requests", "bs4", "pypdf", "docx", "openpyxl", "rich", "typer"]
    for package in packages:
        status = "ok" if importlib.util.find_spec(package) else "missing"
        table.add_row(package, status)
    table.add_row("BOARDDOCS_USERNAME", "set" if username else "missing")
    table.add_row("BOARDDOCS_PASSWORD", "set" if password else "missing")
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        writable = "ok"
    except Exception as exc:
        writable = f"failed: {exc}"
    table.add_row(str(root), writable)
    table.add_row("session state", "present" if SESSION_STATE.exists() else "not present")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        pw_status = "ok"
    except Exception as exc:
        pw_status = f"failed: {exc}"
    table.add_row("Playwright chromium", pw_status)
    console.print(table)
    if "failed" in pw_status:
        raise typer.Exit(code=1)


@app.command()
def web() -> None:
    """Placeholder for a future local web wrapper."""
    console.print("No web UI is bundled yet. Use the CLI commands or wrap them with your preferred local UI.")


if __name__ == "__main__":
    app()
