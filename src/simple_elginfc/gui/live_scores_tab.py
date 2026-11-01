"""The Live Scores tab: a page for each Scottish league, its games today
(live as they happen) on the left and its table on the right. On a day
a league has no games, it shows the last results and the next fixtures."""
from __future__ import annotations

import html
from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QScrollArea, QVBoxLayout, QWidget

from simple_elginfc.core.scoreboard import CUPS, LEAGUES, LeagueBoard
from simple_elginfc.core.sources.bbc import DONE, LIVE, PRE, Game
from simple_elginfc.gui.club_tab import card, rich
from simple_elginfc.gui.style import BLACK, LINE, LOSS_COLOUR, MUTED, RESULT_COLOURS

ELGIN = "Elgin City"
LIVE_RED = "#c62828"
NAMES = {k: n for k, n, _ in LEAGUES + CUPS}


def _kickoff(iso: str) -> str:
    """Local kick-off time; "" when there isn't one yet (midnight in the feed)."""
    if not iso or iso.endswith("T00:00:00Z"):
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%H:%M")
    except ValueError:
        return ""


def _day(iso: str) -> str:
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return iso
    return "Today" if d == date.today() else f"{d:%A} {d.day} {d:%B}"


def _reds(n: int) -> str:
    return " " + "<span style='background:#d32f2f; color:#d32f2f'>▮</span>" * n if n else ""


def game_html(g: Game) -> str:
    live = g.state == LIVE
    if g.state == PRE:
        middle = f"<span style='color:{MUTED}'>{html.escape(_kickoff(g.kickoff) or 'TBC')}</span>"
        if g.status and g.status.lower() not in ("scheduled", ""):
            middle = f"<span style='color:{LOSS_COLOUR}'>{html.escape(g.status)}</span>"
    else:
        middle = f"<b>{g.home_score} - {g.away_score}</b>"
    if live:
        status = f"<b style='color:{LIVE_RED}'>● {html.escape(g.status or 'LIVE')}</b>"
    elif g.state == DONE:
        status = f"<span style='color:{MUTED}'>{html.escape(g.status or 'FT')}</span>"
    else:
        status = ""
    weight_home = "font-weight:700" if g.home == ELGIN else ""
    weight_away = "font-weight:700" if g.away == ELGIN else ""
    winner_home = g.state == DONE and g.home_score is not None and g.home_score > (g.away_score or 0)
    winner_away = g.state == DONE and g.away_score is not None and g.away_score > (g.home_score or 0)
    if winner_home:
        weight_home = "font-weight:700"
    if winner_away:
        weight_away = "font-weight:700"
    background = "background:#fff4f4;" if live else ""
    row = (f"<tr style='{background}'>"
           f"<td align=right width='42%' style='padding:8px 8px 2px 8px; {weight_home}'>{html.escape(g.home)}{_reds(g.home_reds)}</td>"
           f"<td align=center width='16%' style='padding:8px 4px 2px 4px; font-size:13pt'>{middle}</td>"
           f"<td width='42%' style='padding:8px 8px 2px 8px; {weight_away}'>{_reds(g.away_reds)}{html.escape(g.away)}</td></tr>")
    scorers_home = ", ".join(g.home_scorers)
    scorers_away = ", ".join(g.away_scorers)
    extra = []
    if g.half_time and g.state == DONE:
        extra.append(f"HT {g.half_time}")
    if g.note:
        extra.append(g.note)
    row += (f"<tr style='{background}'><td align=right style='padding:0 8px 8px 8px; color:{MUTED}; font-size:9pt'>"
            f"{html.escape(scorers_home)}</td>"
            f"<td align=center style='padding:0 4px 8px 4px; font-size:9pt'>{status}"
            f"{'<br><span style=color:' + MUTED + '>' + html.escape(' · '.join(extra)) + '</span>' if extra else ''}</td>"
            f"<td style='padding:0 8px 8px 8px; color:{MUTED}; font-size:9pt'>{html.escape(scorers_away)}</td></tr>"
            f"<tr><td colspan=3 style='border-bottom:1px solid {LINE}; font-size:1pt'>&nbsp;</td></tr>")
    return row


def games_html(title: str, games: list[Game]) -> str:
    if not games:
        return ""
    out = []
    by_day: dict[str, list[Game]] = {}
    for g in games:
        by_day.setdefault(g.date, []).append(g)
    for day, day_games in by_day.items():
        out.append(f"<p style='margin:10px 0 2px 0; color:{MUTED}; font-size:9pt; font-weight:700; letter-spacing:1px'>"
                   f"{html.escape((title + ' · ' if title else '') + _day(day)).upper()}</p>")
        out.append("<table cellspacing=0 width='100%'>" + "".join(game_html(g) for g in day_games) + "</table>")
    return "".join(out)


