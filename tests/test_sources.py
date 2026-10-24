from simple_elginfc.core import club
from simple_elginfc.core.models import AWAY, HOME
from simple_elginfc.core.sources import bbc, espn, fchd


def test_espn_event():
    event = {"date": "2002-03-26T19:30Z", "seasonType": {"name": "2001/2002 Scottish Division Three"},
             "league": {"name": "Scottish Division Three"},
             "competitions": [{"attendance": 369, "venue": {"fullName": "Borough Briggs"},
                               "status": {"type": {"name": "STATUS_FULL_TIME"}},
                               "competitors": [
                                   {"id": "419", "homeAway": "home", "score": {"displayValue": "0"}, "team": {"displayName": "Elgin City"}},
                                   {"id": "1", "homeAway": "away", "score": {"displayValue": "1"}, "team": {"displayName": "Albion Rovers"}}]}]}
    m = espn.parse_event(event)
    assert (m.season, m.competition, m.opponent, m.venue, m.score, m.attendance) == (
        "2001-02", "Scottish League", "Albion Rovers", HOME, "0-1", 369)


def test_espn_playoff_round():
    event = {"date": "2016-05-07T14:00Z", "seasonType": {"name": "Semi-finals"}, "league": {"name": "Scottish League One"},
             "competitions": [{"status": {"type": {"name": "STATUS_FULL_TIME"}}, "notes": [{"headline": "2nd Leg"}],
                               "competitors": [
                                   {"id": "2", "homeAway": "home", "score": "0", "team": {"displayName": "Clyde"}},
                                   {"id": "419", "homeAway": "away", "score": "2", "team": {"displayName": "Elgin City"}}]}]}
    m = espn.parse_event(event)
    assert (m.competition, m.round, m.venue, m.score, m.note) == ("Play-offs", "Semi-finals", AWAY, "2-0", "2nd Leg")


def test_bbc_event_with_scorers():
    payload = {"eventGroups": [{"secondaryGroups": [{"events": [{
        "eventGroupingLabel": "Scotland - Scottish Cup - 3rd Round", "status": "PostEvent",
        "date": {"isoDate": "2025-11-29"}, "startDateTime": "2025-11-29T15:00:00Z",
        "statusComment": {"value": "AET"}, "periodLabel": {"value": "FT"},
        "home": {"fullName": "Elgin City", "urn": bbc.TEAM_URN, "score": "4", "runningScores": {"halftime": "1"},
                 "actions": [{"actionType": "goal", "playerName": "J. MacIver",
                              "actions": [{"type": "Goal", "timeLabel": {"value": "9'"}}, {"type": "Penalty", "timeLabel": {"value": "51'"}}]}]},
        "away": {"fullName": "Stirling Albion", "score": "2", "runningScores": {"halftime": "0"}}}]}]}]}
    (m,) = bbc.parse_scores(payload)
    assert (m.competition, m.round, m.score, m.note, m.half_time) == ("Scottish Cup", "3rd Round", "4-2", "aet", "1-0")
    assert m.elgin_scorers == ["J. MacIver 9', 51' pen"]


def test_bbc_fixture_not_in_history():
    payload = {"eventGroups": [{"secondaryGroups": [{"events": [{
        "eventGroupingLabel": "Scotland - Scottish League Two", "status": "PreEvent", "date": {"isoDate": "2026-10-31"},
        "home": {"fullName": "Kelty Hearts"}, "away": {"fullName": "Elgin City", "urn": bbc.TEAM_URN}}]}]}]}
    assert bbc.parse_scores(payload) == []
    (ev,) = bbc.parse_events(payload)
    assert ev.state == bbc.PRE and ev.match.venue == AWAY and not ev.match.played


def test_fchd_page():
    page = """<h2>Preliminary Round One</h2><ul>
<li>Dumbarton                    0-0 Berwick Rangers
<li>Elgin City                   3-1 Albion Rovers
</ul><h2>Round Two Replay</h2><ul>
<li>Berwick Rangers              3-3 Elgin City (Elgin City won 7-6 on penalties)
</ul>"""
    ms = fchd.parse_season(page, "1967-68")
    assert [(m.round, m.opponent, m.venue, m.score) for m in ms] == [
        ("Preliminary Round 1", "Albion Rovers", HOME, "3-1"), ("Round 2 replay", "Berwick Rangers", AWAY, "3-3")]
    assert "penalties" in ms[1].note


