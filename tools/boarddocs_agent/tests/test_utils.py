from pathlib import Path

from boarddocs_agent.utils import month_bounds, parse_date, sanitize_filename, sha256_file


def test_sanitize_filename_removes_path_and_invalid_chars():
    assert sanitize_filename('../Policy: A/B?*.pdf') == '_Policy A_B.pdf'


def test_parse_date_supports_boarddocs_labels():
    assert parse_date('May 12, 2026 - Regular Meeting').isoformat() == '2026-05-12'
    assert parse_date('05/12/2026').isoformat() == '2026-05-12'


def test_month_bounds():
    start, end = month_bounds('2026-05')
    assert start.isoformat() == '2026-05-01'
    assert end.isoformat() == '2026-05-31'


def test_sha256_file(tmp_path: Path):
    path = tmp_path / 'sample.txt'
    path.write_text('abc', encoding='utf-8')
    assert sha256_file(path) == 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
