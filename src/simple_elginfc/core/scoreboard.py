"""Live scores across Scotland: each league's games today (or, when it has
none, its last results and next fixtures) with its table, from BBC Sport."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Callable, Optional

from simple_elginfc.core.sources import bbc

# (key, name, BBC tournament)
LEAGUES = [
    ("premiership", "Premiership", "scottish-premiership"),
    ("championship", "Championship", "scottish-championship"),
    ("league-one", "League One", "scottish-league-one"),
    ("league-two", "League Two", "scottish-league-two"),
    ("highland", "Highland League", "scottish-highland-league"),
    ("lowland-east", "Lowland League East", "scottish-lowland-league-east"),
    ("lowland-west", "Lowland League West", "scottish-lowland-league-west"),
]


@dataclass
class LeagueBoard:
    key: str
    name: str
    today: list[dict] = field(default_factory=list)  # bbc.Game as dicts
    recent: list[dict] = field(default_factory=list)  # the last matchday's results, when none today
    upcoming: list[dict] = field(default_factory=list)  # the next matchday's games, when none today
    table_name: str = ""
    table: list[dict] = field(default_factory=list)  # bbc.TableRow as dicts
    playing: list[str] = field(default_factory=list)  # teams the table marks as playing now
    updated: float = 0.0

    def games(self, which: str = "today") -> list[bbc.Game]:
        return [bbc.Game(**g) for g in getattr(self, which)]

    def rows(self) -> list[bbc.TableRow]:
        return [bbc.TableRow(**r) for r in self.table]

    @property
    def live_count(self) -> int:
        return sum(1 for g in self.today if g["state"] == bbc.LIVE)

    @property
    def any_today(self) -> bool:
        return bool(self.today)


def _month_end(d: date) -> date:
    return bbc.month_end(d)


def _matchday(games: list[bbc.Game], last: bool, span_days: int = 3) -> list[bbc.Game]:
    """The latest (or next) round of games: the date nearest now with any,
    and the others within a few days of it (a Friday game and the
    Saturday ones, say)."""
    dates = sorted({g.date for g in games if g.date})
    if not dates:
        return []
    anchor = date.fromisoformat(dates[-1] if last else dates[0])
    keep = {d for d in dates if abs((date.fromisoformat(d) - anchor).days) < span_days}
    return [g for g in games if g.date in keep]


def fetch_league(key: str, today: Optional[date] = None, get: Callable = None,
                 with_table: bool = True, around: bool = True) -> LeagueBoard:
    """One league's board. `around`: when there are no games today, also
    find the last results and the next fixtures (BBC's feed only answers
    a day, a month, the month so far or the rest of the month)."""
    from simple_elginfc.core.live import get_json

    get = get or get_json
    today = today or date.today()
    _, name, slug = next(league for league in LEAGUES if league[0] == key)
    board = LeagueBoard(key, name)
    games_today = bbc.parse_games(get(bbc.tournament_scores_url(slug, today, today, today)))
    board.today = [asdict(g) for g in games_today]
    still_to_come = any(g.state != bbc.DONE for g in games_today)
    if around and not games_today:
        first = today.replace(day=1)
        past: list[bbc.Game] = []
        if today > first:
            past = bbc.parse_games(get(bbc.tournament_scores_url(slug, first, today - timedelta(days=1), today)))
        if not past:
            previous = (first - timedelta(days=1)).replace(day=1)
            past = bbc.parse_games(get(bbc.tournament_scores_url(slug, previous, _month_end(previous), today)))
        board.recent = [asdict(g) for g in _matchday([g for g in past if g.state == bbc.DONE], last=True)]
    if around and not still_to_come:
        future: list[bbc.Game] = []
        if today < _month_end(today):
            future = bbc.parse_games(get(bbc.tournament_scores_url(slug, today + timedelta(days=1), _month_end(today), today)))
        if not future:
            following = _month_end(today) + timedelta(days=1)
            future = bbc.parse_games(get(bbc.tournament_scores_url(slug, following, _month_end(following), today)))
        board.upcoming = [asdict(g) for g in _matchday([g for g in future if g.state == bbc.PRE], last=False)]
    if with_table:
        payload = get(bbc.table_url(slug))
        board.table_name, rows = bbc.parse_table(payload)
        board.table = [asdict(r) for r in rows]
        board.playing = sorted(bbc.parse_playing(payload))
    board.updated = time.time()
    return board


def fetch_all(previous: Optional[dict[str, LeagueBoard]] = None, today: Optional[date] = None,
              get: Callable = None) -> dict[str, LeagueBoard]:
    """Every league. A league that fails keeps its last board."""
    boards = dict(previous or {})
    for key, _, _ in LEAGUES:
        try:
            boards[key] = fetch_league(key, today, get)
        except (OSError, ValueError, KeyError):
            pass
    if not boards:
        raise OSError("BBC Sport didn't answer")
    return boards


def any_live(boards: dict[str, LeagueBoard]) -> bool:
    return any(b.live_count for b in boards.values())


def kickoff_soon(boards: dict[str, LeagueBoard], now_utc) -> bool:
    """A game today that's about to start or should still be on."""
    from datetime import datetime

    for b in boards.values():
        for g in b.games("today"):
            if g.state == bbc.LIVE:
                return True
            if g.state == bbc.PRE and g.kickoff:
                try:
                    k = datetime.fromisoformat(g.kickoff.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if k - timedelta(minutes=10) <= now_utc <= k + timedelta(hours=2, minutes=30):
                    return True
    return False
