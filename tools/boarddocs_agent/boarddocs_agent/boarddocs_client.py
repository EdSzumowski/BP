from __future__ import annotations

import mimetypes
import re
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # optional at runtime; regex fallback keeps tests and doctor usable
    BeautifulSoup = None

from .models import AgendaItem, Attachment, Meeting
from .utils import parse_date, sanitize_filename

LOGIN_URL = "https://go.boarddocs.com/ny/bpcsd/Board.nsf/Private?open&login"
BASE_NSF = "https://go.boarddocs.com/ny/bpcsd/Board.nsf"
SESSION_DIR = Path(".boarddocs_session")
SESSION_STATE = SESSION_DIR / "state.json"


@dataclass(slots=True)
class BrowserConfig:
    headful: bool = False
    timeout_ms: int = 30000
    session_state: Path = SESSION_STATE


class BoardDocsClient:
    """BoardDocs navigation wrapper with selectors isolated in one module."""

    def __init__(self, config: BrowserConfig | None = None):
        self.config = config or BrowserConfig()
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    def __enter__(self) -> "BoardDocsClient":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def start(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=not self.config.headful)
        state = str(self.config.session_state) if self.config.session_state.exists() else None
        self._context = self._browser.new_context(storage_state=state, accept_downloads=True)
        self._page = self._context.new_page()
        self._page.set_default_timeout(self.config.timeout_ms)

    def close(self) -> None:
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    @property
    def page(self):
        if self._page is None:
            raise RuntimeError("BoardDocsClient.start() must be called first")
        return self._page

    @property
    def context(self):
        if self._context is None:
            raise RuntimeError("BoardDocsClient.start() must be called first")
        return self._context

    def login(self, username: str | None, password: str | None, interactive: bool = False) -> None:
        self.page.goto(LOGIN_URL, wait_until="domcontentloaded")
        if username and password:
            user = self._first_locator(['input[name="Username"]', 'input[name="username"]', 'input[type="email"]', 'input[type="text"]'])
            pwd = self._first_locator(['input[name="Password"]', 'input[name="password"]', 'input[type="password"]'])
            if user and pwd:
                user.fill(username)
                pwd.fill(password)
                submit = self._first_locator(['input[type="submit"]', 'button[type="submit"]', 'text=/log ?in|sign ?in/i'])
                if submit:
                    submit.click()
                else:
                    pwd.press("Enter")
                self.page.wait_for_load_state("domcontentloaded")
        if interactive:
            print("Complete any BoardDocs login, MFA, or captcha challenge in the browser window.")
            print("Press Enter here after the meetings or agenda page is available.")
            input()
        self.save_session_state()

    def save_session_state(self) -> None:
        self.config.session_state.parent.mkdir(parents=True, exist_ok=True)
        self.context.storage_state(path=str(self.config.session_state))

    def discover_meetings(self, start_date: date, end_date: date) -> list[Meeting]:
        html_blobs = []
        for url in (
            f"{BASE_NSF}/BD-GetMeetingsList?open",
            f"{BASE_NSF}/Private?open",
            f"{BASE_NSF}/Public?open",
        ):
            try:
                self.page.goto(url, wait_until="domcontentloaded")
                html_blobs.append(self.page.content())
            except Exception:
                continue
        meetings: dict[tuple[str, str, str | None], Meeting] = {}
        for html in html_blobs:
            for meeting in parse_meetings_list(html):
                if start_date <= meeting.meeting_date <= end_date:
                    key = (meeting.meeting_date.isoformat(), meeting.meeting_type, meeting.meeting_id)
                    meetings[key] = meeting
        return sorted(meetings.values(), key=lambda item: item.meeting_date)

    def load_agenda(self, meeting: Meeting) -> Meeting:
        html = ""
        if meeting.meeting_id:
            html = self._post_boarddocs("BD-GetAgenda", {"id": meeting.meeting_id})
        if not html and meeting.url:
            self.page.goto(meeting.url, wait_until="networkidle")
            html = self.page.content()
        meeting.agenda_html = html
        meeting.agenda_items = parse_agenda(html)
        for item in meeting.agenda_items:
            if item.item_id and not item.attachments:
                try:
                    item.attachments = parse_attachments(self._post_boarddocs("BD-GetItem", {"id": item.item_id}))
                except Exception:
                    pass
        return meeting

    def download_attachment(self, attachment: Attachment, target: Path) -> tuple[Path, str | None]:
        if not attachment.url:
            raise ValueError(f"Attachment has no URL: {attachment.title}")
        target.parent.mkdir(parents=True, exist_ok=True)
        cookies = {cookie["name"]: cookie["value"] for cookie in self.context.cookies()}
        with requests.get(attachment.url, cookies=cookies, timeout=60, stream=True) as response:
            response.raise_for_status()
            content_type = response.headers.get("content-type") or attachment.content_type
            with target.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        return target, content_type

    def _post_boarddocs(self, endpoint: str, data: dict[str, str]) -> str:
        response = self.page.request.post(
            f"{BASE_NSF}/{endpoint}?open&{time.time()}",
            form=data,
            headers={"X-Requested-With": "XMLHttpRequest", "Accept": "text/html,*/*"},
        )
        if not response.ok:
            raise RuntimeError(f"BoardDocs {endpoint} request failed: {response.status}")
        return response.text()

    def _first_locator(self, selectors: list[str]):
        for selector in selectors:
            locator = self.page.locator(selector).first
            try:
                if locator.count() and locator.is_visible(timeout=1000):
                    return locator
            except Exception:
                continue
        return None


