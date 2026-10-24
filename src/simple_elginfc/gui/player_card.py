"""A player's card, like a baseball card: his photo, number and name on
the front, with his details and Elgin goals underneath. The arrows (or
the arrow keys) go through the rest of the squad."""
from __future__ import annotations

import html
from datetime import date
from typing import Callable, Optional

from PySide6.QtCore import QObject, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from simple_elginfc.core import live
from simple_elginfc.core.models import Match
from simple_elginfc.core.players import Player, goals_for, joined_text
from simple_elginfc.gui.match_table import nice_date
from simple_elginfc.gui.style import BLACK, INK, LINE, MUTED

CARD_W, PHOTO_H = 360, 330
PHOTO_CREDIT = "Photo: Bob Crombie / Elgin City FC"


class PhotoLoader(QObject):
    """Players' photos: from the cache, or fetched in the background (and
    then cached). The callback gets the photo's bytes, or b"" if there's none."""

    def __init__(self, runner, cache: live.Cache, parent=None):
        super().__init__(parent)
        self._runner = runner
        self._cache = cache
        self._waiting: dict[str, list[Callable[[bytes], None]]] = {}

    def load(self, url: str, callback: Callable[[bytes], None]) -> None:
        if not url:
            callback(b"")
            return
        cached = self._cache.photo(url)
        if cached:
            callback(cached)
            return
        if url in self._waiting:
            self._waiting[url].append(callback)
            return
        self._waiting[url] = [callback]
        self._runner.run(lambda: self._download(url), lambda data, url=url: self._done(url, data),
                         lambda error, url=url: self._done(url, b""))

    @staticmethod
    def _download(url: str) -> bytes:
        try:
            return live.get_bytes(url)
        except OSError:
            # some players only have the smaller picture the squad page uses
            return live.get_bytes(url.replace("/_personPhotograph/", "/_newsArticleListing/"))

    def _done(self, url: str, data: bytes) -> None:
        if data:
            self._cache.save_photo(url, data)
        for callback in self._waiting.pop(url, []):
            callback(data)


