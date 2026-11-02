"""Apply the phone registry seed idempotently (02 section 3.5).

    python scripts/phone_registry_seed.py            # DATABASE_URL from the environment

Inserts missing rows with origin ``seed``; on a rerun only seed columns change. Prints the registry counts.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine  # noqa: E402

from postgres.session import _database_url  # noqa: E402
from services.phone import registry  # noqa: E402


def main():
    engine = create_engine(_database_url())
    with engine.begin() as conn:
        print(registry.apply_seed(conn))


if __name__ == "__main__":
    main()
