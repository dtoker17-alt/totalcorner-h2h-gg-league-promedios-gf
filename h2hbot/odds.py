from __future__ import annotations

import csv
from pathlib import Path

from .models import Fixture


def load_odds(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def find_odds(rows: list[dict[str, str]], fixture: Fixture, market: str, line: float) -> float | None:
    home = fixture.home.upper()
    away = fixture.away.upper()
    for row in rows:
        if (row.get("home", "").upper(), row.get("away", "").upper()) != (home, away):
            continue
        if row.get("market", "").lower() != market.lower():
            continue
        try:
            row_line = float(row.get("line", "0"))
            odds = float(row.get("odds", "0"))
        except ValueError:
            continue
        if abs(row_line - line) < 0.001 and odds > 1:
            return odds
    return None
