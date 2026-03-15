import urllib.request
import urllib.parse
import http.cookiejar
import random
import re

BASE = "https://go.boarddocs.com"
NSF  = f"{BASE}/ny/bpcsd/Board.nsf"

# The Finance Committee is a SINGLE agenda item — all Finance reports are
# file attachments to it, not separate agenda items. Match by attachment filename.
FINANCE_COMMITTEE_TERMS = ["Finance Committee"]


class BoardDocsClient:
    def __init__(self, username, password):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [
            ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
            ("Referer", f"{NSF}/Private?open&login")
        ]
        self.authenticated = False
        self._login(username, password)

    def _login(self, username, password):
        data = urllib.parse.urlencode({
            "Username": username,
            "Password": password,
            "RedirectTo": "/ny/bpcsd/Board.nsf/Private?open&login",
            "%%ModDate": "0000000100007F22"
        }).encode()
        try:
            self.opener.open(
                urllib.request.Request(
                    f"{BASE}/names.nsf?Login", data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST"),
                timeout=20)
        except Exception:
            pass  # Redirects may raise; check cookies below

        for cookie in self.jar:
            if cookie.name == "LtpaToken":
                self.authenticated = True
                return
        raise ValueError("Authentication failed — check credentials")

    def _post(self, endpoint, data):
        req = urllib.request.Request(
            f"{NSF}/{endpoint}?open&{random.random()}",
            data=urllib.parse.urlencode(data).encode(),
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,*/*"
            },
            method="POST")
        r = self.opener.open(req, timeout=30)
        return r.read().decode("utf-8", errors="replace")

    def get_agenda(self, meeting_id):
        return self._post("BD-GetAgenda", {"id": meeting_id})

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _fuzzy_match(self, search_terms, target):
        """
        True if any search term is a fuzzy substring of target.
        Normalizes punctuation and whitespace so "M&T" matches "M & T", etc.
        """
        def normalize(s):
            s = s.lower()
            s = re.sub(r'[^a-z0-9\s]', ' ', s)   # strip punctuation
            s = re.sub(r'\s+', ' ', s).strip()
            return s

        target_norm = normalize(target)
        for term in search_terms:
            term_norm = normalize(term)
            if term_norm in target_norm:
                return True
            # Also check all words in term appear in target (handles word reordering)
            words = [w for w in term_norm.split() if len(w) > 2]
            if words and all(w in target_norm for w in words):
                return True
        return False

    def _all_agenda_items(self, html):
        """
        Extract all (item_id, xtitle) pairs from agenda HTML.
        Handles both attribute orderings: id…Xtitle and Xtitle…id.
        """
        items = []
        seen = set()
        # id before Xtitle
        for iid, title in re.findall(
                r'id="([A-Z0-9]{10,20})"[^>]*?Xtitle="([^"]*)"', html, re.I):
            if iid not in seen:
                seen.add(iid)
                items.append((iid, title))
        # Xtitle before id
        for title, iid in re.findall(
                r'Xtitle="([^"]*)"[^>]*?id="([A-Z0-9]{10,20})"', html, re.I):
            if iid not in seen:
                seen.add(iid)
                items.append((iid, title))
        # data-id fallback (some agenda markup variants)
        for iid, title in re.findall(
                r'data-id="([A-Z0-9]{10,20})"[^>]*?(?:Xtitle|data-title)="([^"]*)"', html, re.I):
            if iid not in seen:
                seen.add(iid)
                items.append((iid, title))
        return items

    # ── Finance reports (attachment-based) ───────────────────────────────────

    def find_finance_committee_id(self, meeting_id):
        """
        Returns the item_id for the Finance Committee agenda item, or None.
        All individual finance report PDFs are attachments to this single item.
        """
        html = self.get_agenda(meeting_id)
        for iid, title in self._all_agenda_items(html):
            if self._fuzzy_match(FINANCE_COMMITTEE_TERMS, title):
                return iid
        return None

    def find_finance_attachment(self, meeting_id, search_terms):
        """
        For Finance reports:
        1. Locate the Finance Committee agenda item.
        2. Retrieve all its file attachments.
        3. Return (url, filename) for the attachment whose name fuzzy-matches
           any of the search_terms.
        Returns (None, error_message) on failure.
        """
        fc_id = self.find_finance_committee_id(meeting_id)
        if not fc_id:
            return None, "Finance Committee item not found in agenda"

        files = self.get_item_files(fc_id)
        if not files:
            return None, "No files attached to Finance Committee item"

        for url, filename in files:
            if self._fuzzy_match(search_terms, filename):
                return url, filename

        available = [name for _, name in files]
        return None, f"No match in Finance attachments. Available: {available}"

    def list_finance_attachments(self, meeting_id):
        """Return all (url, filename) pairs from the Finance Committee item."""
        fc_id = self.find_finance_committee_id(meeting_id)
        if not fc_id:
            return []
        return self.get_item_files(fc_id)

    # ── Director reports (agenda-item-based) ─────────────────────────────────

    def find_director_item(self, meeting_id, search_terms):
        """
        For Director reports:
        Each director has their own agenda item whose Xtitle contains their
        name. Fuzzy-match against search_terms; return item_id or None.
        """
        html = self.get_agenda(meeting_id)
        for iid, title in self._all_agenda_items(html):
            if self._fuzzy_match(search_terms, title):
                return iid
        return None

    def find_director_attachment(self, meeting_id, search_terms):
        """
        For Director reports: find the agenda item and return its first PDF
        attachment as (url, filename), or (None, error_message).
        """
        item_id = self.find_director_item(meeting_id, search_terms)
        if not item_id:
            return None, "Director report item not found in agenda"

        files = self.get_item_files(item_id)
        if not files:
            return None, "No PDF attached to this director report item"
        return files[0]

    # ── Shared helpers ────────────────────────────────────────────────────────

    def get_item_files(self, item_id):
        """Return list of (url, filename) for PDF files attached to an item."""
        html = self._post("BD-GetPublicFiles", {"id": item_id})
        files = []
        for match in re.finditer(
                r'href="(/ny/bpcsd/Board\.nsf/files/[^"]+)"[^>]*>\s*([^<\n]+?)\s*</a>',
                html):
            path, name = match.group(1), match.group(2).strip()
            if name and ('.pdf' in name.lower() or '.pdf' in path.lower()):
                files.append((f"{BASE}{path}", name))
        return files

    def download_file(self, url):
        """Download a URL and return raw bytes."""
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        r = self.opener.open(req, timeout=60)
        return r.read()

    def discover_agenda_items(self, meeting_id):
        """Return dict of {xtitle: item_id} for debugging."""
        html = self.get_agenda(meeting_id)
        return {title: iid for iid, title in self._all_agenda_items(html)}
