from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .settings import Settings

H2H_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://h2hggl.com",
    "Referer": "https://h2hggl.com/",
}

LEAGUES = [
    {
        "id": "h2hgg",
        "name": "Esoccer H2H GG League - 8 mins",
        "totalcorner_url": "https://www.totalcorner.com/league/view/37552",
        "fixture_source": "h2h_api",
        "markets": "ou_only",
    },
    {
        "id": "gt",
        "name": "Esoccer GT Leagues - 12 mins",
        "totalcorner_url": "https://www.totalcorner.com/league/view/12985",
        "fixture_source": "totalcorner_live",
        "markets": "1x2_only",
    },
    {
        "id": "battle",
        "name": "Esoccer Battle - 8 mins",
        "totalcorner_url": "https://www.totalcorner.com/league/view/12995",
        "fixture_source": "totalcorner_live",
        "markets": "1x2_only",
    },
    {
        "id": "volta",
        "name": "Esoccer Battle Volta - 6 mins",
        "totalcorner_url": "https://www.totalcorner.com/league/view/38895",
        "fixture_source": "totalcorner_live",
        "markets": "1x2_only",
    },
]

PLAYER_RE = re.compile(r"^(?P<team>.*?)\s*\((?P<player>[^)]+)\)")


@dataclass
class TeamStat:
    player: str
    games: int
    gf: float
    ga: float
    win_pct: float
    draw_pct: float
    over15: float
    over25: float
    over35: float
    recent_form: float
    attacking_strength: float
    defensive_stability: float
    xg_for: float | None
    avg_shots: float | None
    avg_shots_on_goal: float | None
    dangerous_attacks_per_goal: float | None
    elo: float
    source: str


@dataclass
class MatchPick:
    id: str
    league_id: str
    league: str
    market_mode: str
    time: str
    iso_time: str
    room: str
    home_team: str
    away_team: str
    home_player: str
    away_player: str
    home_goals_exp: float
    away_goals_exp: float
    total_goals_exp: float
    p_home: float
    p_draw: float
    p_away: float
    p_over15: float
    p_under15: float
    p_over25: float
    p_under25: float
    p_over35: float
    p_under35: float
    goal_trend_score: float
    winner_score_home: float
    winner_score_away: float
    draw_risk_score: float
    over15_filter: str
    false_over_alert: str
    best_market: str
    best_pick: str
    best_probability: float
    value_score: float
    confidence: str
    sample_quality: str
    risk: str
    argument: str
    notes: str


def load_dashboard(settings: Settings) -> dict:
    now = datetime.now(ZoneInfo(settings.timezone))
    errors: list[str] = []
    totalcorner_pages = _fetch_totalcorner_pages(errors)
    fixtures = _fetch_h2h_upcoming(settings.timezone, errors)
    fixtures.extend(_fetch_totalcorner_live_fixtures(totalcorner_pages, settings.timezone, errors))
    totalcorner_stats = _fetch_totalcorner_stats(totalcorner_pages, errors)
    elo_ratings = _build_elo_ratings(totalcorner_pages)
    for key, rating in elo_ratings.items():
        if key in totalcorner_stats:
            totalcorner_stats[key].elo = rating

    h2h_fixtures = [f for f in fixtures if f["league_id"] == "h2hgg"]
    players = sorted({f["home_player"] for f in h2h_fixtures} | {f["away_player"] for f in h2h_fixtures})
    h2h_stats = _fetch_h2h_stats(players, errors)
    picks = [_analyze_fixture(f, totalcorner_stats, h2h_stats) for f in fixtures]
    picks = [p for p in picks if p is not None]
    picks.sort(key=lambda item: (_sample_rank(item.sample_quality), item.value_score), reverse=True)
    from .calibration import apply_precision_filter

    picks = apply_precision_filter(picks, settings.picks_xlsx)

    return {
        "updated_at": now.isoformat(timespec="seconds"),
        "timezone": settings.timezone,
        "fixture_count": len(fixtures),
        "stat_players_totalcorner": len(totalcorner_stats),
        "stat_players_h2h": len(h2h_stats),
        "leagues": [{"id": item["id"], "name": item["name"], "markets": item["markets"]} for item in LEAGUES],
        "mode": "precision",
        "sources": {
            "fixtures": "H2H GG API for H2H GG; TotalCorner live rows for GT/Battle/Volta",
            "recent_stats": "TotalCorner rolling 48h tables per league",
            "fallback_stats": "H2H GG API participant/fifa/stats when TotalCorner has no recent row",
            "odds": "Manual odds CSV not required yet; missing odds reduce value confidence",
        },
        "errors": errors[:8],
        "matches": [asdict(p) for p in picks],
    }


