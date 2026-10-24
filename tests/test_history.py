from simple_elginfc.core.history import History, merge
from simple_elginfc.core.models import AWAY, HOME, Match


def m(**kw):
    base = dict(season="2010-11", competition="Scottish Cup", opponent="Livingston", venue=HOME,
                elgin_goals=2, opponent_goals=1)
    base.update(kw)
    return Match(**base)


def test_same_day_is_one_game_and_details_combine():
    espn = m(date="2010-11-20", round="Round 3", attendance=802, ground="Borough Briggs", source="espn")
    bbc = m(date="2010-11-20", elgin_scorers=["A. Player 10'"], source="bbc")
    (one,) = merge([espn], [bbc])
    assert one.attendance == 802 and one.elgin_scorers == ["A. Player 10'"] and one.source == "bbc+espn"


def test_undated_tie_folds_into_dated_copy():
    fchd = m(round="Third round", source="fchd")
    espn = m(date="2010-11-20", round="Round 3", source="espn")
    (one,) = merge([fchd], [espn])
    assert one.date == "2010-11-20"


def test_replay_kept_apart():
    first = m(round="Round 3", venue=AWAY, elgin_goals=0, opponent_goals=0, source="fchd")
    replay = m(round="Round 3 replay", source="fchd")
    assert len(merge([first, replay])) == 2


def test_different_games_same_season_kept():
    a = m(date="2010-08-07", competition="Scottish League", opponent="Clyde")
    b = m(date="2010-08-14", competition="Scottish League", opponent="Clyde", venue=AWAY)
    assert len(merge([a, b])) == 2


def test_recent_results_saved_and_reloaded(tmp_path):
    h = History(tmp_path)
    new = m(season="2099-00", date="2099-08-01", competition="Scottish League", opponent="Clyde", source="bbc")
    assert h.add_recent([new])
    again = History(tmp_path)
    assert any(x.date == "2099-08-01" for x in again.matches)
    assert not again.add_recent([new])
