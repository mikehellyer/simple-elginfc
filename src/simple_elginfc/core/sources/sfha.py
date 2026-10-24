"""The Scottish Football Historical Results Archive (sfha.org.uk).

Its pages are Word documents saved as HTML, written for reading, not for
machines, in two layouts:

- League seasons (and Highland League Cup sections) as a grid: one row per
  home side, one column per away side, each cell "5 Oct 4-1".
- Cup seasons as running text under a "1968-69 North of Scotland Cup"
  heading, round headings ("Semi-final", "Final at Station Park, Nairn")
  and one line per tie: "22 Mar Caledonian v Elgin City 1-2".

Both are read here into Matches for Elgin City. The archive asks that
it's acknowledged wherever its results are used, which the app does.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from simple_elginfc.core.models import AWAY, ELGIN, HOME, NEUTRAL, Match
from simple_elginfc.core.sources.htmlblocks import Block, read_blocks
from simple_elginfc.core.teams import canonical

BASE_URL = "http://sfha.org.uk/"
# page -> the competition its results are for when a heading doesn't say
PAGES = {
    "highlandleagueresults.htm": "Highland League",
    "highlandleaguecup.htm": "Highland League Cup",
    "highlandcups.htm": "North of Scotland Cup",
    "scotqualcup.htm": "Scottish Qualifying Cup",
    "elginshirecharity.htm": "Elginshire Charity Cup",
    "elgindistrictcup.htm": "Elgin District Cup",
}

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(?:Jan|Feb|Mar|Apr|May|June?|July?|Aug|Sept?|Oct|Nov|Dec)[a-z]*\.?"
_NAME = r"[A-Z][A-Za-z'&.()\-/ ]{1,48}?"
_SCORE = r"(\d{1,2})\s*-\s*(\d{1,2})"

MATCH_RE = re.compile(
    rf"(?:\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MON})\s+)?"
    rf"\b({_NAME})\s+v\.?\s+({_NAME})\s+{_SCORE}(?![\d-])"
    r"(\s*\(?(?:aet|a\.e\.t\.?|after extra time)\)?)?"
    r"((?:,?\s*\(?\d{1,2}-\d{1,2} (?:on )?pen[a-z]*\)?)|(?:,?\s*\(?[\w\s]{0,6}?(?:won|lost) \d{1,2}-\d{1,2} on pen[a-z]*\)?))?"
    r"(\s*(?:abandoned|stopped|declared void|void|result (?:stood|stands)|match (?:stood|rescinded))[^|]{0,60})?"
)
GRID_CELL_RE = re.compile(rf"(?:(\d{{1,2}})\s+({_MON})\s+)?{_SCORE}(?![\d-])")
HEADING_RE = re.compile(
    r"\b(1[89]\d\d|20\d\d)\s*[-/]\s*(\d{2}|\d{4})\s+"
    r"((?:[A-Z][\w'&.]*|of|and|the|&)(?:\s+(?:[A-Z][\w'&.]*|of|and|the|&))*)")
_COMPETITION_WORDS = ("Cup", "League", "Shield", "Trophy", "Championship", "Tournament", "Competition", "Medals", "Rosebowl")
ROUND_RE = re.compile(
    r"\b(Preliminary round|Qualifying round|(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh) round|"
    r"Round (?:One|Two|Three|Four|Five|Six|\d)|Quarter[- ]finals?|Semi[- ]finals?|Final|Decider|Play-off|"
    r"Championship play-off)(\s+(?:second |2nd )?replays?)?(?:\s+at\s+([^|]{3,60}?)(?=\s+\d{1,2}\s+" + _MON + r"|\s*$|\s+[A-Z][a-z]+ v ))?",
    re.IGNORECASE)


def is_elgin(name: str) -> bool:
    name = name.strip()
    # (the club was "Elgin City United" in the early 1900s)
    return name in ("Elgin City", "Elgin", "City (Elgin)", "Elgin C", "Elgin City United")


def heading_competition(words: str) -> Optional[str]:
    """"North of Scotland Cup First round" -> "North of Scotland Cup";
    None if the words don't name a competition."""
    parts = words.split()
    while parts and parts[-1] not in _COMPETITION_WORDS:
        parts.pop()
    return " ".join(parts) or None


def season_year(season: str, month: int) -> int:
    """Seasons run from about July to June."""
    start = int(season[:4])
    return start if month >= 7 else start + 1


def make_date(season: str, day: Optional[str], month: Optional[str]) -> Optional[str]:
    if not (day and month):
        return None
    m = MONTHS.get(month[:3].lower())
    if not m:
        return None
    try:
        return date(season_year(season, m), m, int(day)).isoformat()
    except ValueError:
        return None


def _season(start: str, end: str) -> str:
    return f"{start}-{end[-2:]}"


@dataclass
class _Context:
    page_competition: str
    season: str = ""
    competition: str = ""
    round: str = ""
    ground: str = ""
    found: list[Match] = field(default_factory=list)


