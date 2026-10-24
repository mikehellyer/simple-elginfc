from datetime import date

from simple_elginfc.core import players
from simple_elginfc.core.models import HOME, Match
from simple_elginfc.core.players import Player, RosterEntry

CLUB_PAGE = """
<a href="https://www.elgincity.net/team/players/kyle-girvan" class="person-listing" style="background-image: url('https://s3.example/uploads/_newsArticleListing/PIC-Kyle-Girvan.jpg'); background-position: 50% 0%;" data-equalizer-watch>
  <div class="person-details"><h3>Kyle Girvan</h3><h4>Defence</h4></div></a>
<a href="https://www.elgincity.net/team/players/owen-cairns" class="person-listing" style="background-image: url(&quot;https://s3.example/uploads/_newsArticleListing/PIC-Owen-Cairns.jpg&quot;);">
  <div class="person-details"><h3>OWEN CAIRNS</h3><h4>DEFENCE</h4></div></a>
"""

ARTICLE = """{{Infobox football biography
|name        = Russell Dingwall
|birth_date  = {{birth date and age|1997|06|26|df=y}}
|birth_place = [[Inverness]], Scotland
|years1      = 2017–2019
|clubs1      = [[Ross County F.C.|Ross County]]
|years2      = 2018
|clubs2      = → [[Forfar Athletic F.C.|Forfar Athletic]] (loan)
|years3      = 2019–
|clubs3      = [[Elgin City F.C.|Elgin City]]
|caps3       = 216
|goals3      = 37
}}"""


def test_club_players_page():
    found = players.parse_club_players(CLUB_PAGE)
    assert [(p["name"], p["position"]) for p in found] == [("Kyle Girvan", "Defender"), ("Owen Cairns", "Defender")]
    assert found[0]["photo"] == "https://s3.example/uploads/_personPhotograph/PIC-Kyle-Girvan.jpg"


def test_article():
    a = players.parse_article(ARTICLE)
    assert (a["born"], a["birthplace"], a["joined"], a["apps"], a["goals"]) == ("1997-06-26", "Inverness, Scotland", "2019", "216", "37")
    assert a["clubs"] == ["→ Forfar Athletic (loan) (2018)", "Ross County (2017-2019)"]


def test_roster_spelling_and_first_season():
    rosters = players.merge_rosters([
        ("2007-08", {"bryan cameron": RosterEntry("1991-09-29", "", "")}),
        ("2015-16", {"brian cameron": RosterEntry("1991-09-29", "6 ft", "")}),
        ("2015-16", {"cameron brown": RosterEntry("2000-01-02", "", "")}),
    ])
    r = players.find_roster(rosters, "Brian Cameron")
    assert (r.first_season, r.born) == ("2007-08", "1991-09-29")
    assert players.find_roster(rosters, "Calum Brown") is None


def test_roster_skips_stand_in_birthdays():
    _, entries = players.parse_roster({"season": {"displayName": "2008/09 Scottish Division Three"},
                                       "athletes": [{"displayName": "A Player", "dateOfBirth": "2008-01-01T00:00Z"}]})
    assert entries["a player"].born == "" and entries["a player"].first_season == "2008-09"


def test_squad_merges_sources_and_sorts_by_number():
    wiki = [{"no": "9", "nat": "SCO", "pos": "FW", "name": "Kane Hester", "other": "", "article": ""},
            {"no": "5", "nat": "SCO", "pos": "DF", "name": "Kyle Girvan", "other": "", "article": ""}]
    club = [{"name": "Kyle Girvan", "position": "Defender", "photo": "p.jpg", "profile": ""},
            {"name": "Cole Taylor", "position": "Goalkeeper", "photo": "c.jpg", "profile": ""}]
    rosters = {"kane hester": RosterEntry("1995-07-12", "", "2018-19")}
    squad = players.build_squad(wiki, club, {}, rosters)
    assert [p.name for p in squad] == ["Kyle Girvan", "Kane Hester", "Cole Taylor"]
    assert squad[0].photo_url == "p.jpg" and squad[1].joined == "2018-19"
    assert squad[1].age(date(2026, 10, 24)) == 31


def test_goals_only_from_when_he_joined():
    def m(season, day, scorers):
        return Match(season=season, competition="Scottish League", opponent="Clyde", venue=HOME, date=day,
                     elgin_goals=3, opponent_goals=1, elgin_scorers=scorers)
    games = [m("2005-06", "2005-09-01", ["J. Murray 10'"]),  # an earlier J. Murray
             m("2024-25", "2024-09-01", ["J. Murray 12', 80'", "K. Hester 5'"]),
             m("2025-26", "2025-09-01", ["J. Murray 33' og"])]
    record = players.goals_for(Player("Jack Murray", joined="2024-25"), games)
    assert (record.goals, record.games, record.best_goals, record.best.season) == (2, 1, 2, "2024-25")
    assert players.joined_text(Player("Jack Murray", joined="2024-25"), record) == "2024-25 season"
