import unittest
from datetime import date

from briefing.compute.market import breadth_ratio
from briefing.fetch.base import FetchResult
from briefing.payload.common import PayloadContext, crore, is_after_hours, num, pct, side
from briefing.payload.evening import build_evening_payload
from briefing.verify import payload_numbers

DAY = date(2026, 9, 10)


def ok(name, data):
    return FetchResult.success(name, data)


def indices_data():
    def row(name, last, pct_change):
        return {
            "name": name, "last": last, "open": last, "high": last, "low": last,
            "previous_close": last, "change": 1.0, "percent_change": pct_change,
        }

    return {
        "timestamp": "10-Sep-2026 15:30",
        "benchmarks": {
            "NIFTY 50": row("NIFTY 50", 23457.40, 0.11),
            "NIFTY BANK": row("NIFTY BANK", 56459.05, 0.29),
            "INDIA VIX": row("INDIA VIX", 11.70, -1.82),
        },
        "sectors": [row("NIFTY IT", 100.0, 1.5), row("NIFTY AUTO", 200.0, -0.9)],
        "breadth": {"advances": 4416, "declines": 5129, "unchanged": 80},
    }


class FormattingTests(unittest.TestCase):
    def test_numbers_are_pre_formatted_for_printing(self):
        self.assertEqual(num(23457.4), "23,457.40")
        self.assertEqual(num(24000.0, 0), "24,000")
        self.assertEqual(pct(-0.45), "-0.45%")
        self.assertEqual(pct(1.2), "+1.20%")
        self.assertEqual(crore(-2840.5), "2,840.50")

    def test_direction_is_words_not_a_sign(self):
        self.assertEqual(side(-100), "SELLers")
        self.assertEqual(side(100), "BUYers")
        self.assertIsNone(side(None))

    def test_breadth_ratio_stays_faithful(self):
        self.assertEqual(breadth_ratio({"advances": 4416, "declines": 5129})["ratio"], "1:1.2")
        self.assertEqual(breadth_ratio({"advances": 3000, "declines": 6000})["ratio"], "1:2.0")


class AfterHoursTests(unittest.TestCase):
    def test_todays_post_close_filing_is_after_hours(self):
        item = {"time": "10-Sep-2026 16:15:00"}
        self.assertTrue(is_after_hours(item, DAY))

    def test_yesterday_evening_is_not_todays_after_hours(self):
        item = {"time": "09-Sep-2026 21:47:00"}
        self.assertFalse(is_after_hours(item, DAY))

    def test_intraday_filing_is_not_after_hours(self):
        self.assertFalse(is_after_hours({"time": "10-Sep-2026 11:00:00"}, DAY))

    def test_missing_timestamp_is_not_after_hours(self):
        self.assertFalse(is_after_hours({}, DAY))


class EveningPayloadTests(unittest.TestCase):
    def build(self, results, news=None):
        ctx = PayloadContext.from_results(results)
        return build_evening_payload(ctx, DAY, news or [])

    def all_sources(self):
        chain = {
            "symbol": "NIFTY", "expiry": "15-Sep-2026", "underlying": 23450.0,
            "rows": [
                {"strike": 23400.0, "call_oi": 100, "put_oi": 900},
                {"strike": 24000.0, "call_oi": 800, "put_oi": 100},
            ],
        }
        return [
            ok("nse.indices", indices_data()),
            ok("nse.option_chain.nifty", chain),
            ok("nse.option_chain.banknifty", dict(chain, symbol="BANKNIFTY")),
            ok("macro.yfinance", {
                "quotes": {"brent_crude": {"last": 100.66, "percent_change": -0.54}},
                "history": {},
            }),
        ]

    def test_full_payload_shape(self):
        payload = self.build(self.all_sources() + [
            ok("nse.fii_dii", {
                "FII/FPI": {"date": "10-Sep-2026", "net_value": -582.99,
                            "buy_value": 16392.90, "sell_value": 16975.89},
                "DII": {"date": "10-Sep-2026", "net_value": 1509.04,
                        "buy_value": 18130.76, "sell_value": 16621.72},
            }),
            ok("nse.fno_ban", {"symbols": ["SAIL", "KAYNES"]}),
        ])
        self.assertEqual(payload["index_data"]["nifty_50"]["close"], "23,457.40")
        self.assertEqual(payload["fii_dii_data"]["fii"]["direction"], "SELLers")
        self.assertEqual(payload["fii_dii_data"]["dii"]["direction"], "BUYers")
        self.assertEqual(payload["derivatives"]["fno_ban"], ["SAIL", "KAYNES"])
        self.assertEqual(payload["market_breadth"]["ratio"], "1:1.2")
        self.assertFalse(payload["degraded"])

    def test_failed_source_marks_the_run_degraded(self):
        payload = self.build(self.all_sources() + [
            FetchResult.failure("nse.fii_dii", "timeout"),
        ])
        self.assertTrue(payload["degraded"])
        self.assertIn("foreign and domestic investor flows", payload["missing_sections"])
        self.assertNotIn("fii_dii_data", payload)

    def test_news_splits_into_intraday_and_after_hours(self):
        news = [
            {"headline": "Midday move", "time": "10-Sep-2026 11:00:00", "category": "macro", "score": 8},
            {"headline": "Post-close result", "time": "10-Sep-2026 16:15:00", "category": "earnings", "score": 9},
        ]
        payload = self.build([ok("nse.indices", indices_data())], news)
        self.assertEqual(len(payload["filtered_news"]), 1)
        self.assertEqual(payload["after_hours_filings"][0]["headline"], "Post-close result")

    def test_every_printed_figure_is_traceable(self):
        """The verifier's guarantee only holds if the payload carries the numbers."""
        payload = self.build([ok("nse.indices", indices_data())])
        numbers = payload_numbers(payload)
        self.assertIn(23457.40, numbers)
        self.assertIn(56459.05, numbers)


if __name__ == "__main__":
    unittest.main()
