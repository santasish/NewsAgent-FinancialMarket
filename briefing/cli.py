from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from briefing.config import load_config
from briefing.generate import generate
from briefing.llm.base import get_provider
from briefing.pipeline import VERIFICATION_BANNER, run_pipeline
from briefing.schedule import EDITIONS, resolve_prompt, today_ist
from briefing.verify import verify, violations_feedback

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def _parse_date(value: str | None) -> date:
    return date.fromisoformat(value) if value else today_ist()


def _report_run_failure(prompt_name: str, day: date, exc: Exception) -> int:
    """A run that cannot produce a briefing must still tell you why.

    Cron would otherwise swallow a traceback into a log nobody reads, and the first
    sign of trouble would be a missing email.
    """
    from briefing.alerts import send_alert

    detail = str(exc)
    hint = ""
    if "RESOURCE_EXHAUSTED" in detail or "429" in detail:
        if "spending cap" in detail:
            hint = "The Gemini project spending cap is exhausted — raise it at https://ai.studio/spend"
        else:
            hint = "Gemini rate limit or quota hit — the next scheduled run should recover."
    elif "PERMISSION_DENIED" in detail or "API key" in detail:
        hint = "Check GEMINI_API_KEY in .env."

    print(f"[FAILED] {prompt_name} for {day}: {type(exc).__name__}", file=sys.stderr)
    print(f"         {detail[:300]}", file=sys.stderr)
    if hint:
        print(f"         {hint}", file=sys.stderr)

    body = f"The {prompt_name} briefing for {day} could not be generated.\n\n{detail[:1500]}"
    if hint:
        body += f"\n\n{hint}"
    if send_alert(f"[Briefing] {prompt_name} {day.isoformat()} — RUN FAILED", body):
        print("[alert] failure email sent", file=sys.stderr)
    return 1


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config()
    day = _parse_date(args.date)

    prompt_name = resolve_prompt(args.edition, day)

    if getattr(args, "model", None):
        provider_name = args.provider or config.get("llm.provider")
        config.data["llm"]["tiers"]["generate"][provider_name] = args.model

    provider = get_provider(config, override=args.provider)
    if provider.name == "stub":
        provider.prompt_name = prompt_name

    out_dir = Path(args.out or config.get("output_dir", "out"))
    payload_path = args.payload or (FIXTURES / f"{prompt_name}_payload.json" if args.fixture else None)

    if payload_path:
        with open(payload_path, encoding="utf-8") as fh:
            payload = json.load(fh)
        try:
            output = generate(config, provider, prompt_name, payload)
        except Exception as exc:
            return _report_run_failure(prompt_name, day, exc)
        result = verify(
            output,
            payload,
            tolerance=config.get("verify.relative_tolerance", 0.001),
            min_magnitude=config.get("verify.min_magnitude", 100),
        )
        for _ in range(config.get("verify.max_regenerations", 1)):
            if result.ok:
                break
            print(f"[verify] {result.summary()}", file=sys.stderr)
            corrected = dict(payload, _correction=violations_feedback(result))
            output = generate(config, provider, prompt_name, corrected)
            result = verify(output, payload)
        if not result.ok:
            output = f"{VERIFICATION_BANNER}\n\n{output}"
        failed_sources: list[str] = []
    else:
        print(f"Running the {prompt_name} pipeline on live data...", file=sys.stderr)
        try:
            run = run_pipeline(config, provider, prompt_name, day, out_dir=out_dir)
        except Exception as exc:
            return _report_run_failure(prompt_name, day, exc)
        output, result, failed_sources = run.output, run.verification, run.failed_sources

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{day.isoformat()}_{prompt_name}.txt"
    out_file.write_text(output, encoding="utf-8")

    print(output)
    print(f"\n[provider] {provider.name}  [prompt] {prompt_name}", file=sys.stderr)
    if failed_sources:
        print(f"[degraded] sources unavailable: {', '.join(failed_sources)}", file=sys.stderr)
    print(f"[verify] {result.summary()}", file=sys.stderr)
    usage = getattr(provider, "usage", None)
    if usage and usage["calls"]:
        print(
            f"[tokens] {usage['calls']} calls, {usage['input_tokens']:,} in / "
            f"{usage['output_tokens']:,} out",
            file=sys.stderr,
        )
    print(f"[written] {out_file}", file=sys.stderr)

    from briefing.alerts import is_configured as email_configured
    from briefing.deliver import telegram

    if args.no_deliver or not (telegram.is_configured() or email_configured()):
        reason = "--no-deliver" if args.no_deliver else "no delivery channel configured in .env"
        print(f"[deliver] skipped ({reason})", file=sys.stderr)
        return 0 if result.ok else 1

    from briefing.deliver import deliver

    delivery = deliver(
        config,
        prompt_name=prompt_name,
        day=day,
        body=output,
        degraded=bool(failed_sources),
        verification_ok=result.ok,
        verification_summary=result.summary(),
        failed_sources=failed_sources,
    )
    if delivery.telegrammed:
        print("[deliver] sent to Telegram", file=sys.stderr)
    if delivery.emailed:
        print("[deliver] emailed", file=sys.stderr)
    if delivery.event_url:
        print(f"[deliver] calendar event created", file=sys.stderr)
    if delivery.archived:
        print("[deliver] archive row appended", file=sys.stderr)
    for error in delivery.errors:
        print(f"[deliver] {error}", file=sys.stderr)
    if delivery.alert_sent:
        print("[alert] failure email sent", file=sys.stderr)

    return 0 if (result.ok and delivery.ok) else 1


