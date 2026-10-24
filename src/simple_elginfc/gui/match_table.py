"""A table of matches, shared by the Matches and Head to Head tabs."""
from __future__ import annotations

from datetime import date
from typing import Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView

from simple_elginfc.core.models import AWAY, HOME, NEUTRAL, Match
from simple_elginfc.core.stats import counts
from simple_elginfc.core.teams import matches_query
from simple_elginfc.gui.style import MUTED, RESULT_COLOURS

COLUMNS = ["Date", "Season", "Competition", "Round", "Opponent", "Venue", "Result", "Score", "Attendance"]
VENUE_NAMES = {HOME: "Home", AWAY: "Away", NEUTRAL: "Neutral"}
SORT_ROLE = Qt.UserRole + 1
MATCH_ROLE = Qt.UserRole + 2


def nice_date(iso: Optional[str]) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d.day} {d:%b %Y}"


def describe(m: Match) -> str:
    """One line: "Sat 3 Oct 2026 · Elgin City 6-2 Clyde · Scottish League"."""
    when = ""
    if m.date:
        d = date.fromisoformat(m.date)
        when = f"{d:%a} {d.day} {d:%b %Y}"
    else:
        when = m.season
    score = m.home_away_score or "v"
    comp = m.competition + (f", {m.round}" if m.round else "")
    return f"{when} · {m.home_team} {score} {m.away_team} · {comp}"


class MatchModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._matches: list[Match] = []

    def set_matches(self, matches: list[Match]) -> None:
        self.beginResetModel()
        self._matches = list(matches)
        self.endResetModel()

    def match_at(self, row: int) -> Match:
        return self._matches[row]

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._matches)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        m = self._matches[index.row()]
        col = COLUMNS[index.column()]
        if role == MATCH_ROLE:
            return m
        if role == Qt.DisplayRole:
            return {
                "Date": nice_date(m.date) or "—",
                "Season": m.season,
                "Competition": m.competition,
                "Round": m.round,
                "Opponent": m.opponent,
                "Venue": VENUE_NAMES.get(m.venue, m.venue),
                "Result": m.result if counts(m) else ("—" if not m.played else "void"),
                "Score": m.score or ("v" if not m.played else ""),
                "Attendance": f"{m.attendance:,}" if m.attendance else "",
            }[col]
        if role == SORT_ROLE:
            # (Qt compares these itself, so strings and numbers, not tuples)
            if col == "Date":
                return f"{m.date or m.season[:4] + '-07-00'} {m.round}"
            if col == "Score":
                return ((m.elgin_goals or 0) - (m.opponent_goals or 0)) * 100 + (m.elgin_goals or 0)
            if col == "Attendance":
                return m.attendance or 0
            return self.data(index, Qt.DisplayRole)
        if role == Qt.ForegroundRole:
            if col in ("Result", "Score") and counts(m):
                return QBrush(QColor(RESULT_COLOURS[m.result]))
            if not m.played or col == "Date" and not m.date:
                return QBrush(QColor(MUTED))
        if role == Qt.FontRole and col in ("Result", "Score"):
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.TextAlignmentRole and col in ("Result", "Score", "Venue", "Attendance"):
            return int(Qt.AlignCenter if col != "Attendance" else Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ToolTipRole:
            tip = describe(m)
            if m.note:
                tip += f"\n{m.note}"
            return tip
        return None


class MatchFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(SORT_ROLE)
        self.opponent = ""
        self.competition = ""
        self.venue = ""
        self.result = ""
        self.season_from = ""
        self.season_to = ""

    def set_filters(self, **values) -> None:
        for k, v in values.items():
            setattr(self, k, v)
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent) -> bool:
        m: Match = self.sourceModel().match_at(row)
        if self.opponent and not matches_query(m.opponent, self.opponent):
            return False
        if self.competition and m.competition != self.competition:
            return False
        if self.venue and m.venue != self.venue:
            return False
        if self.result and (m.result != self.result or not counts(m)):
            return False
        if self.season_from and m.season < self.season_from:
            return False
        if self.season_to and m.season > self.season_to:
            return False
        return True

    def visible_matches(self) -> list[Match]:
        return [self.data(self.index(r, 0), MATCH_ROLE) for r in range(self.rowCount())]


class MatchTable(QTableView):
    def __init__(self, parent=None, hide: tuple[str, ...] = ()):
        super().__init__(parent)
        self.model_ = MatchModel(self)
        self.filter = MatchFilter(self)
        self.filter.setSourceModel(self.model_)
        self.setModel(self.filter)
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.DescendingOrder)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(28)
        header = self.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(QHeaderView.Interactive)
        widths = {"Date": 110, "Season": 70, "Competition": 170, "Round": 150, "Opponent": 200, "Venue": 70,
                  "Result": 60, "Score": 60, "Attendance": 90}
        for i, name in enumerate(COLUMNS):
            self.setColumnWidth(i, widths[name])
            if name in hide:
                self.hideColumn(i)
        header.setSectionResizeMode(COLUMNS.index("Opponent"), QHeaderView.Stretch)

    def set_matches(self, matches: list[Match]) -> None:
        self.model_.set_matches(matches)

    def selected_match(self) -> Optional[Match]:
        rows = self.selectionModel().selectedRows()
        return self.filter.data(rows[0], MATCH_ROLE) if rows else None
