# Simple-ElginFC

Everything about Elgin City Football Club: the club today, every game
they've played, and their record against any opponent. Part of the
Simple-* range.

- **Club**: the badge, ground, board, management and squad, this season at
  a glance (last result, next match, league position), honours and records.
- **Matches**: every known game since 1893, filtered by opponent,
  competition, season, home/away and result, with each game's details.
- **Head to Head**: pick an opponent to see the full record against them
  (home, away, by competition), the biggest wins and defeats, runs and
  crowds, and every game. Saves as a spreadsheet (CSV).
- **Latest**: results and fixtures around now (live during a game), the
  League Two table, and the news.

It keeps itself up to date: results and fixtures every 10 minutes (every
minute while a game is on), the table hourly, news every 20 minutes and
the club's details twice a day. Everything is cached, so it works offline
with what it last knew.

## Where the data comes from

| What | Source |
|---|---|
| Highland League and northern cup results, 1893–2000 | [Scottish Football Historical Results Archive](http://sfha.org.uk/) (non-profit use, with acknowledgement) |
| Scottish Cup ties, 1946–2016 (no dates) | [Football Club History Database](https://fchd.info/) |
| Scottish League and cup games, 2001–2019, with crowds | ESPN's site API |
| Results, fixtures, scorers, table and news since 2020 | BBC Sport |
| Club details, honours, records, squad, staff | Wikipedia |
| The board | Companies House (Elgin City Football Club Limited, SC207126) |

Known gaps: the 2000–01 season, Scottish Cup ties before 1946, and dates
for Scottish Cup ties before 2001.

## Development

```bash
python3 -m venv venv
venv/bin/pip install -r requirements-dev.txt -e .
venv/bin/pytest
venv/bin/simple-elginfc
```

The bundled history (`src/simple_elginfc/data/history.json.gz`) is built by
`venv/bin/python tools/build_history.py`, which downloads each source once
into `tools/.cache/`. `tools/compare_wikipedia.py` checks the league seasons
against Wikipedia's list of Elgin City seasons.

Installers for Windows, macOS and Linux are built by GitHub Actions when a
`v*` tag is pushed; `bash packaging/linux/build-local.sh` builds a .deb here.
