from simple_elginfc.core import stats
from simple_elginfc.core.models import AWAY, HOME, NEUTRAL, Match


def game(day, eg, og, venue=HOME, opponent="Clachnacuddin", comp="Highland League", **kw):
    return Match(season=f"{day[:4]}-{int(day[2:4]) + 1:02d}", competition=comp, opponent=opponent, venue=venue,
                 date=day, elgin_goals=eg, opponent_goals=og, **kw)


GAMES = [
    game("1950-08-01", 5, 0),
    game("1950-09-01", 1, 3, AWAY),
    game("1951-08-01", 2, 2, NEUTRAL, comp="North of Scotland Cup"),
    game("1951-09-01", 4, 4, AWAY, note="abandoned after 60 mins"),
    game("1952-08-01", 3, 1, AWAY, attendance=900),
    game("1952-09-01", 2, 0),
    game("1952-10-01", 1, 0, opponent="Forres Mechanics"),
]


def test_record_skips_abandoned_and_other_clubs():
    h = stats.head_to_head(GAMES, ["Clachnacuddin"])
    r = h.overall
    assert (r.played, r.won, r.drawn, r.lost, r.goals_for, r.goals_against) == (5, 3, 1, 1, 13, 6)
    assert len(h.matches) == 6  # the abandoned game is still listed
    assert (h.home.played, h.away.played, h.neutral.played) == (2, 2, 1)
    assert list(h.by_competition) == ["Highland League", "North of Scotland Cup"]


def test_highlights():
    h = stats.head_to_head(GAMES, ["Clachnacuddin"])
    assert h.biggest_win.date == "1950-08-01"
    assert h.biggest_defeat.date == "1950-09-01"
    assert h.best_attendance.attendance == 900
    assert h.first.date == "1950-08-01" and h.last.date == "1952-09-01"
    assert h.longest_unbeaten == 3
    assert h.current_run == "2 wins in a row"


def test_related_clubs():
    games = [game("1990-08-01", 1, 0, opponent="Inverness Caledonian"),
             game("2001-08-01", 0, 2, opponent="Inverness Caledonian Thistle")]
    assert stats.head_to_head(games, ["Inverness Caledonian Thistle"]).overall.played == 1
    assert stats.head_to_head(games, ["Inverness Caledonian Thistle"], include_related=True).overall.played == 2


def test_scorer_goals():
    assert stats.scorer_goals("J. MacIver 9', 51'") == ("J. MacIver", 2)
    assert stats.scorer_goals("K. Hester 38' pen") == ("K. Hester", 1)


def test_current_run_wording():
    assert stats.current_run([game("2000-01-01", 1, 0), game("2000-02-01", 0, 0), game("2000-03-01", 0, 0)]) == "2 draws in a row"
    assert stats.current_run([game("2000-02-01", 1, 0), game("2000-03-01", 0, 0)]) == "unbeaten in 2"


def test_friendlies_listed_but_not_counted():
    games = [game("2020-09-12", 9, 0, comp="Friendly"), game("2020-10-17", 1, 0)]
    h = stats.head_to_head(games, ["Clachnacuddin"])
    assert h.overall.played == 1 and len(h.matches) == 2
