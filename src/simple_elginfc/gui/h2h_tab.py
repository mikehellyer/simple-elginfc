"""The Head to Head tab: pick an opponent and see every game Elgin City
have played against them, with the record and its highlights. The games
can be saved as a spreadsheet (CSV)."""
from __future__ import annotations

import csv
import html
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QCompleter, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSplitter,
                               QVBoxLayout, QWidget)

from simple_elginfc.core.models import Match
from simple_elginfc.core.stats import HeadToHead, Record, head_to_head, opponents_matching
from simple_elginfc.gui.club_tab import card, rich
from simple_elginfc.gui.match_table import VENUE_NAMES, MatchTable, nice_date
from simple_elginfc.gui.matches_tab import match_details_html
from simple_elginfc.gui.style import DRAW_COLOUR, LOSS_COLOUR, MUTED, WIN_COLOUR


def _when(m: Optional[Match]) -> str:
    return (nice_date(m.date) or m.season) if m else ""


def _game(m: Optional[Match]) -> str:
    if not m:
        return "—"
    where = {"H": "at home", "A": "away", "N": "on neutral ground"}.get(m.venue, "")
    return f"{m.score} {where}, {_when(m)} ({m.competition}{', ' + m.round if m.round else ''})"


def record_row(label: str, r: Record) -> str:
    if not r.played:
        return ""
    return (f"<tr><td style='padding:3px 16px 3px 0'><b>{html.escape(label)}</b></td>"
            f"<td align=right style='padding:3px 10px'>{r.played}</td>"
            f"<td align=right style='padding:3px 10px; color:{WIN_COLOUR}'><b>{r.won}</b></td>"
            f"<td align=right style='padding:3px 10px; color:{DRAW_COLOUR}'><b>{r.drawn}</b></td>"
            f"<td align=right style='padding:3px 10px; color:{LOSS_COLOUR}'><b>{r.lost}</b></td>"
            f"<td align=right style='padding:3px 10px'>{r.goals_for}-{r.goals_against}</td>"
            f"<td align=right style='padding:3px 0 3px 10px'>{r.win_percent:.0f}%</td></tr>")


def records_table(rows: list[tuple[str, Record]]) -> str:
    head = "".join(f"<th align=right style='padding:3px 10px; color:{MUTED}'>{h}</th>" for h in ("P", "W", "D", "L", "Goals", "Won"))
    body = "".join(record_row(label, r) for label, r in rows)
    return f"<table cellspacing=0><tr><th></th>{head}</tr>{body}</table>"


def save_csv(path: Path, matches: list[Match]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Date", "Season", "Competition", "Round", "Opponent", "Venue", "Elgin", "Opponent goals",
                    "Result", "Home team", "Score", "Away team", "Attendance", "Ground", "Elgin scorers", "Note"])
        for m in matches:
            w.writerow([m.date or "", m.season, m.competition, m.round, m.opponent, VENUE_NAMES.get(m.venue, m.venue),
                        "" if m.elgin_goals is None else m.elgin_goals,
                        "" if m.opponent_goals is None else m.opponent_goals, m.result, m.home_team,
                        m.home_away_score, m.away_team, m.attendance or "", m.ground, "; ".join(m.elgin_scorers), m.note])


