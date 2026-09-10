import unittest

from briefing.config import load_config
from briefing.filter.rules import apply_caps, rule_filter
from briefing.filter.scorer import score_items
from briefing.llm.stub import StubProvider


class RuleGateTests(unittest.TestCase):
    def test_keeps_high_impact_items(self):
        items = [
            {"headline": "Tata Motors Q1 net profit up 28% YoY"},
            {"headline": "Gensol Engineering bags order worth Rs 480 crore"},
            {"headline": "RBI keeps repo rate unchanged at 5.25%"},
        ]
        kept, dropped = rule_filter(items)
        self.assertEqual(len(kept), 3)
        self.assertEqual(dropped, [])

    def test_drops_retail_filler(self):
        items = [
            {"headline": "Top 5 stocks to buy this week"},
            {"headline": "Should you switch your mutual fund SIP portfolio now?"},
            {"headline": "How to open a demat account"},
        ]
        kept, dropped = rule_filter(items)
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 3)

    def test_drops_items_with_no_market_keyword(self):
        kept, dropped = rule_filter([{"headline": "Monsoon arrives over Kerala coast"}])
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["dropped_because"], "no high-impact keyword")

    def test_matches_on_announcement_fields_too(self):
        kept, _ = rule_filter([{"subject": "Board approves buyback", "company": "LTTS"}])
        self.assertEqual(len(kept), 1)

    def test_multi_word_keywords_match(self):
        items = [
            {"headline": "Gensol bags order worth Rs 480 crore"},
            {"headline": "Promoter completes stake sale in the company"},
            {"headline": "Heavy block deal seen in Concord Control"},
            {"headline": "Firm signs letter of intent for new plant"},
        ]
        kept, dropped = rule_filter(items)
        self.assertEqual(len(kept), 4, [d["headline"] for d in dropped])

    def test_word_boundaries_prevent_false_matches(self):
        kept, dropped = rule_filter([{"headline": "It was a mistake by the umpire"}])
        self.assertEqual(kept, [])


class CapTests(unittest.TestCase):
    def test_caps_trim_to_the_highest_scores(self):
        items = [{"category": "earnings", "score": s, "headline": f"h{s}"} for s in (5, 9, 7, 8)]
        capped = apply_caps(items, {"earnings": 2})
        self.assertEqual([i["score"] for i in capped["earnings"]], [9, 8])

    def test_uncapped_category_keeps_everything(self):
        items = [{"category": "macro", "score": s} for s in (6, 7)]
        self.assertEqual(len(apply_caps(items, {"earnings": 1})["macro"]), 2)


class ScorerTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.provider = StubProvider(self.config)

    def test_scores_are_labelled_and_thresholded(self):
        items = [
            {"headline": "RBI holds repo rate, flags inflation risk"},
            {"headline": "Reliance board approves demerger of retail arm"},
            {"headline": "Company issues routine compliance certificate"},
        ]
        kept, scored = score_items(self.config, self.provider, items)
        self.assertEqual(len(scored), 3)
        for item in scored:
            self.assertIn("category", item)
            self.assertTrue(0 <= item["score"] <= 10)
        self.assertTrue(all(i["score"] >= 7 for i in kept))
        self.assertEqual(kept, sorted(kept, key=lambda i: i["score"], reverse=True))

    def test_batching_covers_every_item(self):
        items = [{"headline": f"Company {i} reports Q1 results"} for i in range(25)]
        _, scored = score_items(self.config, self.provider, items, batch_size=10)
        self.assertEqual(len(scored), 25)

    def test_unparseable_response_is_excluded_not_guessed(self):
        class Broken:
            name = "broken"

            def complete(self, system, user, tier):
                return "I cannot comply with that request."

        kept, scored = score_items(self.config, Broken(), [{"headline": "RBI cuts repo rate"}])
        self.assertEqual(kept, [])
        self.assertEqual(scored[0]["score"], 0)
        self.assertEqual(scored[0]["category"], "unscored")

    def test_empty_input_is_handled(self):
        self.assertEqual(score_items(self.config, self.provider, []), ([], []))


if __name__ == "__main__":
    unittest.main()
