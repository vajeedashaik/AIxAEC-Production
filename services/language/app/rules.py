"""Offline rule grammar: instruction → candidate command dict. Never invents ids or coordinates.

Anything it isn't sure about returns None (→ UNKNOWN). A silent wrong edit is worse than a clarification.
"""

import json
import re
import string
from collections.abc import Callable
from typing import Any

from aec_contracts import COMMAND_ADAPTER, ROOM_SYNONYMS, RoomType, room_type_for_text

UNKNOWN_DETAIL = (
    "That doesn't look like an edit I can apply. Try something like "
    '"move the wall between the kitchen and the living room 300 mm left", '
    '"add a door between the kitchen and the hall" or "rename the bedroom to Guest Room".'
)

Cmd = dict[str, Any]

_WORD_VALUES = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
_NUM_WORD = "|".join(_WORD_VALUES) + "|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million"
_NUM_WORD_RUN = re.compile(rf"\b(?:{_NUM_WORD})(?:[\s-]+(?:{_NUM_WORD}))*\b")
_SPOKEN_DECIMAL = re.compile(r"\b(\d+) point (\d+)\b")

_POLITE = re.compile(
    r"^(?:(?:please|kindly|now|ok|okay|can you|could you|would you|i want to|i'd like to|i would like to|let's|"
    r"lets)[\s,]+)+", re.IGNORECASE)
_NEGATIVE = re.compile(r"(?:^|[\s(,=])[-−–]\s*\.?\d|\bminus\b")
_QUANTIFIER = re.compile(r"\b(?:all|every|each|both)\b")
_ACTION = (r"move|shift|push|pull|slide|nudge|translate|relocate|add|draw|create|build|place|put|insert|install|cut|"
           r"make|expand|enlarge|grow|extend|widen|lengthen|increase|shrink|contract|reduce|narrow|shorten|decrease|"
           r"delete|remove|erase|demolish|clear|knock|tear|take|get rid|rename|call|label|name|calibrate|set")
_LEADING_ACTION = re.compile(rf"^(?:{_ACTION})\b")
_COMPOUND = re.compile(rf"(?:\band\b|\bthen\b|[,;])\s*(?:then\s+)?(?:{_ACTION})\b", re.IGNORECASE)

_NUM = r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?|\.\d+"
_UNIT = r"millimet(?:er|re)s?|mms?|centimet(?:er|re)s?|cms?|met(?:er|re)s?|m|pixels?|px"
_MEASURE = re.compile(rf"(?:\bby\s+)?(?<![\w.,-])({_NUM})[\s-]*({_UNIT})\b")

_DIRECTIONS = {"left": "LEFT", "right": "RIGHT", "up": "UP", "down": "DOWN", "north": "UP", "south": "DOWN",
               "east": "RIGHT", "west": "LEFT", "top": "UP", "bottom": "DOWN"}
# Lookahead: a direction ends the clause. "north wall" and "left bedroom" name things; they aren't movements.
_DIRECTION = re.compile(
    rf"(?:\b(?:to|towards?|from|on|at)\s+(?:the\s+)?)?\b({'|'.join(_DIRECTIONS)})(?:wards?)?\b(?:\s+side)?"
    rf"(?=\s*(?:$|,|the\b|(?:{'|'.join(_DIRECTIONS)})\b))")

_LEAD = re.compile(r"^(?:(?:the|a|an|on|in|to|into|of|along|at|across|through|for|from)\s+)+")
_SIDE = r"north|south|east|west|top|bottom|left|right"
_BETWEEN = re.compile(r"\b(?:between|separating|dividing|joining)\s+(.+?)\s+(?:and|&)\s+(.+?)(?:\s+wall)?$")
_SIDE_OF = re.compile(rf"\b({_SIDE})\s+wall\s+(?:of|in|on)\s+(.+)$")
_POSSESSIVE = re.compile(rf"^(.+?)'s\s+({_SIDE})\s+wall\b")
_WALL_OF = re.compile(r"\bwall\s+(?:of|in|on)\s+(.+)$")
_WALL_PHRASE = re.compile(r"^(.*?)\bwall\b")
_OPENING = re.compile(r"\b(?:door|window)s?\b")
_PRONOUN = {"it", "this", "that", "them", "there", "here", "one"}
_ROOM_ADJECTIVES = {"living": "living room", "dining": "dining room"}  # "the kitchen/living wall"

_RENAME = re.compile(r"^(?:rename|call|label|name)\s+(.+)$", re.IGNORECASE | re.DOTALL)
_MARK_AS = re.compile(r"^(.*?)\s+and\s+(?:mark|set|type|label|tag|classify)\s+it\s+as\s+(?:an?\s+)?(.+)$",
                      re.IGNORECASE | re.DOTALL)
