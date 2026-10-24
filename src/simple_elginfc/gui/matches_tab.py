"""The Matches tab: every game Elgin City are known to have played, to
filter, sort and read the details of."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QPushButton, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from simple_elginfc.core.models import AWAY, HOME, NEUTRAL, Match
from simple_elginfc.core.stats import record, season_summaries
from simple_elginfc.gui.match_table import VENUE_NAMES, MatchTable, describe
from simple_elginfc.gui.style import MUTED, result_chip

SOURCE_NAMES = {
    "sfha": "Scottish Football Historical Results Archive",
    "fchd": "Football Club History Database",
    "espn": "ESPN",
    "bbc": "BBC Sport",
}


def match_details_html(m: Match) -> str:
    lines = [f"<p style='font-size:15pt; margin:0 0 4px 0'>{result_chip(m.result)} "
             f"<b>{html.escape(m.home_team)} {m.home_away_score or 'v'} {html.escape(m.away_team)}</b></p>",
             f"<p style='margin:0 0 8px 0; color:{MUTED}'>{html.escape(describe(m))}</p>"]
    rows = []
    if m.half_time:
        rows.append(("Half time", f"{m.half_time} (Elgin first)"))
    if m.elgin_scorers:
        rows.append(("Elgin scorers", ", ".join(m.elgin_scorers)))
    if m.opponent_scorers:
        rows.append((f"{m.opponent} scorers", ", ".join(m.opponent_scorers)))
    if m.ground:
        rows.append(("Ground", m.ground))
    elif m.venue == HOME and m.season >= "1921":  # Borough Briggs opened in 1921
        rows.append(("Ground", "Borough Briggs"))
    if m.attendance:
        rows.append(("Attendance", f"{m.attendance:,}"))
    if m.note:
        rows.append(("Note", m.note))
    rows.append(("Source", ", ".join(SOURCE_NAMES.get(s, s) for s in m.source.split("+") if s)))
    lines.append("<table cellspacing=0>" + "".join(
        f"<tr><td style='color:{MUTED}; padding:1px 14px 1px 0'>{html.escape(k)}</td><td>{html.escape(v)}</td></tr>"
        for k, v in rows) + "</table>")
    return "".join(lines)


def record_line(matches: list[Match]) -> str:
    r = record(matches)
    if not r.played:
        return f"{len(matches)} games"
    return (f"<b>{len(matches):,}</b> games &nbsp;·&nbsp; P {r.played:,} &nbsp;"
            f"<span style='color:#1e8e3e'><b>W {r.won:,}</b></span> &nbsp;"
            f"<span style='color:#8a8a8e'><b>D {r.drawn:,}</b></span> &nbsp;"
            f"<span style='color:#c62828'><b>L {r.lost:,}</b></span> &nbsp;·&nbsp; "
            f"Goals {r.goals_for:,}-{r.goals_against:,} &nbsp;·&nbsp; won {r.win_percent:.0f}%")


class MatchesTab(QWidget):
    head_to_head_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        bar = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Opponent (e.g. Clach, Forres, ICT)…")
        self._search.setClearButtonEnabled(True)
        self._competition = QComboBox()
        self._season_from = QComboBox()
        self._season_to = QComboBox()
        self._venue = QComboBox()
        self._venue.addItem("Home & away", "")
        for code in (HOME, AWAY, NEUTRAL):
            self._venue.addItem(VENUE_NAMES[code], code)
        self._result = QComboBox()
        for label, code in (("Any result", ""), ("Wins", "W"), ("Draws", "D"), ("Defeats", "L")):
            self._result.addItem(label, code)
        reset = QPushButton("Clear")
        reset.clicked.connect(self._reset)
        self._seasons_button = QPushButton("Seasons")
        self._seasons_button.setCheckable(True)
        self._seasons_button.setToolTip("Season by season, for the games filtered")
        self._seasons_button.toggled.connect(self._toggle_seasons)
        bar.addWidget(self._search, stretch=2)
        bar.addWidget(self._competition, stretch=1)
        bar.addWidget(QLabel("from"))
        bar.addWidget(self._season_from)
        bar.addWidget(QLabel("to"))
        bar.addWidget(self._season_to)
        bar.addWidget(self._venue)
        bar.addWidget(self._result)
        bar.addWidget(reset)
        bar.addWidget(self._seasons_button)
        layout.addLayout(bar)

        self._summary = QLabel()
        self._summary.setTextFormat(Qt.RichText)
        layout.addWidget(self._summary)

        split = QSplitter(Qt.Vertical)
        self.table = MatchTable()
        split.addWidget(self.table)
        detail = QFrame()
        detail.setObjectName("card")
        dl = QHBoxLayout(detail)
        dl.setContentsMargins(16, 12, 16, 12)
        self._detail = QLabel(f"<span style='color:{MUTED}'>Pick a game to see its details.</span>")
        self._detail.setTextFormat(Qt.RichText)
        self._detail.setWordWrap(True)
        self._detail.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dl.addWidget(self._detail, stretch=1)
        self._h2h_button = QPushButton("Head to head")
        self._h2h_button.setEnabled(False)
        self._h2h_button.clicked.connect(self._open_h2h)
        dl.addWidget(self._h2h_button, alignment=Qt.AlignTop)
        split.addWidget(detail)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        self._stack = QStackedWidget()
        self._stack.addWidget(split)
        self._seasons = self._make_seasons_table()
        self._stack.addWidget(self._seasons)
        layout.addWidget(self._stack, stretch=1)

        self._search.textChanged.connect(self._apply)
        for combo in (self._competition, self._season_from, self._season_to, self._venue, self._result):
            combo.currentIndexChanged.connect(self._apply)
        self.table.selectionModel().selectionChanged.connect(self._show_selected)
        self._filling = False

    def set_matches(self, matches: list[Match]) -> None:
        self._filling = True
        keep = (self._competition.currentData(), self._season_from.currentData(), self._season_to.currentData())
        self.table.set_matches(matches)
        self._competition.clear()
        self._competition.addItem("All competitions", "")
        for comp in sorted({m.competition for m in matches}):
            self._competition.addItem(comp, comp)
        seasons = sorted({m.season for m in matches})
        for combo, label in ((self._season_from, "first season"), (self._season_to, "latest season")):
            combo.clear()
            combo.addItem(label, "")
            for s in seasons:
                combo.addItem(s, s)
        for combo, value in zip((self._competition, self._season_from, self._season_to), keep):
            i = combo.findData(value)
            combo.setCurrentIndex(max(0, i))
        self._filling = False
        self._apply()

    def show_opponent(self, name: str) -> None:
        self._search.setText(name)

    def _reset(self) -> None:
        self._filling = True
        self._search.clear()
        for combo in (self._competition, self._season_from, self._season_to, self._venue, self._result):
            combo.setCurrentIndex(0)
        self._filling = False
        self._apply()

    def _apply(self) -> None:
        if self._filling:
            return
        self.table.filter.set_filters(
            opponent=self._search.text().strip(),
            competition=self._competition.currentData() or "",
            season_from=self._season_from.currentData() or "",
            season_to=self._season_to.currentData() or "",
            venue=self._venue.currentData() or "",
            result=self._result.currentData() or "",
        )
        visible = self.table.filter.visible_matches()
        self._summary.setText(record_line(visible))
        if self._seasons_button.isChecked():
            self._fill_seasons(visible)

    # --- season by season

    SEASON_COLUMNS = ["Season", "League", "P", "W", "D", "L", "Goals", "All games", "W", "D", "L", "Goals", "Competitions"]

    def _make_seasons_table(self) -> QTableWidget:
        table = QTableWidget(0, len(self.SEASON_COLUMNS))
        table.setHorizontalHeaderLabels(self.SEASON_COLUMNS)
        table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setShowGrid(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(len(self.SEASON_COLUMNS) - 1, QHeaderView.Stretch)
        table.setToolTip("Double-click a season to see its games")
        table.cellDoubleClicked.connect(self._open_season)
        return table

    def _fill_seasons(self, matches: list[Match]) -> None:
        summaries = list(reversed(season_summaries(matches)))
        self._seasons.setRowCount(len(summaries))
        for row, s in enumerate(summaries):
            league_games = [m for m in matches if m.season == s.season and m.competition in ("Highland League", "Scottish League")]
            league = league_games[0].competition if league_games else ""
            values = [s.season, league,
                      s.league.played, s.league.won, s.league.drawn, s.league.lost,
                      f"{s.league.goals_for}-{s.league.goals_against}" if s.league.played else "",
                      s.all.played, s.all.won, s.all.drawn, s.all.lost, f"{s.all.goals_for}-{s.all.goals_against}",
                      ", ".join(c for c in s.competitions if c not in ("Highland League", "Scottish League"))]
            for col, value in enumerate(values):
                if isinstance(value, int) and col in (2, 7) and not value:
                    value = ""
                item = QTableWidgetItem(str(value))
                if col not in (0, 1, 12):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._seasons.setItem(row, col, item)

    def _toggle_seasons(self, on: bool) -> None:
        self._stack.setCurrentIndex(1 if on else 0)
        if on:
            self._fill_seasons(self.table.filter.visible_matches())

    def _open_season(self, row: int, _col: int) -> None:
        season = self._seasons.item(row, 0).text()
        self._filling = True
        for combo in (self._season_from, self._season_to):
            combo.setCurrentIndex(max(0, combo.findData(season)))
        self._filling = False
        self._seasons_button.setChecked(False)
        self._apply()

    def _show_selected(self) -> None:
        m = self.table.selected_match()
        self._h2h_button.setEnabled(m is not None)
        if m:
            self._detail.setText(match_details_html(m))
            self._h2h_button.setText(f"Head to head v {m.opponent}")

    def _open_h2h(self) -> None:
        m = self.table.selected_match()
        if m:
            self.head_to_head_requested.emit(m.opponent)
