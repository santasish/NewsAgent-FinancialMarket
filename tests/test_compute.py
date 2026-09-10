import unittest
from datetime import datetime

from briefing.compute.derivatives import analyse_option_chain, max_pain
from briefing.compute.market import breadth_ratio, fii_futures_stance, rank_sectors
from briefing.compute.pivots import classic_pivots, compute_levels, drop_incomplete_session
from briefing.schedule import IST


def bar(day, high, low, close, open_=None):
    return {"date": day, "open": open_ or close, "high": high, "low": low, "close": close}


class PivotTests(unittest.TestCase):
    def test_classic_pivots_match_the_textbook_formula(self):
        p = classic_pivots(high=110.0, low=90.0, close=100.0)
        self.assertEqual(p["pivot"], 100.0)
        self.assertEqual(p["r1"], 110.0)  # 2P - L
        self.assertEqual(p["s1"], 90.0)  # 2P - H
        self.assertEqual(p["r2"], 120.0)  # P + (H - L)
        self.assertEqual(p["s2"], 80.0)  # P - (H - L)

    def test_incomplete_session_is_dropped_before_the_close(self):
        rows = [bar("2026-09-09", 105, 95, 100), bar("2026-09-10", 101, 99, 100)]
        during = datetime(2026, 9, 10, 12, 0, tzinfo=IST)
        self.assertEqual(len(drop_incomplete_session(rows, during)), 1)

    def test_completed_session_is_kept_after_the_close(self):
        rows = [bar("2026-09-09", 105, 95, 100), bar("2026-09-10", 101, 99, 100)]
        after = datetime(2026, 9, 10, 18, 0, tzinfo=IST)
        self.assertEqual(len(drop_incomplete_session(rows, after)), 2)

    def test_levels_use_the_last_completed_session(self):
        rows = [bar("2026-09-09", 110, 90, 100), bar("2026-09-10", 101, 99, 100)]
        during = datetime(2026, 9, 10, 12, 0, tzinfo=IST)
        levels = compute_levels(rows, now=during)
        self.assertEqual(levels["reference_session"], "2026-09-09")
        self.assertEqual(levels["pivots"]["pivot"], 100.0)

    def test_moving_averages_need_enough_history(self):
        rows = [bar(f"2026-01-{d:02d}", 10, 8, 9) for d in range(1, 6)]
        levels = compute_levels(rows, now=datetime(2026, 2, 1, 18, 0, tzinfo=IST))
        self.assertIsNone(levels["dma_20"])
        self.assertIsNone(levels["dma_50"])


class DerivativeTests(unittest.TestCase):
    def chain(self):
        return {
            "symbol": "NIFTY",
            "expiry": "15-Sep-2026",
            "underlying": 23450.0,
            "rows": [
                {"strike": 23400.0, "call_oi": 100, "put_oi": 900},
                {"strike": 23500.0, "call_oi": 500, "put_oi": 400},
                {"strike": 23600.0, "call_oi": 800, "put_oi": 100},
            ],
        }

    def test_pcr_and_walls(self):
        result = analyse_option_chain(self.chain())
        self.assertEqual(result["pcr"], round(1400 / 1400, 2))
        self.assertEqual(result["call_wall"], 23600.0)
        self.assertEqual(result["put_wall"], 23400.0)

    def test_low_pcr_reads_as_stretched_to_the_downside(self):
        chain = self.chain()
        chain["rows"] = [{"strike": 23500.0, "call_oi": 1000, "put_oi": 300}]
        self.assertIn("far outnumber bets on a fall", analyse_option_chain(chain)["pcr_assessment"])

    def test_max_pain_is_the_least_costly_strike_for_writers(self):
        rows = [
            {"strike": 100.0, "call_oi": 0, "put_oi": 1000},
            {"strike": 110.0, "call_oi": 1000, "put_oi": 0},
        ]
        self.assertIn(max_pain(rows), (100.0, 110.0))

    def test_empty_chain_returns_none(self):
        self.assertIsNone(analyse_option_chain({"rows": []}))


class MarketTests(unittest.TestCase):
    def test_breadth_reduces_to_a_readable_ratio(self):
        result = breadth_ratio({"advances": 3891, "declines": 5644, "unchanged": 82})
        self.assertEqual(result["ratio"], "1:1.5")
        self.assertEqual(result["advances"], 3891)

    def test_breadth_ratio_orients_to_the_winning_side(self):
        self.assertEqual(breadth_ratio({"advances": 6000, "declines": 3000})["ratio"], "2.0:1")

    def test_breadth_needs_both_sides(self):
        self.assertIsNone(breadth_ratio({"advances": 0, "declines": 100}))

    def test_sectors_split_into_leaders_and_laggards(self):
        sectors = [
            {"name": "NIFTY IT", "percent_change": 1.5, "last": 100},
            {"name": "NIFTY AUTO", "percent_change": -0.9, "last": 200},
            {"name": "NIFTY FMCG", "percent_change": 0.2, "last": 300},
        ]
        ranked = rank_sectors(sectors)
        self.assertEqual(ranked["outperforming"][0]["name"], "NIFTY IT")
        self.assertEqual(ranked["underperforming"][0]["name"], "NIFTY AUTO")

    def test_fii_stance_finds_columns_despite_header_drift(self):
        data = {
            "date": "09092026",
            "participants": {
                "FII": {"Future Index Long": 20000.0, "Future Index  Short": 80000.0}
            },
        }
        stance = fii_futures_stance(data)
        self.assertEqual(stance["long_ratio_percent"], 20.0)
        self.assertIn("betting on the index falling", stance["assessment"])

    def test_fii_stance_absent_when_columns_missing(self):
        self.assertIsNone(fii_futures_stance({"participants": {"FII": {"Total Long": 1}}}))


if __name__ == "__main__":
    unittest.main()