_RENAME_TO = re.compile(r"^(.+?)\s+(?:to|as)\s+(.+)$", re.IGNORECASE | re.DOTALL)
_QUOTED_NAME = re.compile(r"""^(.+?)\s+['"‘“](.+?)['"’”]$""", re.DOTALL)

_SCALE_PREFIX = r"(?:(?:set|fix)\s+(?:the\s+)?scale|scale|calibrate)"
_SET_SCALE = re.compile(
    rf"^({_SCALE_PREFIX}(?:\s+(?:using|with|from|to|by|on))?\s*:?\s*)?(.*\bwall\b.*?)\s*"
    rf"(?:\bis\b|=|\bmeasures\b|\bequals\b|\bshould be\b)\s*({_NUM})\s*({_UNIT})\b(?:\s+(?:long|in length))?$")

_WALL_VERB = re.compile(r"^(?:add|draw|create|build|place|put|insert|make)\b.*\bwall\b")
_N = r"\d+(?:\.\d+)?"
_POINTS = re.compile(rf"\(?\s*({_N})\s*,\s*({_N})\s*\)?\s+(?:to|and)\s+\(?\s*({_N})\s*,\s*({_N})\s*\)?")
_XY = re.compile(rf"x1\s*[=:]\s*({_N})[\s,]+y1\s*[=:]\s*({_N})[\s,]+x2\s*[=:]\s*({_N})[\s,]+y2\s*[=:]\s*({_N})")
_THICK_PX = re.compile(rf"\b({_N})[\s-]*(?:px|pixels?)[\s-]+thick\b")

_MOVE_VERB = re.compile(r"^(?:move|shift|push|pull|slide|nudge|translate|relocate)\s+(.+)$")
_RESIZE_VERB = re.compile(r"^(?:make|expand|enlarge|grow|extend|widen|lengthen|increase|shrink|contract|reduce|narrow|"
                          r"shorten|decrease)\b(.*)$")
_EXPAND = r"expand|enlarge|grow|extend|widen|lengthen|increase|wider|bigger|larger|longer|taller"
_CONTRACT = r"shrink|contract|reduce|narrower|narrow|shorten|decrease|smaller|shorter"
_RESIZE_WORD = re.compile(rf"\b({_EXPAND}|{_CONTRACT})\b")
_EXPAND_WORD = re.compile(rf"^(?:{_EXPAND})$")

_ADD_OPENING = re.compile(r"^(?:add|put|insert|place|create|install|cut|make)\s+(.+)$")
_PERCENT = re.compile(rf"(?:\b(?:at|to)\s+|@\s*)?({_N})\s*(?:%|percent\b|per\s+cent\b)"
                      r"(?:\s+(?:of(?:\s+the\s+way)?|along|on|in|across)\b)?")
_MIDDLE = re.compile(r"\b(?:(?:in|at|on)\s+the\s+(?:middle|centre|center)(?:\s+of)?|"
                     r"halfway(?:\s+(?:along|on|across))?)\b")
_PERCENT_LEFT = re.compile(r"%|\bper\s?cent\b")
_BARE_WIDTH = re.compile(rf"(?<![\w.,-])({_NUM})\s+wide\b")

_DELETE_VERB = re.compile(r"^(?:delete|remove|erase|demolish|clear|knock\s+(?:down|out)|tear\s+down|"
                          r"take\s+(?:out|away)|get\s+rid\s+of)\s+(.+)$")


def _number(text: str) -> float:
    return float(text.replace(",", ""))


def _to_mm(value: float, unit: str) -> float:
    factor = 1 if unit.startswith(("mm", "milli")) else 10 if unit.startswith("c") else 1000
    return round(value * factor, 6)  # 1.1 * 1000 is 1100.0000000000002


def _distance(value: str, unit: str) -> Cmd:
    if unit.startswith("p"):
        return {"value": _number(value), "unit": "px"}
    return {"value": _to_mm(_number(value), unit), "unit": "mm"}


def _take_measures(text: str) -> tuple[list[Cmd], str]:
    return [_distance(m[1], m[2]) for m in _MEASURE.finditer(text)], _squash(_MEASURE.sub(" ", text))


def _take_direction(text: str) -> tuple[str | None, str]:
    found = {_DIRECTIONS[m[1]] for m in _DIRECTION.finditer(text)}
    return (found.pop() if len(found) == 1 else None), _squash(_DIRECTION.sub(" ", text))


def _squash(text: str) -> str:
    return " ".join(text.split())


def _room(name: str) -> str:
    name = _LEAD.sub("", name.strip())
    return _ROOM_ADJECTIVES.get(name, name)