def _fetch_h2h_upcoming(tz_name: str, errors: list[str]) -> list[dict]:
    url = "https://api-h2h.hudstats.com/v1/schedule/upcoming/fifa"
    try:
        response = requests.get(url, headers=H2H_HEADERS, timeout=20)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"H2H upcoming: {exc}")
        return []

    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    fixtures = []
    for row in data:
        if row.get("isCancelled"):
            continue
        start = _parse_utc(row.get("startDate")).astimezone(tz)
        home_player = _clean(row.get("participantAName"))
        away_player = _clean(row.get("participantBName"))
        if not home_player or not away_player:
            continue
        delta_seconds = (start - now).total_seconds()
        if delta_seconds < -8 * 60 or delta_seconds > 75 * 60:
            continue
        fixtures.append(
            {
                "id": row.get("externalId") or f"{start.isoformat()}-{home_player}-{away_player}",
                "league_id": "h2hgg",
                "league": "Esoccer H2H GG League - 8 mins",
                "market_mode": "ou_only",
                "start": start,
                "room": row.get("streamName") or "",
                "home_team": row.get("teamAName") or "",
                "away_team": row.get("teamBName") or "",
                "home_player": home_player,
                "away_player": away_player,
            }
        )
    return sorted(fixtures, key=lambda item: item["start"])[:40]


