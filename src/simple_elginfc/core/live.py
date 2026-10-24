"""Keeping up to date: this season's results and fixtures, the league
table, the news, and the club's details.

Each fetch_* runs on a background thread and returns plain data; the
last good copy of each is cached in the user's data folder, so the app
opens with everything it knew last time, even offline.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from platformdirs import user_cache_dir

from simple_elginfc import __version__
from simple_elginfc.core import club
from simple_elginfc.core.http import SSL_CONTEXT
from simple_elginfc.core.models import Match
from simple_elginfc.core.sources import bbc

USER_AGENT = f"Simple-ElginFC/{__version__} (+https://github.com/mikehellyer/simple-elginfc)"
TIMEOUT = 20


def get_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT, context=SSL_CONTEXT) as response:
        return response.read()


def get_json(url: str):
    return json.loads(get_bytes(url).decode("utf-8"))


@dataclass
class Fixtures:
    """Around now: recent results and the coming games (with live ones)."""
    events: list[dict] = field(default_factory=list)  # bbc.Event as dicts, oldest first
    updated: float = 0.0

    def as_events(self) -> list[bbc.Event]:
        out = []
        for e in self.events:
            out.append(bbc.Event(Match.from_dict(e["match"]), e["state"], e["kickoff"], e["status"]))
        return out


def fetch_fixtures(today: Optional[date] = None, get: Callable = get_json) -> Fixtures:
    today = today or date.today()
    events: dict[str, bbc.Event] = {}
    got_any = False
    for start, end in bbc.current_ranges(today):
        try:
            payload = get(bbc.scores_url(start, end, today))
        except (OSError, ValueError):
            continue
        got_any = True
        for ev in bbc.parse_events(payload):
            events[ev.match.date + ev.match.opponent] = ev
    if not got_any:
        raise OSError("BBC Sport didn't answer")
    ordered = sorted(events.values(), key=lambda ev: ev.kickoff or ev.match.date)
    return Fixtures([{"match": ev.match.to_dict(), "state": ev.state, "kickoff": ev.kickoff, "status": ev.status}
                     for ev in ordered], time.time())


def fetch_season_results(season_start: int, today: Optional[date] = None, get: Callable = get_json) -> list[Match]:
    """Every finished game this season, month by month: tops up the history."""
    today = today or date.today()
    month = date(season_start, 7, 1)
    found: list[Match] = []
    while month <= today:
        end = min(bbc.month_end(month), today)
        try:
            found += bbc.parse_scores(get(bbc.scores_url(month, end, today)))
        except (OSError, ValueError):
            pass
        month = bbc.month_end(month).replace(day=1)
        month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    return found


@dataclass
class LeagueTable:
    name: str = ""
    rows: list[dict] = field(default_factory=list)  # bbc.TableRow as dicts
    updated: float = 0.0

    def as_rows(self) -> list[bbc.TableRow]:
        return [bbc.TableRow(**r) for r in self.rows]


def fetch_table(get: Callable = get_json) -> LeagueTable:
    name, rows = bbc.parse_table(get(bbc.table_url()))
    if not rows:
        raise ValueError("no table")
    return LeagueTable(name, [asdict(r) for r in rows], time.time())


@dataclass
class News:
    items: list[dict] = field(default_factory=list)  # bbc.NewsItem as dicts
    updated: float = 0.0

    def as_items(self) -> list[bbc.NewsItem]:
        return [bbc.NewsItem(**i) for i in self.items]


def fetch_news(get: Callable = get_bytes) -> News:
    items = bbc.parse_news(get(bbc.NEWS_URL))
    return News([asdict(i) for i in items], time.time())


@dataclass
class ClubDetails:
    info: club.ClubInfo
    honours: list[tuple[str, str]]  # (competition, "Champions: 1931-32, …")
    records: list[tuple[str, str]]  # ("Win", "18-1 v Brora Rangers on 6 February 1960 (…)")
    staff: list[tuple[str, str]]  # ("Manager", "Stefan Laird")
    squad: list[dict]  # {"no": "1", "pos": "GK", "name": "Tom Ritchie", "nat": "SCO", "other": ""}
    managers: list[str]  # "Alex Caldwell (24 February 2000 - 9 December 2002)"
    crest_png: bytes = b""

    def to_json(self) -> str:
        data = {"info": json.loads(self.info.to_json()), "honours": self.honours, "records": self.records,
                "staff": self.staff, "squad": self.squad, "managers": self.managers}
        return json.dumps(data)

    @classmethod
    def from_json(cls, text: str, crest: bytes = b"") -> "ClubDetails":
        d = json.loads(text)
        return cls(club.ClubInfo.from_json(json.dumps(d["info"])), [tuple(x) for x in d["honours"]],
                   [tuple(x) for x in d["records"]], [tuple(x) for x in d["staff"]], d["squad"], d["managers"], crest)


def fetch_club(get: Callable = get_json, get_raw: Callable = get_bytes) -> ClubDetails:
    page = get(club.wikitext_url(club.CLUB_PAGE, whole=True))["parse"]["wikitext"]
    info = club.ClubInfo()
    club.apply_club_infobox(info, page)
    try:
        club.apply_ground_infobox(info, get(club.wikitext_url(club.GROUND_PAGE))["parse"]["wikitext"])
    except (OSError, ValueError, KeyError):
        pass
    try:
        info.board = club.parse_officers(get_raw(club.OFFICERS_URL).decode("utf-8", errors="replace"))
    except OSError:
        pass
    crest = b""
    if info.crest_file:
        try:
            url = club.parse_crest_url(get(club.image_url_query(info.crest_file)))
            if url:
                crest = get_raw(url)
        except (OSError, ValueError):
            pass
    sections = club.sections(page)
    info.updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return ClubDetails(
        info=info,
        honours=club.parse_honours(sections.get("honours", "")),
        records=club.parse_bold_list(sections.get("club records", "")),
        staff=club.parse_officials(sections.get("staff", "")),
        squad=club.parse_squad(sections.get("first-team squad", "")),
        managers=club.parse_bullets(sections.get("managers since entry to the sfl", "")),
        crest_png=crest,
    )


class Cache:
    """The last good copy of each kind of live data."""

    def __init__(self, folder: Optional[Path] = None):
        self.folder = folder or Path(user_cache_dir("Simple-ElginFC"))

    def _path(self, name: str) -> Path:
        return self.folder / name

    def save(self, name: str, text: str) -> None:
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            self._path(name).write_text(text)
        except OSError:
            pass

    def save_bytes(self, name: str, data: bytes) -> None:
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            self._path(name).write_bytes(data)
        except OSError:
            pass

    def load(self, name: str) -> Optional[str]:
        try:
            return self._path(name).read_text()
        except OSError:
            return None

    def load_bytes(self, name: str) -> bytes:
        try:
            return self._path(name).read_bytes()
        except OSError:
            return b""

    # --- typed helpers

    def save_fixtures(self, f: Fixtures) -> None:
        self.save("fixtures.json", json.dumps(asdict(f)))

    def load_fixtures(self) -> Fixtures:
        try:
            return Fixtures(**json.loads(self.load("fixtures.json") or ""))
        except (ValueError, TypeError):
            return Fixtures()

    def save_table(self, t: LeagueTable) -> None:
        self.save("table.json", json.dumps(asdict(t)))

    def load_table(self) -> LeagueTable:
        try:
            return LeagueTable(**json.loads(self.load("table.json") or ""))
        except (ValueError, TypeError):
            return LeagueTable()

    def save_news(self, n: News) -> None:
        self.save("news.json", json.dumps(asdict(n)))

    def load_news(self) -> News:
        try:
            return News(**json.loads(self.load("news.json") or ""))
        except (ValueError, TypeError):
            return News()

    def save_club(self, c: ClubDetails) -> None:
        self.save("club.json", c.to_json())
        if c.crest_png:
            self.save_bytes("crest.png", c.crest_png)

    def load_club(self) -> Optional[ClubDetails]:
        text = self.load("club.json")
        if not text:
            return None
        try:
            return ClubDetails.from_json(text, self.load_bytes("crest.png"))
        except (ValueError, KeyError, TypeError):
            return None
