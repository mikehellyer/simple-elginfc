import re
from datetime import date

from simple_elginfc.core import scoreboard
from simple_elginfc.core.sources import bbc
from simple_elginfc.gui.live_scores_tab import game_html, table_html


def event(home, away, status, day, hs=None, aws=None, label="", kickoff="15:00"):
    e = {"status": status, "date": {"isoDate": day}, "startDateTime": f"{day}T{kickoff}:00Z",
         "periodLabel": {"value": label}, "home": {"fullName": home}, "away": {"fullName": away}}
    if hs is not None:
        e["home"].update(score=str(hs), actions=[{"actionType": "goal", "playerName": "A. Scorer",
                                                 "actions": [{"type": "Goal", "timeLabel": {"value": "12'"}}]}])
        e["away"]["score"] = str(aws)
    return e


def payload(*events):
    return {"eventGroups": [{"secondaryGroups": [{"events": list(events)}]}]}


TODAY = date(2026, 11, 7)


def fake_get(url):
    if "football-table" in url:
        return {"tournaments": [{"name": "Scottish League Two", "matchParticipantUrns": [], "stages": [{"rounds": [{
            "participants": [{"name": "Elgin City", "rank": 1, "matchesPlayed": 12, "wins": 7, "draws": 3, "losses": 2,
                              "goalsScoredFor": 30, "goalsScoredAgainst": 15, "points": 24,
                              "formGuide": [{"value": "W"}]},
                             {"name": "Dumbarton", "rank": 2, "matchesPlayed": 12, "points": 20}]}]}]}]}
    if "selectedStartDate=2026-11-07&" in url and "selectedEndDate=2026-11-07" in url:
        return payload(event("Elgin City", "Dumbarton", "MidEvent", "2026-11-07", 1, 0, "67'"),
                       event("Clyde", "The Spartans", "PreEvent", "2026-11-07", kickoff="17:30"))
    return payload()


def test_live_game_parsed():
    (g,) = bbc.parse_games(payload(event("Elgin City", "Dumbarton", "MidEvent", "2026-11-07", 1, 0, "67'")))
    assert (g.state, g.status, g.home_score, g.away_score, g.home_scorers) == (bbc.LIVE, "67'", 1, 0, ["A. Scorer 12'"])
    assert "67&#x27;" in game_html(g) and "1 - 0" in game_html(g)


def test_league_board_today():
    b = scoreboard.fetch_league("league-two", TODAY, fake_get)
    assert b.live_count == 1 and len(b.today) == 2
    assert not b.recent  # games today: no need for last results
    assert scoreboard.any_live({"league-two": b})
    html = table_html(b)
    assert "Elgin City" in html and "playing now" in html


def test_no_games_today_shows_last_and_next_rounds():
    def get(url):
        if "football-table" in url:
            return {"tournaments": []}
        if "selectedStartDate=2026-11-01&selectedEndDate" not in url and "selectedEndDate=2026-11-01" in url:
            return payload()  # (today)
        if "2026-10-01" in url or "selectedStartDate=2026-11-01" in url:
            return payload(event("A", "B", "PostEvent", "2026-10-31", 1, 1, "FT"),
                           event("C", "D", "PostEvent", "2026-10-30", 2, 0, "FT"),
                           event("E", "F", "PostEvent", "2026-10-03", 0, 3, "FT"))
        return payload(event("G", "H", "PreEvent", "2026-11-06"), event("I", "J", "PreEvent", "2026-11-07"),
                       event("K", "L", "PreEvent", "2026-11-21"))
    b = scoreboard.fetch_league("league-two", date(2026, 11, 1), get, with_table=False)
    assert {g["date"] for g in b.recent} == {"2026-10-31", "2026-10-30"}
    assert {g["date"] for g in b.upcoming} == {"2026-11-06", "2026-11-07"}


def cup_event(home, away, status, day, label, hs=None, aws=None):
    e = event(home, away, status, day, hs, aws, "FT" if status == "PostEvent" else "")
    e["eventGroupingLabel"] = f"Scotland - Scottish Cup - {label}"
    return e


def test_cup_round_names():
    (g,) = bbc.parse_games(payload(cup_event("Elgin City", "Partick Thistle", "PreEvent", "2026-11-28", "3rd Round")))
    assert g.round == "3rd Round"


def test_cup_groups():
    tables = bbc.parse_tables({"tournaments": [{"stages": [{"name": "Group Stage", "rounds": [
        {"name": "Group A", "participants": [{"name": "Aberdeen", "rank": 1, "points": 12}]},
        {"name": "Group B", "participants": [{"name": "Dundee United", "rank": 1, "points": 9}]}]}]}]})
    assert [(n, rows[0].team) for n, rows in tables] == [("Group A", "Aberdeen"), ("Group B", "Dundee United")]


def test_cup_season_fetches_finished_months_once():
    calls = []

    season = [cup_event("Stirling University", "Elgin City", "PostEvent", "2026-10-24", "2nd Round", 1, 2),
              cup_event("Elgin City", "Partick Thistle", "PreEvent", "2026-11-28", "3rd Round")]

    def get(url):
        calls.append(url)
        if "football-table" in url:
            return {"tournaments": []}
        start = re.search(r"selectedStartDate=([\d-]+)", url).group(1)
        end = re.search(r"selectedEndDate=([\d-]+)", url).group(1)
        # like BBC's feed: only the games in the range asked for
        return payload(*[e for e in season if start <= e["date"]["isoDate"] <= end])

    first = scoreboard.fetch_cup("scottish-cup", date(2026, 11, 1), get)
    assert [g["round"] for g in first.season] == ["2nd Round", "3rd Round"]
    assert "2026-10" in first.months and "2026-11" not in first.months
    calls.clear()
    again = scoreboard.fetch_cup("scottish-cup", date(2026, 11, 1), get, first)
    assert not any("selectedStartDate=2026-10-01" in u for u in calls)  # October isn't asked for again
    assert len(again.season) == 2
