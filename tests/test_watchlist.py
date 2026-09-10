import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from briefing import pipeline
from briefing.compute.derivatives import contract_snapshot
from briefing.config import Config
from briefing.deliver import gsheets
from briefing.fetch.base import FetchResult
from briefing.fetch.nse import _resolve_expiry
from briefing.payload.common import PayloadContext, watchlist_block
from briefing.payload.evening import build_evening_payload
from briefing.payload.morning import build_morning_payload

DAY = date(2026, 9, 10)


class ReadWatchlistTests(unittest.TestCase):
    def setUp(self):
        gsheets._ensure_watchlist_tab.cache_clear()

    def _mock_sheets(self, *, existing_sheets, rows):
        sheets = MagicMock()
        sheets.spreadsheets().get.return_value.execute.return_value = {"sheets": existing_sheets}
        sheets.spreadsheets().values().get.return_value.execute.return_value = {"values": rows}
        return sheets

    @patch("briefing.deliver.gsheets.service")
    def test_plain_stock_row_has_no_option_fields(self, service):
        service.return_value = self._mock_sheets(
            existing_sheets=[{"properties": {"title": "Watchlist"}}],
            rows=[["TCS", "", "", "", "Tata Consultancy"]],
        )
        entries = gsheets.read_watchlist("sheet123")
        self.assertEqual(entries, [{"symbol": "TCS", "name": "Tata Consultancy"}])

    @patch("briefing.deliver.gsheets.service")
    def test_option_row_needs_all_three_fields(self, service):
        service.return_value = self._mock_sheets(
            existing_sheets=[{"properties": {"title": "Watchlist"}}],
            rows=[["GVT&D", "4700", "CE", "29-Sep-2026", ""]],
        )
        entries = gsheets.read_watchlist("sheet123")
        self.assertEqual(entries, [{
            "symbol": "GVT&D", "strike": 4700.0, "option_type": "CE", "expiry": "29-Sep-2026",
        }])

    @patch("briefing.deliver.gsheets.service")
    def test_partial_option_fields_fall_back_to_a_plain_stock(self, service):
        service.return_value = self._mock_sheets(
            existing_sheets=[{"properties": {"title": "Watchlist"}}],
            rows=[["RELIANCE", "3000", "", ""]],
        )
        entries = gsheets.read_watchlist("sheet123")
        self.assertEqual(entries, [{"symbol": "RELIANCE"}])

    @patch("briefing.deliver.gsheets.service")
    def test_non_numeric_strike_is_dropped_not_guessed(self, service):
        service.return_value = self._mock_sheets(
            existing_sheets=[{"properties": {"title": "Watchlist"}}],
            rows=[["INFY", "not-a-number", "PE", "29-Sep-2026"]],
        )
        entries = gsheets.read_watchlist("sheet123")
        self.assertEqual(entries, [])

    @patch("briefing.deliver.gsheets.service")
    def test_blank_symbol_is_skipped(self, service):
        service.return_value = self._mock_sheets(
            existing_sheets=[{"properties": {"title": "Watchlist"}}],
            rows=[["", "", "", ""], ["TCS", "", "", ""]],
        )
        entries = gsheets.read_watchlist("sheet123")
        self.assertEqual(entries, [{"symbol": "TCS"}])

    @patch("briefing.deliver.gsheets.service")
    def test_creates_the_tab_when_it_does_not_exist_yet(self, service):
        sheets = self._mock_sheets(existing_sheets=[], rows=[])
        sheets.spreadsheets().batchUpdate.return_value.execute.return_value = {}
        service.return_value = sheets

        gsheets.read_watchlist("sheet123")

        sheets.spreadsheets().batchUpdate.assert_called_once()


class ResolveExpiryTests(unittest.TestCase):
    EXPIRIES = ["25-Sep-2026", "02-Oct-2026", "09-Oct-2026", "30-Oct-2026"]

    def test_exact_date_match(self):
        self.assertEqual(_resolve_expiry(self.EXPIRIES, "29-Sep-2026"), "02-Oct-2026")

    def test_iso_format_is_understood(self):
        self.assertEqual(_resolve_expiry(self.EXPIRIES, "2026-09-25"), "25-Sep-2026")

    def test_date_without_year_assumes_this_year(self):
        self.assertEqual(_resolve_expiry(self.EXPIRIES, "25 Sep"), "25-Sep-2026")

    def test_unparseable_hint_falls_back_to_nearest(self):
        self.assertEqual(_resolve_expiry(self.EXPIRIES, "whenever"), self.EXPIRIES[0])

    def test_date_past_every_expiry_falls_back_to_the_closest_one(self):
        self.assertEqual(_resolve_expiry(self.EXPIRIES, "2026-12-25"), "30-Oct-2026")


