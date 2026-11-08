import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def _ignore_local_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """A developer's .env holds real keys. Tests state their own settings and must not pick those up."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
