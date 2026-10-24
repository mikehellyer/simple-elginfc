"""A single Elgin City match, whatever source it came from."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional

ELGIN = "Elgin City"

HOME, AWAY, NEUTRAL = "H", "A", "N"
WIN, DRAW, LOSS = "W", "D", "L"


@dataclass
class Match:
    season: str  # "1895-96"
    competition: str  # "Highland League", "Scottish Cup"…
    opponent: str  # the canonical name (core.teams)
    venue: str  # HOME, AWAY or NEUTRAL (from Elgin's point of view)
    date: Optional[str] = None  # ISO "1895-10-05"; None when a source only gives the season
    round: str = ""  # "Semi-final", "Second round replay"…
    elgin_goals: Optional[int] = None  # None: not played yet, or no score known
    opponent_goals: Optional[int] = None
    ground: str = ""  # "Borough Briggs"; a neutral final's ground
    attendance: Optional[int] = None
    note: str = ""  # "aet", "4-3 on penalties", "abandoned after 73 mins"…
    elgin_scorers: list[str] = field(default_factory=list)  # "J. MacIver 9'"
    opponent_scorers: list[str] = field(default_factory=list)
    half_time: str = ""  # Elgin's goals first, like the full-time score: "2-1"
    source: str = ""  # "sfha", "fchd", "espn", "bbc"
    ref: str = ""  # the source's own id for the game, where it has one: "espn:sco.4:45122"

    @property
    def played(self) -> bool:
        return self.elgin_goals is not None and self.opponent_goals is not None

    @property
    def result(self) -> str:
        """W, D or L for Elgin; "" if there's no score. A cup tie that was
        level at full time counts as a draw, whoever went through."""
        if not self.played:
            return ""
        if self.elgin_goals > self.opponent_goals:
            return WIN
        return DRAW if self.elgin_goals == self.opponent_goals else LOSS

    @property
    def score(self) -> str:
        """Elgin's goals first: "3-1"."""
        return f"{self.elgin_goals}-{self.opponent_goals}" if self.played else ""

    @property
    def home_team(self) -> str:
        return self.opponent if self.venue == AWAY else ELGIN

    @property
    def away_team(self) -> str:
        return ELGIN if self.venue == AWAY else self.opponent

    @property
    def home_away_score(self) -> str:
        """The score as it's usually written, home side first."""
        if not self.played:
            return ""
        if self.venue == AWAY:
            return f"{self.opponent_goals}-{self.elgin_goals}"
        return f"{self.elgin_goals}-{self.opponent_goals}"

    @property
    def sort_key(self) -> tuple:
        # Undated matches (some old cup ties) sort to the start of their season.
        return (self.season, self.date or "", self.competition, self.round)

    @property
    def year(self) -> Optional[int]:
        return date.fromisoformat(self.date).year if self.date else None

    def to_dict(self) -> dict:
        data = asdict(self)
        return {k: v for k, v in data.items() if v not in (None, "", [])}

    @classmethod
    def from_dict(cls, data: dict) -> "Match":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def season_of(day: date) -> str:
    """The football season a date falls in: July onwards starts a new one."""
    start = day.year if day.month >= 7 else day.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def season_start_year(season: str) -> int:
    return int(season[:4])