class CardFront(QWidget):
    """The photo, with the number badge and the name banner painted over it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(CARD_W, PHOTO_H)
        self._photo: Optional[QPixmap] = None
        self._player: Optional[Player] = None
        self._crest: Optional[QPixmap] = None

    def set_player(self, player: Player, crest: Optional[QPixmap]) -> None:
        self._player, self._photo, self._crest = player, None, crest
        self.update()

    def set_photo(self, data: bytes) -> None:
        pix = QPixmap()
        self._photo = pix if data and pix.loadFromData(data) else None
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), 10, 10)
        p.setClipPath(clip)
        if self._photo and not self._photo.isNull():
            # fill the frame, keeping the top of the picture (the face) in it
            scaled = self._photo.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap(-(scaled.width() - w) // 2, 0, scaled)
        else:
            # no photo: black and white stripes, the club's colours
            stripe = w / 9
            for i in range(9):
                p.fillRect(QRectF(i * stripe, 0, stripe + 1, h), QColor(BLACK if i % 2 else "#f4f4f6"))
        player = self._player
        if not player:
            return
        # the name banner, slanted, across the bottom of the photo
        banner = QPainterPath()
        banner.moveTo(0, h - 70)
        banner.lineTo(w, h - 92)
        banner.lineTo(w, h)
        banner.lineTo(0, h)
        banner.closeSubpath()
        p.fillPath(banner, QColor(17, 17, 17, 235))
        p.setPen(QPen(QColor("white"), 2))
        p.drawLine(0, h - 70, w, h - 92)
        p.setPen(QColor("white"))
        f = QFont(self.font())
        f.setPointSizeF(19)
        f.setWeight(QFont.Black)
        f.setLetterSpacing(QFont.PercentageSpacing, 104)
        p.setFont(f)
        p.drawText(QRectF(16, h - 66, w - 32, 34), Qt.AlignLeft | Qt.AlignVCenter, player.name.upper())
        f.setPointSizeF(10.5)
        f.setWeight(QFont.DemiBold)
        f.setLetterSpacing(QFont.PercentageSpacing, 112)
        p.setFont(f)
        p.setPen(QColor("#d0d0d4"))
        detail = " · ".join(x for x in (player.position.upper(), player.note.upper() if "captain" in player.note.lower() else "") if x)
        p.drawText(QRectF(16, h - 32, w - 32, 22), Qt.AlignLeft | Qt.AlignVCenter, detail)
        # the shirt number, in a badge at the top left
        if player.number:
            p.setBrush(QColor("white"))
            p.setPen(QPen(QColor(BLACK), 3))
            p.drawEllipse(QRectF(12, 12, 58, 58))
            f.setPointSizeF(20 if len(player.number) < 3 else 15)
            f.setWeight(QFont.Black)
            f.setLetterSpacing(QFont.PercentageSpacing, 100)
            p.setFont(f)
            p.setPen(QColor(BLACK))
            p.drawText(QRectF(12, 12, 58, 58), Qt.AlignCenter, player.number)
        # and the crest at the top right
        if self._crest and not self._crest.isNull():
            p.drawPixmap(w - 58, 14, self._crest.scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation))


def _rows(player: Player, matches: list[Match], today: Optional[date] = None) -> list[tuple[str, str]]:
    rows = []
    age = player.age(today)
    if age is not None:
        b = date.fromisoformat(player.born)
        rows.append(("Age", f"{age}  (born {b.day} {b:%B %Y})"))
    if player.birthplace:
        rows.append(("From", player.birthplace))
    if player.nationality:
        rows.append(("Nationality", player.nationality))
    if player.height:
        rows.append(("Height", player.height))
    record = goals_for(player, matches)
    joined = joined_text(player, record)
    if joined:
        rows.append(("Joined", joined))
    if player.note and "captain" not in player.note.lower():
        rows.append(("Signed", player.note[0].upper() + player.note[1:]))
    if player.apps:
        rows.append(("League record", f"{player.apps} games, {player.goals or 0} goals"))
    if record.goals:
        rows.append(("Elgin goals", f"{record.goals} in {record.games} game{'s' if record.games != 1 else ''}"))
        if record.best_goals > 1:
            best = record.best
            rows.append(("Best game", f"{record.best_goals} goals v {best.opponent}, {nice_date(best.date) or best.season} "
                                      f"({best.score})"))
        last = record.last
        rows.append(("Last goal", f"v {last.opponent}, {nice_date(last.date) or last.season}"))
    elif player.position != "Goalkeeper":
        rows.append(("Elgin goals", "none yet"))
    clubs = [c for c in player.clubs if not c.startswith("→")]  # (not his loans)
    if clubs:
        rows.append(("Before Elgin", ", ".join(clubs[:3])))
    return rows


class PlayerCard(QDialog):
    def __init__(self, squad: list[Player], index: int, matches: list[Match], photos: PhotoLoader,
                 crest: Optional[QPixmap] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Player")
        self._squad, self._index, self._matches, self._photos, self._crest = squad, index, matches, photos, crest
        self.setStyleSheet(f"QDialog {{ background: {BLACK}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 12)
        outer.setSpacing(10)
        card = QWidget()
        card.setObjectName("playerCard")
        card.setStyleSheet(f"#playerCard {{ background: white; border-radius: 14px; }}")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(8, 8, 8, 10)
        cl.setSpacing(8)
        self._front = CardFront()
        cl.addWidget(self._front, alignment=Qt.AlignHCenter)
        self._details = QLabel()
        self._details.setTextFormat(Qt.RichText)
        self._details.setWordWrap(True)
        self._details.setFixedWidth(CARD_W)
        self._details.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._details.setStyleSheet(f"color: {INK}; background: white; padding: 2px 6px;")
        cl.addWidget(self._details)
        credit = QLabel(PHOTO_CREDIT)
        credit.setStyleSheet(f"color: {MUTED}; background: white; font-size: 8pt; padding: 0 6px;")
        self._credit = credit
        cl.addWidget(credit)
        outer.addWidget(card)

        nav = QHBoxLayout()
        self._prev = QPushButton("◀")
        self._next = QPushButton("▶")
        self._count = QLabel()
        self._count.setStyleSheet("color: #bdbdc2;")
        self._count.setAlignment(Qt.AlignCenter)
        for b in (self._prev, self._next):
            b.setFixedWidth(56)
            b.setStyleSheet(f"QPushButton {{ background: #2a2a2e; color: white; border: 1px solid #444; border-radius: 6px; padding: 5px; }}"
                            f"QPushButton:hover {{ border-color: white; }}")
        self._prev.clicked.connect(lambda: self._show(self._index - 1))
        self._next.clicked.connect(lambda: self._show(self._index + 1))
        nav.addWidget(self._prev)
        nav.addWidget(self._count, stretch=1)
        nav.addWidget(self._next)
        outer.addLayout(nav)
        self._show(index)

    def _show(self, index: int) -> None:
        self._index = index % len(self._squad)
        player = self._squad[self._index]
        self.setWindowTitle(player.name)
        self._front.set_player(player, self._crest)
        self._photos.load(player.photo_url, lambda data, name=player.name: self._photo_arrived(name, data))
        rows = _rows(player, self._matches)
        self._details.setText("<table cellspacing=0 width='100%'>" + "".join(
            f"<tr><td style='color:{MUTED}; padding:3px 12px 3px 0; white-space:nowrap; font-size:9pt; "
            f"text-transform:uppercase; letter-spacing:1px'>{html.escape(k)}</td>"
            f"<td style='padding:3px 0; border-bottom:1px solid {LINE}'>{html.escape(v)}</td></tr>"
            for k, v in rows) + "</table>")
        # rich text that wraps doesn't size itself: give it the height it needs
        self._details.setFixedHeight(self._details.heightForWidth(CARD_W))
        self._credit.setVisible(bool(player.photo_url))
        self._count.setText(f"{self._index + 1} of {len(self._squad)}")
        self.adjustSize()

    def _photo_arrived(self, name: str, data: bytes) -> None:
        if self._squad[self._index].name == name:  # still showing him
            self._front.set_photo(data)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Left, Qt.Key_Up):
            self._show(self._index - 1)
        elif event.key() in (Qt.Key_Right, Qt.Key_Down):
            self._show(self._index + 1)
        else:
            super().keyPressEvent(event)
