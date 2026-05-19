from pathlib import Path

from boarddocs_agent.categorization_extraction import detect_report_family, normalize_extraction_fields, persist_extracted_outputs
from boarddocs_agent.models import DocumentRecord


def test_detect_report_family_prefers_treasurer_report_for_finance_patterns():
    family = detect_report_family('Finance', 'Treasurer report and warrant claims', 'Monthly report')
    assert family == 'treasurer_report'


def test_normalized_extraction_fields_extracts_machine_friendly_strings():
    text = 'Treasurer report dated May 12, 2026 includes $12,345.67 for Business Office.'
    fields = normalize_extraction_fields(text, 'ok')
    assert 'May 12, 2026' in fields['dates_mentioned']
    assert '$12,345.67' in fields['dollar_amounts']
    assert 'Business Office' in fields['people_departments']


def test_persist_extracted_outputs_writes_structured_json_with_provenance(tmp_path: Path):
    record = DocumentRecord(
        meeting_date='2026-05-12', meeting_type='Regular', agenda_title='Agenda', agenda_item_title='Treasurer report',
        document_title='May treasurer', original_url='https://example.com/doc.pdf', downloaded_filepath='Meetings/2025-2026/2026-05-12/Business/May.pdf',
        content_type='application/pdf', sha256_checksum='abc123', first_downloaded_at='now', last_checked_at='now',
        category='Claims/Audits/Treasurer', extraction_status='ok', summary_path='Meetings/2025-2026/2026-05-12/summaries/summary.md', source_section='Finance',
    )
    downloaded_path = tmp_path / 'May.pdf'
    downloaded_path.write_text('dummy', encoding='utf-8')
    persist_extracted_outputs(
        meeting_root=tmp_path,
        downloaded_path=downloaded_path,
        record=record,
        text='example text',
        normalized_fields={'keywords': 'treasurer', 'dates_mentioned': '', 'dollar_amounts': '', 'people_departments': ''},
    )
    json_path = tmp_path / 'summaries' / 'extracted_documents' / 'May.json'
    assert json_path.exists()
    payload = json_path.read_text(encoding='utf-8')
    assert 'provenance' in payload
    assert 'report_family' in payload

