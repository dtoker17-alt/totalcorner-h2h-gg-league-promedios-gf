from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .models import Fixture, Result

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
    )
}

TEAM_RE = re.compile(r"(?P<team>[A-Za-z .'-]+)\s*\((?P<player>[A-Za-z0-9_ .'-]+)\)")
SCORE_RE = re.compile(r"(?P<hscore>\d{1,2})\s*[-:x]\s*(?P<ascore>\d{1,2})", re.I)
TIME_RE = re.compile(r"\b(?P<hour>\d{1,2}):(?P<minute>\d{2})\b")


def fetch_html(url: str, timeout: int = 20) -> str:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return response.text


def player_name(raw_team: str) -> str:
    match = TEAM_RE.search(raw_team)
    if match:
        return clean_name(match.group("player"))
    value = raw_team
    if "(" in value and ")" in value:
        value = value.split("(", 1)[1].split(")", 1)[0]
    return clean_name(value)


def clean_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    value = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", value)
    return value.upper()


def parse_clock(value: str, now: datetime) -> datetime | None:
    match = TIME_RE.search(value)
    if not match:
        return None
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate < now - timedelta(hours=12):
        candidate += timedelta(days=1)
    if candidate > now + timedelta(hours=18):
        candidate -= timedelta(days=1)
    return candidate


def scrape_fixtures(urls: list[str], tz_name: str) -> tuple[list[Fixture], list[str]]:
    now = datetime.now(ZoneInfo(tz_name))
    fixtures: list[Fixture] = []
    errors: list[str] = []
    for url in urls:
        try:
            html = fetch_html(url)
            fixtures.extend(_fixtures_from_html(html, now, url))
        except Exception as exc:  # noqa: BLE001 - reported to operator.
            errors.append(f"fixtures {url}: {exc}")
    return _dedupe_fixtures(fixtures), errors


def scrape_results(urls: list[str], tz_name: str) -> tuple[list[Result], list[str]]:
    now = datetime.now(ZoneInfo(tz_name))
    results: list[Result] = []
    errors: list[str] = []
    for url in urls:
        try:
            html = fetch_html(url)
            results.extend(_results_from_html(html, now, url))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"results {url}: {exc}")
    return _dedupe_results(results), errors


def _fixtures_from_html(html: str, now: datetime, source: str) -> list[Fixture]:
    soup = BeautifulSoup(html, "html.parser")
    text_lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
    fixtures: list[Fixture] = []

    # Works for public book pages that render: Team A Team B Today HH:MM.
    for idx, line in enumerate(text_lines):
        dt = parse_clock(line, now)
        if not dt or dt < now - timedelta(minutes=5):
            continue
        window = " ".join(text_lines[max(0, idx - 4) : idx + 1])
        teams = TEAM_RE.findall(window)
        if len(teams) >= 2:
            home = clean_name(teams[-2][1])
            away = clean_name(teams[-1][1])
            if home and away and home != away:
                fixtures.append(Fixture(dt, home, away, source=source))

    # Table fallback: inspect row text.
    for row in soup.select("tr"):
        row_text = " ".join(row.get_text(" ", strip=True).split())
        dt = parse_clock(row_text, now)
        teams = TEAM_RE.findall(row_text)
        if dt and len(teams) >= 2 and dt >= now - timedelta(minutes=5):
            fixtures.append(Fixture(dt, clean_name(teams[0][1]), clean_name(teams[1][1]), source=source))
    return fixtures


def _results_from_html(html: str, now: datetime, source: str) -> list[Result]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[Result] = []
    candidates = [" ".join(row.get_text(" ", strip=True).split()) for row in soup.select("tr")]
    if not candidates:
        candidates = [" ".join(line.split()) for line in soup.get_text("\n").splitlines()]

    for text in candidates:
        score = SCORE_RE.search(text)
        teams = TEAM_RE.findall(text)
        if not score or len(teams) < 2:
            continue
        match_time = parse_clock(text, now)
        results.append(
            Result(
                match_time=match_time,
                home=clean_name(teams[0][1]),
                away=clean_name(teams[1][1]),
                home_goals=int(score.group("hscore")),
                away_goals=int(score.group("ascore")),
                source=source,
            )
        )
    return results


def _dedupe_fixtures(fixtures: list[Fixture]) -> list[Fixture]:
    seen: set[str] = set()
    unique: list[Fixture] = []
    for fixture in sorted(fixtures, key=lambda item: item.match_time):
        if fixture.key not in seen:
            seen.add(fixture.key)
            unique.append(fixture)
    return unique


def _dedupe_results(results: list[Result]) -> list[Result]:
    seen: set[str] = set()
    unique: list[Result] = []
    for result in results:
        key = f"{result.match_time}|{result.home}|{result.away}|{result.home_goals}-{result.away_goals}"
        if key not in seen:
            seen.add(key)
            unique.append(result)
    return unique
