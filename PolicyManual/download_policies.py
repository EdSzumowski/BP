import csv
import os
import re
import time
from html import unescape
from urllib.parse import urljoin
from urllib.request import Request, urlopen

BASE = 'https://www.bpcsd.org'
INDEX_URL = f'{BASE}/board-of-education/board-policies'
OUT_DIR = os.path.join(os.path.dirname(__file__), 'text')
INDEX_CSV = os.path.join(os.path.dirname(__file__), 'policies_index.csv')


def fetch(url: str) -> str:
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8', errors='replace')


def strip_tags(value: str) -> str:
    value = re.sub(r'<script[\s\S]*?</script\s*>', ' ', value, flags=re.I)
    value = re.sub(r'<style[\s\S]*?</style\s*>', ' ', value, flags=re.I)
    value = re.sub(r'<[^>]+>', ' ', value)
    return re.sub(r'\s+', ' ', unescape(value)).strip()


def slugify(text: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9._-]+', '_', text).strip('_')
    return cleaned[:120] or 'policy'


def parse_policy_links(index_html: str):
    matches = re.findall(r'<a[^>]+href="([^"]+/news/default-post-display-page/~board/board-of-education-policies/post/[^"]+)"[^>]*>(.*?)</a>', index_html, flags=re.I | re.S)
    seen = set()
    items = []
    for href, label_html in matches:
        url = urljoin(BASE, href)
        title = strip_tags(label_html)
        if url not in seen and title:
            seen.add(url)
            items.append((title, url))
    return items


def parse_policy_body(page_html: str) -> str:
    marker = re.search(r'<h1[^>]*>\s*([^<]+)\s*</h1>', page_html, flags=re.I)
    title = strip_tags(marker.group(1)) if marker else 'Policy'

    main_match = re.search(r'<main[^>]*>([\s\S]*?)</main>', page_html, flags=re.I)
    source = main_match.group(1) if main_match else page_html

    source = re.sub(r'<nav[\s\S]*?</nav>', ' ', source, flags=re.I)
    source = re.sub(r'<footer[\s\S]*?</footer>', ' ', source, flags=re.I)
    text = strip_tags(source)

    cut = 'Previous posts Next posts'
    if cut in text:
        text = text.split(cut, 1)[0].strip()

    return f'{title}\n\n{text}\n'


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    index_html = fetch(INDEX_URL)
    items = parse_policy_links(index_html)

    with open(INDEX_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['title', 'url', 'file'])

        for i, (title, url) in enumerate(items, 1):
            try:
                html = fetch(url)
                body = parse_policy_body(html)
                filename = f'{i:03d}_{slugify(title)}.txt'
                with open(os.path.join(OUT_DIR, filename), 'w', encoding='utf-8') as out:
                    out.write(body)
                writer.writerow([title, url, filename])
                print(f'[{i}/{len(items)}] saved {filename}')
            except Exception as exc:
                writer.writerow([title, url, f'ERROR: {exc}'])
                print(f'[{i}/{len(items)}] ERROR {title}: {exc}')
            finally:
                time.sleep(0.25)


if __name__ == '__main__':
    main()