def parse_meetings_list(html: str) -> list[Meeting]:
    meetings: list[Meeting] = []
    seen: set[tuple[str | None, str]] = set()

    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        option_rows = [(option.get("value") or option.get("data-id"), option.get_text(" ", strip=True)) for option in soup.find_all("option")]
    else:
        option_rows = [
            (match.group("value"), _strip_tags(match.group("label")))
            for match in re.finditer(r'<option[^>]+(?:value|data-id)=["\'](?P<value>[^"\']+)["\'][^>]*>(?P<label>.*?)</option>', html, re.I | re.S)
        ]
    for value, label in option_rows:
        meeting = _meeting_from_label(label, value)
        if meeting and ((meeting.meeting_id or "").upper(), meeting.meeting_date.isoformat()) not in seen:
            meetings.append(meeting)
            seen.add(((meeting.meeting_id or "").upper(), meeting.meeting_date.isoformat()))

    for match in re.finditer(r'(?P<id>(?=[A-Z0-9]{6,24}\b)(?=[A-Z0-9]*\d)[A-Z0-9]+).{0,160}?(?P<date>(?:\d{1,2}/\d{1,2}/\d{2,4}|\d{4}/\d{1,2}/\d{1,2}|[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}))(?P<label>.{0,160})', html, re.I | re.S):
        label = re.sub(r"<[^>]+>", " ", match.group("date") + " " + match.group("label"))
        meeting = _meeting_from_label(label, match.group("id").upper())
        if meeting and ((meeting.meeting_id or "").upper(), meeting.meeting_date.isoformat()) not in seen:
            meetings.append(meeting)
            seen.add(((meeting.meeting_id or "").upper(), meeting.meeting_date.isoformat()))
    return meetings


