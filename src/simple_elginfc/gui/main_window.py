"""The main window: the tabs, the update banner, the menus, and keeping
everything up to date in the background."""
from __future__ import annotations

import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from PySide6.QtCore import QByteArray, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from simple_elginfc import __version__
from simple_elginfc.core import live
from simple_elginfc.core.diagnostics import log_event
from simple_elginfc.core.history import History
from simple_elginfc.core.models import season_start_year, season_of
from simple_elginfc.core.self_update import download_asset, find_asset_for_this_platform, launch_installer
from simple_elginfc.core.settings import SettingsStore
from simple_elginfc.core.sources.bbc import DONE, LIVE, PRE
from simple_elginfc.core.updater import API_TIMEOUT_SECONDS, check_for_update
from simple_elginfc.gui.club_tab import ClubTab
from simple_elginfc.gui.h2h_tab import HeadToHeadTab, save_csv
from simple_elginfc.gui.latest_tab import LatestTab
from simple_elginfc.gui.matches_tab import MatchesTab
from simple_elginfc.gui.update_banner import UpdateBanner
from simple_elginfc.gui.workers import BackgroundRunner

UPDATE_OWNER = "mikehellyer"
UPDATE_REPO = "simple-elginfc"
BACKGROUND_JOIN_TIMEOUT_MS = (max(API_TIMEOUT_SECONDS, live.TIMEOUT) + 1) * 1000
ICON_PATH = Path(__file__).parent / "resources" / "icon.png"
SERVICE_MS = 30_000  # how often to see what wants fetching

# how often each kind of data is fetched, in seconds
EVERY = {"fixtures": 10 * 60, "fixtures_live": 60, "table": 60 * 60, "news": 20 * 60, "club": 12 * 60 * 60}

