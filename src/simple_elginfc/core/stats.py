"""Records worked out from the matches: head-to-heads, seasons, and the
club's biggest days."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

from simple_elginfc.core.models import AWAY, DRAW, HOME, LOSS, NEUTRAL, WIN, Match
from simple_elginfc.core.teams import matches_query, related


def counts(m: Match) -> bool:
    """Does this game count in the records? (Not friendlies, or unplayed,
    abandoned or void games; those still show in the lists.)"""
    if m.competition == "Friendly":
        return False
    note = m.note.lower()
    if "result stood" in note or "result stands" in note:
        return m.played
    return m.played and not any(w in note for w in ("abandon", "stopped", "void", "rescinded"))


@dataclass
class Record:
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0

    def add(self, m: Match) -> None:
        self.played += 1
        self.won += m.result == WIN
        self.drawn += m.result == DRAW
        self.lost += m.result == LOSS
        self.goals_for += m.elgin_goals
        self.goals_against += m.opponent_goals

    @property
    def win_percent(self) -> float:
        return 100.0 * self.won / self.played if self.played else 0.0

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


def record(matches: Iterable[Match]) -> Record:
    r = Record()
    for m in matches:
        if counts(m):
            r.add(m)
    return r


def _margin(m: Match) -> tuple[int, int]:
    return (m.elgin_goals - m.opponent_goals, m.elgin_goals)


@dataclass
class HeadToHead:
    opponent: str  # what was searched for, or the one club found
    clubs: list[str]  # every club it covers
    matches: list[Match]  # oldest first
    overall: Record
    home: Record
    away: Record
    neutral: Record
    by_competition: dict[str, Record]
    biggest_win: Optional[Match] = None
    biggest_defeat: Optional[Match] = None
    highest_scoring: Optional[Match] = None
    best_attendance: Optional[Match] = None
    first: Optional[Match] = None
    last: Optional[Match] = None
    next_fixture: Optional[Match] = None
    longest_unbeaten: int = 0
    longest_winless: int = 0
    current_run: str = ""  # "3 wins", "unbeaten in 5"…
    top_scorers: list[tuple[str, int]] = field(default_factory=list)  # Elgin's, where known


def opponents_matching(all_opponents: Iterable[str], query: str) -> list[str]:
    return sorted(o for o in all_opponents if matches_query(o, query))


def head_to_head(matches: list[Match], clubs: Iterable[str], include_related: bool = False) -> HeadToHead:
    clubs = set(clubs)
    if include_related:
        clubs = set().union(*(related(c) for c in clubs)) if clubs else clubs
    games = sorted((m for m in matches if m.opponent in clubs), key=lambda m: m.sort_key)
    played = [m for m in games if counts(m)]
    by_venue = {HOME: Record(), AWAY: Record(), NEUTRAL: Record()}
    by_comp: dict[str, Record] = defaultdict(Record)
    for m in played:
        by_venue[m.venue].add(m)
        by_comp[m.competition].add(m)
    h = HeadToHead(
        opponent=", ".join(sorted(clubs)),
        clubs=sorted(clubs),
        matches=games,
        overall=record(played),
        home=by_venue[HOME],
        away=by_venue[AWAY],
        neutral=by_venue[NEUTRAL],
        by_competition=dict(sorted(by_comp.items(), key=lambda kv: -kv[1].played)),
    )
    if played:
        wins = [m for m in played if m.result == WIN]
        losses = [m for m in played if m.result == LOSS]
        h.biggest_win = max(wins, key=_margin) if wins else None
        h.biggest_defeat = min(losses, key=lambda m: (m.elgin_goals - m.opponent_goals, -m.opponent_goals)) if losses else None
        h.highest_scoring = max(played, key=lambda m: (m.elgin_goals + m.opponent_goals, m.elgin_goals))
        with_crowd = [m for m in played if m.attendance]
        h.best_attendance = max(with_crowd, key=lambda m: m.attendance) if with_crowd else None
        h.first, h.last = played[0], played[-1]
        h.longest_unbeaten = _longest(played, lambda m: m.result != LOSS)
        h.longest_winless = _longest(played, lambda m: m.result != WIN)
        h.current_run = current_run(played)
    upcoming = [m for m in games if not m.played and m.date and not m.note]
    h.next_fixture = upcoming[0] if upcoming else None
    scorers: dict[str, int] = defaultdict(int)
    for m in played:
        for s in m.elgin_scorers:
            name, goals = scorer_goals(s)
            scorers[name] += goals
    h.top_scorers = sorted(scorers.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return h


def scorer_goals(entry: str) -> tuple[str, int]:
    """"J. MacIver 9', 51'" -> ("J. MacIver", 2). Own goals count for no one."""
    if "'" not in entry:
        return entry, 1
    name, _, times = entry.partition(" ")
    while times and not times[0].isdigit():
        word, _, times = times.partition(" ")
        name = f"{name} {word}"
    goals = [t for t in times.split(",") if "og" not in t]
    return name.strip(), len(goals)


def _longest(matches: list[Match], keeps_going) -> int:
    best = run = 0
    for m in matches:
        run = run + 1 if keeps_going(m) else 0
        best = max(best, run)
    return best


def current_run(matches: list[Match]) -> str:
    """How things stand from the most recent game back: "3 wins in a row",
    "unbeaten in 5", "4 without a win"."""
    if not matches:
        return ""
    recent = list(reversed(matches))
    same = 0
    for m in recent:
        if m.result != recent[0].result:
            break
        same += 1
    word = {WIN: ("win", "wins"), DRAW: ("draw", "draws"), LOSS: ("defeat", "defeats")}[recent[0].result]
    if same > 1:
        return f"{same} {word[1]} in a row"
    unbeaten = next((i for i, m in enumerate(recent) if m.result == LOSS), len(recent))
    winless = next((i for i, m in enumerate(recent) if m.result == WIN), len(recent))
    if unbeaten > 1:
        return f"unbeaten in {unbeaten}"
    if winless > 1:
        return f"{winless} without a win"
    return f"last game a {word[0]}"


@dataclass
class SeasonSummary:
    season: str
    league: Record
    all: Record
    competitions: list[str]
    top_scorer: str = ""


def season_summaries(matches: list[Match]) -> list[SeasonSummary]:
    by_season: dict[str, list[Match]] = defaultdict(list)
    for m in matches:
        by_season[m.season].append(m)
    out = []
    for season, games in sorted(by_season.items()):
        league = [m for m in games if m.competition in ("Highland League", "Scottish League")]
        out.append(SeasonSummary(season, record(league), record(games), sorted({m.competition for m in games})))
    return out


@dataclass
class ClubRecords:
    total: Record
    biggest_wins: list[Match]
    biggest_defeats: list[Match]
    best_attendances: list[Match]
    most_played: list[tuple[str, int]]


def club_records(matches: list[Match], top: int = 5) -> ClubRecords:
    played = [m for m in matches if counts(m)]
    per_opponent: dict[str, int] = defaultdict(int)
    for m in played:
        per_opponent[m.opponent] += 1
    return ClubRecords(
        total=record(played),
        biggest_wins=sorted((m for m in played if m.result == WIN), key=_margin, reverse=True)[:top],
        biggest_defeats=sorted((m for m in played if m.result == LOSS),
                               key=lambda m: (m.elgin_goals - m.opponent_goals, -m.opponent_goals))[:top],
        best_attendances=sorted((m for m in played if m.attendance), key=lambda m: -m.attendance)[:top],
        most_played=sorted(per_opponent.items(), key=lambda kv: -kv[1])[:top],
    )
