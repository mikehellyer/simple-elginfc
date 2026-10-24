"""Elgin City's results from ESPN's (unofficial, keyless) site API.

ESPN has every league and cup game from 2001-02, with the ground and the
attendance, from its team schedule: one call per competition per season.
For 2002-03 to 2005-06 the league schedule answers 500, so those seasons
are read a day at a time from the scoreboard instead. ESPN stopped
keeping Scotland's lower leagues up to date in 2025, so BBC Sport
(sources.bbc) covers recent seasons.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from simple_elginfc.core.models import AWAY, HOME, NEUTRAL, Match, season_of
from simple_elginfc.core.teams import canonical

ELGIN_ID = "419"
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# ESPN league -> our competition name
SCHEDULE_LEAGUES = {
    "sco.4": "Scottish League",
    "sco.3": "Scottish League",  # only ever the League One play-offs
    "sco.tennents": "Scottish Cup",
    "sco.cis": "League Cup",
    "sco.challenge": "Challenge Cup",
}
SCOREBOARD_SEASONS = [(date(y, 7, 1), date(y + 1, 6, 15)) for y in range(2002, 2006)]

_DONE = {"STATUS_FULL_TIME", "STATUS_FINAL", "STATUS_FINAL_AET", "STATUS_FINAL_PEN", "STATUS_FINAL_ET"}


def schedule_url(league: str, season_year: int) -> str:
    return f"{BASE}/{league}/teams/{ELGIN_ID}/schedule?season={season_year}&fixture=false"


def scoreboard_url(league: str, day: date) -> str:
    return f"{BASE}/{league}/scoreboard?dates={day:%Y%m%d}"


def _competition(event: dict, league_name: str) -> tuple[str, str]:
    """(competition, round)."""
    stage = ((event.get("seasonType") or {}).get("name") or "").strip()
    league = (league_name or (event.get("league") or {}).get("name") or "").lower()
    if "challenge" in league:
        comp = "Challenge Cup"
    elif "league cup" in league or "slc" in league:
        comp = "League Cup"
    elif "scottish cup" in league:
        comp = "Scottish Cup"
    else:
        comp = "Scottish League"
    rnd = ""
    if stage and stage != "Regular Season" and not any(w in stage for w in ("Division", "League One", "League Two", "/")):
        rnd = stage.title() if stage.isupper() else stage
        rnd = rnd.replace("Scottish League Cup - ", "").replace("Group Stage", "Group stage")
        if comp == "Scottish League":
            comp = "Play-offs"
    return comp, rnd


def _score(side: dict) -> Optional[int]:
    score = side.get("score")
    if isinstance(score, dict):
        score = score.get("displayValue", score.get("value"))
    try:
        return int(float(score))
    except (TypeError, ValueError):
        return None


def summary_url(league: str, event_id: str) -> str:
    return f"{BASE}/{league}/summary?event={event_id}"


def parse_event(event: dict, league_name: str = "", league: str = "") -> Optional[Match]:
    comps = event.get("competitions") or []
    if not comps:
        return None
    c = comps[0]
    sides = c.get("competitors") or []
    elgin = next((s for s in sides if str(s.get("id") or (s.get("team") or {}).get("id")) == ELGIN_ID), None)
    other = next((s for s in sides if s is not elgin), None)
    if not elgin or not other:
        return None
    status = ((c.get("status") or event.get("status") or {}).get("type") or {}).get("name", "")
    try:
        day = date.fromisoformat((event.get("date") or "")[:10])
    except ValueError:
        return None
    comp, rnd = _competition(event, league_name)
    venue = HOME if elgin.get("homeAway") == "home" else AWAY
    if c.get("neutralSite"):
        venue = NEUTRAL
    notes = [n.get("headline", "") for n in c.get("notes") or [] if n.get("headline")]
    if status == "STATUS_FINAL_AET":
        notes.insert(0, "aet")
    if elgin.get("shootoutScore") is not None and other.get("shootoutScore") is not None:
        notes.append(f"{int(elgin['shootoutScore'])}-{int(other['shootoutScore'])} on penalties")
    played = status in _DONE
    if status == "STATUS_ABANDONED":
        notes.append("abandoned")
    if status in ("STATUS_POSTPONED", "STATUS_CANCELED"):
        return None  # it'll be played (and listed) another day
    team = other.get("team") or {}
    attendance = c.get("attendance") or None
    return Match(
        season=season_of(day),
        competition=comp,
        opponent=canonical(team.get("displayName") or team.get("location") or "?"),
        venue=venue,
        date=day.isoformat(),
        round=rnd,
        elgin_goals=_score(elgin) if played else None,
        opponent_goals=_score(other) if played else None,
        ground=((c.get("venue") or {}).get("fullName") or "").strip(),
        attendance=int(attendance) if attendance else None,
        note="; ".join(notes),
        source="espn",
        ref=f"espn:{league}:{event.get('id')}" if league and event.get("id") else "",
    )


def parse_schedule(payload: dict, league: str = "") -> list[Match]:
    """A team schedule or a scoreboard; only Elgin's games are kept."""
    league_name = ""
    leagues = payload.get("leagues") or []
    if leagues:
        league_name = leagues[0].get("name", "")
    found = []
    for event in payload.get("events") or []:
        match = parse_event(event, league_name or ((event.get("league") or {}).get("name") or ""), league)
        if match:
            found.append(match)
    return found


def _initial(name: str) -> str:
    """"Kyle Macleod" -> "K. Macleod", like BBC Sport writes scorers."""
    parts = name.split()
    return f"{parts[0][0]}. {' '.join(parts[1:])}" if len(parts) > 1 else name


def parse_summary(payload: dict) -> Optional[tuple[int, int, list[str], list[str]]]:
    """(Elgin's goals, the other side's, Elgin's scorers, theirs) from a
    game's key events, or None if ESPN has no events for it.

    ESPN's schedule shows a 0-0 for some games it never got the score of
    (most of the second half of 2015-16), but its key events are right."""
    events = payload.get("keyEvents")
    if not events:
        return None
    goals = {True: 0, False: 0}
    scorers: dict[bool, dict[str, list[str]]] = {True: {}, False: {}}
    for e in events:
        if not e.get("scoringPlay"):
            continue
        if ((e.get("period") or {}).get("number") or 0) >= 5:  # a penalty shoot-out
            continue
        kind = ((e.get("type") or {}).get("text") or "").lower()
        ours = str((e.get("team") or {}).get("id")) == ELGIN_ID
        goals[ours] += 1
        who = ((e.get("participants") or [{}])[0].get("athlete") or {}).get("displayName") or "?"
        minute = ((e.get("clock") or {}).get("displayValue") or "").strip()
        if "penalty" in kind:
            minute += " pen"
        elif "own goal" in kind:
            minute += " og"
        scorers[ours].setdefault(_initial(who), []).append(minute.strip())
    listed = {side: [f"{name} {', '.join(times)}".strip() for name, times in scorers[side].items()] for side in (True, False)}
    return goals[True], goals[False], listed[True], listed[False]


def apply_summary(match: Match, summary: Optional[tuple[int, int, list[str], list[str]]]) -> None:
    """Correct the score (where the schedule's is short) and add the scorers."""
    if summary is None or not match.played:
        return
    ours, theirs, our_scorers, their_scorers = summary
    if ours + theirs >= match.elgin_goals + match.opponent_goals:
        match.elgin_goals, match.opponent_goals = ours, theirs
    if ours + theirs == match.elgin_goals + match.opponent_goals:
        match.elgin_scorers, match.opponent_scorers = our_scorers, their_scorers
