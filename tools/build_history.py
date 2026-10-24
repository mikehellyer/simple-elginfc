"""Builds the match history bundled with the app:
src/simple_elginfc/data/history.json.gz.

Reads every source once (downloads are kept in tools/.cache, so a re-run
is quick and kind to the sites), merges them, and writes the result. The
app itself only ever tops this up with the current season.

Usage: venv/bin/python tools/build_history.py [--refresh]
  --refresh  download everything again instead of using the cache
"""
from __future__ import annotations

import gzip
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from simple_elginfc.core import history  # noqa: E402
from simple_elginfc.core.models import Match  # noqa: E402
from simple_elginfc.core.sources import bbc, espn, fchd, sfha  # noqa: E402

CACHE = ROOT / "tools" / ".cache"
OUT = ROOT / "src" / "simple_elginfc" / "data" / "history.json.gz"
REFRESH = "--refresh" in sys.argv
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) SimpleElginFC-history-builder"


def fetch(url: str, name: str, encoding: str = "utf-8", pause: float = 0.3) -> str | None:
    """The page at url, from the cache when we have it. None if it's missing."""
    path = CACHE / name
    if path.exists() and not REFRESH:
        data = path.read_bytes()
    else:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        data = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                break
            except urllib.error.HTTPError as e:
                if e.code in (400, 404):
                    break
                time.sleep(1 + attempt)
            except OSError:
                time.sleep(1 + attempt)
        if data is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        time.sleep(pause)
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode(encoding, errors="replace")


def from_sfha() -> list[Match]:
    found = []
    for page, competition in sfha.PAGES.items():
        html = fetch(sfha.BASE_URL + page, page, encoding="cp1252", pause=2)
        if html:
            matches = sfha.parse_page(html, competition)
            print(f"  sfha {page}: {len(matches)}")
            found += matches
    return found


def from_fchd() -> list[Match]:
    found = []
    for start in range(1946, 2016):
        season = f"{start}-{(start + 1) % 100:02d}"
        html = fetch(fchd.season_url(season), f"fchd/scottishcup{season}.htm", encoding="cp1252", pause=1)
        if html:
            found += fchd.parse_season(html, season)
    print(f"  fchd Scottish Cup: {len(found)}")
    return found


def from_espn() -> list[Match]:
    found = []
    for year in range(2000, date.today().year + 1):
        got = []
        for league in espn.SCHEDULE_LEAGUES:
            text = fetch(espn.schedule_url(league, year), f"espn/{league}-{year}.json")
            if text:
                got += espn.parse_schedule(json.loads(text), league)
        found += got
        print(f"  espn {year}: {len(got)}")
    # The seasons ESPN's team schedule can't serve (it answers 500): walk
    # the days of the season on the scoreboard instead.
    for start, end in espn.SCOREBOARD_SEASONS:
        got = []
        day = start
        while day <= end:
            text = fetch(espn.scoreboard_url("sco.4", day), f"espn/sb/sco.4-{day:%Y%m%d}.json", pause=0.15)
            if text:
                got += espn.parse_schedule(json.loads(text), "sco.4")
            day += timedelta(days=1)
        found += got
        print(f"  espn scoreboard {start:%Y}-{end:%y}: {len(got)}")
    # each game's key events: the right score where the schedule's is
    # wrong, and the goalscorers
    corrected = 0
    for m in found:
        if not m.ref:
            continue
        _, league, event_id = m.ref.split(":")
        text = fetch(espn.summary_url(league, event_id), f"espn/summary/{event_id}.json", pause=0.15)
        if text:
            before = m.score
            espn.apply_summary(m, espn.parse_summary(json.loads(text)))
            corrected += m.score != before
    print(f"  espn summaries: {corrected} scores corrected")
    return found


def from_bbc() -> list[Match]:
    found = []
    month = bbc.FIRST_MONTH
    today = date.today()
    while month <= today:
        end = bbc.month_end(month)
        text = fetch(bbc.scores_url(month, min(end, today), today), f"bbc/{month:%Y-%m}.json")
        if text:
            found += bbc.parse_scores(json.loads(text))
        month = end + timedelta(days=1)
    print(f"  bbc: {len(found)}")
    return found


def main() -> None:
    print("Reading sources…")
    groups = [from_sfha(), from_fchd(), from_espn(), from_bbc()]
    merged = history.merge(*groups)
    played = [m for m in merged if m.played]
    print(f"{len(merged)} matches ({len(played)} with scores)")
    print("by competition:", Counter(m.competition for m in merged).most_common())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"built": date.today().isoformat(), "matches": [m.to_dict() for m in merged]}
    OUT.write_bytes(gzip.compress(json.dumps(payload, separators=(",", ":")).encode(), mtime=0))
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
