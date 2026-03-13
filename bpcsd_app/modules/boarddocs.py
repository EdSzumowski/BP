import urllib.request
import urllib.parse
import http.cookiejar
import random
import re
import json

BASE = "https://go.boarddocs.com"
NSF  = f"{BASE}/ny/bpcsd/Board.nsf"


class BoardDocsClient:
    def __init__(self, username, password):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [
            ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
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
                    f"{BASE}/names.nsf?Login",
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST"
                ),
                timeout=20
            )
        except Exception:
            pass  # Some redirects raise exceptions; still check cookies

        # Check if we got an LtpaToken
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
            method="POST"
        )
        r = self.opener.open(req, timeout=30)
        return r.read().decode("utf-8", errors="replace")

    def get_agenda(self, meeting_id):
        return self._post("BD-GetAgenda", {"id": meeting_id})

    def find_report_item(self, meeting_id, search_terms):
        """Find an agenda item ID matching any of the search terms."""
        html = self.get_agenda(meeting_id)
        for term in search_terms:
            # Try exact title match first
            matches = re.findall(
                r'id="([A-Z0-9]{12,14})"[^>]*Xtitle="[^"]*' + re.escape(term) + r'[^"]*"',
                html, re.I
            )
            if matches:
                return matches[0], html
            # Also try reversed attribute order
            matches = re.findall(
                r'Xtitle="([^"]*' + re.escape(term) + r'[^"]*)"[^>]*id="([A-Z0-9]{12,14})"',
                html, re.I
            )
            if matches:
                return matches[0][1], html
        return None, html

    def get_item_files(self, item_id):
        """Get list of (url, filename) for files attached to an item."""
        html = self._post("BD-GetPublicFiles", {"id": item_id})
        files = []
        for match in re.finditer(
            r'href="(/ny/bpcsd/Board\.nsf/files/[^"]+)"[^>]*>\s*([^<\n]+?)\s*</a>',
            html
        ):
            path, name = match.group(1), match.group(2).strip()
            if name and (name.lower().endswith('.pdf') or '.pdf' in path.lower()):
                files.append((f"{BASE}{path}", name))
        return files

    def download_file(self, url):
        """Download a file and return bytes."""
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        r = self.opener.open(req, timeout=60)
        return r.read()

    def discover_agenda_items(self, meeting_id):
        """Return dict of {xtitle: item_id} for all items in a meeting."""
        html = self.get_agenda(meeting_id)
        items = {}
        for m in re.finditer(r'id="([A-Z0-9]{12,14})"[^>]*Xtitle="([^"]+)"', html):
            items[m.group(2)] = m.group(1)
        return items
