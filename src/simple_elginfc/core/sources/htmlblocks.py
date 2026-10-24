"""Turning an HTML page into a plain stream of text and tables, in the
order they come on the page.

The archive pages are exported from Word, so everything that matters is
paragraphs and <table>s. Some pages put a whole season (its heading, its
cup ties as text, and its league grids as tables) inside the cells of one
big layout table. So a table that has another table inside it is treated
as layout: its cells' text comes out as text, in place, with the inner
tables between, rather than as one table read before everything in it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Optional, Union

Text = str
Table = list[list[str]]  # rows of cell texts
Block = Union[Text, Table]

_SKIP = {"script", "style", "head", "title"}
_BREAKS = {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6"}


def tidy(text: str) -> str:
    text = text.replace("\xa0", " ").replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class _OpenTable:
    rows: Table = field(default_factory=list)
    cell: Optional[list[str]] = None  # the open cell's text so far
    layout: bool = False  # has a table inside it


class _Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._text: list[str] = []  # text outside any table
        self._skip = 0
        self._tables: list[_OpenTable] = []

    # --- emitting, in page order

    def _emit_text(self, pieces: list[str]) -> None:
        text = tidy("".join(pieces))
        if text:
            self.blocks.append(text)

    def _flush_outside_text(self) -> None:
        self._emit_text(self._text)
        self._text = []

    def _become_layout(self, t: _OpenTable) -> None:
        """A table turns out to hold another: what's been read of it so far
        comes out as text now, before the inner table."""
        if t.layout:
            return
        t.layout = True
        for row in t.rows:
            for cell in row:
                self._emit_text([cell])
        t.rows = []
        if t.cell:
            self._emit_text(t.cell)
            t.cell = []

    # --- parsing

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        elif tag == "table":
            if self._tables:
                self._become_layout(self._tables[-1])
                if self._tables[-1].cell:
                    self._emit_text(self._tables[-1].cell)
                    self._tables[-1].cell = []
            else:
                self._flush_outside_text()
            self._tables.append(_OpenTable())
        elif self._tables and tag == "tr":
            self._close_cell()
            self._tables[-1].rows.append([])
        elif self._tables and tag in ("td", "th"):
            self._close_cell()
            self._tables[-1].cell = []
        elif tag in _BREAKS:
            self._piece("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag == "table" and self._tables:
            self._close_cell()
            t = self._tables.pop()
            if not t.layout:
                rows = [r for r in t.rows if any(c for c in r)]
                if rows:
                    self.blocks.append(rows)
        elif self._tables and tag in ("td", "th"):
            self._close_cell()
        elif tag in _BREAKS:
            self._piece("\n")

    def _close_cell(self) -> None:
        t = self._tables[-1]
        if t.cell is None:
            return
        if t.layout:
            self._emit_text(t.cell)
        else:
            if not t.rows:
                t.rows.append([])
            t.rows[-1].append(tidy("".join(t.cell)))
        t.cell = None

    def _piece(self, data: str) -> None:
        if self._tables:
            t = self._tables[-1]
            if t.cell is not None:
                t.cell.append(data)
            elif t.layout:
                self._emit_text([data])
            # (text between a plain table's cells is only whitespace)
        else:
            self._text.append(data)

    def handle_data(self, data):
        if not self._skip:
            self._piece(data)

    def close(self):
        super().close()
        while self._tables:
            self.handle_endtag("table")
        self._flush_outside_text()


def read_blocks(html: str) -> list[Block]:
    reader = _Reader()
    reader.feed(html)
    reader.close()
    return reader.blocks
