"""Scottish Cup ties from the Football Club History Database (fchd.info).

One page per season from 1946-47 to 2015-16: <h2> round headings, then
"<li>Elgin City   3-1 Albion Rovers" (home side first). FCHD gives no
dates, so these ties carry their season and round only.
"""
from __future__ import annotations

import html as htmllib
import re

from simple_elginfc.core.models import AWAY, HOME, Match
from simple_elginfc.core.sources.sfha import is_elgin
from simple_elginfc.core.teams import canonical

COMPETITION = "Scottish Cup"

_ROUND_RE = re.compile(r"<h2>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
_TIE_RE = re.compile(r"<li>\s*(.+?)\s+(\d{1,2})-(\d{1,2})\s+(.+?)\s*(?:\((.*?)\))?\s*(?=<|$)", re.MULTILINE)


def season_url(season: str) -> str:
    return f"https://fchd.info/cups/scottishcup{season}.htm"


def _round_name(text: str) -> str:
    text = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", text))).strip()
    words = {"One": "1", "Two": "2", "Three": "3", "Four": "4", "Five": "5", "Six": "6"}
    text = re.sub(r"\bRound (One|Two|Three|Four|Five|Six)\b", lambda m: f"Round {words[m.group(1)]}", text)
    return text.replace("Replays", "replay").replace("Replay", "replay")


def parse_season(page: str, season: str) -> list[Match]:
    found = []
    pieces = _ROUND_RE.split(page)
    # pieces: [before, round1, body1, round2, body2, …]
    for i in range(1, len(pieces) - 1, 2):
        rnd = _round_name(pieces[i])
        for m in _TIE_RE.finditer(pieces[i + 1]):
            home, hg, ag, away, note = m.groups()
            home, away = htmllib.unescape(home).strip(), htmllib.unescape(away).strip()
            if is_elgin(home) == is_elgin(away):
                continue
            elgin_home = is_elgin(home)
            found.append(Match(
                season=season,
                competition=COMPETITION,
                opponent=canonical(away if elgin_home else home),
                venue=HOME if elgin_home else AWAY,
                round=rnd,
                elgin_goals=int(hg) if elgin_home else int(ag),
                opponent_goals=int(ag) if elgin_home else int(hg),
                note=htmllib.unescape(note or "").strip(),
                source="fchd",
            ))
    return found