def _pair(a: str, b: str, noun: str) -> str | None:
    a, b = _room(a), _room(b)
    return None if not a or not b or " and " in f"{a} {b}" else f"{noun} between {a} and {b}"


def _split_rooms(phrase: str) -> tuple[str, str] | None:
    """"kitchen/bedroom", "kitchen-bedroom", "living room kitchen" → the two rooms. Slash splits any label."""
    if phrase.count("/") == 1:
        a, b = phrase.split("/")
        return a.strip(), b.strip()
    if phrase in ROOM_SYNONYMS:  # "en-suite" is one room
        return None
    words = phrase.replace("-", " ").split()
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if a in ROOM_SYNONYMS and b in ROOM_SYNONYMS:
            return a, b
    return None


def _wall_target(text: str) -> str | None:
    text = _LEAD.sub("", text.strip())
    if _OPENING.search(text):  # "move the door …": MOVE_WALL would edit the wrong element
        return None
    if m := _BETWEEN.search(text):
        return _pair(m[1], m[2], "wall")
    if re.search(r"\bbetween\b", text):  # only one room named: don't lose it and target any "wall"
        return None
    if m := _SIDE_OF.search(text):
        return f"{m[1]} wall of {_room(m[2])}"
    if m := _POSSESSIVE.search(text):
        return f"{m[2]} wall of {_room(m[1])}"
    if m := _WALL_OF.search(text):
        return f"{_room(m[1])} wall"
    if not (m := _WALL_PHRASE.search(text)):
        return None
    phrase = _LEAD.sub("", m[1].strip()).removesuffix("'s")
    if not phrase:
        return "wall"
    if rooms := _split_rooms(phrase):
        return _pair(*rooms, "wall")
    return f"{phrase} wall"


def _room_target(text: str) -> str | None:
    target = _room(text)
    if not target or target in _PRONOUN or " and " in target or re.search(r"\bwalls?\b", target):
        return None
    return None if _OPENING.search(target) else target


def _rename(raw: str) -> Cmd | None:
    if not (m := _RENAME.match(raw)):
        return None
    body, room_type = m[1], None
    if mark := _MARK_AS.match(body):
        body = mark[1]
        room_type, _ = room_type_for_text(mark[2])
    if to := _RENAME_TO.match(body):
        target, name = to[1], to[2].strip()
        quoted = len(name) > 2 and name[0] in "'\"‘“" and name[-1] in "'\"’”"
        name = name[1:-1] if quoted else (string.capwords(name) if name.islower() else name)
    elif q := _QUOTED_NAME.match(body):
        target, name = q[1], q[2]
    else:
        return None
    target = _LEAD.sub("", target.strip().lower())
    target = re.sub(r"^room\s+(?!\d)", "", target)
    if not target or target in _PRONOUN:
        return None
    if room_type is None:  # only a name that means a different kind of room changes the type
        implied, _ = room_type_for_text(name)
        current, _ = room_type_for_text(target)
        room_type = implied if implied != current else None
    cmd: Cmd = {"operation": "RENAME_ROOM", "target_query": target, "name": name}
    if room_type is not None and room_type is not RoomType.UNKNOWN:
        cmd["room_type"] = room_type.value
    return cmd


def _set_scale(text: str) -> Cmd | None:
    if not (m := _SET_SCALE.match(text)) or m[4].startswith("p"):  # a px length can't calibrate anything
        return None
    phrase = m[2].strip()
    if _LEADING_ACTION.match(phrase) or not (m[1] or re.match(r"(?:the|this|that|wall)\b", phrase)):
        return None
    if not (target := _wall_target(phrase)):
        return None
    return {"operation": "SET_SCALE", "target_query": target, "length_mm": _to_mm(_number(m[3]), m[4])}


def _add_wall(text: str) -> Cmd | None:
    if not _WALL_VERB.match(text) or not (m := _POINTS.search(text) or _XY.search(text)):
        return None
    cmd: Cmd = {"operation": "ADD_WALL", "start": {"x": float(m[1]), "y": float(m[2])},
                "end": {"x": float(m[3]), "y": float(m[4])}}
    if thick := _THICK_PX.search(text):
        cmd["thickness_px"] = float(thick[1])
    elif re.search(r"\bthick", text):  # "10 mm thick": thickness is px-only and px is never mm
        return None
    return cmd


def _move(text: str) -> Cmd | None:
    if not (m := _MOVE_VERB.match(text)):
        return None
    measures, rest = _take_measures(m[1])
    direction, rest = _take_direction(rest)
    if len(measures) != 1 or direction is None:
        return None
    target = _wall_target(rest)
    return {"operation": "MOVE_WALL", "target_query": target, "direction": direction,
            "distance": measures[0]} if target else None


