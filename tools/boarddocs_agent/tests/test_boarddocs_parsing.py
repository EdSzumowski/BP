from boarddocs_agent.boarddocs_client import parse_agenda, parse_attachments, parse_meetings_list


def test_parse_meetings_list_from_options():
    html = '<select><option value="DCCNK760440C">May 12, 2026 - Regular Meeting</option></select>'
    meetings = parse_meetings_list(html)
    assert len(meetings) == 1
    assert meetings[0].meeting_id == 'DCCNK760440C'
    assert meetings[0].meeting_date.isoformat() == '2026-05-12'


def test_parse_agenda_and_attachments():
    html = '''
    <div class="section">Business</div>
    <div id="ABCD123456" Xtitle="Treasurer Report">
      <a href="/ny/bpcsd/Board.nsf/files/report.pdf">Treasurer Report.pdf</a>
    </div>
    '''
    items = parse_agenda(html)
    assert items[0].title == 'Treasurer Report'
    assert items[0].attachments[0].filename == 'Treasurer Report.pdf'


def test_parse_attachments_filters_non_download_links():
    html = '<a href="https://example.test/page">Page</a><a href="https://example.test/file.docx">File</a>'
    attachments = parse_attachments(html)
    assert len(attachments) == 1
    assert attachments[0].url == 'https://example.test/file.docx'
