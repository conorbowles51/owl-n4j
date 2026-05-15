"""
Compatibility entry point for embedding backfills.

Document-level embedding backfills now use the Postgres evidence-backed chunk
backfill implementation. This module is kept as a CLI alias for operators who
still call scripts/backfill_embeddings.py directly.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from scripts.backfill_chunk_embeddings import backfill_chunk_embeddings


def backfill_embeddings(
    dry_run: bool = False,
    skip_existing: bool = True,
    batch_size: int = 10,
) -> Dict[str, Any]:
    return backfill_chunk_embeddings(
        dry_run=dry_run,
        skip_existing=skip_existing,
        batch_size=batch_size,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Backfill embeddings from Postgres evidence")
    parser.add_argument("--dry-run", action="store_true", help="Run without making changes")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", action="store_false", dest="skip_existing")
    parser.add_argument("--batch-size", type=int, default=10)

    args = parser.parse_args()
    result = backfill_embeddings(
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
        batch_size=args.batch_size,
    )
    if result.get("status") == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
