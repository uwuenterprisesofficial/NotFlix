"""MyAnimeList's genre ids, split the way MAL's site groups them.

The MAL API returns genres, themes and demographics together in one `genres` list; which one
an entry is follows from its id.
"""

from typing import Literal

Category = Literal["genre", "explicit", "demographic", "theme"]

GENRE_IDS = frozenset(
    {
        1,  # Action
        2,  # Adventure
        5,  # Avant Garde
        46,  # Award Winning
        28,  # Boys Love
        4,  # Comedy
        8,  # Drama
        10,  # Fantasy
        26,  # Girls Love
        47,  # Gourmet
        14,  # Horror
        7,  # Mystery
        22,  # Romance
        24,  # Sci-Fi
        36,  # Slice of Life
        30,  # Sports
        37,  # Supernatural
        41,  # Suspense
    }
)
EXPLICIT_GENRE_IDS = frozenset({9, 49, 12})  # Ecchi, Erotica, Hentai
DEMOGRAPHIC_IDS = frozenset({27, 42, 25, 43, 15})  # Shounen, Seinen, Shoujo, Josei, Kids

# Names for the genre picker when neither Jikan nor the local catalog can list them.
KNOWN_TAGS: dict[int, str] = {
    1: "Action", 2: "Adventure", 3: "Racing", 4: "Comedy", 5: "Avant Garde", 6: "Mythology",
    7: "Mystery", 8: "Drama", 9: "Ecchi", 10: "Fantasy", 11: "Strategy Game", 12: "Hentai",
    13: "Historical", 14: "Horror", 15: "Kids", 17: "Martial Arts", 18: "Mecha", 19: "Music",
    20: "Parody", 21: "Samurai", 22: "Romance", 23: "School", 24: "Sci-Fi", 25: "Shoujo",
    26: "Girls Love", 27: "Shounen", 28: "Boys Love", 29: "Space", 30: "Sports",
    31: "Super Power", 32: "Vampire", 35: "Harem", 36: "Slice of Life", 37: "Supernatural",
    38: "Military", 39: "Detective", 40: "Psychological", 41: "Suspense", 42: "Seinen",
    43: "Josei", 46: "Award Winning", 47: "Gourmet", 48: "Workplace", 49: "Erotica",
    50: "Adult Cast", 51: "Anthropomorphic", 52: "CGDCT", 53: "Childcare", 54: "Combat Sports",
    55: "Delinquents", 56: "Educational", 57: "Gag Humor", 58: "Gore", 59: "High Stakes Game",
    60: "Idols (Female)", 61: "Idols (Male)", 62: "Isekai", 63: "Iyashikei",
    64: "Love Polygon", 65: "Magical Sex Shift", 66: "Mahou Shoujo", 67: "Medical",
    68: "Organized Crime", 69: "Otaku Culture", 70: "Performing Arts", 71: "Pets",
    72: "Reincarnation", 73: "Reverse Harem", 74: "Love Status Quo", 75: "Showbiz",
    76: "Survival", 77: "Team Sports", 78: "Time Travel", 79: "Video Game", 80: "Visual Arts",
    81: "Crossdressing", 82: "Urban Fantasy", 83: "Villainess",
}  # fmt: skip


def category(tag_id: int) -> Category:
    if tag_id in GENRE_IDS:
        return "genre"
    if tag_id in EXPLICIT_GENRE_IDS:
        return "explicit"
    if tag_id in DEMOGRAPHIC_IDS:
        return "demographic"
    return "theme"


_BY_NAME = {name.lower(): tag_id for tag_id, name in KNOWN_TAGS.items()} | {
    # Older or long names MAL has used for the same ids.
    "romantic subtext": 74,
    "cute girls doing cute things": 52,
    "sci fi": 24,
}


def tags_from_names(names: list[str]) -> list[dict]:
    """Genre ids for shows cached before the ids were stored (only their names are), so they
    still count until their details are fetched again."""
    return [
        {"id": _BY_NAME[name.lower()], "name": name} for name in names if name.lower() in _BY_NAME
    ]
