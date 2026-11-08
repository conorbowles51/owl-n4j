"""Daily outside time-stamp of each case's audit chain head (services/financial/audit_head_anchor.py).

    set -a; . <app>/.env; set +a
    python scripts/anchor_audit_heads.py stamp --all-cases --output <dir> --tsa-url <url> --ca-file <root.pem>
    python scripts/anchor_audit_heads.py verify --case-id <uuid> --output <dir>

stamp prints one JSON line per case and a last line with the counts by status; exit 0 when every case is stamped,
unchanged or has no events, 2 when any case needs attention (its line says why). Only each checkpoint's SHA-256
fingerprint is sent to the authority.
"""
import argparse
import json
import os
from collections import Counter
from pathlib import Path
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

FINE = {"timestamp_verified", "unchanged_verified_head", "no_recorded_events"}


def _cases(engine, args):
    if args.case_id:
        return [str(c) for c in args.case_id]
    from sqlalchemy import text
    with engine.connect() as connection:
        # Every case with recorded audit events, deleted cases included: their chains stay in the database.
        return [str(r[0]) for r in connection.execute(text(
            "SELECT DISTINCT case_id FROM financial_audit_events ORDER BY case_id"))]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("stamp", "verify"))
    parser.add_argument("--case-id", type=UUID, action="append")
    parser.add_argument("--all-cases", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tsa-url")
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--openssl", default="openssl")
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    args = parser.parse_args(argv)
    if bool(args.case_id) == args.all_cases:
        parser.error("Give --all-cases or one or more --case-id.")
    if args.mode == "stamp" and (not args.tsa_url or not args.ca_file or not args.ca_file.is_file()):
        parser.error("stamp needs --tsa-url and an existing --ca-file.")
    url = os.environ.get(args.database_url_env)
    if not url:
        parser.error("The database URL environment variable must be set.")
    from sqlalchemy import create_engine
    from services.financial import audit_head_anchor as anchor
    engine = create_engine(url)
    counts = Counter()
    try:
        for case_id in _cases(engine, args):
            try:
                if args.mode == "stamp":
                    result = anchor.anchor_audit_head(engine, case_id, output=args.output, tsa_url=args.tsa_url,
                                                ca_file=args.ca_file, openssl=args.openssl)
                else:
                    result = anchor.verify_audit_head(engine, case_id, output=args.output, openssl=args.openssl)
            except Exception as exc:  # noqa: BLE001 - reported per case; the others still run
                result = dict(case_id=case_id, status="attention_required",
                              reason=f"{type(exc).__name__}: {str(exc)[:300]}")
            counts[result["status"]] += 1
            print(json.dumps(result), flush=True)
    finally:
        engine.dispose()
    print(json.dumps({"summary": dict(counts)}), flush=True)
    good = FINE if args.mode == "stamp" else {"verified"}
    return 0 if set(counts) <= good else 2


if __name__ == "__main__":
    sys.exit(main())