def cmd_test_sources(args: argparse.Namespace) -> int:
    from briefing.sources import fetch_all, preview

    config = load_config()
    print("Fetching every source. NSE calls are rate-limited, so this takes ~30-60s.\n")
    results = fetch_all(config, include_news=not args.no_news)

    width = max(len(r.name) for r in results)
    failures = 0
    for result in results:
        status = "OK  " if result.ok else "FAIL"
        if not result.ok:
            failures += 1
        print(f"[{status}] {result.name:<{width}}  {preview(result)}")

    print(f"\n{len(results) - failures}/{len(results)} sources OK")
    if failures:
        print("Failed sources cause their sections to be omitted, not the run to abort.")
    return 0


def cmd_score_news(args: argparse.Namespace) -> int:
    from briefing.fetch import news as news_fetch
    from briefing.fetch import nse as nse_fetch
    from briefing.filter import apply_caps, rule_filter, score_items

    config = load_config()

    print("Fetching headlines and announcements...")
    items: list[dict] = []
    feed = news_fetch.fetch_news(
        domains=config.get("news_domains"), queries=config.get("news_queries", None)
    )
    if feed.ok:
        items.extend(feed.data)
    else:
        print(f"  news feed failed: {feed.error}", file=sys.stderr)

    announcements = nse_fetch.fetch_corporate_announcements(nse_fetch.NSESession())
    if announcements.ok:
        items.extend(announcements.data)
    else:
        print(f"  NSE announcements failed: {announcements.error}", file=sys.stderr)

    if not items:
        print("nothing fetched", file=sys.stderr)
        return 1

    kept_by_rules, dropped = rule_filter(items)
    print(
        f"\nrule gate: {len(items)} fetched -> {len(kept_by_rules)} worth scoring, "
        f"{len(dropped)} dropped as noise"
    )

    provider = get_provider(config, override=args.provider)
    to_score = kept_by_rules[: args.limit] if args.limit else kept_by_rules
    kept, scored = score_items(config, provider, to_score)

    threshold = config.get("scoring.threshold")
    print(f"scorer ({provider.name}): {len(scored)} scored -> {len(kept)} at or above {threshold}\n")

    capped = apply_caps(kept, config.get("caps", {}))
    for category, group in sorted(capped.items()):
        print(f"--- {category} ({len(group)}) ---")
        for item in group:
            headline = (item.get("headline") or item.get("subject") or "")[:80]
            print(f"  [{item['score']:>2}] {headline}  ({item.get('matched_keyword', '-')})")
    if not capped:
        print("(nothing cleared the threshold)")
    return 0


