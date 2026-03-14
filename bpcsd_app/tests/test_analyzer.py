import unittest

from modules.analyzer import analyze_director_trend


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


if __name__ == "__main__":
    unittest.main()
