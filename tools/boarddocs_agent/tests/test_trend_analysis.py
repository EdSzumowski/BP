from boarddocs_agent.manifest import open_manifest
from boarddocs_agent.models import DocumentRecord
from boarddocs_agent.trend_analysis import detect_anomalies, top_entities


def test_top_entities_and_anomalies(tmp_path):
    manifest = open_manifest(tmp_path)
    try:
        manifest.upsert_document(DocumentRecord(
            meeting_date='2026-05-12', meeting_type='Regular', agenda_title='A', agenda_item_title='Finance',
            document_title='Budget.pdf', original_url='u1', downloaded_filepath='f1.pdf', content_type='application/pdf',
            sha256_checksum='abc', first_downloaded_at='t', last_checked_at='t', category='Budget', extraction_status='ok', summary_path='s'))
        manifest.upsert_document(DocumentRecord(
            meeting_date='2026-05-13', meeting_type='Regular', agenda_title='B', agenda_item_title='Personnel',
            document_title='Staff.pdf', original_url='u2', downloaded_filepath='', content_type='application/pdf',
            sha256_checksum='def', first_downloaded_at='t', last_checked_at='t', category='Personnel', extraction_status='failed', summary_path='s'))
        top = top_entities(manifest)
        assert top[0][1] == 1
        anomalies = detect_anomalies(manifest)
        assert any('missing downloaded filepath' in a for a in anomalies)
        assert any('extraction=failed' in a for a in anomalies)
    finally:
        manifest.close()
