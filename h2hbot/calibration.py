from __future__ import annotations

from pathlib import Path

from .data_service import MatchPick
from .training import TrainingStore


def apply_precision_filter(picks: list[MatchPick], history_path: Path) -> list[MatchPick]:
    performance = _performance_by_group(history_path)
    filtered = []
    for pick in picks:
        keep, reason = _passes_precision(pick, performance)
        if keep:
            filtered.append(pick)
        else:
            pick.risk = _append_reason(pick.risk, reason)
            pick.best_pick = "No Bet precision"
            pick.best_market = "No Bet"
            pick.value_score = min(pick.value_score, 34.0)
            pick.confidence = "Baja"
            filtered.append(pick)
    return sorted(filtered, key=lambda item: (_pick_rank(item), item.value_score), reverse=True)


def _passes_precision(pick: MatchPick, performance: dict[tuple[str, str], dict[str, float]]) -> tuple[bool, str]:
    if pick.best_pick.startswith("No Bet"):
        return False, "no bet"
    if pick.sample_quality != "Alta":
        return False, "muestra no alta"
    if "moderado" in pick.best_pick.lower():
        return False, "senal moderada"

    perf = performance.get((pick.league_id, pick.best_market))
    if perf and perf["resolved"] >= 5 and perf["win_rate"] < 0.55:
        if pick.value_score < 85:
            return False, f"historial bajo {perf['win_rate']:.0%}"
    if perf and perf["resolved"] >= 5 and perf["win_rate"] < 0.70:
        if pick.value_score < 88:
            return False, f"buscando 70%, exige value 88 por historial {perf['win_rate']:.0%}"

    if pick.league_id == "h2hgg":
        if pick.best_market != "Over/Under 2.5":
            return False, "h2hgg solo ou"
        if pick.best_pick == "Over 2.5":
            return (pick.goal_trend_score >= 76 and pick.value_score >= 72, "over h2h no extremo")
        if pick.best_pick == "Under 2.5":
            return (pick.goal_trend_score <= 28 and pick.value_score >= 68 and not pick.false_over_alert, "under h2h no extremo")
        return False, "h2hgg mercado no valido"

    if pick.market_mode == "1x2_only" and pick.best_market != "1X2":
        return False, "liga secundaria solo 1x2"

    if pick.best_market == "1X2":
        edge = abs(pick.winner_score_home - pick.winner_score_away)
        return (edge >= 18 and pick.draw_risk_score < 58 and pick.value_score >= 68, "1x2 sin edge")

    return False, "mercado desconocido"


def _performance_by_group(history_path: Path) -> dict[tuple[str, str], dict[str, float]]:
    try:
        summary = TrainingStore(history_path).summary()
    except Exception:  # noqa: BLE001
        return {}
    output: dict[tuple[str, str], dict[str, float]] = {}
    for league_id, market, _total, won, lost, _pending, win_rate in summary["groups"]:
        resolved = int(won) + int(lost)
        output[(str(league_id), str(market))] = {"resolved": resolved, "win_rate": float(win_rate)}
    return output


def _append_reason(risk: str, reason: str) -> str:
    if not risk or risk == "controlado":
        return f"filtrado precision: {reason}"
    return f"{risk}, filtrado precision: {reason}"


def _pick_rank(pick: MatchPick) -> int:
    if pick.best_pick.startswith("No Bet"):
        return 0
    if pick.confidence == "Alta":
        return 3
    if pick.confidence == "Media":
        return 2
    return 1
