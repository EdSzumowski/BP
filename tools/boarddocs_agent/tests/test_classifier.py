from boarddocs_agent.classifier import classify_document


def test_classifies_personnel():
    assert classify_document('Consent Agenda', 'Personnel appointments', 'Substitute list') == 'Personnel'


def test_classifies_claims_audits_treasurer_before_general_finance():
    assert classify_document('Finance', 'Treasurer report and warrant claims', '') == 'Claims/Audits/Treasurer'


def test_classifies_other_when_no_rules_match():
    assert classify_document('Ceremonial', 'Recognition', 'Photo') == 'Other'
