from __future__ import annotations

import hashlib
import os
import re
from datetime import date, datetime
from pathlib import Path

DATE_PATTERNS = ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y")
MAX_FILENAME_LENGTH = 140


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def sanitize_filename(value: str, default: str = "document") -> str:
    value = value.replace("/", "_").replace("\\", "_")
    value = re.sub(r"[\x00-\x1f\x7f<>:\"|?*]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = re.sub(r"\s+(\.[A-Za-z0-9]{1,10})$", r"\1", value)
    if not value:
        value = default
    stem, suffix = os.path.splitext(value)
    if len(value) <= MAX_FILENAME_LENGTH:
        return value
    suffix = suffix[:20]
    return f"{stem[: MAX_FILENAME_LENGTH - len(suffix)]}{suffix}".strip(" .")


def slug_category(category: str) -> str:
    return sanitize_filename(category.replace("/", " and ").replace(",", "").replace(" ", "_"))


def parse_date(value: str) -> date:
    cleaned = re.sub(r"\s+", " ", value.strip())
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", cleaned, flags=re.I)
    for pattern in DATE_PATTERNS:
        try:
            return datetime.strptime(cleaned, pattern).date()
        except ValueError:
            continue
    match = re.search(r"\b(\d{1,2}/\d{1,2}/\d{4})\b", cleaned)
    if match:
        return datetime.strptime(match.group(1), "%m/%d/%Y").date()
    match = re.search(r"\b([A-Z][a-z]+\s+\d{1,2},\s+\d{4})\b", cleaned)
    if match:
        return datetime.strptime(match.group(1), "%B %d, %Y").date()
    raise ValueError(f"Unable to parse date: {value!r}")


def month_bounds(month: str) -> tuple[date, date]:
    start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, date.fromordinal(end.toordinal() - 1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def now_stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    version = 2
    while True:
        candidate = parent / f"{stem}__v{version}{suffix}"
        if not candidate.exists():
            return candidate
        version += 1
