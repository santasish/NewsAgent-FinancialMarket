"""End-to-end run: fetch -> compute -> filter -> payload -> generate -> verify.

Delivery is driven by the CLI once the briefing is on disk.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from briefing.compute import analyse_option_chain, compute_levels, contract_snapshot
from briefing.config import Config
from briefing.dedup import headline_key, load_seen, record_seen
from briefing.deliver.gsheets import read_watchlist
from briefing.fetch import news as news_fetch
from briefing.fetch import nse as nse_fetch
from briefing.fetch import watchlist as watchlist_fetch
from briefing.fetch.base import FetchResult, save_raw
from briefing.filter import apply_caps, rule_filter, score_items
from briefing.generate import generate
from briefing.llm.base import Provider
from briefing.payload import BUILDERS, PayloadContext
from briefing.payload.common import OPTIONAL_SOURCES
from briefing.sources import fetch_all
from briefing.verify import VerifyResult, verify, violations_feedback

VERIFICATION_BANNER = (
    "A note before we start: some figures in this issue could not be matched to the "
    "source data, so treat the numbers with care."
)

# Text-shaped feeds, with the plain name the issue uses when one is down. A failure
# here does not blank a section outright, but it does mean thinner coverage, so the
# run is marked degraded and the issue says so.
NEWS_SOURCES = {
    "news.google_rss": "press headlines",
    "nse.announcements": "company filings from the NSE",
    "bse.announcements": "company filings from the BSE",
    "pib.releases": "government releases",
}


@dataclass
class RunResult:
    prompt_name: str
    payload: dict[str, Any]
    output: str
    verification: VerifyResult
    fetches: list[FetchResult] = field(default_factory=list)
    scored: list[dict[str, Any]] = field(default_factory=list)
    kept_news: list[dict[str, Any]] = field(default_factory=list)

    @property
    def failed_sources(self) -> list[str]:
        """Sources that should have worked and did not. Optional ones never count."""
        return [f.name for f in self.fetches if not f.ok and f.name not in OPTIONAL_SOURCES]

    @property
    def degraded(self) -> bool:
        return bool(self.payload.get("degraded"))


def gather_news(
    config: Config,
    provider: Provider,
    fetches: list[FetchResult],
    *,
    already_seen: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rule-gate, score and cap everything text-shaped that was fetched.

    `already_seen` is the set of headline keys an earlier edition today already used —
    see `briefing.dedup`. Excluding them before scoring, rather than after, also means
    they never cost a Gemini call.
    """
    items: list[dict[str, Any]] = []
    for name in NEWS_SOURCES:
        result = next((f for f in fetches if f.name == name), None)
        if result and result.ok and isinstance(result.data, list):
            items.extend(result.data)

    if not items:
        return [], []

    candidates, _ = rule_filter(items)
    if already_seen:
        candidates = [c for c in candidates if headline_key(c) not in already_seen]
    kept, scored = score_items(config, provider, candidates)
    capped = apply_caps(kept, config.get("caps", {}))
    flattened = [item for group in capped.values() for item in group]
    flattened.sort(key=lambda i: i.get("score", 0), reverse=True)
    return flattened, scored