class ContractSnapshotTests(unittest.TestCase):
    def chain(self):
        return {
            "symbol": "GVT&D", "expiry": "29-Sep-2026", "underlying": 4550.0,
            "rows": [
                {"strike": 4700.0, "call_oi": 5000, "call_oi_change": 300, "call_ltp": 42.5,
                 "call_iv": 24.1, "put_oi": 1200, "put_oi_change": -50, "put_ltp": 180.0, "put_iv": 27.3},
            ],
        }

    def test_call_contract_pulls_the_call_side(self):
        snapshot = contract_snapshot(self.chain(), 4700.0, "CE")
        self.assertEqual(snapshot["premium"], 42.5)
        self.assertEqual(snapshot["open_interest"], 5000)
        self.assertEqual(snapshot["kind"], "call")

    def test_put_contract_pulls_the_put_side(self):
        snapshot = contract_snapshot(self.chain(), 4700.0, "PE")
        self.assertEqual(snapshot["premium"], 180.0)
        self.assertEqual(snapshot["kind"], "put")

    def test_strike_not_in_chain_returns_none(self):
        self.assertIsNone(contract_snapshot(self.chain(), 5000.0, "CE"))

    def test_untraded_contract_with_no_last_price_returns_none(self):
        chain = self.chain()
        chain["rows"][0]["call_ltp"] = None
        self.assertIsNone(contract_snapshot(chain, 4700.0, "CE"))


class WatchlistBlockTests(unittest.TestCase):
    def test_stock_entry_carries_technicals_and_news(self):
        raw = [{
            "symbol": "TCS",
            "name": "Tata Consultancy",
            "technicals": {
                "reference_session": "09-Sep-2026", "reference_close": 4200.0,
                "pivots": {"pivot": 4210, "r1": 4250, "r2": 4290, "s1": 4170, "s2": 4130},
                "dma_20": 4180.0, "dma_50": 4100.0, "trend": "above both averages",
            },
            "option_chain": {
                "expiry": "25-Sep-2026", "pcr": 1.1, "pcr_assessment": "balanced",
                "call_wall": 4300.0, "put_wall": 4100.0, "max_pain": 4200.0,
            },
            "news": [{"headline": "TCS wins large deal", "source": "GoogleNews"}],
        }]
        shaped = watchlist_block(raw, DAY)
        self.assertEqual(len(shaped), 1)
        entry = shaped[0]
        self.assertEqual(entry["symbol"], "TCS")
        self.assertEqual(entry["technicals"]["reference_close"], "4,200.00")
        self.assertEqual(entry["option_chain"]["call_wall_strike"], "4,300")
        self.assertEqual(entry["news"][0]["headline"], "TCS wins large deal")

    def test_option_entry_carries_days_to_expiry(self):
        raw = [{
            "symbol": "GVT&D",
            "contract": {
                "strike": 4700.0, "option_type": "CE", "kind": "call", "expiry": "29-Sep-2026",
                "premium": 42.5, "open_interest": 5000, "oi_change": 300,
                "implied_volatility": 24.1, "underlying": 4550.0,
            },
            "underlying_technicals": {
                "reference_session": "09-Sep-2026", "reference_close": 4550.0,
                "pivots": {"pivot": 4560, "r1": 4600, "r2": 4650, "s1": 4520, "s2": 4480},
                "dma_20": 4500.0, "dma_50": 4400.0, "trend": None,
            },
            "news": [],
        }]
        shaped = watchlist_block(raw, DAY)
        entry = shaped[0]
        self.assertEqual(entry["contract"]["days_to_expiry"], 19)
        self.assertEqual(entry["contract"]["premium"], "42.50")
        self.assertEqual(entry["contract"]["kind"], "call")
        self.assertNotIn("news", entry)

    def test_entry_with_nothing_usable_is_dropped(self):
        raw = [{"symbol": "GHOST", "technicals": None, "option_chain": None, "news": []}]
        self.assertEqual(watchlist_block(raw, DAY), [])


class PayloadWiringTests(unittest.TestCase):
    """Both editions must thread the watchlist argument into payload['watchlist']."""

    RAW = [{
        "symbol": "TCS",
        "technicals": {
            "reference_session": "09-Sep-2026", "reference_close": 4200.0,
            "pivots": {"pivot": 4210, "r1": 4250, "r2": 4290, "s1": 4170, "s2": 4130},
            "dma_20": 4180.0, "dma_50": 4100.0, "trend": "above both averages",
        },
        "option_chain": None,
        "news": [],
    }]

    def test_morning_payload_carries_the_watchlist(self):
        ctx = PayloadContext.from_results([])
        payload = build_morning_payload(ctx, DAY, [], watchlist=self.RAW)
        self.assertEqual(payload["watchlist"][0]["symbol"], "TCS")

    def test_evening_payload_carries_the_watchlist(self):
        ctx = PayloadContext.from_results([])
        payload = build_evening_payload(ctx, DAY, [], watchlist=self.RAW)
        self.assertEqual(payload["watchlist"][0]["symbol"], "TCS")

    def test_no_watchlist_argument_omits_the_section_in_both(self):
        ctx = PayloadContext.from_results([])
        self.assertNotIn("watchlist", build_morning_payload(ctx, DAY, []))
        self.assertNotIn("watchlist", build_evening_payload(ctx, DAY, []))


