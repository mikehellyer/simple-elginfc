"""The Latest tab: results and fixtures around now (live during a game),
the league table, and the news."""
from __future__ import annotations

import html
from datetime import datetime
from email.utils import parsedate_to_datetime

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QScrollArea, QFrame, QVBoxLayout, QWidget

from simple_elginfc.core.live import Fixtures, LeagueTable, News
from simple_elginfc.core.sources.bbc import DONE, LIVE, PRE
from simple_elginfc.gui.club_tab import card, rich
from simple_elginfc.gui.match_table import nice_date
from simple_elginfc.gui.style import BLACK, INK, MUTED, RESULT_COLOURS, SHADE, result_chip


def _kickoff(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%H:%M")
    except ValueError:
        return ""


def _day_time(dt: datetime) -> str:
    """"3 Oct, 15:00" (strftime's %-d isn't there on Windows)."""
    return f"{dt.day} {dt:%b, %H:%M}"


def _ago(when: float) -> str:
    return _day_time(datetime.fromtimestamp(when)) if when else "not yet"


class LatestTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        left = QScrollArea()
        left.setWidgetResizable(True)
        left.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        left.setWidget(page)
        ll = QVBoxLayout(page)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(12)
        self._games_card, gl = card("Results & fixtures")
        self._games = rich()
        gl.addWidget(self._games)
        self._table_card, tl = card("League table")
        self._table = rich()
        tl.addWidget(self._table)
        ll.addWidget(self._table_card)
        ll.addWidget(self._games_card)
        ll.addStretch()
        layout.addWidget(left, stretch=3)

        news_card, nl = card("News")
        self._news = QListWidget()
        self._news.setWordWrap(True)
        self._news.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._news.setStyleSheet(
            "QListWidget { border: none; }"
            "QListWidget::item { padding: 8px 4px; border-bottom: 1px solid #ececf0; }"
            f"QListWidget::item:hover {{ background: {SHADE}; color: {INK}; }}"
            f"QListWidget::item:selected {{ background: {BLACK}; color: white; }}")
        self._news.itemActivated.connect(self._open)
        self._news.itemClicked.connect(self._open)
        nl.addWidget(self._news, stretch=1)
        hint = QLabel("Click a story to read it on BBC Sport.")
        hint.setObjectName("muted")
        nl.addWidget(hint)
        layout.addWidget(news_card, stretch=2)

    def show_fixtures(self, fixtures: Fixtures) -> None:
        events = fixtures.as_events()
        if not events:
            self._games.setText(f"<span style='color:{MUTED}'>Nothing yet — checking BBC Sport…</span>")
            return
        rows = []
        for e in reversed(events):  # newest first
            m = e.match
            if e.state == LIVE:
                status = f"<b style='color:#c62828'>{html.escape(e.status or 'LIVE')}</b>"
            elif e.state == PRE:
                status = html.escape(e.status) if e.status and e.status.lower() not in ("scheduled", "") else _kickoff(e.kickoff)
            else:
                status = result_chip(m.result) if m.played else html.escape(e.status)
            score = m.home_away_score if m.played else "v"
            colour = RESULT_COLOURS.get(m.result, BLACK) if e.state == DONE else BLACK
            bold_home = "font-weight:700" if m.home_team == "Elgin City" else ""
            bold_away = "font-weight:700" if m.away_team == "Elgin City" else ""
            scorers = ""
            if m.elgin_scorers:
                scorers = f"<br><span style='color:{MUTED}; font-size:9pt'>⚽ {html.escape(', '.join(m.elgin_scorers))}</span>"
            rows.append(
                f"<tr><td style='padding:6px 12px 6px 0; color:{MUTED}; white-space:nowrap'>{nice_date(m.date)}</td>"
                f"<td align=right style='padding:6px 8px; {bold_home}'>{html.escape(m.home_team)}</td>"
                f"<td align=center style='padding:6px 8px; font-weight:700; color:{colour}'>{score}</td>"
                f"<td style='padding:6px 8px; {bold_away}'>{html.escape(m.away_team)}{scorers}</td>"
                f"<td style='padding:6px 8px; color:{MUTED}'>{html.escape(m.competition)}</td>"
                f"<td align=center style='padding:6px 0 6px 8px'>{status}</td></tr>")
        self._games.setText(f"<table cellspacing=0 width='100%'>{''.join(rows)}</table>"
                            f"<p style='color:{MUTED}; font-size:9pt'>From BBC Sport · updated {_ago(fixtures.updated)}</p>")

    def show_table(self, table: LeagueTable) -> None:
        rows = table.as_rows()
        if not rows:
            self._table.setText(f"<span style='color:{MUTED}'>No table yet</span>")
            return
        self._table_card.findChild(QLabel, "cardTitle").setText((table.name or "League table").upper())
        head = "".join(f"<th align={a} style='padding:4px 8px; color:{MUTED}'>{h}</th>" for h, a in (
            ("", "right"), ("Team", "left"), ("P", "right"), ("W", "right"), ("D", "right"), ("L", "right"),
            ("GF", "right"), ("GA", "right"), ("GD", "right"), ("Pts", "right"), ("Form", "left")))
        body = []
        for r in rows:
            ours = r.team == "Elgin City"
            style = f"background:{BLACK}; color:white; font-weight:700" if ours else ""
            form = "".join(f"<span style='color:{RESULT_COLOURS.get(c, MUTED) if not ours else 'white'}'>{c}</span>" for c in r.form)
            gd = r.goals_for - r.goals_against
            cells = [str(r.rank), html.escape(r.team), str(r.played), str(r.won), str(r.drawn), str(r.lost),
                     str(r.goals_for), str(r.goals_against), f"{gd:+d}" if gd else "0", f"<b>{r.points}</b>", form]
            body.append(f"<tr style='{style}'>" + "".join(
                f"<td align={'left' if i in (1, 10) else 'right'} style='padding:4px 8px'>{c}</td>"
                for i, c in enumerate(cells)) + "</tr>")
        self._table.setText(f"<table cellspacing=0 width='100%'><tr>{head}</tr>{''.join(body)}</table>"
                            f"<p style='color:{MUTED}; font-size:9pt'>From BBC Sport · updated {_ago(table.updated)}</p>")

    def show_news(self, news: News) -> None:
        self._news.clear()
        for item in news.as_items():
            when = ""
            try:
                when = _day_time(parsedate_to_datetime(item.published).astimezone())
            except (TypeError, ValueError):
                pass
            entry = QListWidgetItem(f"{item.title}\n{item.summary}\n{when}")
            entry.setData(Qt.UserRole, item.link)
            entry.setToolTip(item.link)
            self._news.addItem(entry)
        if not self._news.count():
            self._news.addItem("No news yet")

    def _open(self, item: QListWidgetItem) -> None:
        link = item.data(Qt.UserRole)
        if link:
            QDesktopServices.openUrl(QUrl(link))
