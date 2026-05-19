from datetime import date
from pathlib import Path

from boarddocs_agent.downloader import DownloaderService, filter_meetings
from boarddocs_agent.models import Meeting


def _meeting(meeting_id: str, meeting_date: str, meeting_type: str = 'Regular Meeting') -> Meeting:
    return Meeting(meeting_id=meeting_id, meeting_date=date.fromisoformat(meeting_date), meeting_type=meeting_type, agenda_title=meeting_type)


def test_filter_meetings_applies_date_window_and_deduplicates():
    meetings = [
        _meeting('ONE', '2026-05-12'),
        _meeting('ONE', '2026-05-12'),
        _meeting('TWO', '2026-04-01'),
        _meeting('THREE', '2026-06-15'),
    ]

    filtered = filter_meetings(meetings, date(2026, 5, 1), date(2026, 5, 31))

    assert len(filtered) == 1
    assert filtered[0].meeting_id == 'ONE'
    assert filtered[0].meeting_date.isoformat() == '2026-05-12'


def test_requires_saved_session_uses_session_state_presence(monkeypatch, tmp_path: Path):
    missing_state = tmp_path / 'missing' / 'state.json'
    monkeypatch.setattr('boarddocs_agent.downloader.SESSION_STATE', missing_state)
    service = DownloaderService(tmp_path)

    assert service.requires_saved_session(headful=False, username=None, password=None)
    assert not service.requires_saved_session(headful=True, username=None, password=None)

    missing_state.parent.mkdir(parents=True)
    missing_state.write_text('{}', encoding='utf-8')

    assert not service.requires_saved_session(headful=False, username=None, password=None)
    assert not service.requires_saved_session(headful=False, username='user', password='pass')
