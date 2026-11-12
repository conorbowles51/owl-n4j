"""Process a case's failed files again, through the production send (chunked: services/evidence_chunking.py).

Selects by status = 'failed', never by error text, and prints every reason found first (services/evidence_failures).
Dry run by default; --apply sends. The backend settles each status within 5 minutes of its job ending.
    set -a; . <app>/.env; set +a; PYTHONPATH=. python scripts/reprocess_failed_files.py --case <uuid> [--apply]
"""
import argparse
import asyncio
import sys
import uuid
from collections import Counter


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, type=uuid.UUID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    from postgres.session import _get_session_local
    from services import evidence_failures
    from services.evidence_processing_service import process_db_files

    with _get_session_local()() as db:
        found = evidence_failures.summary(db, args.case)
        print(f"failed files: {found['total']}")
        for line in evidence_failures.report_lines(found["by_case"].get(str(args.case)) or Counter()):
            print(f"  {line}")
        if not args.apply or not found["total"]:
            return 0
        result = asyncio.run(process_db_files(db, case_id=args.case,
                                              file_ids=[uuid.UUID(i) for i in found["file_ids"]]))
        print(result.get("message"))
        for item in result.get("refused") or []:
            print(f"  refused: {item['name']}: {item['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
