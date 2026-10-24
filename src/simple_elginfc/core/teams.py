"""One name per opponent, whichever source spelt it.

Each source writes clubs its own way ("Inverness CT", "Inverness Caley
Thistle", "ICT"…), so every name goes through canonical() before it's
stored. Clubs that merged or renamed keep their own names, because a
1950s "Inverness Caledonian" game was not against today's Inverness
Caledonian Thistle; RELATED links them so a search for one finds both.
"""
from __future__ import annotations

import re
import unicodedata

# lower-cased spelling -> canonical name
ALIASES = {
    "caledonian": "Inverness Caledonian",
    "caley": "Inverness Caledonian",
    "caledonian thistle res": "Inverness Caledonian Thistle res",
    "buckie th": "Buckie Thistle",
    "forres m": "Forres Mechanics",
    "forresmechanics": "Forres Mechanics",
    "nairn co": "Nairn County",
    "ross": "Ross County",
    "kosb": "King's Own Scottish Borderers",
    "inv caley": "Inverness Caledonian",
    "inverness caley": "Inverness Caledonian",
    "inverness cal": "Inverness Caledonian",
    "inverness ct": "Inverness Caledonian Thistle",
    "inverness c.t.": "Inverness Caledonian Thistle",
    "inverness caley thistle": "Inverness Caledonian Thistle",
    "inverness cal thistle": "Inverness Caledonian Thistle",
    "caledonian thistle": "Inverness Caledonian Thistle",
    "inverness": "Inverness Caledonian Thistle",
    "ict": "Inverness Caledonian Thistle",
    "inv thistle": "Inverness Thistle",
    "thistle": "Inverness Thistle",
    "citadel": "Inverness Citadel",
    "clach": "Clachnacuddin",
    "forres": "Forres Mechanics",
    "forres mechs": "Forres Mechanics",
    "nairn": "Nairn County",
    "ross co": "Ross County",
    "buckie": "Buckie Thistle",
    "brora": "Brora Rangers",
    "huntly fc": "Huntly",
    "fort william fc": "Fort William",
    "lossiemouth fc": "Lossiemouth",
    "wick": "Wick Academy",
    "golspie": "Golspie Sutherland",
    "strathspey": "Strathspey Thistle",
    "inverurie locos": "Inverurie Loco Works",
    "inverurie loco works": "Inverurie Loco Works",
    "turriff": "Turriff United",
    "formartine": "Formartine United",
    "cove": "Cove Rangers",
    "keith fc": "Keith",
    "rothes fc": "Rothes",
    "deveronvale fc": "Deveronvale",
    "fraserburgh fc": "Fraserburgh",
    "peterhead fc": "Peterhead",
    "aberdeen fc": "Aberdeen",
    "e stirlingshire": "East Stirlingshire",
    "e. stirlingshire": "East Stirlingshire",
    "east stirling": "East Stirlingshire",
    "the spartans": "Spartans",
    "spartans fc": "Spartans",
    "edinburgh city": "Edinburgh City",
    "fc edinburgh": "FC Edinburgh",
    "edinburgh": "FC Edinburgh",
    "albion": "Albion Rovers",
    "queens park": "Queen's Park",
    "queen's park": "Queen's Park",
    "queen of south": "Queen of the South",
    "qots": "Queen of the South",
    "stirling": "Stirling Albion",
    "stenhousemuir fc": "Stenhousemuir",
    "berwick": "Berwick Rangers",
    "annan": "Annan Athletic",
    "bonnyrigg": "Bonnyrigg Rose",
    "bonnyrigg rose athletic": "Bonnyrigg Rose",
    "kelty": "Kelty Hearts",
    "cowdenbeath fc": "Cowdenbeath",
    "east fife fc": "East Fife",
    "forfar": "Forfar Athletic",
    "brechin": "Brechin City",
    "montrose fc": "Montrose",
    "arbroath fc": "Arbroath",
    "alloa": "Alloa Athletic",
    "dumbarton fc": "Dumbarton",
    "clyde fc": "Clyde",
    "stranraer fc": "Stranraer",
    "hamilton": "Hamilton Academical",
    "hamilton accies": "Hamilton Academical",
    "hamilton academical": "Hamilton Academical",
    "dunfermline": "Dunfermline Athletic",
    "raith": "Raith Rovers",
    "airdrie": "Airdrieonians",
    "airdrie united": "Airdrie United",
    "morton": "Greenock Morton",
    "greenock morton": "Greenock Morton",
    "partick": "Partick Thistle",
    "st johnstone": "St Johnstone",
    "st. johnstone": "St Johnstone",
    "st mirren": "St Mirren",
    "st. mirren": "St Mirren",
    "hearts": "Heart of Midlothian",
    "heart of midlothian": "Heart of Midlothian",
    "hibs": "Hibernian",
    "dundee utd": "Dundee United",
    "dundee united": "Dundee United",
    "ayr": "Ayr United",
    "queen's park fc": "Queen's Park",
    "livingston fc": "Livingston",
    "gretna fc": "Gretna",
    "kilmarnock fc": "Kilmarnock",
    "motherwell fc": "Motherwell",
    "falkirk fc": "Falkirk",
    "celtic fc": "Celtic",
    "rangers fc": "Rangers",
    "civil service strollers": "Civil Service Strollers",
    "the open goal broomhill": "Broomhill",
    "university of stirling": "University of Stirling",
    "stirling university": "University of Stirling",
    "highland light infantry": "Highland Light Infantry",
    "hli": "Highland Light Infantry",
}

# Clubs that are the same club under another name, or that merged into
# another: searching for any one of a group finds them all.
RELATED = [
    {"Inverness Caledonian", "Inverness Thistle", "Inverness Caledonian Thistle"},
    {"Meadowbank Thistle", "Livingston", "Ferranti Thistle"},
    {"Airdrieonians", "Airdrie United"},
    {"Clydebank", "Airdrieonians"},
    {"Edinburgh City", "FC Edinburgh"},
]


def _clean(name: str) -> str:
    name = unicodedata.normalize("NFKC", name).replace("’", "'").replace("`", "'")
    name = re.sub(r"\s+", " ", name).strip(" .,;:*")
    return name


def canonical(name: str) -> str:
    name = _clean(name)
    key = name.lower()
    if key in ALIASES:
        return ALIASES[key]
    if key.endswith(" fc") and key[:-3] in ALIASES:
        return ALIASES[key[:-3]]
    if key.endswith(" fc"):
        name = name[:-3]
    return name


def related(name: str) -> set[str]:
    """The club and any it's the same as or merged into."""
    found = {name}
    for group in RELATED:
        if name in group:
            found |= group
    return found


def search_key(name: str) -> str:
    """For matching what's typed against names: lower case, no punctuation."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(ch for ch in name if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9 ]", "", name.lower())


def matches_query(name: str, query: str) -> bool:
    """Does `name` match what's typed? Every word typed must start a word
    of the name ("inv cal" finds Inverness Caledonian), or the query can
    be one of its aliases ("ict", "hibs")."""
    q = search_key(query).split()
    if not q:
        return True
    if ALIASES.get(" ".join(q)) == name:
        return True
    words = search_key(name).split()
    return all(any(w.startswith(part) for w in words) for part in q)
