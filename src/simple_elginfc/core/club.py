"""The club as it is now: the badge, ground, manager and board.

- Wikipedia's infoboxes for Elgin City and Borough Briggs: nickname,
  founded, ground, capacity, record attendance, chairman, manager, and the
  crest (fetched, never bundled: it's the club's own artwork).
- Companies House's public register for the board: Elgin City Football
  Club Limited (SC207126)'s serving directors and secretary. Only names,
  roles and appointment dates are kept; never addresses or birth dates.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import urllib.parse
from dataclasses import asdict, dataclass, field
from typing import Optional

WIKI_API = "https://en.wikipedia.org/w/api.php"
CLUB_PAGE = "Elgin_City_F.C."
GROUND_PAGE = "Borough_Briggs"
COMPANY_NUMBER = "SC207126"
OFFICERS_URL = f"https://find-and-update.company-information.service.gov.uk/company/{COMPANY_NUMBER}/officers"


def wikitext_url(page: str, whole: bool = False) -> str:
    """The page's wikitext: just the lead (with the infobox), or all of it."""
    query = {"action": "parse", "page": page, "prop": "wikitext", "format": "json", "formatversion": 2}
    if not whole:
        query["section"] = 0
    return f"{WIKI_API}?{urllib.parse.urlencode(query)}"


def image_url_query(filename: str, width: int = 400) -> str:
    query = {"action": "query", "titles": f"File:{filename}", "prop": "imageinfo", "iiprop": "url",
             "iiurlwidth": width, "format": "json", "formatversion": 2}
    return f"{WIKI_API}?{urllib.parse.urlencode(query)}"


def _strip_markup(value: str) -> str:
    """Wikitext -> plain text, enough for an infobox value."""
    value = re.sub(r"<ref[^>]*/>", "", value)
    value = re.sub(r"(?s)<ref[^>]*>.*?</ref>", "", value)
    value = re.sub(r"<br\s*/?>", ", ", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\{\{(?:Start date and age|start date and age)\|(\d{4})[^}]*\}\}", r"\1", value)
    value = re.sub(r"\{\{(?:URL|url)\|([^}|]+)[^}]*\}\}", r"\1", value)
    value = re.sub(r"\{\{nowrap\|([^}]*)\}\}", r"\1", value, flags=re.IGNORECASE)
    value = re.sub(r"\{\{[^{}]*\}\}", "", value)
    value = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", value)
    value = re.sub(r"\[https?://\S+ ([^\]]+)\]", r"\1", value)
    value = re.sub(r"'''?", "", value)
    return htmllib.unescape(re.sub(r"\s+", " ", value)).strip(" ,")


def parse_infobox(wikitext: str) -> dict[str, str]:
    start = wikitext.lower().find("{{infobox")
    if start < 0:
        return {}
    # the infobox runs to its matching closing braces
    depth, i = 0, start
    while i < len(wikitext) - 1:
        pair = wikitext[i:i + 2]
        if pair == "{{":
            depth += 1
            i += 2
            continue
        if pair == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                break
            continue
        i += 1
    body = wikitext[start + 2:i - 2]
    fields_: dict[str, str] = {}
    # split on top-level pipes only
    depth, current, parts = 0, [], []
    j = 0
    while j < len(body):
        two = body[j:j + 2]
        if two in ("{{", "[["):
            depth += 1
            current.append(two)
            j += 2
            continue
        if two in ("}}", "]]"):
            depth -= 1
            current.append(two)
            j += 2
            continue
        if body[j] == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(body[j])
        j += 1
    parts.append("".join(current))
    for part in parts[1:]:
        key, sep, value = part.partition("=")
        if sep:
            fields_[key.strip().lower()] = value.strip()
    return fields_


@dataclass
class Officer:
    name: str  # "Alan Murray"
    role: str  # "Director", "Secretary"
    appointed: str  # "18 March 2024"


@dataclass
class ClubInfo:
    full_name: str = "Elgin City Football Club"
    nickname: str = ""
    founded: str = ""
    ground: str = ""
    capacity: str = ""
    chairman: str = ""
    manager: str = ""
    league: str = ""
    website: str = ""
    crest_file: str = ""  # on Wikimedia
    ground_opened: str = ""
    record_attendance: str = ""
    ground_surface: str = ""
    board: list[Officer] = field(default_factory=list)
    updated: str = ""  # ISO date-time of the last fetch

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, text: str) -> "ClubInfo":
        data = json.loads(text)
        board = [Officer(**o) for o in data.pop("board", [])]
        known = set(cls.__dataclass_fields__)
        return cls(board=board, **{k: v for k, v in data.items() if k in known})


def apply_club_infobox(info: ClubInfo, wikitext: str) -> None:
    box = parse_infobox(wikitext)
    get = lambda k: _strip_markup(box.get(k, ""))  # noqa: E731
    info.full_name = get("fullname") or info.full_name
    info.nickname = get("nickname")
    info.founded = get("founded")
    info.ground = get("ground")
    info.capacity = get("capacity")
    info.chairman = get("chairman")
    info.manager = get("manager") or get("head coach")
    info.website = get("website")
    info.crest_file = box.get("image", "").strip()
    if not info.league:
        info.league = "Scottish League Two"


