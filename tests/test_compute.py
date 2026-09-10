import unittest
from datetime import datetime

from briefing.compute.derivatives import analyse_option_chain, max_pain
from briefing.compute.market import breadth_ratio, fii_futures_stance, rank_sectors
from briefing.compute.momentum import extra_technicals, price_momentum, rsi, rsi_assessment, volume_trend
from briefing.compute.pivots import classic_pivots, compute_levels, drop_incomplete_session
from briefing.schedule import IST


def bar(day, high, low, close, open_=None, volume=None):
    row = {"date": day, "open": open_ or close, "high": high, "low": low, "close": close}
    if volume is not None:
        row["volume"] = volume
    return row


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


class MomentumTests(unittest.TestCase):
    """Watchlist-only technicals: see SPEC.md's note on why these are kept separate
    from the market-wide pivots/DMA above.
    """

    def test_rsi_needs_enough_history(self):
        self.assertIsNone(rsi([100.0] * 10, period=14))

    def test_rsi_is_100_when_every_change_is_a_gain(self):
        closes = [100.0 + i for i in range(20)]
        self.assertEqual(rsi(closes, period=14), 100.0)

    def test_rsi_is_low_when_every_change_is_a_loss(self):
        closes = [120.0 - i for i in range(20)]
        self.assertEqual(rsi(closes, period=14), 0.0)

    def test_rsi_assessment_bands(self):
        self.assertIn("stretched to the upside", rsi_assessment(75))
        self.assertIn("stretched to the downside", rsi_assessment(20))
        self.assertIn("neutral", rsi_assessment(50))

    def test_rsi_assessment_never_says_overbought_or_oversold(self):
        for value in (10, 30, 50, 70, 95):
            text = rsi_assessment(value).lower()
            self.assertNotIn("overbought", text)
            self.assertNotIn("oversold", text)

    def test_price_momentum_reads_direction_and_percent(self):
        closes = [100.0] * 5 + [110.0]
        result = price_momentum(closes, period=5)
        self.assertEqual(result["direction"], "risen")
        self.assertEqual(result["change_percent"], 10.0)
        self.assertEqual(result["period_days"], 5)

    def test_price_momentum_needs_enough_history(self):
        self.assertIsNone(price_momentum([100.0, 101.0], period=5))

    def test_volume_trend_flags_heavy_interest(self):
        rows = [bar(f"day{i}", 100, 90, 95, volume=1000) for i in range(20)]
        rows.append(bar("day20", 100, 90, 95, volume=2000))
        result = volume_trend(rows, period=20)
        self.assertEqual(result["ratio"], 2.0)
        self.assertIn("unusually heavy", result["assessment"])

    def test_volume_trend_needs_enough_history(self):
        rows = [bar("day0", 100, 90, 95, volume=1000)]
        self.assertIsNone(volume_trend(rows, period=20))

    def test_extra_technicals_bundles_dma8_rsi_momentum_and_volume(self):
        rows = [
            bar(f"2026-08-{i:02d}", 100 + i, 90 + i, 95 + i, volume=1000)
            for i in range(1, 25)
        ]
        bundle = extra_technicals(rows, now=datetime(2026, 9, 10, 18, 0, tzinfo=IST))
        self.assertIn("dma_8", bundle)
        self.assertIn("rsi", bundle)
        self.assertIn("momentum", bundle)
        self.assertIn("volume_trend", bundle)

    def test_extra_technicals_empty_for_no_data(self):
        self.assertEqual(extra_technicals([]), {})


if __name__ == "__main__":
    unittest.main()
