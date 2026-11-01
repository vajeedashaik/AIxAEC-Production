import math

import cv2
import numpy as np

from app.vision.preprocess import Preprocessed
from app.vision.rooms import detect_rooms
from app.vision.strokes import estimate_wall_thickness
from app.vision.walls import WallDetection

from .conftest import APARTMENT_WORDS, fixture_model, pre_and_walls, sp, two_room_with_openings, word


def blank(width: int = 1000, height: int = 800) -> np.ndarray:
    return np.full((height, width), 255, np.uint8)


def test_two_room_walls(two_room: tuple[Preprocessed, WallDetection]) -> None:
    walls = two_room[1].walls
    assert len(walls) == 5  # 4 outer + the partition: T-junction pieces merge into one wall
    assert all(w.is_horizontal or w.is_vertical for w in walls)
    assert all(w.confidence == 0.9 for w in walls)
    ends = {tuple(round(v) for v in (w.x1, w.y1, w.x2, w.y2)) for w in walls}
    assert ends == {
        (100, 100, 900, 100),
        (100, 500, 900, 500),
        (100, 100, 100, 500),
        (900, 100, 900, 500),
        (500, 100, 500, 500),
    }


def test_thickness_estimate_within_one_px(two_room: tuple[Preprocessed, WallDetection]) -> None:
    assert two_room[1].thickness is not None
    assert abs(two_room[1].thickness - 20) <= 1


def test_each_wall_keeps_its_own_thickness(two_room: tuple[Preprocessed, WallDetection]) -> None:
    partition = next(w for w in two_room[1].walls if round(w.x1) == 500)
    assert abs(partition.thickness - 10) <= 1
    assert all(abs(w.thickness - 20) <= 1 for w in two_room[1].walls if w is not partition)


def test_door_gap_bridged_and_window_classified() -> None:
    _, detection = pre_and_walls(two_room_with_openings())
    assert len(detection.walls) == 5  # bridged: still one continuous wall each
    partition = next(w for w in detection.walls if round(w.x1) == 500)
    assert (round(partition.y1), round(partition.y2)) == (100, 500)
    assert sorted(o.kind for o in detection.openings) == ["door", "window"]
    door = next(o for o in detection.openings if o.kind == "door")
    window = next(o for o in detection.openings if o.kind == "window")
    assert abs(door.width - 90) <= 3
    assert abs(window.width - 120) <= 3
    assert abs(door.x1 - 500) <= 1 and abs(door.y1 - 250) <= 3


def test_apartment_openings_match_fixture(apartment: tuple[Preprocessed, WallDetection]) -> None:
    kinds = [o.kind for o in apartment[1].openings]
    assert kinds.count("door") == 4 and kinds.count("window") == 3


def test_gap_between_t_junctions_is_open_floor_not_a_door(apartment: tuple[Preprocessed, WallDetection]) -> None:
    """x=960 stops at the hall's two walls with 150 px between: under the bridge limit, but no wall there."""
    verticals = [w for w in apartment[1].walls if round(w.x1) == 960 and w.is_vertical]
    assert sorted((round(w.y1), round(w.y2)) for w in verticals) == [(100, 550), (700, 900)]


def test_collinear_walls_of_different_thickness_stay_separate(apartment: tuple[Preprocessed, WallDetection]) -> None:
    row = sorted((w for w in apartment[1].walls if round(w.y1) == 700 and w.is_horizontal), key=lambda w: w.x1)
    assert [(round(w.x1), round(w.x2)) for w in row] == [(100, 960), (960, 1300)]
    assert row[0].thickness > row[1].thickness


def test_hatching_and_text_yield_no_walls() -> None:
    img = blank()
    for c in range(-800, 1000, 14):
        cv2.line(img, (c, 0), (c + 800, 800), 0, 1)
    cv2.putText(img, "NOT A WALL", (100, 400), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2, cv2.LINE_AA)
    _, detection = pre_and_walls(img)
    assert detection.walls == []


def test_hairline_plan_has_no_thickness() -> None:
    img = blank()
    cv2.rectangle(img, (100, 100), (900, 700), 0, 1)
    cv2.rectangle(img, (104, 104), (896, 696), 0, 1)
    pre, detection = pre_and_walls(img)
    assert estimate_wall_thickness(pre.binary) is None
    assert detection.walls == []


def test_blank_image_yields_nothing() -> None:
    _, detection = pre_and_walls(blank())
    assert detection.walls == [] and detection.thickness is None


