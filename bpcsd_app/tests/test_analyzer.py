import unittest

from modules.analyzer import analyze_director_trend, analyze_meeting_themes


class AnalyzerDirectorTests(unittest.TestCase):
    def test_low_coverage_flag_emitted(self):
        data = {
            "July": "Students participated in summer camp. $5,000 donated to program.",
            "August": None,
            "September": None,
            "October": None,
        }
        analysis = analyze_director_trend(data)
        items = {f["item"] for f in analysis["flags"]}
        self.assertIn("Low Report Coverage", items)

    def test_meeting_theme_analysis_extracts_theme_and_money(self):
        docs = [{
            "meeting": "2025-10 - Oct 20, 2025",
            "section": "Finance Committee",
            "label": "Revenue Status",
            "filename": "Revenue Status October 2025.pdf",
            "text": "Budget discussion included appropriation updates and a transfer of $1,250,000.00.",
        }]
        out = analyze_meeting_themes(docs)

        self.assertTrue(out["themes"])
        self.assertEqual(out["monetary_items"][0]["amount"], 1250000.0)


if __name__ == "__main__":
    unittest.main()
