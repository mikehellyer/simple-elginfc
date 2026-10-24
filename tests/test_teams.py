from simple_elginfc.core.teams import canonical, matches_query


def test_aliases():
    assert canonical("Inverness CT") == "Inverness Caledonian Thistle"
    assert canonical("E Stirlingshire") == "East Stirlingshire"
    assert canonical("The Spartans") == "Spartans"
    assert canonical("Brechin City FC") == "Brechin City"
    assert canonical("  Forres   Mechanics ") == "Forres Mechanics"


def test_search():
    assert matches_query("Inverness Caledonian Thistle", "inv cal")
    assert matches_query("Inverness Caledonian Thistle", "ict")
    assert matches_query("Queen's Park", "queens")
    assert not matches_query("Clachnacuddin", "forres")