def parse_agenda(html: str) -> list[AgendaItem]:
    html = html or ""
    items: list[AgendaItem] = []
    seen: set[str] = set()
    current_section: str | None = None
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(True):
            text = tag.get_text(" ", strip=True)
            classes = " ".join(tag.get("class", []))
            if text and re.search(r"section|header|category", classes, re.I):
                current_section = text
            item_id = tag.get("id") or tag.get("data-id")
            title = tag.get("Xtitle") or tag.get("xtitle") or tag.get("data-title")
            if item_id and title and item_id not in seen and re.fullmatch(r"[A-Z0-9]{8,24}", item_id, re.I):
                items.append(AgendaItem(item_id=item_id, title=title, section=current_section, body=text, attachments=parse_attachments(str(tag))))
                seen.add(item_id)
        if not items:
            for heading in soup.find_all(["h1", "h2", "h3", "h4", "strong", "b"]):
                title = heading.get_text(" ", strip=True)
                if title:
                    items.append(AgendaItem(item_id=None, title=title, section=current_section, body=title))
        return items

    section_match = re.search(r'class=["\'][^"\']*(?:section|header|category)[^"\']*["\'][^>]*>(?P<section>.*?)<', html, re.I | re.S)
    current_section = _strip_tags(section_match.group("section")) if section_match else None
    for match in re.finditer(r'<(?P<tag>\w+)(?P<attrs>[^>]*(?:id|data-id)=["\'][A-Z0-9]{8,24}["\'][^>]*(?:Xtitle|xtitle|data-title)=["\'][^"\']+["\'][^>]*)>(?P<body>.*?)</(?P=tag)>', html, re.I | re.S):
        attrs = match.group("attrs")
        item_id = _attr(attrs, "id") or _attr(attrs, "data-id")
        title = _attr(attrs, "Xtitle") or _attr(attrs, "xtitle") or _attr(attrs, "data-title")
        if item_id and title and item_id not in seen:
            items.append(AgendaItem(item_id=item_id, title=title, section=current_section, body=_strip_tags(match.group("body")), attachments=parse_attachments(match.group(0))))
            seen.add(item_id)
    return items


def parse_attachments(html: str) -> list[Attachment]:
    attachments: list[Attachment] = []
    if BeautifulSoup is not None:
        soup = BeautifulSoup(html or "", "html.parser")
        link_rows = [(link["href"], link.get_text(" ", strip=True), link.get("type")) for link in soup.find_all("a", href=True)]
    else:
        link_rows = [(m.group("href"), _strip_tags(m.group("label")), _attr(m.group("attrs"), "type")) for m in re.finditer(r'<a(?P<attrs>[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*)>(?P<label>.*?)</a>', html or "", re.I | re.S)]
    for href, label, link_type in link_rows:
        if not _looks_downloadable(href, label):
            continue
        url = urljoin(BASE_NSF + "/", href)
        title = label or Path(href.split("?", 1)[0]).name or "attachment"
        filename = sanitize_filename(title)
        suffix = Path(filename).suffix
        if not suffix:
            guessed = mimetypes.guess_extension(link_type or "") or Path(href.split("?", 1)[0]).suffix
            filename = sanitize_filename(filename + (guessed or ""))
        attachments.append(Attachment(title=title, url=url, filename=filename, content_type=link_type))
    return attachments


def _meeting_from_label(label: str, meeting_id: str | None) -> Meeting | None:
    if not label:
        return None
    try:
        meeting_date = parse_date(label)
    except ValueError:
        return None
    parts = re.split(r"\s+-\s+|\s+–\s+", label, maxsplit=1)
    meeting_type = parts[1].strip() if len(parts) > 1 else "Board Meeting"
    meeting_type = re.sub(r"\s+", " ", meeting_type)[:120] or "Board Meeting"
    return Meeting(meeting_id=meeting_id, meeting_date=meeting_date, meeting_type=meeting_type, agenda_title=label, url=None)


def _looks_downloadable(href: str, label: str) -> bool:
    haystack = f"{href} {label}".lower()
    return any(token in haystack for token in ("download", "attach", ".pdf", ".doc", ".xls", ".ppt", ".csv", ".txt"))


def _strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def _attr(attrs: str, name: str) -> str | None:
    match = re.search(rf'{re.escape(name)}=["\']([^"\']+)["\']', attrs or "", re.I)
    return match.group(1) if match else None