def _resize(text: str) -> Cmd | None:
    if not (m := _RESIZE_VERB.match(text)):
        return None
    modes = {"EXPAND" if _EXPAND_WORD.match(w[1]) else "CONTRACT" for w in _RESIZE_WORD.finditer(text)}
    measures, rest = _take_measures(m[1])
    direction, rest = _take_direction(rest)
    if len(modes) != 1 or len(measures) != 1 or direction is None:
        return None
    target = _room_target(_squash(_RESIZE_WORD.sub(" ", rest)))
    return {"operation": "RESIZE_ROOM", "target_query": target, "direction": direction, "distance": measures[0],
            "mode": modes.pop()} if target else None


def _add_opening(text: str) -> Cmd | None:
    if not (m := _ADD_OPENING.match(text)):
        return None
    body = m[1]
    nouns = set(re.findall(r"\b(door|window)\b", body))
    if len(nouns) != 1 or re.search(r"\b(?:door|window)s\b", body):
        return None
    noun = nouns.pop()

    percents = _PERCENT.findall(body)
    middle = _MIDDLE.search(body)
    if len(percents) > 1 or (percents and middle):
        return None
    position = round(float(percents[0]) / 100, 6) if percents else 0.5
    body = _MIDDLE.sub(" ", _PERCENT.sub(" ", body))
    if _PERCENT_LEFT.search(body):  # "at thirty percent" must not silently become the default position
        return None

    bare = _BARE_WIDTH.findall(body)  # "900 wide": a bare width is millimetres
    measures, body = _take_measures(_BARE_WIDTH.sub(" ", body))
    widths = [{"value": _number(v), "unit": "mm"} for v in bare] + measures
    if len(widths) > 1:
        return None
    body = re.sub(r"\bwide\b", " ", body)

    before, _, after = body.partition(noun)
    if re.search(r"\d", before):  # "a 900 door": a number we can't interpret
        return None
    after = _squash(after)
    target = _wall_target(after) if re.search(r"\b(?:wall|between)\b", after) else _room_target(after)
    if not target:
        return None
    cmd: Cmd = {"operation": f"ADD_{noun.upper()}", "target_query": target, "position": position}
    if widths:
        cmd["width"] = widths[0]
    return cmd


def _opening_target(noun: str, text: str) -> str | None:
    text = _LEAD.sub("", text)
    if m := _BETWEEN.search(text):
        return _pair(m[1], m[2], noun)
    if not (m := re.fullmatch(rf"(.*?)\s*\b{noun}(?:\s+(?:in|of|from|on|at|for|to)\s+(.+))?", text)):
        return None
    return _squash(" ".join((_room(m[2] or ""), m[1], noun)))


def _delete(text: str) -> Cmd | None:
    if not (m := _DELETE_VERB.match(text)):
        return None
    body = m[1]
    nouns = set(re.findall(r"\b(door|window)\b", body))
    if len(nouns) > 1:
        return None
    if nouns:
        noun = nouns.pop()
        target = _opening_target(noun, body)
        return {"operation": f"DELETE_{noun.upper()}", "target_query": target} if target else None
    target = _wall_target(body)
    return {"operation": "DELETE_WALL", "target_query": target} if target else None


_HANDLERS: tuple[Callable[[str], Cmd | None], ...] = (_set_scale, _add_wall, _move, _resize, _add_opening, _delete)


def check_command(raw: Cmd) -> None:
    """Quality gate. Raises ValueError (pydantic's ValidationError is one) if the command isn't contract-valid."""
    COMMAND_ADAPTER.validate_python(raw)
    json.dumps(raw, allow_nan=False)  # thickness_px accepts inf, which can't be serialized


def _normalize(raw: str) -> str:
    text = raw.lower().replace("’", "'")
    # A run like "twenty five" stays as words: no digits, so "5 mm" can't be misread out of it.
    text = _NUM_WORD_RUN.sub(lambda m: _WORD_VALUES.get(m[0], m[0]), text)
    return _squash(_SPOKEN_DECIMAL.sub(r"\1.\2", re.sub(r"\bplease\b", " ", text)))


def parse_rules(instruction: str) -> Cmd | None:
    raw = _POLITE.sub("", instruction.strip()).rstrip(" .!?").strip()
    if _COMPOUND.search(raw):  # one command per request: never apply half of a sentence
        return None
    cmd = _rename(raw)
    if cmd is None:
        text = _normalize(raw)
        if _NEGATIVE.search(text) or _QUANTIFIER.search(text):
            return None
        cmd = next((c for handler in _HANDLERS if (c := handler(text)) is not None), None)
    if cmd is None:
        return None
    try:
        check_command(cmd)
    except ValueError:
        return None
    return cmd