class GatherWatchlistTests(unittest.TestCase):
    def config(self, **overrides):
        data = {"google": {"sheet_id": "sheet123"}, "news_domains": ["moneycontrol.com"]}
        data.update(overrides)
        return Config(data=data, root=None)

    def test_no_sheet_id_returns_nothing(self):
        result = pipeline.gather_watchlist(self.config(google={"sheet_id": ""}), DAY)
        self.assertEqual(result, [])

    @patch("briefing.pipeline.read_watchlist", side_effect=RuntimeError("no credentials"))
    def test_sheet_read_failure_is_non_fatal(self, _read):
        self.assertEqual(pipeline.gather_watchlist(self.config(), DAY), [])

    @patch("briefing.pipeline.news_fetch.fetch_news")
    @patch("briefing.pipeline.nse_fetch.fetch_option_chain")
    @patch("briefing.pipeline.watchlist_fetch.fetch_watchlist_quotes")
    @patch("briefing.pipeline.read_watchlist")
    def test_stock_and_option_entries_are_both_assembled(
        self, read_watchlist, fetch_quotes, fetch_chain, fetch_news
    ):
        read_watchlist.return_value = [
            {"symbol": "TCS", "name": "Tata Consultancy"},
            {"symbol": "GVT&D", "strike": 4700.0, "option_type": "CE", "expiry": "29-Sep-2026"},
        ]
        history = [
            {"date": f"2026-08-{d:02d}", "open": 100 + d, "high": 105 + d, "low": 95 + d, "close": 100 + d}
            for d in range(1, 25)
        ]
        fetch_quotes.return_value = FetchResult.success("watchlist.yfinance", {"TCS": history, "GVT&D": history})

        def chain_side_effect(session, symbol, *, expiry=None):
            if symbol == "TCS":
                return FetchResult.success("nse.option_chain.tcs", {
                    "symbol": "TCS", "expiry": "25-Sep-2026", "underlying": 4200.0,
                    "rows": [{"strike": 4200.0, "call_oi": 500, "put_oi": 400}],
                })
            return FetchResult.success("nse.option_chain.gvt&d", {
                "symbol": "GVT&D", "expiry": "29-Sep-2026", "underlying": 4550.0,
                "rows": [{"strike": 4700.0, "call_oi": 5000, "call_oi_change": 300,
                          "call_ltp": 42.5, "call_iv": 24.1}],
            })

        fetch_chain.side_effect = chain_side_effect
        fetch_news.return_value = FetchResult.success("news.google_rss", [
            {"headline": "TCS wins deal", "topic": "watchlist::TCS", "source": "GoogleNews"},
        ])

        out = pipeline.gather_watchlist(self.config(), DAY)

        self.assertEqual(len(out), 2)
        stock, option = out
        self.assertEqual(stock["symbol"], "TCS")
        self.assertIsNotNone(stock["technicals"])
        self.assertIsNotNone(stock["option_chain"])
        self.assertEqual(stock["news"][0]["headline"], "TCS wins deal")

        self.assertEqual(option["symbol"], "GVT&D")
        self.assertEqual(option["contract"]["premium"], 42.5)
        self.assertIsNotNone(option["underlying_technicals"])

    @patch("briefing.pipeline.read_watchlist")
    def test_more_than_the_cap_is_trimmed(self, read_watchlist):
        read_watchlist.return_value = [{"symbol": f"SYM{i}"} for i in range(20)]
        config = self.config()
        config.data["watchlist"] = {"max_symbols": 3}
        with patch("briefing.pipeline.watchlist_fetch.fetch_watchlist_quotes") as fetch_quotes, \
             patch("briefing.pipeline.nse_fetch.fetch_option_chain") as fetch_chain, \
             patch("briefing.pipeline.news_fetch.fetch_news") as fetch_news:
            fetch_quotes.return_value = FetchResult.failure("watchlist.yfinance", "n/a")
            fetch_chain.return_value = FetchResult.failure("nse.option_chain", "n/a")
            fetch_news.return_value = FetchResult.failure("news.google_rss", "n/a")
            out = pipeline.gather_watchlist(config, DAY)
        self.assertEqual(len(out), 3)


if __name__ == "__main__":
    unittest.main()
