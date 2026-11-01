"""Room-label lexicon shared by vision (labelling), geometry (entity resolution) and language (classify)."""

import re

from .model import RoomType

# Ordered: the first match wins, so specific phrases come before generic ones (master bed before bed).
# Leading \b only, so "bed" also matches "bedroom" and "hall" matches "hallway".
_RULES: tuple[tuple[RoomType, str], ...] = (
    (RoomType.MASTER_BEDROOM, r"\b(?:master|primary|main)[\s\-_]*(?:bed|br\b|suite)|\bmbr\b|\bm\.?\s?bed"),
    (RoomType.BATHROOM, r"\b(?:bath|wc\b|w\.c\.|toilet|ensuite|en[\s\-]suite|shower|powder|lavatory|restroom)"),
    (RoomType.CLOSET, r"\b(?:walk[\s\-]*in|wic\b|closet|wardrobe|dressing|cloak)"),
    (RoomType.BEDROOM, r"\b(?:bed|br\b|bdrm|guest\s*room|nursery|kids?\s*room)"),
    (RoomType.KITCHEN, r"\b(?:kitchen|kitchenette|kit\b|galley|cooking)"),
    (RoomType.LIVING_ROOM, r"\b(?:living|lounge|family|sitting|great\s*room|drawing\s*room|salon)"),
    (RoomType.DINING_ROOM, r"\b(?:dining|dinette|breakfast|eating)"),
    (RoomType.STAIRWELL, r"\b(?:stair|staircase|stairwell|stairs)"),
    (RoomType.HALLWAY, r"\b(?:hall|corridor|passage|foyer|entry|entrance|lobby|vestibule|landing|gallery)"),
    (RoomType.GARAGE, r"\b(?:garage|carport|parking)"),
    (RoomType.OFFICE, r"\b(?:office|study|den\b|library|workroom|work\s*room)"),
    (RoomType.LAUNDRY, r"\b(?:laundry|wash\s*room|washroom|mud\s*room)"),
    (RoomType.UTILITY, r"\b(?:utility|mechanical|plant\s*room|boiler|furnace|electrical|server)"),
    (RoomType.BALCONY, r"\b(?:balcony|terrace|deck\b|patio|veranda|verandah|porch|loggia)"),
    (RoomType.STORAGE, r"\b(?:storage|store|storeroom|pantry|larder|shed|attic|cellar|basement)"),
)
_COMPILED = tuple((rt, re.compile(p, re.IGNORECASE)) for rt, p in _RULES)

# Phrase → RoomType, for entity resolution ("the kitchen", "between the lounge and the hall").
ROOM_SYNONYMS: dict[str, RoomType] = {
    "master bedroom": RoomType.MASTER_BEDROOM, "master bed": RoomType.MASTER_BEDROOM,
    "primary bedroom": RoomType.MASTER_BEDROOM, "main bedroom": RoomType.MASTER_BEDROOM,
    "master suite": RoomType.MASTER_BEDROOM, "mbr": RoomType.MASTER_BEDROOM,
    "bathroom": RoomType.BATHROOM, "bath": RoomType.BATHROOM, "wc": RoomType.BATHROOM,
    "toilet": RoomType.BATHROOM, "ensuite": RoomType.BATHROOM, "en-suite": RoomType.BATHROOM,
    "shower room": RoomType.BATHROOM, "powder room": RoomType.BATHROOM, "restroom": RoomType.BATHROOM,
    "closet": RoomType.CLOSET, "walk-in closet": RoomType.CLOSET, "walk in closet": RoomType.CLOSET,
    "wic": RoomType.CLOSET, "wardrobe": RoomType.CLOSET, "dressing room": RoomType.CLOSET,
    "bedroom": RoomType.BEDROOM, "bed": RoomType.BEDROOM, "guest room": RoomType.BEDROOM,
    "nursery": RoomType.BEDROOM,
    "kitchen": RoomType.KITCHEN, "kitchenette": RoomType.KITCHEN, "galley": RoomType.KITCHEN,
    "living room": RoomType.LIVING_ROOM, "living": RoomType.LIVING_ROOM, "lounge": RoomType.LIVING_ROOM,
    "family room": RoomType.LIVING_ROOM, "sitting room": RoomType.LIVING_ROOM,
    "great room": RoomType.LIVING_ROOM,
    "dining room": RoomType.DINING_ROOM, "dining": RoomType.DINING_ROOM, "dinette": RoomType.DINING_ROOM,
    "hallway": RoomType.HALLWAY, "hall": RoomType.HALLWAY, "corridor": RoomType.HALLWAY,
    "passage": RoomType.HALLWAY, "foyer": RoomType.HALLWAY, "entry": RoomType.HALLWAY,
    "entrance": RoomType.HALLWAY, "lobby": RoomType.HALLWAY,
    "garage": RoomType.GARAGE, "carport": RoomType.GARAGE,
    "office": RoomType.OFFICE, "study": RoomType.OFFICE, "den": RoomType.OFFICE,
    "laundry": RoomType.LAUNDRY, "laundry room": RoomType.LAUNDRY, "mudroom": RoomType.LAUNDRY,
    "utility": RoomType.UTILITY, "utility room": RoomType.UTILITY, "mechanical room": RoomType.UTILITY,
    "balcony": RoomType.BALCONY, "terrace": RoomType.BALCONY, "deck": RoomType.BALCONY,
    "patio": RoomType.BALCONY, "porch": RoomType.BALCONY,
    "storage": RoomType.STORAGE, "store": RoomType.STORAGE, "storeroom": RoomType.STORAGE,
    "pantry": RoomType.STORAGE,
    "stair": RoomType.STAIRWELL, "stairs": RoomType.STAIRWELL, "stairwell": RoomType.STAIRWELL,
    "staircase": RoomType.STAIRWELL,
}

_NOISE = re.compile(r"[\d#.:()\[\]]+|\s+")


def room_type_for_text(text: str) -> tuple[RoomType, float]:
    """Classify a label such as "BED 2" or "Kitchenette". (UNKNOWN, 0.0) when nothing matches."""
    norm = _NOISE.sub(" ", text.lower()).strip()
    if not norm:
        return RoomType.UNKNOWN, 0.0
    if norm in ROOM_SYNONYMS:
        return ROOM_SYNONYMS[norm], 0.95
    for room_type, pattern in _COMPILED:
        if pattern.search(text):
            return room_type, 0.8
    return RoomType.UNKNOWN, 0.0
