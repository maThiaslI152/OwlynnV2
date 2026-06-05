"""
HITL Fixtures Loader

Loads canonical interrupt payloads from tests/fixtures/hitl/ for use by
tests, dev API, and frontend mock previews.
"""

import json
from pathlib import Path

_FIXTURE_DIR = (
    Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "hitl"
)


def load_fixture(name: str) -> dict:
    """Load a HITL fixture by name (without .json extension).

    Returns the fixture dict, mirroring ``serialize_interrupt_item`` output shape.

    Example::

        >>> load_fixture("security_delete_file")
        {"type": "security_approval_required", ...}
    """
    if not name.endswith(".json"):
        name = f"{name}.json"
    path = _FIXTURE_DIR / name
    if not path.exists():
        available = [p.stem for p in sorted(_FIXTURE_DIR.glob("*.json"))]
        raise FileNotFoundError(
            f"Fixture '{name}' not found. Available: {', '.join(available)}"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def list_fixtures() -> list[str]:
    """Return sorted list of available fixture names (without .json extension)."""
    return sorted(p.stem for p in _FIXTURE_DIR.glob("*.json"))
