"""Check the league seasons we've read against Wikipedia's "List of Elgin
City F.C. seasons" (P W D L F A per season), to find what a parser
missed or misread. A development tool; not part of the app.

Usage: venv/bin/python tools/compare_wikipedia.py [history.json.gz]
"""
from __future__ import annotations

import gzip
import json
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from simple_elginfc.core.models import Match  # noqa: E402

CACHE = ROOT / "tools" / ".cache" / "wiki_seasons.json"
URL = ("https://en.wikipedia.org/w/api.php?action=parse&page=List_of_Elgin_City_F.C._seasons"
       "&prop=wikitext&format=json&formatversion=2")
LEAGUES = ("Highland League", "Scottish League", "Banffshire")


def wiki_seasons() -> dict[str, tuple[str, list[int]]]:
    if not CACHE.exists():
        req = urllib.request.Request(URL, headers={"User-Agent": "SimpleElginFC-dev (mikehellyer@gmail.com)"})
        CACHE.write_bytes(urllib.request.urlopen(req, timeout=30).read())
    text = json.loads(CACHE.read_text())["parse"]["wikitext"]
    out = {}
    for chunk in text.split("\n|-")[1:]:
        m = re.search(r"!\s*(\d{4})[–-](\d{2,4})", chunk)
        if not m:
            continue
        season = f"{m.group(1)}-{m.group(2)[-2:]}"
        cells = [c.strip() for c in re.split(r"\n\||\|\|", chunk[m.end():])]
        cells = [c for c in cells if c != ""]
        if len(cells) < 8:
            continue
        league = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", cells[0])
        nums = cells[1:7]
        if all(n.lstrip("-").isdigit() for n in nums):
            out[season] = (league, [int(n) for n in nums])
    return out


def ours(path: Path) -> dict[str, list[int]]:
    matches = [Match.from_dict(d) for d in json.loads(gzip.decompress(path.read_bytes()))["matches"]]
    totals = defaultdict(lambda: [0] * 6)
    for m in matches:
        if not m.played or "abandon" in m.note or "stopped" in m.note or "void" in m.note:
            continue
        if m.competition not in ("Highland League", "Scottish League"):
            continue
        t = totals[m.season]
        t[0] += 1
        t[{"W": 1, "D": 2, "L": 3}[m.result]] += 1
        t[4] += m.elgin_goals
        t[5] += m.opponent_goals
    return totals


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "src" / "simple_elginfc" / "data" / "history.json.gz"
    wiki, mine = wiki_seasons(), ours(path)
    good = bad = 0
    for season in sorted(set(wiki) | set(mine)):
        league, w = wiki.get(season, ("", None))
        o = mine.get(season)
        if w == o:
            good += 1
            continue
        bad += 1
        print(f"{season} {league[:24]:24} wiki {w}  ours {o}")
    print(f"{good} seasons agree, {bad} differ")


if __name__ == "__main__":
    main()
