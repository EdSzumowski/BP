import unittest

from modules.discovery import _parse_meetings_list


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


if __name__ == "__main__":
    unittest.main()
