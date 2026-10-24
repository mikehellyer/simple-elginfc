from simple_elginfc.core.settings import SettingsStore


def test_round_trip_and_bad_values(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.update(tab=2, h2h_opponent="Clachnacuddin", h2h_related=True)
    again = SettingsStore(path)
    assert (again.settings.tab, again.settings.h2h_opponent, again.settings.h2h_related) == (2, "Clachnacuddin", True)
    path.write_text('{"tab": 99, "h2h_related": "yes"}')
    bad = SettingsStore(path)
    assert bad.settings.tab == 10 and bad.settings.h2h_related is False