def gather_watchlist(config: Config, day: date) -> list[dict[str, Any]]:
    """Fetch technicals, options data and news for the day's watchlist, if any is set.

    Entirely optional and best-effort: no Sheet configured, an empty Watchlist tab, or
    any fetch failing along the way just means fewer (or zero) entries, never a failed
    run — this is a bonus section, not a source the rest of the briefing depends on.
    """
    sheet_id = config.get("google.sheet_id", "")
    if not sheet_id:
        return []
    try:
        entries = read_watchlist(sheet_id)
    except Exception:
        return []
    if not entries:
        return []

    max_symbols = config.get("watchlist.max_symbols", 8)
    entries = entries[:max_symbols]

    symbols = sorted({e["symbol"] for e in entries})
    quotes_result = watchlist_fetch.fetch_watchlist_quotes(symbols)
    quotes = quotes_result.data if quotes_result.ok else {}

    session = nse_fetch.NSESession()
    chain_cache: dict[tuple[str, str | None], Any] = {}

    def chain_for(symbol: str, expiry: str | None) -> dict[str, Any] | None:
        key = (symbol, expiry)
        if key not in chain_cache:
            result = nse_fetch.fetch_option_chain(session, symbol, expiry=expiry)
            chain_cache[key] = result.data if result.ok else None
        return chain_cache[key]

    news_queries = {f"watchlist::{e['symbol']}": f"\"{e.get('name') or e['symbol']}\"" for e in entries}
    news_result = news_fetch.fetch_news(domains=config.get("news_domains"), queries=news_queries)
    news_by_symbol: dict[str, list[dict[str, Any]]] = {}
    if news_result.ok:
        for item in news_result.data:
            topic = item.get("topic", "")
            if topic.startswith("watchlist::"):
                news_by_symbol.setdefault(topic.split("::", 1)[1], []).append(item)

    out: list[dict[str, Any]] = []
    for entry in entries:
        symbol = entry["symbol"]
        history = quotes.get(symbol, [])
        levels = compute_levels(history) if history else None
        item_news = news_by_symbol.get(symbol, [])[:4]

        if "strike" in entry:
            chain = chain_for(symbol, entry["expiry"])
            snapshot = contract_snapshot(chain, entry["strike"], entry["option_type"]) if chain else None
            out.append({
                "symbol": symbol,
                "name": entry.get("name"),
                "contract": snapshot,
                "underlying_technicals": levels,
                "news": item_news,
            })
        else:
            chain = chain_for(symbol, None)
            analysis = analyse_option_chain(chain) if chain else None
            out.append({
                "symbol": symbol,
                "name": entry.get("name"),
                "technicals": levels,
                "option_chain": analysis,
                "news": item_news,
            })
    return out


def run_pipeline(
    config: Config,
    provider: Provider,
    prompt_name: str,
    day: date,
    *,
    out_dir: Path,
    skip_news: bool = False,
) -> RunResult:
    fetches = fetch_all(config, include_news=not skip_news)
    state_dir = Path(config.get("state_dir", "state"))

    news: list[dict[str, Any]] = []
    scored: list[dict[str, Any]] = []
    if not skip_news:
        already_seen = load_seen(state_dir, day)
        news, scored = gather_news(config, provider, fetches, already_seen=already_seen)
        record_seen(state_dir, day, news)

    ctx = PayloadContext.from_results(fetches)
    for source_name, plain_name in NEWS_SOURCES.items():
        if source_name in OPTIONAL_SOURCES:
            continue
        result = next((f for f in fetches if f.name == source_name), None)
        if result is not None and not result.ok:
            ctx.missing.append(plain_name)

    if prompt_name in ("morning", "evening"):
        watchlist = gather_watchlist(config, day)
        payload = BUILDERS[prompt_name](ctx, day, news, watchlist=watchlist)
    else:
        payload = BUILDERS[prompt_name](ctx, day, news)

    save_raw(fetches, Path(config.get("raw_dir", "raw")), f"{day.isoformat()}_{prompt_name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{day.isoformat()}_{prompt_name}_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if scored:
        # Every headline with its score, so the threshold can be tuned against real days.
        audit = [
            {k: item.get(k) for k in ("score", "category", "score_reason", "headline", "subject", "company", "source")}
            for item in sorted(scored, key=lambda i: i.get("score", 0), reverse=True)
        ]
        (out_dir / f"{day.isoformat()}_{prompt_name}_scored.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8"
        )

    tolerance = config.get("verify.relative_tolerance", 0.001)
    min_magnitude = config.get("verify.min_magnitude", 100)

    output = generate(config, provider, prompt_name, payload)
    result = verify(output, payload, tolerance=tolerance, min_magnitude=min_magnitude)

    for _ in range(config.get("verify.max_regenerations", 1)):
        if result.ok:
            break
        corrected = dict(payload, _correction=violations_feedback(result))
        output = generate(config, provider, prompt_name, corrected)
        result = verify(output, payload, tolerance=tolerance, min_magnitude=min_magnitude)

    if not result.ok:
        output = f"{VERIFICATION_BANNER}\n\n{output}"

    return RunResult(
        prompt_name=prompt_name,
        payload=payload,
        output=output,
        verification=result,
        fetches=fetches,
        scored=scored,
        kept_news=news,
    )