def test_free_standing_column_is_not_a_wall() -> None:
    img = blank()
    cv2.rectangle(img, (100, 100), (900, 700), 0, 20)
    cv2.rectangle(img, (480, 380), (540, 440), 0, -1)
    _, detection = pre_and_walls(img)
    assert len(detection.walls) == 4


def test_diagonal_wall_detected_with_low_confidence() -> None:
    img = blank()
    pts = np.array([[100, 100], [900, 100], [900, 450], [550, 700], [100, 700]], np.int32)
    cv2.polylines(img, [pts], True, 0, 20)
    pre, detection = pre_and_walls(img)
    diagonals = [w for w in detection.walls if not (w.is_horizontal or w.is_vertical)]
    assert len(diagonals) == 1
    assert diagonals[0].confidence == 0.45
    # Snapped: its ends land on the axis walls' centre-lines, closing the room.
    assert math.dist(diagonals[0].ends[0], (550, 700)) <= 6
    assert math.dist(diagonals[0].ends[1], (900, 450)) <= 6
    rooms = detect_rooms(detection.walls, pre.size, [])
    assert len(rooms) == 1
    assert len(rooms[0].points) == 5


def _assert_corners(points: list[tuple[float, float]], expected: list[tuple[float, float]], tol: float = 3.0) -> None:
    assert len(points) == len(expected)
    for corner in expected:
        assert min(math.dist(corner, p) for p in points) <= tol, corner


def test_two_room_polygons_on_centre_lines(two_room: tuple[Preprocessed, WallDetection]) -> None:
    pre, detection = two_room
    rooms = detect_rooms(detection.walls, pre.size, [])
    assert len(rooms) == 2
    left, right = sorted(rooms, key=lambda r: min(p[0] for p in r.points))
    _assert_corners(left.points, [(100, 100), (500, 100), (500, 500), (100, 500)])
    _assert_corners(right.points, [(500, 100), (900, 100), (900, 500), (500, 500)])


def test_apartment_rooms_and_labels(apartment: tuple[Preprocessed, WallDetection]) -> None:
    pre, detection = apartment
    rooms = detect_rooms(detection.walls, pre.size, APARTMENT_WORDS)
    expected = {r["label_text"]: r for r in fixture_model("apartment.model.json")["rooms"]}
    assert sorted(r.label or "" for r in rooms) == sorted(expected)
    for room in rooms:
        assert room.label is not None
        # The fixture spells out collinear vertices along the hall; a polygon only needs the real corners.
        corners = [(p["x"], p["y"]) for p in expected[room.label]["polygon"]]
        for corner in room.points:
            assert min(math.dist(corner, c) for c in corners) <= 3.0


def test_label_ignores_digits_noise_and_low_confidence(two_room: tuple[Preprocessed, WallDetection]) -> None:
    pre, detection = two_room
    words = [word("3600", 300, 300), word("X", 300, 280), word("MASTER", 280, 200), word("BED", 340, 200)]
    faint = word("GHOST", 300, 400)
    words.append(type(faint)(faint.text, faint.x, faint.y, faint.width, faint.height, 0.2))
    rooms = detect_rooms(detection.walls, pre.size, words)
    left = min(rooms, key=lambda r: min(p[0] for p in r.points))
    assert left.label == "MASTER BED"


def test_unclosed_outline_makes_no_rooms() -> None:
    img = blank()
    cv2.line(img, (100, 100), (900, 100), 0, 20)
    cv2.line(img, (100, 100), (100, 700), 0, 20)
    pre, detection = pre_and_walls(img)
    assert detect_rooms(detection.walls, pre.size, []) == []


def test_apartment_plan_is_the_expected_size() -> None:
    assert sp.make_apartment_plan().shape == (1200, 1600)


def test_dense_plan_stays_fast() -> None:
    """19 × 19 rooms with a door in every wall: hundreds of gaps once took minutes to bridge."""
    import time

    img = blank(2400, 2400)
    for i in range(100, 2301, 120):
        cv2.line(img, (100, i), (2300, i), 0, 12)
        cv2.line(img, (i, 100), (i, 2300), 0, 12)
    for i in range(100, 2300, 120):
        for j in range(160, 2300, 120):
            img[i - 8 : i + 8, j - 25 : j + 25] = 255
            img[j - 25 : j + 25, i - 8 : i + 8] = 255
    start = time.perf_counter()
    _, detection = pre_and_walls(img)
    assert time.perf_counter() - start < 10
    assert len(detection.walls) == 38
    assert len(detection.openings) == 684
