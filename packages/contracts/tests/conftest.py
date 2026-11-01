import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
sys.path.insert(0, str(FIXTURES))  # synthetic_plan / builders are plain modules, not part of the package


def load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def apartment() -> dict[str, Any]:
    data: dict[str, Any] = load("apartment.model.json")
    return data
