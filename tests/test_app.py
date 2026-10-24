from simple_elginfc import app
from simple_elginfc.core.history import load_bundled


def test_self_test_passes():
    assert app.self_test() == 0


def test_bundled_history_is_sound():
    built, matches = load_bundled()
    assert built
    assert len(matches) > 4000
    # the club's record win, from Wikipedia: 18-1 v Brora Rangers, 6 February 1960
    assert any(m.date == "1960-02-06" and m.opponent == "Brora Rangers" and m.score == "18-1" for m in matches)
    # no game against Elgin themselves, and every game has a season and a venue
    assert not any("Elgin City" == m.opponent for m in matches)
    assert all(m.season and m.venue in ("H", "A", "N") for m in matches)
