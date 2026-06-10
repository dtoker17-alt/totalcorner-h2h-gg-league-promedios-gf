from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Fixture:
    match_time: datetime
    home: str
    away: str
    league: str = "H2H GG League - 8 mins"
    source: str = ""

    @property
    def key(self) -> str:
        return f"{self.match_time:%Y%m%d%H%M}|{self.home.upper()}|{self.away.upper()}"


@dataclass(frozen=True)
class Result:
    match_time: datetime | None
    home: str
    away: str
    home_goals: int
    away_goals: int
    source: str = ""

    @property
    def total_goals(self) -> int:
        return self.home_goals + self.away_goals


@dataclass(frozen=True)
class PlayerStats:
    player: str
    games: int
    gf: float
    ga: float
    over25_rate: float


@dataclass(frozen=True)
class Pick:
    fixture: Fixture
    market: str
    line: float
    selection: str
    probability: float
    fair_odds: float
    book_odds: float | None
    edge: float | None
    est_goals: float
    notes: str

    @property
    def id(self) -> str:
        return f"{self.fixture.key}|{self.market}|{self.selection}|{self.line}"
