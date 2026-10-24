"""The Club tab: the badge and the club as it is now, with this season at
a glance, the people who run it, the squad, honours and records."""
from __future__ import annotations

import html
from datetime import date
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout,
                               QWidget)

from simple_elginfc.core.live import ClubDetails, Fixtures, LeagueTable
from simple_elginfc.core.models import Match, season_of
from simple_elginfc.core.sources.bbc import DONE, LIVE, PRE
from simple_elginfc.core.stats import club_records, counts, record
from simple_elginfc.gui.match_table import describe, nice_date
from simple_elginfc.gui.style import BLACK, MUTED, result_chip, title


def card(heading: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(6)
    layout.setAlignment(Qt.AlignTop)
    layout.addWidget(title(heading))
    return frame, layout


def rich(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.RichText)
    label.setWordWrap(True)
    label.setOpenExternalLinks(True)
    label.setTextInteractionFlags(Qt.TextBrowserInteraction)
    label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    return label


def rows_html(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return f"<span style='color:{MUTED}'>Not known yet</span>"
    body = "".join(f"<tr><td style='color:{MUTED}; padding:2px 14px 2px 0; white-space:nowrap'>{html.escape(k)}</td>"
                   f"<td style='padding:2px 0'>{html.escape(v)}</td></tr>" for k, v in rows)
    return f"<table cellspacing=0>{body}</table>"


class ClubTab(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        self.setWidget(page)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 16)
        outer.setSpacing(16)

        # the header: badge, name, and the facts everyone wants first
        header = QFrame()
        header.setStyleSheet(f"background: {BLACK};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(28, 22, 28, 22)
        hl.setSpacing(24)
        self._crest = QLabel()
        self._crest.setFixedSize(120, 120)
        self._crest.setAlignment(Qt.AlignCenter)
        self._crest.setStyleSheet("background: white; border-radius: 60px;")
        hl.addWidget(self._crest)
        names = QVBoxLayout()
        self._name = QLabel("Elgin City FC")
        self._name.setStyleSheet("color: white; font-size: 26pt; font-weight: 800;")
        self._facts = QLabel()
        self._facts.setStyleSheet("color: #d0d0d4; font-size: 11.5pt;")
        self._facts.setWordWrap(True)
        names.addStretch()
        names.addWidget(self._name)
        names.addWidget(self._facts)
        names.addStretch()
        hl.addLayout(names, stretch=1)
        outer.addWidget(header)

        grid = QGridLayout()
        grid.setContentsMargins(16, 0, 16, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        outer.addLayout(grid)

        self._last, last_l = card("Last result")
        self._last_body = rich()
        last_l.addWidget(self._last_body)
        self._next, next_l = card("Next match")
        self._next_body = rich()
        next_l.addWidget(self._next_body)
        self._table, table_l = card("League position")
        self._table_body = rich()
        table_l.addWidget(self._table_body)
        self._season, season_l = card("This season")
        self._season_body = rich()
        season_l.addWidget(self._season_body)
        for i, w in enumerate((self._last, self._next, self._table, self._season)):
            grid.addWidget(w, 0, i)

        self._ground, ground_l = card("Ground")
        self._ground_body = rich()
        ground_l.addWidget(self._ground_body)
        self._board, board_l = card("Board")
        self._board_body = rich()
        board_l.addWidget(self._board_body)
        self._staff, staff_l = card("Management & staff")
        self._staff_body = rich()
        staff_l.addWidget(self._staff_body)
        grid.addWidget(self._ground, 1, 0)
        grid.addWidget(self._board, 1, 1)
        grid.addWidget(self._staff, 1, 2, 1, 2)

        self._squad, squad_l = card("First-team squad")
        self._squad_body = rich()
        squad_l.addWidget(self._squad_body)
        self._honours, honours_l = card("Honours")
        self._honours_body = rich()
        honours_l.addWidget(self._honours_body)
        grid.addWidget(self._squad, 2, 0, 1, 2)
        grid.addWidget(self._honours, 2, 2, 1, 2)

        self._records, records_l = card("Club records")
        self._records_body = rich()
        records_l.addWidget(self._records_body)
        self._ours, ours_l = card("From the match history")
        self._ours_body = rich()
        ours_l.addWidget(self._ours_body)
        self._managers, managers_l = card("Managers since 2000")
        self._managers_body = rich()
        managers_l.addWidget(self._managers_body)
        grid.addWidget(self._records, 3, 0, 1, 2)
        grid.addWidget(self._ours, 3, 2)
        grid.addWidget(self._managers, 3, 3)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        for w in (self._last, self._next, self._table, self._season):
            w.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)

        self._sources = rich()
        self._sources.setContentsMargins(20, 0, 20, 0)
        self._sources.setObjectName("muted")
        outer.addWidget(self._sources)
        outer.addStretch()
        self.show_club(None)

    # --- filling in

    def show_club(self, details: Optional[ClubDetails]) -> None:
        if details is None:
            self._facts.setText("Founded 1893 · Borough Briggs, Elgin · Scottish League Two")
            self._crest.setText("<b style='font-size:30pt'>EC</b>")
            for body in (self._ground_body, self._board_body, self._staff_body, self._squad_body,
                         self._honours_body, self._records_body, self._managers_body):
                body.setText(f"<span style='color:{MUTED}'>Fetching…</span>")
            return
        info = details.info
        self._name.setText("Elgin City FC")
        facts = [f"“{info.nickname}”" if info.nickname else "", f"Founded {info.founded}" if info.founded else "",
                 info.ground, info.league]
        self._facts.setText(" · ".join(f for f in facts if f))
        if details.crest_png:
            pix = QPixmap()
            if pix.loadFromData(details.crest_png):
                self._crest.setPixmap(pix.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._ground_body.setText(rows_html([(k, v) for k, v in (
            ("Ground", info.ground), ("Capacity", info.capacity), ("Opened", info.ground_opened),
            ("Surface", info.ground_surface),
            ("Record crowd", next((v for k, v in details.records if k.lower().startswith("home attendance")), "")),
        ) if v]))
        board = [("Chairman", info.chairman)] if info.chairman else []
        for o in info.board:
            if info.chairman and o.name.split()[-1] == info.chairman.split()[-1] and o.name.split()[0] == info.chairman.split()[0]:
                continue  # already shown as chairman
            board.append((o.role, f"{o.name}  (since {o.appointed})" if o.appointed else o.name))
        self._board_body.setText(rows_html(board) + f"<p style='color:{MUTED}; font-size:9pt'>Directors and secretary "
                                 "from the Companies House register.</p>")
        self._staff_body.setText(rows_html(details.staff))
        squad = "".join(
            f"<tr><td style='color:{MUTED}; padding:1px 10px 1px 0; text-align:right'>{html.escape(p['no'])}</td>"
            f"<td style='padding:1px 10px 1px 0; color:{MUTED}'>{html.escape(p['pos'])}</td>"
            f"<td style='padding:1px 0'>{html.escape(p['name'])}"
            f"{' <span style=color:' + MUTED + '>— ' + html.escape(p['other']) + '</span>' if p['other'] else ''}</td></tr>"
            for p in details.squad)
        self._squad_body.setText(f"<table cellspacing=0>{squad}</table>" if squad else "Not known yet")
        self._honours_body.setText("".join(
            f"<p style='margin:0 0 6px 0'><b>{html.escape(c)}</b><br>{html.escape(v)}</p>" for c, v in details.honours))
        self._records_body.setText(rows_html(details.records))
        self._managers_body.setText("<br>".join(html.escape(m) for m in details.managers))
        updated = info.updated[:10]
        self._sources.setText(
            f"<span style='color:{MUTED}; font-size:9pt'>Club details from Wikipedia and Companies House"
            f"{', checked ' + nice_date(updated) if updated else ''}. Badge © Elgin City FC.</span>")

    def show_live(self, fixtures: Fixtures, table: LeagueTable, history: list[Match]) -> None:
        events = fixtures.as_events()
        done = [e for e in events if e.state == DONE and e.match.played]
        live = [e for e in events if e.state == LIVE]
        upcoming = [e for e in events if e.state == PRE and "postpon" not in e.status.lower()]
        if live:
            e = live[-1]
            self._last.findChild(QLabel, "cardTitle").setText("LIVE NOW")
            self._last_body.setText(self._match_html(e.match, f"<b style='color:#c62828'>{html.escape(e.status)}</b>"))
        else:
            self._last.findChild(QLabel, "cardTitle").setText("LAST RESULT")
            previous = done[-1].match if done else next((m for m in reversed(history) if counts(m) and m.date), None)
            self._last_body.setText(self._match_html(previous) if previous else "—")
        if upcoming:
            e = upcoming[0]
            m = e.match
            kick = e.kickoff[11:16] if len(e.kickoff) > 15 else ""
            when = f"{date.fromisoformat(m.date):%A} {nice_date(m.date)}" + (f", {self._local_time(e.kickoff)}" if kick else "")
            self._next_body.setText(
                f"<p style='font-size:14pt; margin:0'><b>{html.escape(m.home_team)}</b> v <b>{html.escape(m.away_team)}</b></p>"
                f"<p style='margin:2px 0'>{html.escape(when)}</p>"
                f"<p style='color:{MUTED}; margin:0'>{html.escape(m.competition)}{', ' + html.escape(m.round) if m.round else ''}</p>")
        else:
            self._next_body.setText(f"<span style='color:{MUTED}'>No fixture announced</span>")
        rows = table.as_rows()
        ours = next((r for r in rows if r.team == "Elgin City"), None)
        if ours:
            self._table_body.setText(
                f"<p style='font-size:26pt; font-weight:800; margin:0'>{_ordinal(ours.rank)}</p>"
                f"<p style='margin:0'>of {len(rows)} in {html.escape(table.name)}</p>"
                f"<p style='color:{MUTED}; margin:2px 0'>{ours.points} pts from {ours.played} · "
                f"W{ours.won} D{ours.drawn} L{ours.lost} · {ours.goals_for}-{ours.goals_against}</p>")
        else:
            self._table_body.setText(f"<span style='color:{MUTED}'>No table yet</span>")
        season = season_of(date.today())
        this = [m for m in history if m.season == season]
        r = record(this)
        home_crowds = [m.attendance for m in this if m.venue == "H" and m.attendance]
        crowd_line = ""
        if home_crowds:
            crowd_line = f"<br>Average home crowd {sum(home_crowds) // len(home_crowds):,}"
        else:
            crowds = self._latest_home_crowds(history)
            if crowds:
                crowd_line = f"<br><span style='color:{MUTED}'>Average home crowd {crowds[1]:,} ({crowds[0]})</span>"
        self._season_body.setText(
            f"<p style='font-size:15pt; margin:0'><b>P{r.played} W{r.won} D{r.drawn} L{r.lost}</b></p>"
            f"<p style='margin:2px 0'>Goals {r.goals_for}-{r.goals_against} in all competitions {crowd_line}</p>")
        cr = club_records(history)
        lines = [f"<b>{cr.total.played:,}</b> games known: {cr.total.won:,} won, {cr.total.drawn:,} drawn, {cr.total.lost:,} lost",
                 f"Goals {cr.total.goals_for:,}-{cr.total.goals_against:,}"]
        if cr.biggest_wins:
            m = cr.biggest_wins[0]
            lines.append(f"Biggest win: {m.score} v {html.escape(m.opponent)}, {nice_date(m.date) or m.season}")
        if cr.most_played:
            lines.append("Most played: " + ", ".join(f"{html.escape(o)} ({n})" for o, n in cr.most_played[:3]))
        self._ours_body.setText("<br>".join(lines))

    @staticmethod
    def _latest_home_crowds(history: list[Match]) -> Optional[tuple[str, int]]:
        by_season: dict[str, list[int]] = {}
        for m in history:
            if m.venue == "H" and m.attendance and m.competition == "Scottish League":
                by_season.setdefault(m.season, []).append(m.attendance)
        if not by_season:
            return None
        season = max(by_season)
        crowds = by_season[season]
        return season, sum(crowds) // len(crowds)

    @staticmethod
    def _local_time(iso: str) -> str:
        from datetime import datetime

        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%H:%M")
        except ValueError:
            return ""

    @staticmethod
    def _match_html(m: Match, extra: str = "") -> str:
        scorers = ", ".join(m.elgin_scorers)
        return (f"<p style='font-size:14pt; margin:0'>{result_chip(m.result)} "
                f"<b>{html.escape(m.home_team)} {m.home_away_score} {html.escape(m.away_team)}</b></p>"
                f"<p style='margin:2px 0'>{html.escape(describe(m).split(' · ')[0])} {extra}</p>"
                f"<p style='color:{MUTED}; margin:0'>{html.escape(m.competition)}"
                f"{'<br>Scorers: ' + html.escape(scorers) if scorers else ''}</p>")


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
