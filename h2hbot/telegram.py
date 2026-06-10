from __future__ import annotations

import requests

from .models import Pick


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> None:
        if not self.enabled:
            print(text)
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        response = requests.post(
            url,
            json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=20,
        )
        response.raise_for_status()


def format_picks(picks: list[Pick], warnings: list[str]) -> str:
    if not picks:
        base = "Sin picks fuertes para los proximos 10 min."
    else:
        lines = ["Mejores picks H2H GG League proximos 10 min:"]
        for idx, pick in enumerate(picks, start=1):
            fixture = pick.fixture
            odds = f" | cuota {pick.book_odds:.2f}" if pick.book_odds else " | cuota pendiente"
            edge = f" | edge {pick.edge:.1%}" if pick.edge is not None else ""
            lines.append(
                f"{idx}. {fixture.match_time:%H:%M} {fixture.home} vs {fixture.away} - "
                f"{pick.selection} {pick.line} goles | prob {pick.probability:.1%} | "
                f"fair {pick.fair_odds:.2f}{odds}{edge} | est {pick.est_goals:.2f}"
            )
        base = "\n".join(lines)
    if warnings:
        base += "\n\nAlertas fuente:\n" + "\n".join(f"- {item}" for item in warnings[:4])
    return base


def format_report(summary: dict[str, float | int]) -> str:
    return (
        "Reporte rendimiento H2H GG:\n"
        f"Total: {summary['total']}\n"
        f"Ganadas: {summary['won']} | Perdidas: {summary['lost']} | Pendientes: {summary['pending']}\n"
        f"Win rate: {summary['win_rate']:.1%}\n"
        f"Profit: {summary['profit_units']:.2f} u"
    )