class ResultBar(QWidget):
    """Won, drawn and lost as one bar, in proportion."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(14)
        self._parts = (0, 0, 0)

    def set_record(self, r: Record) -> None:
        self._parts = (r.won, r.drawn, r.lost)
        self.update()

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QColor, QPainter, QPainterPath

        total = sum(self._parts)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(self.rect(), 7, 7)
        p.setClipPath(clip)
        p.fillRect(self.rect(), QColor("#e6e6ea"))
        x = 0.0
        for n, colour in zip(self._parts, (WIN_COLOUR, DRAW_COLOUR, LOSS_COLOUR)):
            if total and n:
                w = self.width() * n / total
                p.fillRect(int(x), 0, int(round(x + w)) - int(x), self.height(), QColor(colour))
                x += w


class HeadToHeadTab(QWidget):
    show_in_matches = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._matches: list[Match] = []
        self._h2h: Optional[HeadToHead] = None
        self._counts: dict[str, int] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        # left: find the opponent
        left = QVBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Find an opponent…")
        self._search.setClearButtonEnabled(True)
        self._completer_model = QStringListModel(self)
        completer = QCompleter(self._completer_model, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.activated.connect(self._pick_name)
        self._search.setCompleter(completer)
        self._list = QListWidget()
        self._list.setMinimumWidth(240)
        self._list.setMaximumWidth(320)
        self._related = QCheckBox("Include former names and mergers")
        self._related.setToolTip("e.g. count Inverness Caledonian and Inverness Thistle with Inverness Caledonian Thistle")
        left.addWidget(self._search)
        left.addWidget(self._list, stretch=1)
        left.addWidget(self._related)
        layout.addLayout(left)

        # right: the record
        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        right.setWidget(page)
        rl = QVBoxLayout(page)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(12)

        top = QHBoxLayout()
        self._title = QLabel("Pick an opponent")
        self._title.setStyleSheet("font-size: 20pt; font-weight: 800;")
        self._title.setTextFormat(Qt.RichText)
        top.addWidget(self._title, stretch=1)
        self._to_matches = QPushButton("Show in Matches")
        self._to_matches.clicked.connect(lambda: self._h2h and self.show_in_matches.emit(self._search_name()))
        self._export = QPushButton("Save as spreadsheet…")
        self._export.clicked.connect(self._save)
        top.addWidget(self._to_matches)
        top.addWidget(self._export)
        rl.addLayout(top)

        self._numbers = QHBoxLayout()
        self._number_labels = {}
        for key, label, colour in (("played", "Played", None), ("won", "Won", WIN_COLOUR), ("drawn", "Drawn", DRAW_COLOUR),
                                   ("lost", "Lost", LOSS_COLOUR), ("goals", "Goals", None), ("percent", "Won %", None)):
            frame, fl = card(label)
            value = QLabel("–")
            value.setObjectName("big")
            if colour:
                value.setStyleSheet(f"color: {colour};")
            fl.addWidget(value)
            self._number_labels[key] = value
            self._numbers.addWidget(frame)
        rl.addLayout(self._numbers)
        self._bar = ResultBar()
        rl.addWidget(self._bar)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self._venues_card, vl = card("Home and away")
        self._venues = rich()
        vl.addWidget(self._venues)
        self._comps_card, cl = card("By competition")
        self._comps = rich()
        cl.addWidget(self._comps)
        self._facts_card, fl2 = card("Highlights")
        self._facts = rich()
        fl2.addWidget(self._facts)
        grid.addWidget(self._venues_card, 0, 0)
        grid.addWidget(self._comps_card, 0, 1)
        grid.addWidget(self._facts_card, 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        rl.addLayout(grid)

        split = QSplitter(Qt.Vertical)
        self._table = MatchTable(hide=("Opponent",))
        self._table.setMinimumHeight(260)
        split.addWidget(self._table)
        detail = QFrame()
        detail.setObjectName("card")
        dl = QVBoxLayout(detail)
        self._detail = rich(f"<span style='color:{MUTED}'>Pick a game to see its details.</span>")
        dl.addWidget(self._detail)
        split.addWidget(detail)
        rl.addWidget(split, stretch=1)
        layout.addWidget(right, stretch=1)

        self._search.textChanged.connect(self._filter_list)
        self._list.currentItemChanged.connect(self._list_picked)
        self._related.toggled.connect(lambda _: self._refresh())
        self._table.selectionModel().selectionChanged.connect(self._show_selected)
        self._set_enabled(False)

    # --- data in

    def set_matches(self, matches: list[Match]) -> None:
        self._matches = matches
        self._counts = {}
        for m in matches:
            self._counts[m.opponent] = self._counts.get(m.opponent, 0) + 1
        self._completer_model.setStringList(sorted(self._counts))
        current = self._current_club()
        self._filter_list(self._search.text())
        if current:
            self.select(current)

    def set_related(self, on: bool) -> None:
        self._related.setChecked(on)

    @property
    def include_related(self) -> bool:
        return self._related.isChecked()

    def select(self, name: str) -> None:
        """Show the head-to-head against one club."""
        self._search.blockSignals(True)
        self._search.setText(name)
        self._search.blockSignals(False)
        self._filter_list(name, keep=name)

    def current_name(self) -> str:
        return self._current_club() or ""

    # --- picking

    def _pick_name(self, name: str) -> None:
        self.select(name)

    def _filter_list(self, text: str, keep: str = "") -> None:
        names = opponents_matching(self._counts, text) if text.strip() else sorted(self._counts, key=lambda n: -self._counts[n])
        exact = next((n for n in names if n.lower() == text.strip().lower()), None)
        self._list.blockSignals(True)
        self._list.clear()
        for n in names:
            item = QListWidgetItem(f"{n}  ({self._counts[n]})")
            item.setData(Qt.UserRole, n)
            self._list.addItem(item)
        self._list.blockSignals(False)
        want = keep or exact or (names[0] if len(names) == 1 else "")
        if want:
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.UserRole) == want:
                    self._list.setCurrentRow(i)
                    return
        if not self._h2h:
            self._set_enabled(False)

    def _list_picked(self, item, _previous=None) -> None:
        if item is not None:
            self._refresh()

    def _current_club(self) -> Optional[str]:
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item else (self._h2h.clubs[0] if self._h2h and len(self._h2h.clubs) == 1 else None)

    def _search_name(self) -> str:
        return self._current_club() or self._search.text()

    # --- showing

    def _set_enabled(self, on: bool) -> None:
        for w in (self._to_matches, self._export):
            w.setEnabled(on)

    def _refresh(self) -> None:
        club = self._current_club()
        if not club:
            return
        h = head_to_head(self._matches, [club], include_related=self._related.isChecked())
        self._h2h = h
        self._set_enabled(True)
        others = [c for c in h.clubs if c != club]
        self._title.setText(f"Elgin City v {club}")
        self._title.setToolTip("Includes " + ", ".join(others) if others else "")
        if others:
            self._title.setText(f"Elgin City v {club} <span style='font-size:11pt; color:{MUTED}'>(with {html.escape(', '.join(others))})</span>")
        r = h.overall
        self._number_labels["played"].setText(str(r.played))
        self._number_labels["won"].setText(str(r.won))
        self._number_labels["drawn"].setText(str(r.drawn))
        self._number_labels["lost"].setText(str(r.lost))
        self._number_labels["goals"].setText(f"{r.goals_for}-{r.goals_against}")
        self._number_labels["percent"].setText(f"{r.win_percent:.0f}%" if r.played else "–")
        self._bar.set_record(r)
        self._venues.setText(records_table([("Home", h.home), ("Away", h.away), ("Neutral", h.neutral), ("All", h.overall)]))
        self._comps.setText(records_table(list(h.by_competition.items())))
        facts = [
            ("First meeting", _game(h.first)),
            ("Last meeting", _game(h.last)),
            ("Biggest win", _game(h.biggest_win)),
            ("Biggest defeat", _game(h.biggest_defeat)),
            ("Most goals", _game(h.highest_scoring)),
        ]
        if h.best_attendance:
            facts.append(("Biggest crowd", f"{h.best_attendance.attendance:,} — {_game(h.best_attendance)}"))
        if h.overall.played:
            facts.append(("Longest unbeaten run", f"{h.longest_unbeaten} games"))
            facts.append(("Longest run without a win", f"{h.longest_winless} games"))
            facts.append(("Form now", h.current_run))
        if h.top_scorers:
            facts.append(("Elgin's scorers (since 2020)", ", ".join(f"{n} {g}" for n, g in h.top_scorers)))
        if h.next_fixture:
            n = h.next_fixture
            facts.append(("Next meeting", f"{nice_date(n.date)}, {'home' if n.venue == 'H' else 'away'} ({n.competition})"))
        self._facts.setText("<table cellspacing=0>" + "".join(
            f"<tr><td style='color:{MUTED}; padding:2px 16px 2px 0; white-space:nowrap'>{html.escape(k)}</td>"
            f"<td style='padding:2px 0'>{html.escape(v)}</td></tr>" for k, v in facts) + "</table>")
        self._table.set_matches(h.matches)
        self._detail.setText(f"<span style='color:{MUTED}'>Pick a game to see its details.</span>")
        if self._related.isChecked() and len(h.clubs) > 1:
            self._table.showColumn(4)
        else:
            self._table.hideColumn(4)

    def _show_selected(self) -> None:
        m = self._table.selected_match()
        if m:
            self._detail.setText(match_details_html(m))

    def _save(self) -> None:
        if not self._h2h:
            return
        club = self._current_club() or "opponent"
        default = Path.home() / f"Elgin City v {club}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save the games as a spreadsheet", str(default), "CSV (*.csv)")
        if path:
            save_csv(Path(path), self._h2h.matches)

