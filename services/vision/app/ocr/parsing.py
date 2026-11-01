"""Dimension text → millimetres. Returns None for anything that isn't clearly a dimension."""

import re

_METRIC = re.compile(r"^(\d+(?:\.\d+)?)\s*(mm|cm|m)$", re.IGNORECASE)
_BARE = re.compile(r"^\d{1,3}(?:,\d{3})+$|^\d+$")
_IMPERIAL = re.compile(
    r"""^(?:(\d+(?:\.\d+)?)\s*(?:'|ft|feet)\s*-?\s*)?(?:(\d+(?:\.\d+)?)\s*(?:"|''|in|inch|inches))?$""",
    re.IGNORECASE,
)
_METRIC_FACTOR = {"mm": 1.0, "cm": 10.0, "m": 1000.0}


def parse_dimension(text: str) -> float | None:
    s = text.strip().replace("’", "'").replace("′", "'").replace("”", '"').replace("″", '"').replace("“", '"')
    if not s:
        return None
    if m := _METRIC.match(s):
        value = float(m[1]) * _METRIC_FACTOR[m[2].lower()]
        return value if value > 0 else None
    if _BARE.match(s):
        value = float(s.replace(",", ""))
        return value if 100 <= value <= 100_000 else None  # outside this a bare number is not a plausible mm length
    if (m := _IMPERIAL.match(s)) and (m[1] or m[2]):
        value = float(m[1] or 0) * 304.8 + float(m[2] or 0) * 25.4
        return value if value > 0 else None
    return None
