from pathlib import Path
from datetime import date

from boarddocs_agent.manifest import open_manifest
from boarddocs_agent.models import DocumentRecord, Meeting
from boarddocs_agent.reporting import regenerate_indexes
from boarddocs_agent.summarizer import summarize_text, write_meeting_summary


def test_index_generation(tmp_path: Path):
    manifest = open_manifest(tmp_path)
    try:
        manifest.upsert_document(DocumentRecord(
            meeting_date='2026-05-12', meeting_type='Regular', agenda_title='May 12, 2026 - Regular',
            agenda_item_title='Policy', document_title='Policy 123.pdf', original_url=None,
            downloaded_filepath='Meetings/2025-2026/2026-05-12/Policy/Policy 123.pdf', content_type='application/pdf',
            sha256_checksum='abc', first_downloaded_at='now', last_checked_at='now', category='Policy',
            extraction_status='ok', summary_path='Meetings/2025-2026/2026-05-12/summaries/summary.md'))
        regenerate_indexes(tmp_path, manifest)
        assert '- Policy 123.pdf - Policy -' in (tmp_path / 'README.md').read_text(encoding='utf-8')
        assert 'documents' in (tmp_path / 'index.json').read_text(encoding='utf-8')
    finally:
        manifest.close()


def test_summary_generation_from_sample_text(tmp_path: Path):
    details = summarize_text('Budget.pdf', 'Budget', 'The budget presentation recommends $12,500 for technology on May 12, 2026. This item is expected to be considered by the Board of Education.', 'ok')
    assert details['importance'] == 'High'
    assert '$12,500' in details['dollar_amounts']
    meeting = Meeting(None, date(2026, 5, 12), 'Regular', 'May 12, 2026 - Regular')
    doc = DocumentRecord(
        meeting_date='2026-05-12', meeting_type='Regular', agenda_title='May 12, 2026 - Regular',
        agenda_item_title='Budget', document_title='Budget.pdf', original_url=None, downloaded_filepath='Budget.pdf',
        content_type='application/pdf', sha256_checksum='abc', first_downloaded_at='now', last_checked_at='now',
        category='Budget', extraction_status='ok', summary_path=str(tmp_path / 'summary.md'), **details)
    write_meeting_summary(meeting, [doc], [], [], tmp_path / 'summary.md')
    assert 'Finance/budget items' in (tmp_path / 'summary.md').read_text(encoding='utf-8')
