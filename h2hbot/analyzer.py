from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta

from .models import Fixture, Pick, PlayerStats, Result


def build_stats(results: list[Result], now: datetime, lookback_hours: int) -> dict[str, PlayerStats]:
    cutoff = now - timedelta(hours=lookback_hours)
    rows: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for result in results:
        if result.match_time and result.match_time < cutoff:
            continue
        rows[result.home].append((result.home_goals, result.away_goals))
        rows[result.away].append((result.away_goals, result.home_goals))

    stats: dict[str, PlayerStats] = {}
    for player, games in rows.items():
        if not games:
            continue
        gf = sum(item[0] for item in games) / len(games)
        ga = sum(item[1] for item in games) / len(games)
        over25 = sum(1 for gf_i, ga_i in games if gf_i + ga_i > 2.5) / len(games)
        stats[player] = PlayerStats(player=player, games=len(games), gf=gf, ga=ga, over25_rate=over25)
    return stats


def make_picks(
    fixtures: list[Fixture],
    results: list[Result],
    odds_rows: list[dict[str, str]],
    odds_lookup,
    now: datetime,
    lookahead_minutes: int,
    lookback_hours: int,
    min_probability: float,
    min_edge: float,
    max_picks: int,
) -> list[Pick]:
    stats = build_stats(results, now, lookback_hours)
    upcoming = [
        fixture
        for fixture in fixtures
        if now <= fixture.match_time <= now + timedelta(minutes=lookahead_minutes)
    ]
    picks: list[Pick] = []
    for fixture in upcoming:
        home = stats.get(fixture.home)
        away = stats.get(fixture.away)
        if not home or not away or home.games < 3 or away.games < 3:
            continue
        est_goals = ((home.gf + away.ga) / 2) + ((away.gf + home.ga) / 2)
        model_prob = poisson_over_probability(est_goals, 2.5)
        blended_prob = (model_prob * 0.65) + (((home.over25_rate + away.over25_rate) / 2) * 0.35)
        fair_odds = 1 / blended_prob if blended_prob > 0 else 0
        book_odds = odds_lookup(odds_rows, fixture, "over_goals", 2.5)
        edge = (book_odds * blended_prob - 1) if book_odds else None
        if blended_prob < min_probability:
            continue
        if edge is not None and edge < min_edge:
            continue
        picks.append(
            Pick(
                fixture=fixture,
                market="over_goals",
                line=2.5,
                selection="OVER",
                probability=blended_prob,
                fair_odds=fair_odds,
                book_odds=book_odds,
                edge=edge,
                est_goals=est_goals,
                notes=(
                    f"{fixture.home}: {home.gf:.2f} GF/{home.ga:.2f} GA, "
                    f"{fixture.away}: {away.gf:.2f} GF/{away.ga:.2f} GA"
                ),
            )
        )
    return sorted(picks, key=_pick_rank, reverse=True)[:max_picks]


def poisson_over_probability(expected_goals: float, line: float) -> float:
    # For O2.5, P(total >= 3) using Poisson lambda.
    threshold = int(math.floor(line))
    cdf = sum(math.exp(-expected_goals) * expected_goals**k / math.factorial(k) for k in range(threshold + 1))
    return max(0.0, min(1.0, 1 - cdf))


def _pick_rank(pick: Pick) -> float:
    edge = pick.edge if pick.edge is not None else 0
    return pick.probability + edge
