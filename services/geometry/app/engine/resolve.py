"""Entity resolution: turn a free-text target_query into one element id, or ask. Never guesses."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from aec_contracts import TARGET_KIND, Candidate, Direction, FloorPlanModel, Room, Wall
from aec_contracts.commands import Targeted
from aec_contracts.lexicon import ROOM_SYNONYMS
from aec_contracts.model import Opening

from .errors import ClarificationNeeded, ResolutionError
from .geom import midpoint, room_polygons, rooms_by_side, wall_axis

SAME_EDGE_PX = 2.0
_SIDE = {"north": Direction.UP, "top": Direction.UP, "upper": Direction.UP,
         "south": Direction.DOWN, "bottom": Direction.DOWN, "lower": Direction.DOWN,
         "east": Direction.RIGHT, "right": Direction.RIGHT, "west": Direction.LEFT, "left": Direction.LEFT}
_SIDES = "|".join(_SIDE)
_KIND = r"(?:walls?|doors?|windows?)"
# "north wall", "north side of", "north of": never the bare word, which may be part of a label ("East Wing").
_SIDE_BEFORE_KIND = re.compile(rf"\b({_SIDES})(?:ern)?(?:\s+side)?(?:\s+{_KIND}\b|\s+of\b|$)")
_BARE_SIDE = re.compile(rf"\b({_SIDES})(?:ern)?\b")
_FILLER = re.compile(rf"\b(?:{_KIND}|the|a|an|of|in|on|at|to|this|that|my)\b")
_BETWEEN = re.compile(r"^(?:between\s+)?(.+?)\s+and\s+(.+)$")
_SHARED = re.compile(r"\b(?:shared|common|interior|internal)\s+walls?\b")  # not the bare word: "Common Room"
_NOT_A_ROOM = {"front", "back", "rear", "main", "side"}  # "front door" names no room, so it isn't a room phrase
_COMPASS = {Direction.UP: "north", Direction.DOWN: "south", Direction.RIGHT: "east", Direction.LEFT: "west"}
KINDS = {"wall": "walls", "room": "rooms", "door": "doors", "window": "windows"}


def _clean(text: str) -> str:
    text = re.sub(r"['’]s\b", "", text.lower())
    return " ".join(re.sub(r"[^\w\- ]+", " ", text).split())


def room_name(room: Room) -> str:
    if room.label_text:
        return room.label_text.strip().lower()
    return "unnamed room" if room.room_type == "UNKNOWN" else room.room_type.replace("_", " ").lower()


def _contains_word_start(haystack: str, needle: str) -> bool:
    return len(needle) >= 2 and re.search(rf"\b{re.escape(needle)}", haystack) is not None


def match_rooms(model: FloorPlanModel, phrase: str) -> list[Room]:
    """Label substring (either direction) or synonym. "master bedroom" must not also pick a plain "BEDROOM"."""
    synonym = ROOM_SYNONYMS.get(phrase)
    labelled = [(r, _clean(r.label_text or "")) for r in model.rooms]
    direct = [r for r, label in labelled if _contains_word_start(label, phrase) or r.room_type == synonym]
    return direct or [r for r, label in labelled if _contains_word_start(phrase, label)]


@dataclass
class _Query:
    phrase: str
    side: Direction | None = None
    between: tuple[str, str] | None = None
    shared: bool = False


def _parse(model: FloorPlanModel, query: str) -> _Query:
    text = _clean(query)
    side = None
    if m := _SIDE_BEFORE_KIND.search(text):
        side = _SIDE[m[1]]
        text = text[:m.start()] + " " + text[m.end():]
    shared = _SHARED.search(text) is not None
    text = " ".join(_FILLER.sub(" ", _SHARED.sub(" ", text)).split())
    if m := _BETWEEN.match(text):
        return _Query("", side, (m[1], m[2]))
    labels = " ".join(_clean(r.label_text or "") for r in model.rooms)
    if side is None and (m := _BARE_SIDE.search(text)) and m[0] not in labels:  # "north kitchen", but "east wing"
        side = _SIDE[m[1]]
        text = " ".join((text[:m.start()] + text[m.end():]).split())
    return _Query("" if text in _NOT_A_ROOM else text, side, None, shared)


def _in_model_order(walls: Iterable[Wall], model: FloorPlanModel) -> list[Wall]:
    """Deduplicated, so the same input always asks in the same order."""
    ids = {w.id for w in walls}
    return [w for w in model.walls if w.id in ids]


def _walls_of(model: FloorPlanModel, room: Room) -> list[Wall]:
    return [w for w in model.walls if w.id in room.wall_ids]


def _narrow(walls: list[Wall], side: Direction | None) -> list[Wall]:
    """The north wall of a room is its topmost horizontal wall, and so on."""
    if side is None:
        return walls
    horizontal = side in (Direction.UP, Direction.DOWN)
    aligned = [w for w in walls if wall_axis(w) == ("horizontal" if horizontal else "vertical")]
    if not aligned:
        return []
    position = [midpoint(w)[1 if horizontal else 0] for w in aligned]
    edge = min(position) if side in (Direction.UP, Direction.LEFT) else max(position)
    return [w for w, p in zip(aligned, position, strict=True) if abs(p - edge) <= SAME_EDGE_PX]


def _rooms_or_reject(model: FloorPlanModel, phrase: str) -> list[Room]:
    rooms = match_rooms(model, phrase)
    if not rooms:
        raise ResolutionError(f"I can't find a room called '{phrase}'.")
    return rooms


def _walls_for(model: FloorPlanModel, q: _Query) -> list[Wall]:
    """The walls a query can refer to. Empty sets are refused here, with the reason."""
    if q.between:
        first, second = (_rooms_or_reject(model, phrase) for phrase in q.between)
        shared = [w for a in first for b in second if a.id != b.id for w in _walls_of(model, a) if w.id in b.wall_ids]
        if not shared:
            raise ResolutionError("Those rooms don't share a wall.")
        # Vision merges collinear walls, so a long exterior wall can be linked to both rooms without separating them.
        # Prefer walls with one room on each side; if none, keep them all and let the user pick.
        polygons = room_polygons(model)
        a_ids, b_ids = {r.id for r in first}, {r.id for r in second}

        def separates(w: Wall) -> bool:
            one, other = ({r.id for r in side} for side in rooms_by_side(model, w, polygons))
            return bool((one & a_ids and other & b_ids) or (one & b_ids and other & a_ids))

        shared = [w for w in shared if separates(w)] or shared
        walls = _in_model_order(_narrow(shared, q.side), model)
        if not walls:
            raise ResolutionError("Those rooms don't share a wall on that side.")
        return walls
    if q.phrase:
        rooms = _rooms_or_reject(model, q.phrase)
        linked = [w for r in rooms for w in _walls_of(model, r)]
        name = room_name(rooms[0])
        if not linked:
            raise ResolutionError(f"No walls are linked to {name}.")
        walls = _in_model_order([w for r in rooms for w in _narrow(_walls_of(model, r), q.side)], model)
        if not walls:
            raise ResolutionError(f"The {name} has no {_COMPASS[q.side]} wall." if q.side else
                                  f"No walls are linked to {name}.")
        return walls
    if q.shared:
        walls = [w for w in model.walls if sum(w.id in r.wall_ids for r in model.rooms) >= 2]
        if not walls:
            raise ResolutionError("No wall is shared by two rooms.")
        polygons = room_polygons(model)
        return [w for w in walls if all(rooms_by_side(model, w, polygons))] or walls  # rooms on both sides
    walls = _narrow(model.walls, q.side)
    if not walls:
        raise ResolutionError("There is no wall on that side of the plan.")
    return walls


def _rooms_of_wall(model: FloorPlanModel, wall_id: UUID | None) -> list[str]:
    return [room_name(r) for r in model.rooms if wall_id in r.wall_ids]


def _wall_candidate(model: FloorPlanModel, wall: Wall) -> Candidate:
    rooms = _rooms_of_wall(model, wall.id)
    suffix = f" ({' ↔ '.join(rooms)})" if rooms else ""
    x, y = midpoint(wall)
    label = f"{wall_axis(wall)} wall, {wall.length_px:.0f} px long{suffix}"
    return Candidate(id=wall.id, kind="wall", label=label, x=round(x, 2), y=round(y, 2))


def _opening_candidate(model: FloorPlanModel, opening: Opening, kind: Literal["door", "window"]) -> Candidate:
    x, y = opening.bbox.x + opening.bbox.width / 2, opening.bbox.y + opening.bbox.height / 2
    rooms = _rooms_of_wall(model, opening.wall_id) if opening.wall_id else []
    suffix = f" in {' / '.join(rooms)}" if rooms else ""
    return Candidate(id=opening.id, kind=kind,
                     label=f"{kind} at ({x:.0f}, {y:.0f}){suffix}", x=round(x, 2), y=round(y, 2))


def _room_candidate(room: Room) -> Candidate:
    n = len(room.polygon)
    x, y = sum(p.x for p in room.polygon) / n, sum(p.y for p in room.polygon) / n
    return Candidate(id=room.id, kind="room", label=f"{room_name(room)} at ({x:.0f}, {y:.0f})",
                     x=round(x, 2), y=round(y, 2))


def _resolve_room(model: FloorPlanModel, query: str) -> UUID:
    phrase = _clean(re.sub(r"\bthe\b", " ", query, flags=re.IGNORECASE))
    rooms = list(model.rooms) if phrase in ("", "room") else _rooms_or_reject(model, phrase)
    if not rooms:
        raise ResolutionError("This plan has no rooms.")
    if len(rooms) == 1:
        return rooms[0].id
    raise ClarificationNeeded("Which room do you mean?", [_room_candidate(r) for r in rooms])


def _resolve_wall(model: FloorPlanModel, query: str) -> UUID:
    if not model.walls:
        raise ResolutionError("This plan has no walls yet.")
    if len(model.walls) == 1:
        return model.walls[0].id
    q = _parse(model, query)
    walls = _walls_for(model, q)
    if len(walls) == 1:
        return walls[0].id
    question = f"Which {q.phrase} wall do you mean?" if q.phrase else "Which wall do you mean?"
    raise ClarificationNeeded(question, [_wall_candidate(model, w) for w in walls])


def _resolve_opening(model: FloorPlanModel, query: str, kind: Literal["door", "window"],
                     openings: Sequence[Opening]) -> UUID:
    if not openings:
        raise ResolutionError(f"This plan has no {kind}s.")
    q = _parse(model, query)
    if q.between or q.phrase or q.side or q.shared:
        walls = {w.id for w in _walls_for(model, q)}
        matched = [o for o in openings if o.wall_id in walls]
        if not matched:
            where = f"in {q.phrase}" if q.phrase else "there"
            raise ResolutionError(f"I can't find a {kind} {where}.")
    else:
        matched = list(openings)
    if len(matched) == 1:
        return matched[0].id
    raise ClarificationNeeded(f"Which {kind} do you mean?", [_opening_candidate(model, o, kind) for o in matched])


def _check_kind(model: FloorPlanModel, target_id: UUID, kind: str) -> None:
    if any(e.id == target_id for e in getattr(model, KINDS[kind])):
        return
    for other, attr in KINDS.items():
        if any(e.id == target_id for e in getattr(model, attr)):
            raise ResolutionError(f"That target is a {other}, not a {kind}.")
    raise ResolutionError(f"No {kind} with that id exists in this plan.")


def resolve_target(model: FloorPlanModel, command: Targeted, operation: str) -> UUID:
    kind = TARGET_KIND[operation]
    if command.target_id is not None:
        _check_kind(model, command.target_id, kind)
        return command.target_id
    query = command.target_query or ""
    if kind == "room":
        return _resolve_room(model, query)
    if kind == "wall":
        return _resolve_wall(model, query)
    if kind == "door":
        return _resolve_opening(model, query, "door", model.doors)
    return _resolve_opening(model, query, "window", model.windows)
