"""Card vocabulary shared by ingest, retrieval, the API and evals."""

from enum import StrEnum


class Color(StrEnum):
    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"


class Format(StrEnum):
    """Legality keys as Scryfall names them. Ingest stores every key; queries use this subset."""

    COMMANDER = "commander"
    OATHBREAKER = "oathbreaker"
    BRAWL = "brawl"
    STANDARDBRAWL = "standardbrawl"
    COMPETITIVEBRAWL = "competitivebrawl"
    PAUPERCOMMANDER = "paupercommander"
    PREDH = "predh"
    DUEL = "duel"
    STANDARD = "standard"
    FUTURE = "future"
    PIONEER = "pioneer"
    MODERN = "modern"
    LEGACY = "legacy"
    VINTAGE = "vintage"
    PAUPER = "pauper"
    PENNY = "penny"
    HISTORIC = "historic"
    TIMELESS = "timeless"
    GLADIATOR = "gladiator"
    ALCHEMY = "alchemy"
    PREMODERN = "premodern"
    OLDSCHOOL = "oldschool"


NON_GAME_LAYOUTS = frozenset(
    {
        "art_series",
        "token",
        "double_faced_token",
        "emblem",
        "planar",
        "scheme",
        "vanguard",
        "front_card",
    }
)
"""Scryfall layouts that are not cards you put in a deck. Stored, but excluded from search."""

MAX_CARD_NAME_LENGTH = 150
"""The longest printed name is 141 characters."""