def cmd_analyse(args: argparse.Namespace) -> int:
    from briefing.compute import (
        analyse_option_chain,
        breadth_ratio,
        compute_levels,
        fii_futures_stance,
        rank_sectors,
    )
    from briefing.fetch import macro as macro_fetch
    from briefing.fetch import nse as nse_fetch

    load_config()
    session = nse_fetch.NSESession()

    print("Computing levels and derivatives from live data...\n")

    macro = macro_fetch.fetch_macro()
    if macro.ok:
        for name in ("nifty_50", "bank_nifty"):
            levels = compute_levels(macro.data["history"].get(name, []))
            if not levels:
                continue
            pivots = levels["pivots"]
            print(f"{name}  (from session {levels['reference_session']})")
            print(f"  close {levels['reference_close']}  20-DMA {levels['dma_20']}  50-DMA {levels['dma_50']}")
            print(f"  R2 {pivots['r2']} | R1 {pivots['r1']} | P {pivots['pivot']} | S1 {pivots['s1']} | S2 {pivots['s2']}")
            print(f"  {levels['trend']}\n")
    else:
        print(f"macro failed: {macro.error}\n", file=sys.stderr)

    for symbol in ("NIFTY", "BANKNIFTY"):
        chain = nse_fetch.fetch_option_chain(session, symbol)
        if not chain.ok:
            print(f"{symbol} option chain failed: {chain.error}", file=sys.stderr)
            continue
        analysis = analyse_option_chain(chain.data)
        print(f"{symbol} options  expiry {analysis['expiry']}  underlying {analysis['underlying']}")
        print(f"  PCR {analysis['pcr']} ({analysis['pcr_assessment']})")
        print(f"  call wall {analysis['call_wall']} | put wall {analysis['put_wall']} | max pain {analysis['max_pain']}\n")

    indices = nse_fetch.fetch_indices(session)
    if indices.ok:
        breadth = breadth_ratio(indices.data["breadth"])
        if breadth:
            print(f"breadth  {breadth['advances']} up / {breadth['declines']} down "
                  f"= {breadth['ratio']}  ({breadth['summary']})")
        sectors = rank_sectors(indices.data["sectors"])
        for label in ("outperforming", "underperforming"):
            names = ", ".join(f"{s['name']} {s['percent_change']:+}%" for s in sectors[label])
            print(f"  {label}: {names or '(none)'}")
        print()

    participants = nse_fetch.fetch_participant_oi(session)
    if participants.ok:
        stance = fii_futures_stance(participants.data)
        if stance:
            print(f"FII index futures ({stance['as_of']}): long ratio "
                  f"{stance['long_ratio_percent']}% — {stance['assessment']}")
        else:
            print("FII futures stance: columns not found in participant file", file=sys.stderr)
    return 0


def cmd_refresh_holidays(args: argparse.Namespace) -> int:
    import yaml

    from briefing.fetch.nse import NSESession, fetch_holidays

    result = fetch_holidays(NSESession())
    if not result.ok:
        print(f"could not refresh holidays: {result.error}", file=sys.stderr)
        return 1

    path = Path(__file__).resolve().parent / "holidays.yaml"
    by_year: dict[int, list[str]] = {}
    for day in result.data:
        by_year.setdefault(int(day[:4]), []).append(day)

    header = (
        "# NSE trading holidays, refreshed from the NSE holiday-master API by\n"
        "# `briefing refresh-holidays`. Empty years fall back to a weekday-only check\n"
        "# rather than a guessed list.\n"
    )
    path.write_text(header + yaml.safe_dump(by_year, default_flow_style=False), encoding="utf-8")
    for year, days in sorted(by_year.items()):
        print(f"{year}: {len(days)} trading holidays -> {', '.join(days)}")
    print(f"\n[written] {path}")
    return 0


