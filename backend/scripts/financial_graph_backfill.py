"""Draw one case's admitted ledger into the graph, through the worker's own path.

This is not a separate implementation.  It calls
``services.financial.graph_followup.project_case_graph``, the same function the
import worker's follow-up runs, so a backfill and an import produce identical
graphs and the same marker.

Run from ``backend/``:

    python -m scripts.financial_graph_backfill --case <case-uuid>            # dry run
    python -m scripts.financial_graph_backfill --case <case-uuid> --apply    # write

A dry run reads the ledger and (unless ``--no-graph``) reads the case's
projection marker and the legacy-node preflight.  It never writes.  ``--apply``
runs the projection in one Neo4j transaction; it is idempotent, so running it
again changes nothing.  ``--force`` re-runs every MERGE even when the stored
digest says the graph already matches (repairs hand-deleted nodes).

Exit status: 0 on success, 1 if the projection was refused or failed (the
ledger is never touched either way), 2 on bad arguments.
"""
from __future__ import annotations

import argparse
import json
import sys
from uuid import UUID


def _parse(argv):
    parser = argparse.ArgumentParser(prog="python -m scripts.financial_graph_backfill",
                                     description="Project one case's admitted ledger into the graph.")
    parser.add_argument("--case", required=True, type=UUID, help="Case id")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="Report what would be projected (default)")
    mode.add_argument("--apply", action="store_true", help="Write the projection to the graph")
    parser.add_argument("--force", action="store_true",
                        help="With --apply: run every statement even if the graph digest already matches")
    parser.add_argument("--no-graph", action="store_true",
                        help="With a dry run: do not read the graph at all (ledger only)")
    parser.add_argument("--batch-size", type=int, default=None, help="Rows per UNWIND statement")
    return parser.parse_args(argv)


def run(argv=None, *, session_factory=None, graph_session_factory=None, out=None) -> int:
    from services.financial import graph_followup, projection

    out = out or sys.stdout
    args = _parse(argv)
    try:
        report = graph_followup.project_case_graph(
            args.case,
            session_factory=session_factory,
            graph_session_factory=graph_session_factory,
            dry_run=not args.apply,
            force=args.force,
            read_graph=not args.no_graph,
            batch_size=args.batch_size or projection.DEFAULT_BATCH_SIZE,
        )
    except Exception as error:
        json.dump(dict(case_id=str(args.case), dry_run=not args.apply, outcome="failed",
                       error=f"{type(error).__name__}: {error}"), out, indent=2, default=str)
        out.write("\n")
        return 1
    json.dump(report, out, indent=2, default=str, sort_keys=True)
    out.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run())
