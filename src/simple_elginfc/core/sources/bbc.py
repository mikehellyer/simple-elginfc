"""BBC Sport: Elgin City's results, fixtures and goalscorers since 2020,
the League Two table, and the club's news feed.

The scores feed is the one BBC Sport's own pages poll. It only answers
the ranges those pages ask for (a whole month, the month so far, the
rest of the month, or one day), and has nothing before January 2020.
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional
from xml.etree import ElementTree

from simple_elginfc.core.models import AWAY, HOME, Match, season_of
from simple_elginfc.core.teams import canonical

TEAM_URN = "urn:bbc:sportsdata:football:team:elgin-city"
BASE = "https://web-cdn.api.bbci.co.uk/wc-poll-data/container"
NEWS_URL = "https://feeds.bbci.co.uk/sport/football/teams/elgin-city/rss.xml"
FIRST_MONTH = date(2020, 1, 1)

LEAGUES = {
    "scottish-league-two": "Scottish League Two",
    "scottish-league-one": "Scottish League One",
}
PRE, LIVE, DONE = "pre", "live", "done"
_STATES = {"PreEvent": PRE, "MidEvent": LIVE, "PostEvent": DONE}


def month_end(d: date) -> date:
    following = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return following - timedelta(days=1)


def scores_url(start: date, end: date, today: date) -> str:
    query = urllib.parse.urlencode({"selectedEndDate": end.isoformat(), "selectedStartDate": start.isoformat(),
                                    "todayDate": today.isoformat(), "urn": TEAM_URN})
    return f"{BASE}/sport-data-scores-fixtures?{query}"


def table_url(league: str = "scottish-league-two") -> str:
    urn = f"urn:bbc:sportsdata:football:tournament:{league}"
    return f"{BASE}/football-table?{urllib.parse.urlencode({'tournamentOrTeamUrn': urn})}"


def current_ranges(today: date) -> list[tuple[date, date]]:
    """What to ask for to cover last month, this month and next month."""
    first = today.replace(day=1)
    previous = (first - timedelta(days=1)).replace(day=1)
    following = month_end(today) + timedelta(days=1)
    ranges = [(previous, month_end(previous)), (first, today)]
    if today < month_end(today):
        ranges.append((today + timedelta(days=1), month_end(today)))
    ranges.append((following, month_end(following)))
    return ranges


def _competition(label: str) -> tuple[str, str]:
    """"Scotland - Scottish Cup - 2nd Round" -> ("Scottish Cup", "2nd Round")."""
    parts = [p.strip() for p in label.split(" - ")]
    if parts and parts[0] in ("Scotland", "World", "Europe", "England"):
        parts = parts[1:]
    if parts and "friendl" in parts[0].lower():
        return "Friendly", ""
    name = parts[0] if parts else ""
    rnd = " - ".join(parts[1:])
    lowered = name.lower()
    if "premiership play-off" in lowered or "play-off" in lowered:
        return "Play-offs", rnd or name
    if lowered.startswith("scottish league") or lowered in ("league two", "league one"):
        return "Scottish League", rnd
    if "challenge cup" in lowered:
        return "Challenge Cup", rnd
    if "league cup" in lowered or "premier sports cup" in lowered:
        return "League Cup", rnd
    if "scottish cup" in lowered:
        return "Scottish Cup", rnd
    return name, rnd


def _scorers(side: dict) -> list[str]:
    out = []
    for action in side.get("actions") or []:
        if action.get("actionType") != "goal":
            continue
        name = action.get("playerName") or "?"
        times = []
        for a in action.get("actions") or []:
            t = ((a.get("timeLabel") or {}).get("value") or "").strip()
            kind = a.get("type", "")
            if kind == "Penalty":
                t += " pen"
            elif kind == "Own Goal":
                t += " og"
            times.append(t.strip())
        out.append(f"{name} {', '.join(times)}".strip())
    return out


def _is_elgin(side: dict) -> bool:
    return side.get("urn") == TEAM_URN or (side.get("fullName") or "").strip() == "Elgin City"


def _int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Event:
    match: Match
    state: str  # PRE, LIVE or DONE
    kickoff: str  # ISO date-time, UTC
    status: str  # "FT", "HT", "62'", "Postponed"…


def parse_events(payload: dict) -> list[Event]:
    found = []
    for group in payload.get("eventGroups") or []:
        for sub in group.get("secondaryGroups") or []:
            for e in sub.get("events") or []:
                event = _parse_event(e)
                if event:
                    found.append(event)
    return found


def _parse_event(e: dict) -> Optional[Event]:
    home, away = e.get("home") or {}, e.get("away") or {}
    if not home or not away or _is_elgin(home) == _is_elgin(away):
        return None
    elgin_home = _is_elgin(home)
    elgin, other = (home, away) if elgin_home else (away, home)
    raw_status = e.get("status") or ""
    state = _STATES.get(raw_status, PRE)
    label = ((e.get("periodLabel") or {}).get("value") or (e.get("statusComment") or {}).get("value") or "").strip()
    comment = ((e.get("statusComment") or {}).get("value") or "").strip()
    try:
        day = date.fromisoformat(((e.get("date") or {}).get("isoDate") or e.get("startDateTime") or "")[:10])
    except ValueError:
        return None
    comp, rnd = _competition(e.get("eventGroupingLabel") or "")
    notes = []
    if raw_status not in _STATES and label:  # postponed, abandoned…
        notes.append(label)
        state = DONE if "abandon" in label.lower() else PRE
    if comment.upper() in ("AET", "AFTER EXTRA TIME"):
        notes.append("aet")
    pens = (_int((elgin.get("runningScores") or {}).get("penaltyShootout")),
            _int((other.get("runningScores") or {}).get("penaltyShootout")))
    if None not in pens:
        notes.append(f"{pens[0]}-{pens[1]} on penalties")
    has_score = state in (LIVE, DONE) and _int(elgin.get("score")) is not None
    ht_e = _int((elgin.get("runningScores") or {}).get("halftime"))
    ht_o = _int((other.get("runningScores") or {}).get("halftime"))
    match = Match(
        season=season_of(day),
        competition=comp,
        opponent=canonical(other.get("fullName") or other.get("shortName") or "?"),
        venue=HOME if elgin_home else AWAY,
        date=day.isoformat(),
        round=rnd,
        elgin_goals=_int(elgin.get("score")) if has_score else None,
        opponent_goals=_int(other.get("score")) if has_score else None,
        note="; ".join(notes),
        elgin_scorers=_scorers(elgin),
        opponent_scorers=_scorers(other),
        half_time=f"{ht_e}-{ht_o}" if ht_e is not None and ht_o is not None and state != PRE else "",
        source="bbc",
    )
    return Event(match, state, e.get("startDateTime") or "", label)


def parse_scores(payload: dict) -> list[Match]:
    """Finished games only (for the history)."""
    return [ev.match for ev in parse_events(payload) if ev.state == DONE and ev.match.played]


@dataclass
class TableRow:
    rank: int
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    points: int
    form: str  # "WWDLW", most recent last


def parse_table(payload: dict) -> tuple[str, list[TableRow]]:
    for tournament in payload.get("tournaments") or []:
        for stage in tournament.get("stages") or []:
            for rnd in stage.get("rounds") or []:
                rows = []
                for p in sorted(rnd.get("participants") or [], key=lambda p: p.get("rank") or 999):
                    form = "".join((f.get("value") or "?")[:1].upper() for f in (p.get("formGuide") or [])
                                   if isinstance(f, dict))
                    rows.append(TableRow(
                        rank=int(p.get("rank") or len(rows) + 1),
                        team=canonical(p.get("name") or p.get("shortName") or "?"),
                        played=int(p.get("matchesPlayed") or 0), won=int(p.get("wins") or 0),
                        drawn=int(p.get("draws") or 0), lost=int(p.get("losses") or 0),
                        goals_for=int(p.get("goalsScoredFor") or 0), goals_against=int(p.get("goalsScoredAgainst") or 0),
                        points=int(p.get("points") or 0), form=form[-5:]))
                if rows:
                    return tournament.get("name") or "League table", rows
    return "", []


@dataclass
class NewsItem:
    title: str
    summary: str
    link: str
    published: str  # as the feed gives it (RFC 822)
    image: str = ""


def parse_news(data: bytes) -> list[NewsItem]:
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return []
    items = []
    media = "{http://search.yahoo.com/mrss/}"
    for item in root.iter("item"):
        thumb = item.find(f"{media}thumbnail")
        items.append(NewsItem(
            title=(item.findtext("title") or "").strip(),
            summary=(item.findtext("description") or "").strip(),
            link=(item.findtext("link") or "").strip(),
            published=(item.findtext("pubDate") or "").strip(),
            image=thumb.get("url", "") if thumb is not None else "",
        ))
    return items
