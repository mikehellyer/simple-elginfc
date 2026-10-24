"""The first-team players, for their cards: photo, number, position, age,
where they're from, when they joined, and their goals for Elgin.

Put together from:
- the club's own site (www.elgincity.net/team/players): each player's
  photo and position. Its pages fill themselves in with a second, AJAX
  request for the same address, which is what's asked for here.
- Wikipedia's squad list (number, nationality, captain or loan notes) and,
  where a player has his own article, its infobox: date and place of
  birth, height, his clubs and the year he joined Elgin.
- ESPN's season-by-season rosters: dates of birth and heights for the
  rest, and the first season each player was in an Elgin squad (the
  history builder gathers the older seasons; tools/build_history.py).
- the match history: the goals each player has scored for Elgin.

Photos are the club's (taken by Bob Crombie), fetched when needed and
never bundled with the app.
"""
from __future__ import annotations

import gzip
import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import date
from importlib import resources
from typing import Callable, Iterable, Optional

from simple_elginfc.core import club
from simple_elginfc.core.models import Match, season_of

CLUB_PLAYERS_URL = "https://www.elgincity.net/team/players"
ESPN_ROSTER_URL = "https://site.api.espn.com/apis/site/v2/sports/soccer/sco.4/teams/419/roster?season={season}"
AJAX_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

POSITIONS = {"GK": "Goalkeeper", "DF": "Defender", "MF": "Midfielder", "FW": "Forward"}
# the club site's words for them
CLUB_POSITIONS = {"goalkeeper": "Goalkeeper", "defence": "Defender", "defender": "Defender",
                  "midfield": "Midfielder", "midfielder": "Midfielder", "forward": "Forward", "attack": "Forward"}
NATIONS = {"SCO": "Scotland", "ENG": "England", "WAL": "Wales", "NIR": "Northern Ireland", "IRL": "Ireland",
           "FIN": "Finland", "NZL": "New Zealand", "BRA": "Brazil", "USA": "United States", "AUS": "Australia",
           "CAN": "Canada", "FRA": "France", "ESP": "Spain", "POR": "Portugal", "NED": "Netherlands",
           "GER": "Germany", "NOR": "Norway", "SWE": "Sweden", "DEN": "Denmark", "POL": "Poland"}


def name_key(name: str) -> str:
    """For matching one source's spelling of a name to another's:
    "Kyle MacLeod", "KYLE MACLEOD" and "Kyle Macleod" are the same."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(ch for ch in name if not unicodedata.combining(ch))
    return re.sub(r"[^a-z ]", "", name.lower()).strip()


def scorer_key(name: str) -> str:
    """"Kane Hester" -> "k hester", the way scorers are written ("K. Hester")."""
    parts = name_key(name).split()
    return f"{parts[0][0]} {' '.join(parts[1:])}" if len(parts) > 1 else name_key(name)


@dataclass
class Player:
    name: str
    number: str = ""
    position: str = ""  # "Midfielder"
    nationality: str = ""  # "Scotland"
    note: str = ""  # "captain", "on loan from Aberdeen"…
    photo_url: str = ""
    article: str = ""  # Wikipedia
    born: str = ""  # ISO date
    birthplace: str = ""
    height: str = ""  # "6' 3\" (1.91 m)" or as Wikipedia gives it
    joined: str = ""  # "2019" or "2019-20"
    clubs: list[str] = field(default_factory=list)  # before Elgin, most recent first
    apps: str = ""  # Elgin league appearances, from Wikipedia
    goals: str = ""  # Elgin league goals, from Wikipedia

    def age(self, today: Optional[date] = None) -> Optional[int]:
        if not self.born:
            return None
        today = today or date.today()
        try:
            b = date.fromisoformat(self.born)
        except ValueError:
            return None
        return today.year - b.year - ((today.month, today.day) < (b.month, b.day))


# --- the club's site

def parse_club_players(page: str) -> list[dict]:
    """[{"name", "position", "photo", "profile"}] from the players page's AJAX answer."""
    found = []
    # (the url() is quoted with ' in the page as served, &quot; once a browser has it)
    for m in re.finditer(r"""(?s)<a href="([^"]+)" class="person-listing"[^>]*?url\((?:'|&quot;)([^'&]+)(?:'|&quot;)\).*?<h3>(.*?)</h3>\s*<h4>(.*?)</h4>""", page):
        profile, photo, name, position = m.groups()
        name = re.sub(r"<[^>]+>", "", name).strip()
        found.append({
            "name": name.title() if name.isupper() else name,
            "position": CLUB_POSITIONS.get(position.strip().lower(), position.strip().title()),
            # the listing's photo is cropped for the grid; the profile's is the whole picture
            "photo": photo.replace("/_newsArticleListing/", "/_personPhotograph/"),
            "profile": profile,
        })
    return found


