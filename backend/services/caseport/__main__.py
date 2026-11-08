"""python -m services.caseport verify|export|import|run-export

verify <package>                         read every part, check every hash and count, say what is wrong (exit 1)
export <case id> <folder> --by <email>   build a package without the web application (carries everything: an operator's copy)
import <package> --by <email> [--title]  load into a new case owned by that person, verifying first
"""
from __future__ import annotations

import argparse
import json
import sys


def _config():
    import config
    return config


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m services.caseport", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify")
    v.add_argument("package")
    e = sub.add_parser("export")
    e.add_argument("case_id")
    e.add_argument("folder")
    e.add_argument("--by", required=True)
    i = sub.add_parser("import")
    i.add_argument("package")
    i.add_argument("--by", required=True)
    i.add_argument("--title")
    r = sub.add_parser("run-export")
    r.add_argument("export_id")
    args = parser.parse_args(argv)

    if args.command == "verify":
        from . import package as P
        result = P.verify(args.package)
        manifest = result["manifest"] or {}
        print(f"{args.package}: {'OK' if result['ok'] else 'NOT OK'}, {result['size']} bytes, sha256 {result['sha256']}")
        if manifest:
            print(f"case {manifest.get('source_case')}, format {manifest.get('format_version')}, schema "
                  f"{manifest.get('schema_revision')}, app {manifest.get('app_sha')}, {len(manifest.get('parts', {}))} parts, "
                  f"{(manifest.get('evidence') or {}).get('files')} evidence files")
            for what, items in (("missing from disk at export", (manifest.get("evidence") or {}).get("missing_from_disk")),
                                ("differ from the recorded hash", (manifest.get("evidence") or {}).get("differ_from_recorded_hash"))):
                if items:
                    print(f"note: {len(items)} evidence files {what}, first: {items[0]}")
            if manifest.get("rows_private_to_others_left_out"):
                print(f"note: rows private to other people left out: {manifest['rows_private_to_others_left_out']}")
        for note in result["notes"]:
            print("note:", note)
        for problem in result["problems"]:
            print("PROBLEM:", problem)
        return 0 if result["ok"] else 1

    if args.command == "run-export":
        from . import jobs
        return jobs.run_one(args.export_id)

    config = _config()
    from .stores import GraphStore, VectorStore
    graph, vectors = GraphStore.from_config(), VectorStore.from_config()
    try:
        if args.command == "export":
            from pathlib import Path
            import psycopg
            from . import export as X
            from . import package as P
            with psycopg.connect(X.psycopg_url(config.DATABASE_URL)) as conn:
                row = conn.execute("SELECT id, email, name FROM users WHERE lower(email) = lower(%s)", (args.by,)).fetchone()
            if row is None:
                print(f"No account for {args.by}.", file=sys.stderr)
                return 2
            target = Path(args.folder) / f"{args.case_id}{P.SUFFIX}"
            out = X.run_export(config.DATABASE_URL, args.case_id, exporter=dict(id=str(row[0]), email=row[1], name=row[2]),
                               target=target, evidence_root=config.EVIDENCE_DATA_ROOT, graph=graph, vectors=vectors,
                               whole=True)
            print(json.dumps(out, indent=1, default=str))
            return 0
        from . import importer
        try:
            report = importer.run_import(config.DATABASE_URL, args.package, by_email=args.by, title=args.title,
                                         evidence_root=config.EVIDENCE_DATA_ROOT, graph=graph, vectors=vectors)
        except importer.ImportRefused as exc:
            print("REFUSED:", exc, file=sys.stderr)
            return 1
        print(json.dumps(report, indent=1, default=str))
        return 0
    finally:
        graph.close()


if __name__ == "__main__":
    sys.exit(main())