def cmd_check_google(args: argparse.Namespace) -> int:
    """Verify the service account can reach the folder, sheet and calendar."""
    config = load_config()

    try:
        from briefing.deliver.google_auth import service, service_account_email
    except ImportError as exc:
        print(f"Google client libraries missing: {exc}", file=sys.stderr)
        print("Run: pip install -r requirements.txt", file=sys.stderr)
        return 1

    try:
        email = service_account_email()
    except Exception as exc:
        print(f"[FAIL] credentials: {exc}", file=sys.stderr)
        return 1
    print(f"[OK  ] credentials: {email}\n")

    problems = 0

    sheet_id = config.get("google.sheet_id", "")
    if sheet_id:
        try:
            meta = (
                service("sheets", "v4").spreadsheets()
                .get(spreadsheetId=sheet_id, fields="properties.title").execute()
            )
            print(f"[OK  ] sheet           {meta['properties']['title']}")
        except Exception as exc:
            problems += 1
            print(f"[FAIL] sheet           {type(exc).__name__}: {str(exc)[:120]}")
    else:
        print("[----] sheet           not configured (google.sheet_id)")

    calendar_id = config.get("google.calendar_id", "")
    if calendar_id:
        try:
            # events.list, not calendars.get: the event-level scope cannot read calendar
            # metadata, and this also reports the access role we actually need.
            meta = (
                service("calendar", "v3").events()
                .list(calendarId=calendar_id, maxResults=1).execute()
            )
            role = meta.get("accessRole")
            if role in ("writer", "owner"):
                print(f"[OK  ] calendar        {meta.get('summary')} (role: {role})")
            else:
                problems += 1
                print(
                    f"[FAIL] calendar        {meta.get('summary')} is {role} — needs "
                    "'Make changes to events'"
                )
        except Exception as exc:
            problems += 1
            print(f"[FAIL] calendar        {type(exc).__name__}: {str(exc)[:120]}")
    else:
        print("[----] calendar        not configured (google.calendar_id)")

    from briefing.alerts import is_configured, send_alert
    from briefing.deliver import telegram

    print(f"[{'OK  ' if telegram.is_configured() else '----'}] telegram        "
          f"{'configured' if telegram.is_configured() else 'set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env'}")
    print(f"[{'OK  ' if is_configured() else '----'}] email           "
          f"{'configured' if is_configured() else 'set ALERT_EMAIL_FROM/TO and GMAIL_APP_PASSWORD in .env'}")
    if not (telegram.is_configured() or is_configured()):
        problems += 1
        print("       at least one delivery channel is required")

    if args.test_alert:
        print("\n[....] sending test alert email")
        if send_alert("[Briefing] test alert", "Alerting is configured correctly."):
            print("[OK  ] alert email sent")
        else:
            problems += 1
            print("[FAIL] alert email — check ALERT_EMAIL_FROM/TO and GMAIL_APP_PASSWORD")

    return 1 if problems else 0


def cmd_dry_run(args: argparse.Namespace) -> int:
    args.provider = "stub"
    args.fixture = True
    args.payload = None
    args.out = args.out or "out"
    return cmd_run(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="briefing", description="Daily market briefing agent")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="generate a briefing from live data")
    run.add_argument("--edition", required=True, choices=EDITIONS)
    run.add_argument("--date", help="YYYY-MM-DD (default: today IST)")
    run.add_argument("--provider", help="override llm.provider from config")
    run.add_argument("--model", help="override the generation model, for A/B comparison")
    run.add_argument("--payload", help="path to a JSON payload file")
    run.add_argument("--fixture", action="store_true", help="use the bundled sample payload")
    run.add_argument("--out", help="output directory")
    run.add_argument("--no-deliver", action="store_true", help="generate but do not publish")
    run.set_defaults(func=cmd_run)

    dry = sub.add_parser("dry-run", help="offline end-to-end run on the sample payload")
    dry.add_argument("--edition", required=True, choices=EDITIONS)
    dry.add_argument("--date", help="YYYY-MM-DD (default: today IST)")
    dry.add_argument("--out", help="output directory")
    dry.set_defaults(func=cmd_dry_run)

    test = sub.add_parser("test-sources", help="fetch every source and report OK/FAIL")
    test.add_argument("--no-news", action="store_true", help="skip the Google News queries")
    test.set_defaults(func=cmd_test_sources)

    score = sub.add_parser("score-news", help="fetch, rule-filter and score today's headlines")
    score.add_argument("--provider", help="override llm.provider (use 'stub' for offline)")
    score.add_argument("--limit", type=int, help="only score the first N items")
    score.set_defaults(func=cmd_score_news)

    analyse = sub.add_parser("analyse", help="show computed pivots, DMAs, PCR and OI walls")
    analyse.set_defaults(func=cmd_analyse)

    google = sub.add_parser("check-google", help="verify Google credentials and access")
    google.add_argument("--test-alert", action="store_true", help="also send a test alert email")
    google.set_defaults(func=cmd_check_google)

    holidays = sub.add_parser("refresh-holidays", help="update the NSE holiday calendar")
    holidays.set_defaults(func=cmd_refresh_holidays)

    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
