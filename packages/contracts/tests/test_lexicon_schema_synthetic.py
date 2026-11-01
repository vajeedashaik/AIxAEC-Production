import hashlib
import json
import sys

import pytest
from conftest import ROOT

from aec_contracts import ROOM_SYNONYMS, RoomType, room_type_for_text


@pytest.mark.parametrize("text,expected", [
    ("MASTER BEDROOM", RoomType.MASTER_BEDROOM), ("Master Bed", RoomType.MASTER_BEDROOM),
    ("MBR", RoomType.MASTER_BEDROOM), ("primary suite", RoomType.MASTER_BEDROOM),
    ("BEDROOM 2", RoomType.BEDROOM), ("Bed 3", RoomType.BEDROOM), ("BR", RoomType.BEDROOM),
    ("Bath", RoomType.BATHROOM), ("WC", RoomType.BATHROOM), ("w.c.", RoomType.BATHROOM),
    ("Toilet", RoomType.BATHROOM), ("Ensuite", RoomType.BATHROOM), ("en-suite", RoomType.BATHROOM),
    ("KITCHEN", RoomType.KITCHEN), ("Kitchenette", RoomType.KITCHEN),
    ("Living", RoomType.LIVING_ROOM), ("LOUNGE", RoomType.LIVING_ROOM), ("Family Room", RoomType.LIVING_ROOM),
    ("Dining", RoomType.DINING_ROOM),
    ("HALL", RoomType.HALLWAY), ("Corridor", RoomType.HALLWAY), ("passage", RoomType.HALLWAY),
    ("Foyer", RoomType.HALLWAY), ("ENTRY", RoomType.HALLWAY),
    ("Closet", RoomType.CLOSET), ("Wardrobe", RoomType.CLOSET), ("WIC", RoomType.CLOSET),
    ("Walk-in closet", RoomType.CLOSET),
    ("Garage", RoomType.GARAGE), ("Office", RoomType.OFFICE), ("Study", RoomType.OFFICE), ("Den", RoomType.OFFICE),
    ("Laundry", RoomType.LAUNDRY), ("Utility", RoomType.UTILITY),
    ("Balcony", RoomType.BALCONY), ("Terrace", RoomType.BALCONY), ("Deck", RoomType.BALCONY),
    ("Storage", RoomType.STORAGE), ("Store", RoomType.STORAGE), ("Pantry", RoomType.STORAGE),
    ("Stair", RoomType.STAIRWELL), ("STAIRS", RoomType.STAIRWELL),
])
def test_room_type_for_text(text: str, expected: RoomType) -> None:
    room_type, confidence = room_type_for_text(text)
    assert room_type == expected
    assert 0 < confidence <= 1


@pytest.mark.parametrize("text", ["", "   ", "123", "XYZZY", "garden"])
def test_unknown_labels(text: str) -> None:
    assert room_type_for_text(text) == (RoomType.UNKNOWN, 0.0)


def test_exact_synonym_scores_higher_than_pattern() -> None:
    assert room_type_for_text("kitchen")[1] > room_type_for_text("kitchen area")[1]


def test_synonyms_agree_with_classifier() -> None:
    for phrase, room_type in ROOM_SYNONYMS.items():
        assert room_type_for_text(phrase)[0] == room_type, phrase


def test_schema_files_up_to_date() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import export_schema

    expected = export_schema.build()
    on_disk = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "schema").glob("*.json")}
    assert on_disk == expected, "run: uv run python scripts/export_schema.py"


def test_synthetic_plans_are_deterministic() -> None:
    import synthetic_plan as sp

    for make, shape in ((sp.make_apartment_plan, (1200, 1600)), (sp.make_two_room_plan, (600, 1000))):
        a, b = make(), make()
        assert a.shape == shape and a.dtype.name == "uint8"
        assert hashlib.sha256(sp.to_png(a)).hexdigest() == hashlib.sha256(sp.to_png(b)).hexdigest()


def test_synthetic_plan_has_ink_where_walls_are() -> None:
    import synthetic_plan as sp

    img = sp.make_apartment_plan()
    assert img[100, 200] == 0                 # north wall of the living room
    assert img[100, 350] == 255               # its window glazing gap
    assert (img[300:400, 200:500] == 0).mean() < 0.05  # room interior is mostly paper