def test_infobox_and_sections():
    text = """{{Infobox football club
| clubname = Elgin City
| ground = [[Borough Briggs]], [[Elgin, Moray|Elgin]]
| founded = {{Start date and age|1893|df=yes}}
| chairman = Alan Murray
}}
Lead.
==Honours==
*'''Highland League'''
** Champions: 1931–32, 1934–35 (2)
==Club records==
'''Win:''' 18–1 v [[Brora Rangers F.C.|Brora Rangers]] on 6 February 1960
===Staff===
*Manager: Stefan Laird
"""
    info = club.ClubInfo()
    club.apply_club_infobox(info, text)
    assert (info.ground, info.founded, info.chairman) == ("Borough Briggs, Elgin", "1893", "Alan Murray")
    s = club.sections(text)
    assert club.parse_honours(s["honours"]) == [("Highland League", "Champions: 1931-32, 1934-35 (2)")]
    assert club.parse_bold_list(s["club records"]) == [("Win", "18-1 v Brora Rangers on 6 February 1960")]
    assert club.parse_officials(s["staff"]) == [("Manager", "Stefan Laird")]


def test_companies_house_officers_active_only():
    page = """<main>
<div class="appointment-1"><a class="govuk-link" href="/officers/abc/appointments">MURRAY, Alan</a>
<span id="officer-status-tag-1" class="status-tag">Active</span>
<dd id="officer-role-1" class="data">Director</dd><dd id="officer-appointed-on-1" class="data">18 March 2024</dd></div>
<div class="appointment-2"><a href="/officers/def/appointments">BENZIE, Isla</a>
<span id="officer-status-tag-2">Resigned</span><dd id="officer-role-2">Director</dd> Resigned on 19 September 2026</div>
</main>"""
    assert club.parse_officers(page) == [club.Officer("Alan Murray", "Director", "18 March 2024")]


def test_espn_summary_corrects_a_placeholder_score():
    from simple_elginfc.core.models import Match

    m = Match(season="2015-16", competition="Scottish League", opponent="Arbroath", venue=HOME, date="2016-04-30",
              elgin_goals=0, opponent_goals=0, source="espn")
    summary = {"keyEvents": [
        {"scoringPlay": True, "type": {"text": "Goal"}, "clock": {"displayValue": "5'"}, "team": {"id": "419"},
         "participants": [{"athlete": {"displayName": "Kyle Macleod"}}]},
        {"scoringPlay": True, "type": {"text": "Penalty - Scored"}, "clock": {"displayValue": "32'"}, "team": {"id": "419"},
         "participants": [{"athlete": {"displayName": "Brian Cameron"}}]},
        {"scoringPlay": True, "type": {"text": "Goal"}, "clock": {"displayValue": "64'"}, "team": {"id": "419"},
         "participants": [{"athlete": {"displayName": "Brian Cameron"}}]},
        {"scoringPlay": True, "type": {"text": "Goal"}, "clock": {"displayValue": "80'"}, "team": {"id": "12"},
         "participants": [{"athlete": {"displayName": "Someone Else"}}]},
        {"scoringPlay": True, "type": {"text": "Penalty - Scored"}, "period": {"number": 5}, "team": {"id": "12"},
         "participants": [{"athlete": {"displayName": "Shootout Taker"}}]},
        {"scoringPlay": False, "type": {"text": "Yellow Card"}, "team": {"id": "12"}},
    ]}
    espn.apply_summary(m, espn.parse_summary(summary))
    assert m.score == "3-1"
    assert m.elgin_scorers == ["K. Macleod 5'", "B. Cameron 32' pen, 64'"]
    assert m.opponent_scorers == ["S. Else 80'"]


def test_espn_summary_without_events_changes_nothing():
    assert espn.parse_summary({"keyEvents": []}) is None


def test_bbc_friendly():
    assert bbc._competition("World - Club Friendlies - Club Friendlies 3") == ("Friendly", "")
    assert bbc._competition("Scotland - Scottish League Two") == ("Scottish League", "")