def _match_for_elgin(ctx: _Context, home: str, away: str, hg: int, ag: int, day: Optional[str],
                     month: Optional[str], note: str = "") -> Optional[Match]:
    home, away = home.strip(), away.strip()
    if is_elgin(home) == is_elgin(away):  # neither, or a typo'd both
        return None
    if not ctx.season:
        return None
    elgin_home = is_elgin(home)
    venue = HOME if elgin_home else AWAY
    if ctx.ground and ctx.round.lower().startswith(("final", "semi")):
        venue = NEUTRAL if "elgin" not in ctx.ground.lower() and "borough briggs" not in ctx.ground.lower() else HOME
    return Match(
        season=ctx.season,
        competition=ctx.competition or ctx.page_competition,
        opponent=canonical(away if elgin_home else home),
        venue=venue,
        date=make_date(ctx.season, day, month),
        round=ctx.round,
        elgin_goals=hg if elgin_home else ag,
        opponent_goals=ag if elgin_home else hg,
        ground=ctx.ground if venue == NEUTRAL else "",
        note=note,
        source="sfha",
    )


def _scan_text(ctx: _Context, text: str) -> None:
    """Headings, rounds and ties in one run of text, in the order they come.

    The text is cut at each heading and round first, and ties are read
    only between them, so a round running straight into a tie
    ("Semi-final Elgin City v Nairn County 7-4") isn't read as a team."""
    marks = []
    for m in HEADING_RE.finditer(text):
        comp = heading_competition(m.group(3))
        if comp:
            # the heading ends with the competition's name: "Second round" after it is a round
            marks.append((m.start(), m.start(3) + len(comp), "heading", m))
    for m in ROUND_RE.finditer(text):
        if not any(s <= m.start() < e for s, e, _, _ in marks):
            marks.append((m.start(), m.end(), "round", m))
    marks.sort(key=lambda e: e[0])
    position = 0
    for start, end, kind, m in marks:
        if start < position:
            continue
        _scan_ties(ctx, text[position:start])
        if kind == "heading":
            ctx.season = _season(m.group(1), m.group(2))
            ctx.competition = heading_competition(m.group(3)) or ""
            ctx.round, ctx.ground = "", ""
        else:
            name = m.group(1)[0].upper() + m.group(1)[1:].lower()
            replay = (m.group(2) or "").strip().lower()
            ctx.round = f"{name} {replay}" if replay else name
            ctx.ground = (m.group(3) or "").strip(" ,.")
        position = end
    _scan_ties(ctx, text[position:])


def _scan_ties(ctx: _Context, text: str) -> None:
    for m in MATCH_RE.finditer(text):
        day, month, home, away, hg, ag, aet, pens, extra = m.groups()
        notes = [s.strip(" ,()") for s in (aet, pens, extra) if s and s.strip(" ,()")]
        match = _match_for_elgin(ctx, home, away, int(hg), int(ag), day, month, "; ".join(notes))
        if match:
            ctx.found.append(match)


def _is_grid(table: list[list[str]]) -> bool:
    if len(table) < 3:
        return False
    header = table[0]
    teams = table[1:]
    width = len(header)
    if width < 3 or len(teams) < width - 1:
        return False
    rows = teams[: width - 1]
    return all(len(r) >= width and r[0] and not GRID_CELL_RE.fullmatch(r[0]) for r in rows) and any(
        GRID_CELL_RE.search(c) for r in rows for c in r[1:])


def _read_grid(ctx: _Context, table: list[list[str]]) -> None:
    width = len(table[0])
    rows = table[1:width]
    names = [r[0] for r in rows]
    for i, row in enumerate(rows):
        for j, cell in enumerate(row[1:width]):
            if i == j or j >= len(names):
                continue
            home, away = names[i], names[j]
            if not (is_elgin(home) or is_elgin(away)):
                continue
            for m in GRID_CELL_RE.finditer(cell):
                day, month, hg, ag = m.groups()
                match = _match_for_elgin(ctx, home, away, int(hg), int(ag), day, month)
                if match:
                    ctx.found.append(match)


def parse_page(html: str, page_competition: str) -> list[Match]:
    ctx = _Context(page_competition)
    for block in read_blocks(html):
        _read_block(ctx, block)
    return dedupe(ctx.found)


def _read_block(ctx: _Context, block: Block) -> None:
    if isinstance(block, str):
        _scan_text(ctx, block)
    elif _is_grid(block):
        # a heading can sit in the grid's corner cell ("1964-65 Highland League Cup District 3")
        _scan_text(ctx, block[0][0])
        _read_grid(ctx, block)
        for row in block[len(block[0]):]:  # rows under the grid: notes, deciders
            for cell in row:
                _scan_text(ctx, cell)
    else:
        for row in block:
            for cell in row:
                _scan_text(ctx, cell)


def dedupe(matches: list[Match]) -> list[Match]:
    """The same tie read twice (a grid and a note under it) is kept once."""
    seen = set()
    out = []
    for m in matches:
        key = (m.season, m.competition, m.opponent, m.date, m.venue, m.elgin_goals, m.opponent_goals)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out