def _fetch_totalcorner_pages(errors: list[str]) -> dict[str, str]:
    pages: dict[str, str] = {}
    for league in LEAGUES:
        try:
            response = requests.get(league["totalcorner_url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            response.raise_for_status()
            pages[league["id"]] = response.text
        except Exception as exc:  # noqa: BLE001
            errors.append(f"TotalCorner {league['name']}: {exc}")
    return pages


def _fetch_totalcorner_live_fixtures(pages: dict[str, str], tz_name: str, errors: list[str]) -> list[dict]:
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    fixtures: list[dict] = []
    for league in LEAGUES:
        if league["fixture_source"] != "totalcorner_live":
            continue
        html = pages.get(league["id"])
        if not html:
            continue
        try:
            soup = BeautifulSoup(html, "html.parser")
            tables = soup.select("table")
            if not tables:
                continue
            for row in tables[-1].select("tr"):
                cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
                if len(cols) < 5 or cols[1].lower() == "full":
                    continue
                home_team, home_player = _split_team_player(cols[2])
                away_team, away_player = _split_team_player(cols[4])
                if not home_player or not away_player:
                    continue
                start = _parse_totalcorner_time(cols[0], tz)
                delta_seconds = (start - now).total_seconds()
                if delta_seconds < -8 * 60 or delta_seconds > 75 * 60:
                    continue
                fixtures.append(
                    {
                        "id": f"{league['id']}|{cols[0]}|{home_player}|{away_player}",
                        "league_id": league["id"],
                        "league": league["name"],
                        "market_mode": league["markets"],
                        "start": start,
                        "room": "TotalCorner live",
                        "home_team": home_team,
                        "away_team": away_team,
                        "home_player": home_player,
                        "away_player": away_player,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"TotalCorner live {league['name']}: {exc}")
    return fixtures


def _fetch_h2h_stats(players: list[str], errors: list[str]) -> dict[str, TeamStat]:
    stats: dict[str, TeamStat] = {}
    for player in players:
        url = f"https://api-h2h.hudstats.com/v1/participant/fifa/stats?participant={player}"
        try:
            response = requests.get(url, headers=H2H_HEADERS, timeout=15)
            response.raise_for_status()
            row = response.json()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"H2H stats {player}: {exc}")
            continue
        games = int(row.get("matchesPlayed") or 0)
        if not games:
            continue
        gf = float(row.get("goalsFor") or 0) / games
        ga = float(row.get("goalsAgainst") or 0) / games
        win_pct = float(row.get("matchesWinPct") or 0) / 100
        draw_pct = float(row.get("matchesDrawn") or 0) / games
        over25 = _poisson_over(gf + ga, 2.5)
        stats[player] = TeamStat(
            player=player,
            games=games,
            gf=gf,
            ga=ga,
            win_pct=win_pct,
            draw_pct=draw_pct,
            over15=_poisson_over(gf + ga, 1.5),
            over25=over25,
            over35=_poisson_over(gf + ga, 3.5),
            recent_form=_form_from_sequence(row.get("matchForm") or []),
            attacking_strength=_scale(gf, 0.6, 2.2),
            defensive_stability=_scale(2.2 - ga, 0.4, 2.0),
            xg_for=_to_optional_float(row.get("avgExpectedGoals")),
            avg_shots=_to_optional_float(row.get("avgShots")),
            avg_shots_on_goal=_avg_shots_on_goal(row, games),
            dangerous_attacks_per_goal=None,
            elo=1500.0,
            source="h2h-api",
        )
    return stats


def _fetch_totalcorner_stats(pages: dict[str, str], errors: list[str]) -> dict[str, TeamStat]:
    merged: dict[str, TeamStat] = {}
    for league in LEAGUES:
        html = pages.get(league["id"])
        if not html:
            continue
        try:
            soup = BeautifulSoup(html, "html.parser")
            tables = soup.select("table.stats_table")
            if tables:
                _merge_league_table(tables[0], merged, league["id"])
            if len(tables) > 1:
                _merge_over_table(tables[1], merged, league["id"])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"TotalCorner stats {league['name']}: {exc}")
    return merged


def _build_elo_ratings(pages: dict[str, str]) -> dict[str, float]:
    ratings: dict[str, float] = {}
    for league in LEAGUES:
        html = pages.get(league["id"])
        if not html:
            continue
        matches = _full_results_from_totalcorner(html)
        for home, away, home_goals, away_goals in reversed(matches):
            home_key = _stat_key(league["id"], home)
            away_key = _stat_key(league["id"], away)
            ratings.setdefault(home_key, 1500.0)
            ratings.setdefault(away_key, 1500.0)
            expected_home = 1 / (1 + 10 ** ((ratings[away_key] - ratings[home_key]) / 400))
            if home_goals > away_goals:
                actual_home = 1.0
            elif home_goals == away_goals:
                actual_home = 0.5
            else:
                actual_home = 0.0
            margin = abs(home_goals - away_goals)
            k = 18 + min(margin, 4) * 2
            change = k * (actual_home - expected_home)
            ratings[home_key] += change
            ratings[away_key] -= change
    return ratings


def _full_results_from_totalcorner(html: str) -> list[tuple[str, str, int, int]]:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.select("table")
    if not tables:
        return []
    results: list[tuple[str, str, int, int]] = []
    for row in tables[-1].select("tr"):
        cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        if len(cols) < 5 or cols[1].strip().lower() != "full":
            continue
        _home_team, home_player = _split_team_player(cols[2])
        _away_team, away_player = _split_team_player(cols[4])
        score = re.search(r"(?P<h>\d{1,2})\s*-\s*(?P<a>\d{1,2})", cols[3])
        if home_player and away_player and score:
            results.append((home_player, away_player, int(score.group("h")), int(score.group("a"))))
    return results


def _merge_league_table(table, merged: dict[str, TeamStat], league_id: str) -> None:
    for row in table.select("tr")[1:]:
        cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        if len(cols) < 10:
            continue
        player = _clean(cols[1])
        games = _to_int(cols[2])
        if not player or not games:
            continue
        wins = _to_int(cols[3])
        draws = _to_int(cols[4])
        gf = _to_float(cols[8])
        ga = _to_float(cols[9])
        merged[_stat_key(league_id, player)] = TeamStat(
            player=player,
            games=games,
            gf=gf,
            ga=ga,
            win_pct=wins / games if games else 0,
            draw_pct=draws / games if games else 0,
            over15=_poisson_over(gf + ga, 1.5),
            over25=_poisson_over(gf + ga, 2.5),
            over35=_poisson_over(gf + ga, 3.5),
            recent_form=((wins * 3) + draws) / (games * 3) if games else 0.5,
            attacking_strength=_scale(gf, 0.6, 2.2),
            defensive_stability=_scale(2.2 - ga, 0.4, 2.0),
            xg_for=None,
            avg_shots=None,
            avg_shots_on_goal=None,
            dangerous_attacks_per_goal=_to_float(cols[10]) if len(cols) > 10 else None,
            elo=1500.0,
            source="totalcorner-48h",
        )


def _merge_over_table(table, merged: dict[str, TeamStat], league_id: str) -> None:
    for row in table.select("tr")[1:]:
        cols = [c.get_text(" ", strip=True) for c in row.find_all("td")]
        if len(cols) < 8:
            continue
        player = _clean(cols[1])
        if not player:
            continue
        current = merged.get(_stat_key(league_id, player))
        games = _to_int(cols[2]) or (current.games if current else 0)
        gf = _to_float(cols[3]) if cols[3] else (current.gf if current else 0)
        ga = _to_float(cols[4]) if cols[4] else (current.ga if current else 0)
        merged[_stat_key(league_id, player)] = TeamStat(
            player=player,
            games=games,
            gf=gf,
            ga=ga,
            win_pct=current.win_pct if current else 0,
            draw_pct=current.draw_pct if current else 0,
            over15=_pct(cols[5]),
            over25=_pct(cols[6]),
            over35=_pct(cols[7]),
            recent_form=current.recent_form if current else 0.5,
            attacking_strength=_scale(gf, 0.6, 2.2),
            defensive_stability=_scale(2.2 - ga, 0.4, 2.0),
            xg_for=current.xg_for if current else None,
            avg_shots=current.avg_shots if current else None,
            avg_shots_on_goal=current.avg_shots_on_goal if current else None,
            dangerous_attacks_per_goal=current.dangerous_attacks_per_goal if current else None,
            elo=current.elo if current else 1500.0,
            source="totalcorner-48h",
        )


def _analyze_fixture(fixture: dict, tc_stats: dict[str, TeamStat], h2h_stats: dict[str, TeamStat]) -> MatchPick | None:
    home = tc_stats.get(_stat_key(fixture["league_id"], fixture["home_player"]))
    away = tc_stats.get(_stat_key(fixture["league_id"], fixture["away_player"]))
    if fixture["league_id"] == "h2hgg":
        home = home or h2h_stats.get(fixture["home_player"])
        away = away or h2h_stats.get(fixture["away_player"])
    if not home or not away:
        return None

    home_exp = max(0.05, ((home.gf + away.ga) / 2) * _form_factor(home.win_pct, away.win_pct))
    away_exp = max(0.05, ((away.gf + home.ga) / 2) * _form_factor(away.win_pct, home.win_pct))
    p_home, p_draw, p_away = _poisson_1x2(home_exp, away_exp)
    total_exp = home_exp + away_exp
    p_over15 = _blend(_poisson_over(total_exp, 1.5), (home.over15 + away.over15) / 2)
    p_over25 = _blend(_poisson_over(total_exp, 2.5), (home.over25 + away.over25) / 2)
    p_over35 = _blend(_poisson_over(total_exp, 3.5), (home.over35 + away.over35) / 2)
    goal_trend_score = _goal_trend_score(total_exp, home, away, p_over25)
    winner_score_home = _team_power_score(home, away, is_home=True)
    winner_score_away = _team_power_score(away, home, is_home=False)
    draw_risk_score = _draw_risk_score(winner_score_home, winner_score_away, home, away, p_under25=1 - p_over25)

    sample_quality = _sample_quality(home, away)
    candidates = _recommendation_candidates(
        p_home=p_home,
        p_draw=p_draw,
        p_away=p_away,
        p_over25=p_over25,
        goal_trend_score=goal_trend_score,
        winner_score_home=winner_score_home,
        winner_score_away=winner_score_away,
        draw_risk_score=draw_risk_score,
        sample_quality=sample_quality,
        market_mode=fixture["market_mode"],
    )
    best_market, best_pick, best_probability, value_score = max(candidates, key=lambda item: item[3])
    false_over_alert = _false_over_alert(p_over15, p_over25)
    risk = _risk_label(draw_risk_score, false_over_alert, sample_quality)
    argument = _build_argument(best_pick, goal_trend_score, winner_score_home, winner_score_away, draw_risk_score, p_over15, p_over25, home, away)
    return MatchPick(
        id=fixture["id"],
        league_id=fixture["league_id"],
        league=fixture["league"],
        market_mode=fixture["market_mode"],
        time=fixture["start"].strftime("%H:%M"),
        iso_time=fixture["start"].isoformat(timespec="seconds"),
        room=fixture["room"],
        home_team=fixture["home_team"],
        away_team=fixture["away_team"],
        home_player=home.player,
        away_player=away.player,
        home_goals_exp=round(home_exp, 2),
        away_goals_exp=round(away_exp, 2),
        total_goals_exp=round(total_exp, 2),
        p_home=round(p_home, 4),
        p_draw=round(p_draw, 4),
        p_away=round(p_away, 4),
        p_over15=round(p_over15, 4),
        p_under15=round(1 - p_over15, 4),
        p_over25=round(p_over25, 4),
        p_under25=round(1 - p_over25, 4),
        p_over35=round(p_over35, 4),
        p_under35=round(1 - p_over35, 4),
        goal_trend_score=round(goal_trend_score, 1),
        winner_score_home=round(winner_score_home, 1),
        winner_score_away=round(winner_score_away, 1),
        draw_risk_score=round(draw_risk_score, 1),
        over15_filter="Partido abierto" if p_over15 >= 0.70 else "Filtro sin fuerza",
        false_over_alert=false_over_alert,
        best_market=best_market,
        best_pick=best_pick,
        best_probability=round(best_probability, 4),
        value_score=round(value_score, 1),
        confidence=_confidence_from_value(value_score, sample_quality),
        sample_quality=sample_quality,
        risk=risk,
        argument=argument,
        notes=(
            f"Fixture {fixture['room']}. Stats {home.source}/{away.source}: "
            f"{home.player} MP {home.games}, {home.gf:.1f}GF {home.ga:.1f}GA; "
            f"{away.player} MP {away.games}, {away.gf:.1f}GF {away.ga:.1f}GA"
        ),
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _parse_totalcorner_time(value: str, tz: ZoneInfo) -> datetime:
    now_utc = datetime.now(timezone.utc)
    try:
        month_day, clock = value.split(" ", 1)
        month, day = [int(part) for part in month_day.split("/", 1)]
        hour, minute = [int(part) for part in clock.split(":", 1)]
        parsed_utc = datetime(now_utc.year, month, day, hour, minute, tzinfo=timezone.utc)
        if parsed_utc < now_utc.replace(second=0, microsecond=0) and month < now_utc.month:
            parsed_utc = parsed_utc.replace(year=now_utc.year + 1)
        return parsed_utc.astimezone(tz)
    except Exception:  # noqa: BLE001
        return datetime.now(tz)


def _split_team_player(value: str) -> tuple[str, str]:
    match = PLAYER_RE.search(value)
    if not match:
        return value, ""
    return match.group("team").strip(), _clean(match.group("player"))


def _stat_key(league_id: str, player: str) -> str:
    return f"{league_id}|{_clean(player)}"


def _poisson_1x2(home_exp: float, away_exp: float) -> tuple[float, float, float]:
    home_probs = [_poisson_pmf(home_exp, goals) for goals in range(9)]
    away_probs = [_poisson_pmf(away_exp, goals) for goals in range(9)]
    p_home = p_draw = p_away = 0.0
    for h, hp in enumerate(home_probs):
        for a, ap in enumerate(away_probs):
            p = hp * ap
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
    total = p_home + p_draw + p_away
    return p_home / total, p_draw / total, p_away / total


def _poisson_pmf(expected: float, goals: int) -> float:
    return math.exp(-expected) * expected**goals / math.factorial(goals)


def _poisson_over(expected_goals: float, line: float) -> float:
    threshold = int(math.floor(line))
    under_or_equal = sum(_poisson_pmf(expected_goals, goals) for goals in range(threshold + 1))
    return max(0.0, min(1.0, 1 - under_or_equal))


def _blend(model: float, observed: float) -> float:
    return max(0.0, min(1.0, model * 0.6 + observed * 0.4))


def _goal_trend_score(total_exp: float, home: TeamStat, away: TeamStat, p_over25: float) -> float:
    expected_goals_score = _scale(total_exp, 1.8, 3.8) * 100
    recent_form_goals = _scale(((home.gf + away.gf) + (home.ga + away.ga)) / 2, 1.4, 3.4) * 100
    xg_values = [value for value in [home.xg_for, away.xg_for] if value is not None]
    xg_total = sum(xg_values) if xg_values else total_exp
    xg_score = _scale(xg_total, 1.6, 3.6) * 100
    odds_confirmation = 50.0
    return (
        expected_goals_score * 0.30
        + home.over25 * 100 * 0.20
        + away.over25 * 100 * 0.20
        + recent_form_goals * 0.15
        + xg_score * 0.10
        + odds_confirmation * 0.05
    )


def _team_power_score(team: TeamStat, opponent: TeamStat, is_home: bool) -> float:
    recent_form = team.recent_form * 100
    attacking = team.attacking_strength * 100
    defense = team.defensive_stability * 100
    xg_balance = _scale((team.xg_for or team.gf) - opponent.ga + 1.4, 0.0, 2.8) * 100
    elo_strength = _scale(team.elo - opponent.elo + 160, 0, 320) * 100
    home_away = 56.0 if is_home else 50.0
    standings = team.win_pct * 100
    odds_market_signal = 50.0
    lineup_quality = 50.0
    return (
        recent_form * 0.15
        + attacking * 0.15
        + defense * 0.15
        + xg_balance * 0.10
        + elo_strength * 0.20
        + home_away * 0.10
        + standings * 0.10
        + odds_market_signal * 0.10
        + lineup_quality * 0.05
    )


def _draw_risk_score(home_power: float, away_power: float, home: TeamStat, away: TeamStat, p_under25: float) -> float:
    power_gap = abs(home_power - away_power)
    equality_in_model = max(0.0, 100 - power_gap * 5)
    low_offense = max(0.0, 100 - _scale(home.gf + away.gf, 1.2, 3.6) * 100)
    draw_history = ((home.draw_pct + away.draw_pct) / 2) * 100
    form_balance = max(0.0, 100 - abs(home.recent_form - away.recent_form) * 180)
    odds_equality = 50.0
    return (
        odds_equality * 0.25
        + equality_in_model * 0.20
        + low_offense * 0.20
        + draw_history * 0.15
        + p_under25 * 100 * 0.10
        + form_balance * 0.10
    )


def _recommendation_candidates(
    p_home: float,
    p_draw: float,
    p_away: float,
    p_over25: float,
    goal_trend_score: float,
    winner_score_home: float,
    winner_score_away: float,
    draw_risk_score: float,
    sample_quality: str,
    market_mode: str,
) -> list[tuple[str, str, float, float]]:
    quality_penalty = {"Alta": 0.0, "Media": 8.0, "Baja": 16.0}.get(sample_quality, 16.0)
    candidates: list[tuple[str, str, float, float]] = []

    if market_mode == "ou_only":
        if goal_trend_score >= 72:
            candidates.append(("Over/Under 2.5", "Over 2.5", p_over25, goal_trend_score - quality_penalty))
        elif goal_trend_score >= 60:
            candidates.append(("Over/Under 2.5", "Over 2.5 moderado", p_over25, goal_trend_score - 8 - quality_penalty))
        elif goal_trend_score < 45:
            under_prob = 1 - p_over25
            candidates.append(("Over/Under 2.5", "Under 2.5", under_prob, (100 - goal_trend_score) - quality_penalty))
        else:
            candidates.append(("Over/Under 2.5", "No Bet O/U 2.5", max(p_over25, 1 - p_over25), 35 - quality_penalty))

    if market_mode == "1x2_only":
        edge_home = winner_score_home - winner_score_away
        edge_away = winner_score_away - winner_score_home
        draw_block = 20 if draw_risk_score >= 65 else 0
        if edge_home >= 15 and not (draw_risk_score >= 75 and edge_home < 25):
            candidates.append(("1X2", "Local gana", p_home, 50 + edge_home - draw_block - quality_penalty))
        elif edge_away >= 15 and not (draw_risk_score >= 75 and edge_away < 25):
            candidates.append(("1X2", "Visita gana", p_away, 50 + edge_away - draw_block - quality_penalty))
        elif draw_risk_score >= 65:
            candidates.append(("1X2", "No Bet 1X2", max(p_home, p_draw, p_away), 40 - quality_penalty))
        elif abs(edge_home) < 10:
            candidates.append(("1X2", "No Bet 1X2", max(p_home, p_draw, p_away), 36 - quality_penalty))

    return candidates or [("No Bet", "No Bet precision", max(p_home, p_draw, p_away), 0)]


def _false_over_alert(p_over15: float, p_over25: float) -> str:
    if p_over15 >= 0.70 and p_over25 < 0.55:
        return "Over 1.5 alto, pero Over 2.5 bajo: puede quedarse en 1-2 goles."
    return ""


def _risk_label(draw_risk_score: float, false_over_alert: str, sample_quality: str) -> str:
    risks = []
    if draw_risk_score >= 75:
        risks.append("empate alto")
    elif draw_risk_score >= 65:
        risks.append("empate moderado")
    if false_over_alert:
        risks.append("falso over")
    if sample_quality == "Baja":
        risks.append("muestra baja")
    return ", ".join(risks) if risks else "controlado"


def _build_argument(best_pick: str, goal_trend_score: float, home_power: float, away_power: float, draw_risk: float, p_over15: float, p_over25: float, home: TeamStat, away: TeamStat) -> str:
    if best_pick.startswith("Over 2.5"):
        goal_text = f"goalTrendScore {goal_trend_score:.1f}: tendencia suficiente para 3+ goles"
    elif best_pick == "Under 2.5":
        goal_text = f"goalTrendScore {goal_trend_score:.1f}: tendencia baja para 3+ goles"
    elif best_pick.startswith("No Bet O/U"):
        goal_text = f"goalTrendScore {goal_trend_score:.1f}: zona dudosa para O/U 2.5"
    else:
        goal_text = f"Over 1.5 {p_over15:.0%} y Over 2.5 {p_over25:.0%} solo confirman contexto de goles"

    winner_text = f"Power local {home_power:.1f} vs visita {away_power:.1f}; riesgo empate {draw_risk:.1f}"
    data_text = f"{home.player} {home.gf:.1f}GF/{home.ga:.1f}GA, {away.player} {away.gf:.1f}GF/{away.ga:.1f}GA"
    return f"{goal_text}. {winner_text}. Base: {data_text}. Cuotas reales no cargadas; confianza de value limitada."


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _form_factor(player_win: float, opponent_win: float) -> float:
    return max(0.82, min(1.18, 1 + (player_win - opponent_win) * 0.18))


def _confidence_from_value(value_score: float, sample_quality: str) -> str:
    if sample_quality == "Baja":
        return "Baja"
    if value_score >= 68:
        return "Alta"
    if value_score >= 55:
        return "Media"
    return "Baja"


def _sample_quality(home: TeamStat, away: TeamStat) -> str:
    if home.source == "totalcorner-48h" and away.source == "totalcorner-48h":
        if min(home.games, away.games) >= 12:
            return "Alta"
        if min(home.games, away.games) >= 5:
            return "Media"
        return "Baja"
    if min(home.games, away.games) >= 500:
        return "Media"
    return "Baja"


def _sample_rank(value: str) -> int:
    return {"Alta": 3, "Media": 2, "Baja": 1}.get(value, 0)


def _clean(value: str | None) -> str:
    return " ".join((value or "").strip().upper().split())


def _to_int(value: str) -> int:
    try:
        return int(value.replace(",", ""))
    except ValueError:
        return 0


def _to_float(value: str) -> float:
    try:
        return float(value.replace("%", "").replace(",", ""))
    except ValueError:
        return 0.0


def _pct(value: str) -> float:
    return _to_float(value) / 100


def _to_optional_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg_shots_on_goal(row: dict, games: int) -> float | None:
    total = _to_optional_float(row.get("totalShotsOnGoal"))
    if total is None or games <= 0:
        return None
    return total / games


def _form_from_sequence(values: list[str]) -> float:
    if not values:
        return 0.5
    points = 0
    for value in values[:5]:
        if str(value).lower().startswith("w"):
            points += 3
        elif str(value).lower().startswith("d"):
            points += 1
    return points / (len(values[:5]) * 3)
