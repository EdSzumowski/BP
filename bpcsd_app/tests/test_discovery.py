import unittest

from modules.discovery import _parse_meetings_list, _group_into_sections, _find_target_parent_indexes


class DiscoveryParsingTests(unittest.TestCase):
    def test_parse_keeps_regular_and_special_same_month(self):
        html = '''
        <option value="AAAAAAAAAAAA">November 3, 2025 - Special</option>
        <option value="BBBBBBBBBBBB">November 17, 2025 - Regular</option>
        '''
        meetings = _parse_meetings_list(html)

        self.assertIn("2025-11", meetings)
        ids = {v["id"] for v in meetings.values()}
        self.assertEqual(ids, {"AAAAAAAAAAAA", "BBBBBBBBBBBB"})

    def test_parse_json_mmddyyyy_date(self):
        html = '{"id":"CCCCCCCCCCCC","date":"1/27/2025"}'
        meetings = _parse_meetings_list(html)

        self.assertIn("2025-01", meetings)
        self.assertEqual(meetings["2025-01"]["id"], "CCCCCCCCCCCC")

    def test_grouping_does_not_promote_personnel_motion_to_section(self):
        raw_items = [
            {"item_id": "AAAAAAAAAAAA", "title": "Consent Agenda", "level": 1},
            {"item_id": "BBBBBBBBBBBB", "title": "1660 Annual Budget Vote", "level": 2},
            {"item_id": "CCCCCCCCCCCC", "title": "2320 Attendance Members Conferences", "level": 2},
        ]
        grouped = _group_into_sections(raw_items)

        self.assertIn("Consent Agenda", grouped)
        self.assertEqual(len(grouped["Consent Agenda"]["items"]), 2)

    def test_target_parent_detection_is_precise(self):
        raw_items = [
            {"item_id": "AAAA", "title": "1. Call to Order", "level": 1},
            {"item_id": "BBBB", "title": "3. Superintendent's Report", "level": 1},
            {"item_id": "CCCC", "title": "4. Director Reports - Questions or Concerns", "level": 1},
            {"item_id": "DDDD", "title": "5. Consent Agenda", "level": 1},
            {"item_id": "EEEE", "title": "Special Education BOE Report Feb 2025", "level": 2},
        ]
        hits = _find_target_parent_indexes(raw_items)
        areas = [a for a, _ in hits]

        self.assertIn("Superintendent Report", areas)
        self.assertIn("Director Reports", areas)
        self.assertIn("Consent Agenda", areas)
        self.assertNotIn("Special Education", areas)


if __name__ == "__main__":
    unittest.main()
