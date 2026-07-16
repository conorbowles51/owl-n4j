"""Static fixture corpora for the backend test suite."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).parent


def load_fixture(relative_path: str) -> Any:
    """Load a JSON fixture by path relative to tests/fixtures.

    Resolved against ``__file__`` so tests do not depend on the working
    directory.
    """
    return json.loads((FIXTURES_DIR / relative_path).read_text(encoding="utf-8"))
