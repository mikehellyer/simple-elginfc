"""The guards against what comes from the web."""
import csv

from simple_elginfc.core.models import HOME, Match
from simple_elginfc.gui.h2h_tab import safe_cell, safe_filename, save_csv
from simple_elginfc.gui.style import plain_tip


def test_formula_cells_neutralised(tmp_path):
    m = Match(season="2026-27", competition="Scottish League", opponent="=HYPERLINK(\"http://x\")", venue=HOME,
              date="2026-08-01", elgin_goals=1, opponent_goals=0, note="@SUM(A1)")
    path = tmp_path / "games.csv"
    save_csv(path, [m])
    row = list(csv.reader(open(path, encoding="utf-8")))[1]
    assert row[4].startswith("'=") and row[15].startswith("'@")
    assert safe_cell(-2) == -2 and safe_cell("Clyde") == "Clyde"


def test_filename_and_tooltip():
    assert safe_filename("../../etc/passwd") == "etcpasswd"
    assert safe_filename("Queen's Park") == "Queen's Park"
    assert plain_tip("<a href='x'>y</a>") == "<qt>&lt;a href=&#x27;x&#x27;&gt;y&lt;/a&gt;</qt>"
