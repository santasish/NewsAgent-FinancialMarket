import json
import unittest
from pathlib import Path

from briefing.verify import verify

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads((FIXTURES / "evening_payload.json").read_text(encoding="utf-8"))

    def check(self, text):
        return verify(text, self.payload)

    def test_golden_output_is_fully_traceable(self):
        output = (FIXTURES / "evening_output.txt").read_text(encoding="utf-8")
        result = self.check(output)
        self.assertTrue(result.ok, result.summary())
        self.assertGreater(result.checked, 20)

    def test_fabricated_level_is_caught(self):
        result = self.check("• Nifty support sits at 23,780 with a stop below 23,700.")
        self.assertFalse(result.ok)
        self.assertEqual({v.number for v in result.violations}, {"23,780", "23,700"})

    def test_fabricated_percentage_is_caught(self):
        result = self.check("• Eicher Motors fell 2.4% on weak dispatch numbers.")
        self.assertFalse(result.ok)
        self.assertEqual([v.number for v in result.violations], ["2.4"])

    def test_rounded_payload_value_is_accepted(self):
        # payload carries 24,015.50 and 95.20
        result = self.check("• Nifty closed at 24,015 with Brent at $95.")
        self.assertTrue(result.ok, result.summary())

    def test_list_markers_and_urls_are_not_treated_as_data(self):
        text = "1. Heading here\n• Link: [NSE](https://www.nseindia.com/api/x?id=999999)"
        self.assertTrue(self.check(text).ok)

    def test_prose_small_integers_are_ignored(self):
        self.assertTrue(self.check("Costs rise over the next 1-2 quarters.").ok)

    def test_hyphenated_header_text_is_not_data(self):
        text = "📑 AFTER-HOURS CORPORATE FILINGS & EARNINGS RELEASES (Post-3:30 PM Disclosures)"
        self.assertTrue(self.check(text).ok, self.check(text).summary())

    def test_signed_percentages_are_still_checked(self):
        result = self.check("• Nifty Metal fell -4.7% on the session.")
        self.assertFalse(result.ok)
        self.assertEqual([v.number for v in result.violations], ["4.7"])

    def test_index_names_are_not_figures(self):
        payload = {"global_cues": {"nikkei": {"last": "65,270.95"}, "sp500": {"last": "7,636.36"}}}
        text = "Japan's Nikkei 225 reached 65,270.95 while the S&P 500 sat at 7,636.36 and FTSE 100 lagged."
        result = verify(text, payload)
        self.assertTrue(result.ok, result.summary())
        # The real figures are still checked.
        self.assertEqual(result.checked, 2)

    def test_arithmetic_by_the_model_is_rejected(self):
        # The payload carries two yields; a move derived from them is not in the payload.
        payload = {"us_10y_yield": {"last": "4.84%", "previous": "4.72%"}}
        result = verify("The rate on ten-year US bonds rose 12 bps overnight.", payload)
        self.assertFalse(result.ok)
        self.assertEqual([v.number for v in result.violations], ["12"])


if __name__ == "__main__":
    unittest.main()
