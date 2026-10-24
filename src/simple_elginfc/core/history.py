"""Every Elgin City match we know of: the history bundled with the app,
topped up with what's been fetched since (kept in the user's data folder).
"""
from __future__ import annotations

import gzip
import json
from importlib import resources
from pathlib import Path
from typing import Iterable, Optional

from platformdirs import user_data_dir

from simple_elginfc.core.models import Match

# when two sources have the same game, whose score and details win
_TRUST = {"bbc": 4, "espn": 3, "sfha": 2, "fchd": 1, "": 0}


def _combine(a: Match, b: Match) -> Match:
    """One match from two sources' copies of it: the more trusted source's
    score, and every detail either of them has."""
    best, other = (a, b) if _TRUST.get(a.source, 0) >= _TRUST.get(b.source, 0) else (b, a)
    merged = Match.from_dict(best.to_dict())
    for name in ("date", "round", "ground", "attendance", "note", "half_time"):
        if not getattr(merged, name) and getattr(other, name):
            setattr(merged, name, getattr(other, name))
    if not merged.elgin_scorers and other.elgin_scorers:
        merged.elgin_scorers = list(other.elgin_scorers)
    if not merged.opponent_scorers and other.opponent_scorers:
        merged.opponent_scorers = list(other.opponent_scorers)
    if not merged.played and other.played:
        merged.elgin_goals, merged.opponent_goals = other.elgin_goals, other.opponent_goals
    sources = {s for s in (a.source, b.source) if s}
    merged.source = "+".join(sorted(sources, key=lambda s: -_TRUST.get(s, 0)))
    return merged


def _primary(source: str) -> str:
    return source.split("+")[0]


def _same_game(a: Match, b: Match) -> bool:
    if a.date and b.date:
        if a.date != b.date:
            return False
        # Elgin don't play twice in a day: the same day is the same game,
        # unless both sides name different clubs and the scores differ too.
        return a.opponent == b.opponent or (a.played and b.played and a.score == b.score)
    # an undated tie (FCHD) is the dated copy of it from another source
    return (a.season == b.season and a.competition == b.competition and a.opponent == b.opponent
            and a.venue == b.venue and (a.score == b.score or not (a.played and b.played))
            and (not a.round or not b.round or _round_number(a.round) == _round_number(b.round)))


_ORDINALS = (("first", "1"), ("second", "2"), ("third", "3"), ("fourth", "4"), ("fifth", "5"), ("sixth", "6"),
             ("1st", "1"), ("2nd", "2"), ("3rd", "3"), ("4th", "4"), ("5th", "5"), ("6th", "6"))


def _round_number(name: str) -> str:
    """"Second round replay", "Round 2 replay" -> "2 replay"."""
    name = name.lower()
    number = next((n for word, n in _ORDINALS if word in name), None)
    if number is None:
        number = "".join(ch for ch in name if ch.isdigit()) or name.replace(" replay", "")
    return number + (" replay" if "replay" in name else "")


def merge(*groups: Iterable[Match]) -> list[Match]:
    """All the matches, each game once, oldest first."""
    by_season: dict[str, list[Match]] = {}
    # dated matches first, so undated copies fold into them
    everything = sorted((m for g in groups for m in g), key=lambda m: (m.date is None, m.date or ""))
    for m in everything:
        bucket = by_season.setdefault(m.season, [])
        for i, existing in enumerate(bucket):
            if _same_game(existing, m):
                bucket[i] = _combine(existing, m)
                break
        else:
            bucket.append(m)
    out = [m for bucket in by_season.values() for m in bucket]
    out.sort(key=lambda m: m.sort_key)
    return out


def bundled_path():
    return resources.files("simple_elginfc") / "data" / "history.json.gz"


def load_bundled() -> tuple[str, list[Match]]:
    """(the date it was built, its matches)."""
    try:
        payload = json.loads(gzip.decompress(bundled_path().read_bytes()))
    except (OSError, ValueError):
        return "", []
    return payload.get("built", ""), [Match.from_dict(d) for d in payload.get("matches", [])]


class History:
    """The matches, plus the recent ones fetched since the app was built."""

    def __init__(self, data_dir: Optional[Path] = None):
        self._path = (data_dir or Path(user_data_dir("Simple-ElginFC"))) / "recent_matches.json"
        self.built, self._bundled = load_bundled()
        self._recent = self._load_recent()
        self.matches = merge(self._bundled, self._recent)

    def _load_recent(self) -> list[Match]:
        try:
            data = json.loads(self._path.read_text())
            return [Match.from_dict(d) for d in data.get("matches", [])]
        except (OSError, ValueError, TypeError):
            return []

    def add_recent(self, matches: list[Match]) -> bool:
        """Fold in freshly fetched results; True if anything changed."""
        before = [m.to_dict() for m in self.matches]
        self._recent = merge(self._recent, matches)
        self.matches = merge(self._bundled, self._recent)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps({"matches": [m.to_dict() for m in self._recent]}))
        except OSError:
            pass
        return [m.to_dict() for m in self.matches] != before

    def opponents(self) -> list[str]:
        return sorted({m.opponent for m in self.matches})

    def seasons(self) -> list[str]:
        return sorted({m.season for m in self.matches})

    def competitions(self) -> list[str]:
        return sorted({m.competition for m in self.matches})
