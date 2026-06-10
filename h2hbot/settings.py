from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_FIXTURE_URLS = "https://api-h2h.hudstats.com/v1/schedule/upcoming/fifa"
DEFAULT_TOTALCORNER_URLS = "https://www.totalcorner.com/league/view/37552"


def _csv_env(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    timezone: str
    fixture_urls: list[str]
    totalcorner_urls: list[str]
    odds_csv: Path
    picks_xlsx: Path
    loop_minutes: int
    lookahead_minutes: int
    result_lookback_hours: int
    max_picks_per_run: int
    min_probability: float
    min_edge: float


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        timezone=os.getenv("TIMEZONE", "America/Mexico_City"),
        fixture_urls=_csv_env("FIXTURE_URLS", DEFAULT_FIXTURE_URLS),
        totalcorner_urls=_csv_env("TOTALCORNER_URLS", DEFAULT_TOTALCORNER_URLS),
        odds_csv=Path(os.getenv("ODDS_CSV", "data/odds.csv")),
        picks_xlsx=Path(os.getenv("PICKS_XLSX", "data/picks_history.xlsx")),
        loop_minutes=int(os.getenv("LOOP_MINUTES", "10")),
        lookahead_minutes=int(os.getenv("LOOKAHEAD_MINUTES", "10")),
        result_lookback_hours=int(os.getenv("RESULT_LOOKBACK_HOURS", "48")),
        max_picks_per_run=int(os.getenv("MAX_PICKS_PER_RUN", "3")),
        min_probability=float(os.getenv("MIN_PROBABILITY", "0.56")),
        min_edge=float(os.getenv("MIN_EDGE", "0.03")),
    )