def apply_ground_infobox(info: ClubInfo, wikitext: str) -> None:
    box = parse_infobox(wikitext)
    get = lambda k: _strip_markup(box.get(k, ""))  # noqa: E731
    info.ground_opened = get("opened")
    info.record_attendance = get("record_attendance")
    info.ground_surface = get("surface")
    if not info.capacity:
        info.capacity = get("capacity")


def parse_crest_url(payload: dict) -> Optional[str]:
    for page in (payload.get("query") or {}).get("pages") or []:
        for ii in page.get("imageinfo") or []:
            return ii.get("thumburl") or ii.get("url")
    return None


def _person(surname_first: str) -> str:
    """"STEWART, Kenneth Milne" -> "Kenneth Stewart" (first name and surname,
    as the club would write it)."""
    surname, _, forenames = surname_first.partition(",")
    surname = " ".join(w.capitalize() if not w.lower().startswith("mc") else "Mc" + w[2:].capitalize()
                       for w in surname.split())
    first = forenames.split()[0] if forenames.split() else ""
    return f"{first} {surname}".strip()


def sections(wikitext: str) -> dict[str, str]:
    """Each "==Heading==" (any level) -> its text, up to the next heading."""
    out = {}
    parts = re.split(r"\n(=+)\s*([^=\n]+?)\s*\1[ \t]*(?=\n)", "\n" + wikitext)
    for i in range(1, len(parts) - 2, 3):
        out[parts[i + 1].strip().lower()] = parts[i + 2]
    return out


def parse_honours(text: str) -> list[tuple[str, str]]:
    """A competition bullet then its sub-bullets ("** Champions: 1931-32, …")
    -> [("Highland League", "Champions: 1931-32, …")]."""
    out = []
    competition = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("**"):
            if competition:
                out.append((competition, _strip_markup(line.lstrip("* ")).replace("–", "-")))
        elif line.startswith("*"):
            competition = _strip_markup(line.lstrip("* "))
    return out


def parse_bold_list(text: str) -> list[tuple[str, str]]:
    """Lines of a bold label and its value -> [("Win", "18-1 v …")]."""
    out = []
    for m in re.finditer(r"'''(.+?)'''\s*:?\s*(.+)", text):
        label = _strip_markup(m.group(1)).rstrip(":").strip()
        value = _strip_markup(m.group(2)).lstrip(": ").replace("–", "-")
        if label and value:
            out.append((label, value))
    return out


def parse_officials(text: str) -> list[tuple[str, str]]:
    """"*Manager: Stefan Laird" -> [("Manager", "Stefan Laird")]."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("*") and ":" in line:
            role, _, name = _strip_markup(line.lstrip("* ")).partition(":")
            out.append((role.strip(), name.strip()))
    return out


def parse_bullets(text: str) -> list[str]:
    return [_strip_markup(line.strip().lstrip("* ")).replace("–", "-") for line in text.splitlines()
            if line.strip().startswith("*")]


def parse_squad(text: str) -> list[dict]:
    """The {{fs player|no=1|nat=SCO|pos=GK|name=Tom Ritchie}} lines."""
    players = []
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("{{fs player"):
            box = parse_infobox("{{infobox" + line[len("{{fs player"):])
            players.append({k: _strip_markup(box.get(k, "")) for k in ("no", "nat", "pos", "name", "other")})
    return [p for p in players if p["name"]]


def parse_officers(page: str) -> list[Officer]:
    """The active officers from Companies House's officers page."""
    officers = []
    for block in re.findall(r'(?s)<div class="appointment-\d+">(.*?)(?=<div class="appointment-\d+">|</main>)', page):
        name_m = re.search(r'(?s)<a[^>]*href="/officers/[^"]*"[^>]*>(.*?)</a>', block)
        role_m = re.search(r'(?s)id="officer-role-\d+"[^>]*>(.*?)<', block)
        status_m = re.search(r'(?s)id="officer-status-tag-\d+"[^>]*>(.*?)<', block)
        appointed_m = re.search(r'(?s)id="officer-appointed-on-\d+"[^>]*>(.*?)<', block)
        if not name_m:
            continue
        status = htmllib.unescape(status_m.group(1)).strip() if status_m else ""
        if status and status.lower() != "active":
            continue
        if "Resigned on" in block:
            continue
        officers.append(Officer(
            name=_person(htmllib.unescape(re.sub(r"<[^>]+>", "", name_m.group(1))).strip()),
            role=htmllib.unescape(role_m.group(1)).strip().capitalize() if role_m else "",
            appointed=htmllib.unescape(appointed_m.group(1)).strip() if appointed_m else "",
        ))
    return officers
