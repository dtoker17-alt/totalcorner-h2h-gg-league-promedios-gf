from __future__ import annotations

import argparse
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .analyzer import make_picks
from .odds import find_odds, load_odds
from .scrapers import scrape_fixtures, scrape_results
from .settings import load_settings
from .storage import PickStore
from .telegram import Telegram, format_picks, format_report
from .training import run_training_cycle


def run_once(send_report: bool = False) -> None:
    settings = load_settings()
    now = datetime.now(ZoneInfo(settings.timezone))
    telegram = Telegram(settings.telegram_bot_token, settings.telegram_chat_id)
    store = PickStore(settings.picks_xlsx)

    fixtures, fixture_errors = scrape_fixtures(settings.fixture_urls, settings.timezone)
    results, result_errors = scrape_results(settings.totalcorner_urls + settings.fixture_urls, settings.timezone)
    data_warnings = []
    if not fixtures:
        data_warnings.append("no se extrajeron fixtures proximos de las fuentes configuradas")
    if not results:
        data_warnings.append("no se extrajeron resultados/stats de las fuentes configuradas")
    settled = store.settle(results, now)
    odds_rows = load_odds(settings.odds_csv)
    picks = make_picks(
        fixtures=fixtures,
        results=results,
        odds_rows=odds_rows,
        odds_lookup=find_odds,
        now=now,
        lookahead_minutes=settings.lookahead_minutes,
        lookback_hours=settings.result_lookback_hours,
        min_probability=settings.min_probability,
        min_edge=settings.min_edge,
        max_picks=settings.max_picks_per_run,
    )
    saved = store.append_new(picks, now)
    warnings = data_warnings + fixture_errors + result_errors
    telegram.send(format_picks(saved, warnings))
    if settled or send_report:
        telegram.send(format_report(store.summary()))


def settle_only() -> None:
    settings = load_settings()
    now = datetime.now(ZoneInfo(settings.timezone))
    results, errors = scrape_results(settings.totalcorner_urls + settings.fixture_urls, settings.timezone)
    store = PickStore(settings.picks_xlsx)
    settled = store.settle(results, now)
    telegram = Telegram(settings.telegram_bot_token, settings.telegram_chat_id)
    text = f"Resultados actualizados: {settled} picks liquidados."
    if errors:
        text += "\nAlertas fuente:\n" + "\n".join(f"- {item}" for item in errors[:4])
    telegram.send(text)
    telegram.send(format_report(store.summary()))


def report_only() -> None:
    settings = load_settings()
    store = PickStore(settings.picks_xlsx)
    Telegram(settings.telegram_bot_token, settings.telegram_chat_id).send(format_report(store.summary()))


def train_only() -> None:
    settings = load_settings()
    result = run_training_cycle(settings)
    summary = result["summary"]["overall"]
    print(
        "Entrenamiento:\n"
        f"Picks nuevos: {result['added']}\n"
        f"Liquidados: {result['settled']}\n"
        f"Total: {summary['total']} | WON: {summary['won']} | LOST: {summary['lost']} | "
        f"Pendientes: {summary['pending']} | Win rate: {summary['win_rate']:.1%}"
    )


def loop() -> None:
    settings = load_settings()
    while True:
        try:
            run_once(send_report=True)
        except Exception as exc:  # noqa: BLE001 - keep daemon alive and notify.
            Telegram(settings.telegram_bot_token, settings.telegram_chat_id).send(f"Error bot H2H GG: {exc}")
        time.sleep(settings.loop_minutes * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="H2H GG League eSoccer Telegram bot")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run-once")
    sub.add_parser("loop")
    sub.add_parser("settle")
    sub.add_parser("report")
    sub.add_parser("train")
    args = parser.parse_args()

    if args.command == "run-once":
        run_once()
    elif args.command == "loop":
        loop()
    elif args.command == "settle":
        settle_only()
    elif args.command == "report":
        report_only()
    elif args.command == "train":
        train_only()
