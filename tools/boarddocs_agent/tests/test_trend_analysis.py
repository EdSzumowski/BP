import json

from boarddocs_agent.manifest import open_manifest
from boarddocs_agent.models import DocumentRecord
from boarddocs_agent.trend_analysis import aggregate_cross_month, detect_anomalies, top_entities


def _doc(**kwargs):
    base = dict(
        meeting_date='2026-05-12', meeting_type='Regular', agenda_title='A', agenda_item_title='Finance',
        document_title='Budget.pdf', original_url='u1', downloaded_filepath='f1.pdf', content_type='application/pdf',
        sha256_checksum='abc', first_downloaded_at='t', last_checked_at='t', category='Budget', extraction_status='ok', summary_path='s',
        dollar_amounts='$100.00', keywords='budget, transfer', people_departments='Treasurer Office'
    )
    base.update(kwargs)
    return DocumentRecord(**base)


def test_cross_month_aggregation_and_top_entities(tmp_path):
    manifest = open_manifest(tmp_path)
    try:
        manifest.upsert_document(_doc())
        manifest.upsert_document(_doc(
            meeting_date='2026-06-10', document_title='Claims.pdf', original_url='u2', downloaded_filepath='f2.pdf',
            sha256_checksum='def', people_departments='Treasurer Office, Audit Committee', dollar_amounts='$200.00, $300.00'
        ))
        monthly = aggregate_cross_month(manifest)
        assert monthly['2026-05']['documents'] == 1
        assert monthly['2026-06']['amount_count'] == 2
        tops = top_entities(manifest, top_n=2)
        assert tops[0][0] == 'Treasurer Office'
        assert tops[0][1] == 2
    finally:
        manifest.close()


def test_anomaly_detection_source_linked(tmp_path):
    manifest = open_manifest(tmp_path)
    try:
        manifest.upsert_document(_doc(meeting_date='2026-05-12', document_title='A.pdf', original_url='u1', downloaded_filepath='a.pdf', sha256_checksum='a'))
        manifest.upsert_document(_doc(meeting_date='2026-06-12', document_title='B.pdf', original_url='u2', downloaded_filepath='b.pdf', sha256_checksum='b'))
        manifest.upsert_document(_doc(meeting_date='2026-06-13', document_title='C.pdf', original_url='u3', downloaded_filepath='', sha256_checksum='c', extraction_status='failed'))
        issues = detect_anomalies(manifest)
        serialized = json.dumps(issues)
        assert 'missing_file' in serialized
        assert 'extraction_issue' in serialized
        assert 'sources' in serialized
    finally:
        manifest.close()
