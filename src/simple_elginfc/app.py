import sys

from simple_elginfc import __version__


def self_test() -> int:
    """`Simple-ElginFC --self-test`: checks a built app has everything it
    needs bundled (the release workflow runs this on each OS). Exit code
    0 if so."""
    checks = {}
    try:
        from simple_elginfc.core.history import load_bundled

        built, matches = load_bundled()
        checks["match history"] = len(matches) > 3000 and bool(built)
    except Exception:
        checks["match history"] = False
    try:
        from simple_elginfc.core import stats
        from simple_elginfc.core.history import load_bundled

        h = stats.head_to_head(load_bundled()[1], ["Clachnacuddin"])
        checks["head to head"] = h.overall.played > 100
    except Exception:
        checks["head to head"] = False
    try:
        from simple_elginfc.core.players import load_bundled_rosters

        checks["player rosters"] = len(load_bundled_rosters()) > 100
    except Exception:
        checks["player rosters"] = False
    try:
        from simple_elginfc.core.sources import bbc

        checks["news parsing"] = bbc.parse_news(b"<rss><channel><item><title>Hi</title></item></channel></rss>")[0].title == "Hi"
    except Exception:
        checks["news parsing"] = False
    try:
        from simple_elginfc.core import club

        checks["club parsing"] = club.parse_infobox("{{Infobox football club|manager = [[A B|A]]}}")["manager"] == "[[A B|A]]"
    except Exception:
        checks["club parsing"] = False
    try:
        import certifi  # noqa: F401

        checks["certificates"] = True
    except Exception:
        checks["certificates"] = False
    report = ", ".join(f"{name}: {'ok' if ok else 'MISSING'}" for name, ok in checks.items())
    try:
        print(f"Simple-ElginFC {__version__} self-test — {report}", flush=True)
    except (AttributeError, OSError):  # no console (Windows GUI build)
        pass
    return 0 if all(checks.values()) else 1


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    # Qt is imported only now, so --self-test runs even where there's no
    # display or graphics libraries (the release workflow's build machines).
    from PySide6.QtWidgets import QApplication

    from simple_elginfc.core.diagnostics import enable_app_log, enable_crash_log, log_event
    from simple_elginfc.gui import style
    from simple_elginfc.gui.main_window import MainWindow

    enable_app_log(__version__)
    enable_crash_log()
    app = QApplication(sys.argv)
    app.setApplicationName("Simple-ElginFC")
    app.setDesktopFileName("simple-elginfc")
    style.apply(app)
    window = MainWindow()
    window.show()
    code = app.exec()
    log_event(f"event loop finished (code {code})")
    return code


if __name__ == "__main__":
    sys.exit(main())
