from pathlib import Path

from boarddocs_agent.manifest import open_manifest
from boarddocs_agent.models import DocumentRecord


def _record(title='Budget.pdf', checksum='abc'):
    return DocumentRecord(
        meeting_date='2026-05-12',
        meeting_type='Regular',
        agenda_title='May 12, 2026 - Regular',
        agenda_item_title='Budget Presentation',
        document_title=title,
        original_url='https://example.test/budget.pdf',
        downloaded_filepath='Meetings/2025-2026/2026-05-12/Budget/Budget.pdf',
        content_type='application/pdf',
        sha256_checksum=checksum,
        first_downloaded_at='2026-05-18T00:00:00+00:00',
        last_checked_at='2026-05-18T00:00:00+00:00',
        category='Budget',
        extraction_status='ok',
        summary_path='Meetings/2025-2026/2026-05-12/summaries/summary.md',
    )


def test_manifest_insert_update_behavior(tmp_path: Path):
    manifest = open_manifest(tmp_path)
    try:
        first_id = manifest.upsert_document(_record())
        second_id = manifest.upsert_document(_record(checksum='def'))
        assert first_id == second_id
        rows = manifest.all_documents()
        assert len(rows) == 1
        assert rows[0]['sha256_checksum'] == 'def'
    finally:
        manifest.close()