def table_html(board: LeagueBoard, rows=None, compact: bool = False) -> str:
    rows = board.rows() if rows is None else rows
    if not rows:
        return f"<span style='color:{MUTED}'>No table yet</span>"
    playing_now = {g.home for g in board.games() if g.state == LIVE} | {g.away for g in board.games() if g.state == LIVE}
    columns = [("", "right"), ("Team", "left"), ("P", "right"), ("W", "right"), ("D", "right"), ("L", "right"),
               ("GD", "right"), ("Pts", "right"), ("Form", "left")]
    if compact:
        columns = columns[:-1]
    head = "".join(f"<th align={a} style='padding:4px 6px; color:{MUTED}'>{h}</th>" for h, a in columns)
    body = []
    for r in rows:
        ours = r.team == ELGIN
        live = r.team in playing_now
        style = (f"background:{BLACK}; color:white; font-weight:700" if ours
                 else "background:#fff4f4" if live else "")
        form = "".join(f"<span style='color:{'white' if ours else RESULT_COLOURS.get(c, MUTED)}'>{c}</span>" for c in r.form)
        gd = r.goals_for - r.goals_against
        team = html.escape(r.team) + (f" <span style='color:{'white' if ours else LIVE_RED}'>●</span>" if live else "")
        cells = [str(r.rank), team, str(r.played), str(r.won), str(r.drawn), str(r.lost),
                 f"{gd:+d}" if gd else "0", f"<b>{r.points}</b>", form][:len(columns)]
        body.append(f"<tr style='{style}'>" + "".join(
            f"<td align={'left' if i in (1, 8) else 'right'} style='padding:4px 6px'>{c}</td>"
            for i, c in enumerate(cells)) + "</tr>")
    note = ""
    if playing_now and not compact:
        note = (f"<p style='color:{MUTED}; font-size:9pt'><span style='color:{LIVE_RED}'>●</span> playing now. "
                "BBC Sport's table, refreshed every minute while games are on.</p>")
    return f"<table cellspacing=0 width='100%'><tr>{head}</tr>{''.join(body)}</table>{note}"


def _round_order(games: list[Game]) -> list[tuple[str, list[Game]]]:
    """A cup's games by round, the most recent round first."""
    rounds: dict[str, list[Game]] = {}
    for g in games:
        rounds.setdefault(g.round or "Games", []).append(g)
    return sorted(rounds.items(), key=lambda kv: max(g.date for g in kv[1]), reverse=True)


def cup_games_html(board: LeagueBoard) -> str:
    parts = []
    today = board.games("today")
    if today:
        parts.append(games_html("", today))
    for name, games in _round_order(board.games("season")):
        games = [g for g in games if g not in today]
        if not games:
            continue
        parts.append(f"<p style='margin:16px 0 0 0; font-size:12pt; font-weight:800'>{html.escape(name)}</p>")
        parts.append(games_html("", games))
    return "".join(parts) or f"<span style='color:{MUTED}'>No games yet this season.</span>"


def cup_side_html(board: LeagueBoard) -> str:
    """Group tables where the cup has them, else its rounds at a glance;
    and Elgin's run in it either way."""
    parts = []
    tables = board.group_tables()
    for name, rows in tables:
        if len(tables) > 1:
            parts.append(f"<p style='margin:12px 0 2px 0; font-weight:800'>{html.escape(name)}</p>")
        parts.append(table_html(board, rows, compact=len(tables) > 1))
    if not tables:
        head = "".join(f"<th align={a} style='padding:4px 6px; color:{MUTED}'>{h}</th>"
                       for h, a in (("Round", "left"), ("When", "left"), ("Ties", "right"), ("Played", "right")))
        body = []
        for name, games in reversed(_round_order(board.games("season"))):
            dates = sorted({g.date for g in games})
            when = _day(dates[0]) if len(dates) == 1 else f"{_day(dates[0])} – {_day(dates[-1])}"
            played = sum(1 for g in games if g.state == DONE)
            body.append(f"<tr><td style='padding:4px 6px'><b>{html.escape(name)}</b></td>"
                        f"<td style='padding:4px 6px; color:{MUTED}'>{html.escape(when)}</td>"
                        f"<td align=right style='padding:4px 6px'>{len(games)}</td>"
                        f"<td align=right style='padding:4px 6px'>{played}</td></tr>")
        parts.append(f"<table cellspacing=0 width='100%'><tr>{head}</tr>{''.join(body)}</table>")
    ours = [g for g in board.games("season") if ELGIN in (g.home, g.away)]
    if ours:
        lines = []
        for g in ours:
            score = f"{g.home_score}-{g.away_score}" if g.home_score is not None else (_kickoff(g.kickoff) or "v")
            lines.append(f"<tr><td style='padding:3px 8px 3px 0; color:{MUTED}'>{html.escape(g.round)}</td>"
                         f"<td style='padding:3px 0'>{html.escape(g.home)} <b>{score}</b> {html.escape(g.away)}"
                         f"{' (' + html.escape(g.note) + ')' if g.note else ''}</td></tr>")
        parts.append(f"<p style='margin:16px 0 4px 0; font-weight:800'>Elgin City in the {html.escape(board.name)}</p>"
                     f"<table cellspacing=0>{''.join(lines)}</table>")
    return "".join(parts)