CLUB_TAB, MATCHES_TAB, H2H_TAB, LATEST_TAB = range(4)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Simple-ElginFC")
        if ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1360, 860)

        self._store = SettingsStore()
        self._runner = BackgroundRunner(self)
        self._cache = live.Cache()
        self._history = History()
        self._pending_update = None
        self._last_fetch: dict[str, float] = {}
        self._busy: set[str] = set()
        self._fixtures = self._cache.load_fixtures()
        self._table = self._cache.load_table()
        self._news = self._cache.load_news()
        self._club = self._cache.load_club()
        self._finished_ids: set[str] = {e.match.date + e.match.opponent for e in self._fixtures.as_events() if e.state == DONE}

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._update_banner = UpdateBanner()
        self._update_banner.update_clicked.connect(self._start_update)
        layout.addWidget(self._update_banner)
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._club_tab = ClubTab()
        self._matches_tab = MatchesTab()
        self._h2h_tab = HeadToHeadTab()
        self._latest_tab = LatestTab()
        self._tabs.addTab(self._club_tab, "Club")
        self._tabs.addTab(self._matches_tab, "Matches")
        self._tabs.addTab(self._h2h_tab, "Head to Head")
        self._tabs.addTab(self._latest_tab, "Latest")
        layout.addWidget(self._tabs)
        self.setCentralWidget(central)

        self._matches_tab.head_to_head_requested.connect(self._open_h2h)
        self._h2h_tab.show_in_matches.connect(self._open_in_matches)
        self._build_menus()

        self._show_history()
        self._club_tab.show_club(self._club)
        self._show_live()
        self._h2h_tab.set_related(self._store.settings.h2h_related)
        if self._store.settings.h2h_opponent:
            self._h2h_tab.select(self._store.settings.h2h_opponent)
        self._tabs.setCurrentIndex(self._store.settings.tab)
        if self._store.settings.geometry:
            self.restoreGeometry(QByteArray.fromHex(self._store.settings.geometry.encode()))

        self._service_timer = QTimer(self)
        self._service_timer.timeout.connect(self._service)
        self._service_timer.start(SERVICE_MS)
        QTimer.singleShot(200, self._start_fetching)
        QTimer.singleShot(3000, self._check_for_updates)

    # --- menus

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        export = QAction("Save every match as a spreadsheet…", self)
        export.triggered.connect(self._export_all)
        file_menu.addAction(export)
        file_menu.addSeparator()
        quit_ = QAction("Quit", self)
        quit_.setShortcut(QKeySequence.Quit)
        quit_.triggered.connect(self.close)
        file_menu.addAction(quit_)

        view = self.menuBar().addMenu("&View")
        for i, name in enumerate(("Club", "Matches", "Head to Head", "Latest")):
            action = QAction(name, self)
            action.setShortcut(QKeySequence(f"Ctrl+{i + 1}"))
            action.triggered.connect(lambda _=False, i=i: self._tabs.setCurrentIndex(i))
            view.addAction(action)
        view.addSeparator()
        refresh = QAction("Refresh now", self)
        refresh.setShortcut(QKeySequence.Refresh)
        refresh.triggered.connect(self._refresh_now)
        view.addAction(refresh)

        help_menu = self.menuBar().addMenu("&Help")
        sources = QAction("Where the data comes from", self)
        sources.triggered.connect(self._sources)
        help_menu.addAction(sources)
        check = QAction("Check for updates", self)
        check.triggered.connect(lambda: self._check_for_updates(tell=True))
        help_menu.addAction(check)
        about = QAction("About Simple-ElginFC", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    # --- showing

    def _show_history(self) -> None:
        matches = self._history.matches
        self._matches_tab.set_matches(matches)
        self._h2h_tab.set_matches(matches)
        played = sum(1 for m in matches if m.played)
        first = matches[0].season[:4] if matches else ""
        self.statusBar().showMessage(f"{played:,} games known, from {first} to today")

    def _show_live(self) -> None:
        self._club_tab.show_live(self._fixtures, self._table, self._history.matches)
        self._latest_tab.show_fixtures(self._fixtures)
        self._latest_tab.show_table(self._table)
        self._latest_tab.show_news(self._news)

    def _open_h2h(self, opponent: str) -> None:
        self._h2h_tab.select(opponent)
        self._tabs.setCurrentIndex(H2H_TAB)

    def _open_in_matches(self, opponent: str) -> None:
        self._matches_tab.show_opponent(opponent)
        self._tabs.setCurrentIndex(MATCHES_TAB)

    # --- fetching

    def _start_fetching(self) -> None:
        for kind in ("fixtures", "table", "news", "club"):
            self._fetch(kind)
        self._fetch_season()

    def _refresh_now(self) -> None:
        self._last_fetch.clear()
        self._start_fetching()
        self.statusBar().showMessage("Refreshing…", 3000)

    def _match_on(self) -> bool:
        """Is a game on now, or about to start? Then results come every minute."""
        now = datetime.now(timezone.utc)
        for e in self._fixtures.as_events():
            if e.state == LIVE:
                return True
            if e.state == PRE and e.kickoff:
                try:
                    kick = datetime.fromisoformat(e.kickoff.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if kick - timedelta(minutes=10) <= now <= kick + timedelta(hours=2, minutes=30):
                    return True
        return False

    def _service(self) -> None:
        now = time.time()
        fixtures_every = EVERY["fixtures_live"] if self._match_on() else EVERY["fixtures"]
        due = {"fixtures": fixtures_every, "table": EVERY["table"], "news": EVERY["news"], "club": EVERY["club"]}
        for kind, every in due.items():
            if now - self._last_fetch.get(kind, 0) >= every:
                self._fetch(kind)

    def _fetch(self, kind: str) -> None:
        if kind in self._busy:
            return
        self._busy.add(kind)
        self._last_fetch[kind] = time.time()
        job = {"fixtures": live.fetch_fixtures, "table": live.fetch_table, "news": live.fetch_news,
               "club": live.fetch_club}[kind]
        self._runner.run(job, lambda result, kind=kind: self._fetched(kind, result),
                         lambda error, kind=kind: self._fetch_failed(kind, error))

    def _fetch_failed(self, kind: str, error: Exception) -> None:
        self._busy.discard(kind)
        log_event(f"fetching {kind} failed: {error!r}")

    def _fetched(self, kind: str, result) -> None:
        self._busy.discard(kind)
        if kind == "fixtures":
            self._fixtures = result
            self._cache.save_fixtures(result)
            done = [e for e in result.as_events() if e.state == DONE and e.match.played]
            new = {e.match.date + e.match.opponent for e in done} - self._finished_ids
            self._finished_ids |= new
            if done and self._history.add_recent([e.match for e in done]):
                self._show_history()
            if new:
                self._fetch("table")  # a game just finished: the table's changed
        elif kind == "table":
            self._table = result
            self._cache.save_table(result)
        elif kind == "news":
            self._news = result
            self._cache.save_news(result)
        elif kind == "club":
            self._club = result
            self._cache.save_club(result)
            self._club_tab.show_club(result)
        self._show_live()

    def _fetch_season(self) -> None:
        """Every result since the bundled history was built, to fill the gap."""
        built = date.fromisoformat(self._history.built) if self._history.built else date(2020, 1, 1)
        start = season_start_year(season_of(built - timedelta(days=7)))
        self._runner.run(lambda: live.fetch_season_results(start), self._season_fetched, lambda error: None)

    def _season_fetched(self, matches) -> None:
        if matches and self._history.add_recent(matches):
            self._show_history()
            self._show_live()

    # --- saving

    def _export_all(self) -> None:
        default = Path.home() / "Elgin City - every match.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Save every match as a spreadsheet", str(default), "CSV (*.csv)")
        if path:
            save_csv(Path(path), self._history.matches)

    # --- about & updates

    def _sources(self) -> None:
        QMessageBox.information(
            self,
            "Where the data comes from",
            "<b>Match history</b><br>"
            "Highland League, Highland League Cup, North of Scotland, Inverness, Scottish Qualifying, "
            "Elginshire Charity and Elgin District Cup results from 1893 to 2000: "
            "the <a href='http://sfha.org.uk/'>Scottish Football Historical Results Archive</a>, "
            "used for this non-profit app with thanks and acknowledgement.<br>"
            "Scottish Cup ties 1946–2016: the <a href='https://fchd.info/'>Football Club History Database</a> "
            "(Richard Rundle).<br>"
            "Scottish League and cup games 2001–2019, with crowds: ESPN.<br>"
            "Results, fixtures, goalscorers, the table and news since 2020: BBC Sport.<br><br>"
            "<b>The club</b><br>"
            "Club details, honours, records, squad and staff: Wikipedia. "
            "The board: the Companies House register (Elgin City Football Club Limited, SC207126). "
            "Badge © Elgin City FC.<br><br>"
            "<b>Known gaps</b><br>"
            "Elgin's first Scottish League season (2000–01), Scottish Cup ties before 1946, and the dates of "
            "Scottish Cup ties before 2001 aren't in the history yet.<br><br>"
            "For player-by-player records see <a href='https://www.fitbastats.com/elgin/'>FitbaStats</a>.",
        )

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About Simple-ElginFC",
            f"<b>Simple-ElginFC</b> v{__version__}<br><br>"
            "Everything about Elgin City Football Club: the club today, every game they've played, "
            "and their record against any opponent.<br><br>"
            "See Help → Where the data comes from for the sources.<br><br>"
            "By Mike Hellyer, built with Claude Code.",
        )

    def _check_for_updates(self, tell: bool = False) -> None:
        self._runner.run(
            lambda: check_for_update(__version__, UPDATE_OWNER, UPDATE_REPO),
            lambda info: self._on_update_checked(info, tell),
            lambda error: None,
        )

    def _on_update_checked(self, info, tell: bool = False) -> None:
        if info:
            self._pending_update = info
            self._update_banner.announce(info.version)
        elif tell:
            self.statusBar().showMessage(f"Simple-ElginFC v{__version__} is the latest version", 5000)

    def _start_update(self) -> None:
        if self._pending_update is None:
            return
        asset_url = find_asset_for_this_platform(self._pending_update.assets)
        if asset_url is None:
            self._update_banner.set_status(f"No installer for this platform — see {self._pending_update.url}")
            return
        self._update_banner.set_busy(True, "Downloading…")
        self._runner.run(lambda: download_asset(asset_url), self._on_update_downloaded, lambda error: self._on_update_downloaded(None))

    def _on_update_downloaded(self, path) -> None:
        if path is None:
            self._update_banner.set_status("Couldn't download the update — try again")
            self._update_banner.set_busy(False)
            return
        try:
            process = launch_installer(path)
        except OSError:
            self._update_banner.set_status(f"Downloaded to {path} — open it manually")
            self._update_banner.set_busy(False)
            return

        self._update_banner.set_status("Installer launched — closing to finish…")
        if sys.platform not in ("win32", "darwin") and process is not None:
            # Linux: wait for pkexec/apt to finish before quitting — quitting
            # immediately can kill its password prompt before it's answered.
            self._runner.run(lambda: (path, self._wait_for_installer(process)), self._on_installer_finished)
        else:
            QTimer.singleShot(1500, self.close)

    @staticmethod
    def _wait_for_installer(process) -> tuple[int, str]:
        returncode = process.wait()
        stderr_text = process.stderr.read().strip() if process.stderr is not None else ""
        return returncode, stderr_text

    def _on_installer_finished(self, result) -> None:
        path, (returncode, stderr_text) = result
        if returncode == 0:
            self.close()
            return
        detail = f": {stderr_text}" if stderr_text else f" (exit code {returncode})"
        self._update_banner.set_status(f"Update didn't install{detail} — installer is at {path}")
        self._update_banner.set_busy(False)

    def closeEvent(self, event) -> None:
        self._service_timer.stop()
        self._store.update(tab=self._tabs.currentIndex(), geometry=bytes(self.saveGeometry().toHex()).decode(),
                           h2h_opponent=self._h2h_tab.current_name(), h2h_related=self._h2h_tab.include_related)
        self._runner.shutdown(BACKGROUND_JOIN_TIMEOUT_MS)
        super().closeEvent(event)
