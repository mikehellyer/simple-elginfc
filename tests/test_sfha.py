from simple_elginfc.core.models import AWAY, HOME, NEUTRAL
from simple_elginfc.core.sources import sfha

GRID_PAGE = """
<p>1895-96
Highland League</p>
<table>
 <tr><td><p>&nbsp;</p></td><td><p>Clac</p></td><td><p>Elg</p></td><td><p>I Cal</p></td></tr>
 <tr><td><p>Clachnacuddin</p></td><td></td><td><p>7 Dec 4-4</p></td><td><p>12 Oct 2-4</p></td></tr>
 <tr><td><p>Elgin City</p></td><td><p>23 May 2-2</p></td><td></td><td><p>5 Oct 4-1</p></td></tr>
 <tr><td><p>Caledonian</p></td><td><p>1 Feb 2-3</p></td><td><p>8 Feb 3-2</p></td><td></td></tr>
</table>
<p>9 Nov Elgin v Caledonian 2-2 stopped after 73 mins due to poor light</p>
"""

CUP_PAGE = """
<table><tr><td>
<p>1968-69 North of
Scotland Cup</p>
<p>Second round</p>
<p>22 Mar Caledonian v Elgin City 1-2</p>
<p>Semi-final</p>
<p>29 Mar
Brora Rangers v Elgin City 0-4</p>
<p>Final at
Mosset Park, Forres</p>
<p>19 Apr
Elgin City v Nairn County 5-3</p>
</td></tr></table>
<p>1969-70 North of Scotland Cup</p>
<p>First round</p>
<p>28 Feb Brora Rangers v Elgin City 1-5 aet</p>
<p>28 Feb Lossiemouth v Clachnacuddin 2-0</p>
"""


def test_grid_reads_both_ways_round():
    ms = sfha.parse_page(GRID_PAGE, "Highland League")
    by_date = {m.date: m for m in ms}
    home = by_date["1895-10-05"]
    assert (home.opponent, home.venue, home.elgin_goals, home.opponent_goals) == ("Inverness Caledonian", HOME, 4, 1)
    away = by_date["1895-12-07"]  # Clach 4-4 Elgin, at Clach
    assert (away.opponent, away.venue, away.score) == ("Clachnacuddin", AWAY, "4-4")
    assert by_date["1896-02-08"].score == "2-3"  # Caledonian 3-2 Elgin: Elgin's goals first
    assert all(m.season == "1895-96" and m.competition == "Highland League" for m in ms)


def test_note_under_grid_keeps_its_note():
    ms = sfha.parse_page(GRID_PAGE, "Highland League")
    stopped = [m for m in ms if m.date == "1895-11-09"]
    assert stopped and "stopped" in stopped[0].note


def test_cup_rounds_and_neutral_final():
    ms = sfha.parse_page(CUP_PAGE, "North of Scotland Cup")
    rounds = [(m.season, m.round, m.opponent, m.score, m.venue) for m in ms]
    assert ("1968-69", "Second round", "Inverness Caledonian", "2-1", AWAY) in rounds
    assert ("1968-69", "Semi-final", "Brora Rangers", "4-0", AWAY) in rounds
    final = next(m for m in ms if m.round == "Final")
    assert (final.venue, final.ground, final.score, final.date) == (NEUTRAL, "Mosset Park, Forres", "5-3", "1969-04-19")


def test_other_clubs_ties_ignored_and_aet_kept():
    ms = sfha.parse_page(CUP_PAGE, "North of Scotland Cup")
    assert not any(m.opponent == "Lossiemouth" for m in ms)
    brora = next(m for m in ms if m.season == "1969-70")
    assert brora.note == "aet" and brora.score == "5-1"


def test_heading_competition():
    assert sfha.heading_competition("North of Scotland Cup First round") == "North of Scotland Cup"
    assert sfha.heading_competition("Highland League Cup District 3") == "Highland League Cup"
    assert sfha.heading_competition("Elgin City") is None


def test_season_years():
    assert sfha.make_date("1895-96", "5", "Oct") == "1895-10-05"
    assert sfha.make_date("1895-96", "1", "Jan") == "1896-01-01"
    assert sfha.make_date("1899-00", "1", "Sept") == "1899-09-01"


LAYOUT_PAGE = """
<table><tr><td>
<p>1964-65 Highland League Cup</p>
<table>
 <tr><td>District 3</td><td>Elg</td><td>Forr</td></tr>
 <tr><td>Elgin City</td><td></td><td>19 Aug 4-1</td></tr>
 <tr><td>Forres Mechanics</td><td>8 Aug 3-2</td><td></td></tr>
</table>
<p>1965-66 Highland League Cup</p>
<table>
 <tr><td>District 2</td><td>Elg</td><td>Forr</td></tr>
 <tr><td>Elgin City</td><td></td><td>21 Aug 1-1</td></tr>
 <tr><td>Forres Mechanics</td><td>14 Aug 0-2</td><td></td></tr>
</table>
</td></tr></table>
"""


def test_grids_inside_a_layout_table_keep_their_own_season():
    ms = sfha.parse_page(LAYOUT_PAGE, "Highland League Cup")
    assert sorted((m.season, m.date) for m in ms) == [
        ("1964-65", "1964-08-08"), ("1964-65", "1964-08-19"), ("1965-66", "1965-08-14"), ("1965-66", "1965-08-21")]