# --- Wikipedia

def _infobox_date(value: str) -> str:
    """{{birth date and age|1997|06|26|df=y}} -> "1997-06-26"."""
    m = re.search(r"\{\{\s*birth date(?: and age)?\s*\|\s*(\d{4})\s*\|\s*(\d{1,2})\s*\|\s*(\d{1,2})", value, re.IGNORECASE)
    if not m:
        return ""
    y, mo, d = (int(x) for x in m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ""


def parse_article(wikitext: str) -> dict:
    """What a player's article tells us: born, birthplace, height, joined,
    the clubs before Elgin, and his Elgin appearances and goals."""
    box = club.parse_infobox(wikitext)
    out = {"born": _infobox_date(box.get("birth_date", "")),
           "birthplace": club._strip_markup(box.get("birth_place", "")),
           "height": club._strip_markup(box.get("height", ""))}
    clubs = []
    n = 1
    while f"clubs{n}" in box:
        name = club._strip_markup(box[f"clubs{n}"])
        years = club._strip_markup(box.get(f"years{n}", "")).replace("–", "-")
        if "elgin" in name.lower():
            if not out.get("joined"):
                out["joined"] = years.split("-")[0].strip()
            out["apps"] = club._strip_markup(box.get(f"caps{n}", ""))
            out["goals"] = club._strip_markup(box.get(f"goals{n}", ""))
        else:
            clubs.append(f"{name} ({years})" if years else name)
        n += 1
    out["clubs"] = list(reversed(clubs))
    return out


# --- ESPN's rosters

@dataclass
class RosterEntry:
    born: str = ""
    height: str = ""
    first_season: str = ""  # "2019-20"


def parse_roster(payload: dict) -> tuple[str, dict[str, RosterEntry]]:
    """(the season, {name_key: entry})."""
    season = ""
    name = ((payload.get("season") or {}).get("displayName") or "")
    m = re.match(r"(\d{4})\s*[-/]\s*(\d{2,4})", name)  # "2019-20", "2008/09", "2001/2002"
    if m:
        season = f"{m.group(1)}-{m.group(2)[-2:]}"
    out = {}
    for a in payload.get("athletes") or []:
        key = name_key(a.get("displayName") or a.get("fullName") or "")
        born = (a.get("dateOfBirth") or "")[:10]
        if born.endswith("-01-01"):  # ESPN's stand-in when it doesn't know the day
            born = ""
        if key:
            out[key] = RosterEntry(born, a.get("displayHeight") or "", season)
    return season, out


def merge_rosters(rosters: Iterable[tuple[str, dict[str, RosterEntry]]]) -> dict[str, RosterEntry]:
    """Everyone in any season's roster, with the first season they were in one."""
    merged: dict[str, RosterEntry] = {}
    for season, entries in sorted(rosters, key=lambda r: r[0]):
        for key, e in entries.items():
            if key not in merged:
                merged[key] = RosterEntry(e.born, e.height, season or e.first_season)
            else:
                merged[key].born = merged[key].born or e.born
                merged[key].height = merged[key].height or e.height
    return merged


def load_bundled_rosters() -> dict[str, RosterEntry]:
    try:
        data = json.loads(gzip.decompress((resources.files("simple_elginfc") / "data" / "rosters.json.gz").read_bytes()))
    except (OSError, ValueError):
        return {}
    return {k: RosterEntry(**v) for k, v in data.items()}


def rosters_to_bytes(rosters: dict[str, RosterEntry]) -> bytes:
    return gzip.compress(json.dumps({k: asdict(v) for k, v in sorted(rosters.items())}).encode(), mtime=0)


def _one_edit_apart(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = sorted((a, b), key=len)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def find_roster(rosters: dict[str, RosterEntry], name: str, born: str = "") -> Optional[RosterEntry]:
    """His roster entry, allowing for ESPN's spelling ("Bryan Cameron" up
    to 2014-15, "Brian Cameron" after): the same surname and either the
    same date of birth or a first name one letter different. Where he's
    in under two spellings, the earliest season wins."""
    key = name_key(name)
    parts = key.split()
    if len(parts) < 2:
        return rosters.get(key)
    found = [rosters[key]] if key in rosters else []
    known_born = born or (rosters[key].born if key in rosters else "")
    for other, entry in rosters.items():
        o = other.split()
        if other == key or len(o) < 2 or o[-1] != parts[-1]:
            continue
        if (known_born and entry.born == known_born) or _one_edit_apart(o[0], parts[0]):
            found.append(entry)
    if not found:
        return None
    seasons = [e.first_season for e in found if e.first_season]
    return RosterEntry(next((e.born for e in found if e.born), ""), next((e.height for e in found if e.height), ""),
                       min(seasons) if seasons else "")


def joined_text(player: "Player", goals: Optional["GoalRecord"] = None) -> str:
    """When he joined, as well as we know: Wikipedia's year, else the first
    season he was in an Elgin squad or scored for them, whichever's first."""
    if player.joined and "-" not in player.joined:
        return player.joined  # a year, from Wikipedia
    if player.joined:
        return f"{player.joined} season"
    first_goal = goals.first.season if goals and goals.first else ""
    return f"by the {first_goal} season" if first_goal else ""


# --- putting it together

def build_squad(wiki_squad: list[dict], club_players: list[dict], articles: dict[str, dict],
                rosters: dict[str, RosterEntry]) -> list[Player]:
    """One Player for everyone in either squad list, numbered players first."""
    by_key: dict[str, Player] = {}
    for p in wiki_squad:
        key = name_key(p["name"])
        by_key[key] = Player(
            name=p["name"], number=p.get("no", ""), position=POSITIONS.get(p.get("pos", ""), p.get("pos", "")),
            nationality=NATIONS.get(p.get("nat", ""), p.get("nat", "")), note=p.get("other", ""),
            article=p.get("article", ""))
    for c in club_players:
        key = name_key(c["name"])
        player = by_key.setdefault(key, Player(name=c["name"], position=c["position"]))
        player.photo_url = c["photo"]
        player.position = player.position or c["position"]
    for key, player in by_key.items():
        info = articles.get(player.article) or {}
        for name in ("born", "birthplace", "height", "joined", "clubs", "apps", "goals"):
            if info.get(name):
                setattr(player, name, info[name])
        r = find_roster(rosters, player.name, player.born)
        if r:
            player.born = player.born or r.born
            player.height = player.height or r.height
            player.joined = player.joined or r.first_season
    return sorted(by_key.values(), key=lambda p: (not p.number.isdigit(), int(p.number) if p.number.isdigit() else 0, p.name))


@dataclass
class GoalRecord:
    goals: int = 0
    games: int = 0  # games he scored in
    first: Optional[Match] = None
    last: Optional[Match] = None
    best: Optional[Match] = None  # the game he scored most in
    best_goals: int = 0


def since_season(player: Player) -> str:
    """The first season he can have scored for Elgin in, if we know when he
    joined: "2007-08" as it is; Wikipedia's "2019" could be a January
    signing, so from the season that began the year before ("2018-19")."""
    j = player.joined
    if re.fullmatch(r"\d{4}", j):
        return f"{int(j) - 1}-{j[2:]}"
    return j


def goals_for(player: Player, matches: list[Match]) -> GoalRecord:
    """His goals for Elgin that we know of: the history has goalscorers
    from 2001-02 on (ESPN, then BBC Sport). Own goals don't count.

    Scorers are written "K. Hester", so an earlier "J. Murray" would look
    like today's Jack Murray: only games from the season he joined count,
    where we know it."""
    key = scorer_key(player.name)
    record = GoalRecord()
    since = since_season(player)
    for m in matches:
        if since and m.season < since:
            continue
        for entry in m.elgin_scorers:
            name, _, times = entry.partition(" ")
            while times and not times[0].isdigit():
                word, _, times = times.partition(" ")
                name = f"{name} {word}"
            if scorer_key(name.replace(".", "")) != key and name_key(name.replace(".", "")) != name_key(player.name):
                continue
            count = len([t for t in times.split(",") if t.strip() and "og" not in t])
            if not count:
                continue
            record.goals += count
            record.games += 1
            record.first = record.first or m
            record.last = m
            if count > record.best_goals:
                record.best_goals, record.best = count, m
    return record


def fetch_squad(wiki_squad: list[dict], get_text: Callable[[str, dict], str], get_json: Callable[[str], dict],
                today: Optional[date] = None) -> list[Player]:
    """Everything for the cards except the photos (fetched when a card opens)."""
    try:
        club_players = parse_club_players(get_text(CLUB_PLAYERS_URL, AJAX_HEADERS))
    except OSError:
        club_players = []
    articles = {}
    for p in wiki_squad:
        if p.get("article"):
            try:
                articles[p["article"]] = parse_article(get_json(club.wikitext_url(p["article"].replace(" ", "_")))["parse"]["wikitext"])
            except (OSError, ValueError, KeyError):
                pass
    rosters = load_bundled_rosters()
    season = int(season_of(today or date.today())[:4])
    current = {}
    for year in (season - 1, season):  # the seasons since the app was built
        try:
            current[year] = parse_roster(get_json(ESPN_ROSTER_URL.format(season=year)))
        except (OSError, ValueError):
            pass
    # (the bundled entries carry their own first season, and are all older)
    rosters = merge_rosters([("", rosters)] + list(current.values()))
    return build_squad(wiki_squad, club_players, articles, rosters)