class LiveScoresTab(QWidget):
    league_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._boards: dict[str, LeagueBoard] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        self._leagues = QListWidget()
        self._leagues.setFixedWidth(230)
        self._leagues.setStyleSheet("QListWidget::item { padding: 10px 8px; }")
        for heading, entries in (("LEAGUES", LEAGUES), ("CUPS", CUPS)):
            header = QListWidgetItem(heading)
            header.setFlags(Qt.NoItemFlags)  # a heading, not a page
            header.setForeground(Qt.gray)
            self._leagues.addItem(header)
            for key, name, _ in entries:
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, key)
                self._leagues.addItem(item)
        self._leagues.currentItemChanged.connect(
            lambda item, _prev: item and item.data(Qt.UserRole) and self._show(item.data(Qt.UserRole)))
        side = QVBoxLayout()
        side.addWidget(self._leagues, stretch=1)
        self._updated = QLabel()
        self._updated.setObjectName("muted")
        self._updated.setWordWrap(True)
        side.addWidget(self._updated)
        layout.addLayout(side)

        self._games_card, gl = card("Games")
        self._games = rich()
        gl.addWidget(self._games)
        # (pinned to the top, a wrapping label isn't given the height it needs;
        # a stretch under it keeps it at the top instead)
        gl.setAlignment(Qt.Alignment())
        gl.addStretch()
        games_scroll = QScrollArea()
        games_scroll.setWidgetResizable(True)
        games_scroll.setFrameShape(QFrame.NoFrame)
        games_scroll.setWidget(self._games_card)
        layout.addWidget(games_scroll, stretch=5)

        self._table_card, tl = card("Table")
        self._table = rich()
        tl.addWidget(self._table)
        tl.setAlignment(Qt.Alignment())
        tl.addStretch()
        table_scroll = QScrollArea()
        table_scroll.setWidgetResizable(True)
        table_scroll.setFrameShape(QFrame.NoFrame)
        table_scroll.setWidget(self._table_card)
        layout.addWidget(table_scroll, stretch=4)

        self._games.setText(f"<span style='color:{MUTED}'>Fetching the scores…</span>")

    def select(self, key: str) -> None:
        for i in range(self._leagues.count()):
            if self._leagues.item(i).data(Qt.UserRole) == key:
                self._leagues.setCurrentRow(i)
                return

    def current(self) -> str:
        item = self._leagues.currentItem()
        return (item.data(Qt.UserRole) if item else None) or LEAGUES[0][0]

    def show_boards(self, boards: dict[str, LeagueBoard]) -> None:
        self._boards = boards
        for i in range(self._leagues.count()):
            item = self._leagues.item(i)
            key = item.data(Qt.UserRole)
            if not key:
                continue  # a heading
            name = NAMES[key]
            b = boards.get(key)
            if b and b.live_count:
                item.setText(f"{name}   ● {b.live_count} live")
                item.setForeground(Qt.red)
            elif b and b.any_today:
                item.setText(f"{name}   ({len(b.today)} today)")
                item.setForeground(Qt.black)
            else:
                item.setText(name)
                item.setForeground(Qt.black)
        if self._leagues.currentItem() is None:
            # open on a league with games on, else the Premiership
            live = next((k for k, _, _ in LEAGUES + CUPS if boards.get(k) and boards[k].live_count), None)
            today = next((k for k, _, _ in LEAGUES + CUPS if boards.get(k) and boards[k].any_today), None)
            self.select(live or today or LEAGUES[0][0])
        else:
            self._show(self.current())
        newest = max((b.updated for b in boards.values()), default=0)
        if newest:
            self._updated.setText(f"From BBC Sport · updated {datetime.fromtimestamp(newest):%H:%M:%S}")

    def _show(self, key: str) -> None:
        self.league_changed.emit(key)
        board = self._boards.get(key)
        name = NAMES.get(key, key)
        is_cup = key in {k for k, _, _ in CUPS}
        self._games_card.findChild(QLabel, "cardTitle").setText(f"{name.upper()} · {'ROUNDS' if is_cup else 'GAMES'}")
        side = "TABLE" if not is_cup else ("TABLES" if board and len(board.groups) > 1 else
                                          "TABLE" if board and board.groups else "ROUNDS")
        self._table_card.findChild(QLabel, "cardTitle").setText(f"{name.upper()} · {side}")
        if board is None:
            self._games.setText(f"<span style='color:{MUTED}'>Fetching the scores…</span>")
            self._table.setText("")
            return
        if board.kind == "cup":
            self._games.setText(cup_games_html(board))
            self._table.setText(cup_side_html(board))
            return
        today = board.games("today")
        parts = []
        if today:
            parts.append(games_html("", today))
        else:
            parts.append(f"<p style='color:{MUTED}'>No {html.escape(name)} games today.</p>")
            parts.append(games_html("Latest results", board.games("recent")))
        parts.append(games_html("Next", board.games("upcoming")))
        self._games.setText("".join(p for p in parts if p))
        self._table.setText(table_html(board))
