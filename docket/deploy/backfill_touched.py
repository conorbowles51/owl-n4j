#!/usr/bin/env python
"""One-shot backfill for the post-ship telemetry + relatedness features.

Two passes, both idempotent:
  1. touched_paths / touched_routes for tickets that already have a
     docket/DKT-<n> branch (shipped before the agent learned to record them).
     Derived with git plumbing against DOCKET_MAIN_CHECKOUT — no worktree needed.
  2. relatedness links over EXISTING tickets, replaying what detect_links()
     now does at creation time: explicit DKT-<n> mentions → confirmed; lexical
     similarity → suspected. A ticket can only implicate work shipped BEFORE
     the ticket was raised (a complaint can't predate the fix it implicates).

Run from the deployed checkout:
    cd backend && ../venv/bin/python ../docket/deploy/backfill_touched.py
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent.parent / "backend"))

from services import docket_storage as dk  # noqa: E402

MAIN_CHECKOUT = Path(os.environ.get("DOCKET_MAIN_CHECKOUT",
                                    "/home/conorbowles51/app_v2"))

_ROUTE_DECOR_RE = re.compile(
    r'@(?:router|app)\.(?:get|post|put|patch|delete)\(\s*["\']([^"\']*)["\']')
_PREFIX_RE = re.compile(r'APIRouter\([^)]*prefix\s*=\s*["\']([^"\']+)["\']', re.S)


def _git(args):
    r = subprocess.run(["git", "-C", str(MAIN_CHECKOUT), *args],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def _resolve_branch(branch):
    for ref in (branch, f"origin/{branch}"):
        if _git(["rev-parse", "--verify", ref]) is not None:
            return ref
    return None


def touched_from_branch(branch):
    ref = _resolve_branch(branch)
    if not ref:
        return None, None
    names = _git(["diff", "--name-only", f"main...{ref}"])
    if names is None:
        return None, None
    paths = [p for p in names.split() if p]
    routes = set()
    for p in paths:
        if not (p.startswith("backend/") and p.endswith(".py")):
            continue
        src = _git(["show", f"{ref}:{p}"]) or ""
        m = _PREFIX_RE.search(src)
        prefix = m.group(1) if m else ""
        diff = _git(["diff", "-U2", f"main...{ref}", "--", p]) or ""
        found = {prefix + dm.group(1)
                 for dm in _ROUTE_DECOR_RE.finditer(diff) if prefix + dm.group(1)}
        if not found:
            # change was inside a handler body — attribute the file's routes
            found = {prefix + dm.group(1)
                     for dm in _ROUTE_DECOR_RE.finditer(src) if prefix + dm.group(1)}
            if len(found) > 12:
                found = set()
        routes |= found
    return paths[:100], sorted(routes)[:50]


def main():
    dk.init_db()

    # -- pass 1: touched paths/routes from existing branches -------------------
    print("== touched paths/routes from branches ==")
    for t in dk.list_tickets():
        if not t.get("branch") or t.get("touched_routes"):
            continue
        paths, routes = touched_from_branch(t["branch"])
        if paths is None:
            print(f"  {t['ref']}: branch {t['branch']} not found — skipped")
            continue
        dk.update_ticket(t["id"], touched_paths=json.dumps(paths),
                         touched_routes=json.dumps(routes))
        print(f"  {t['ref']}: {len(paths)} files, routes={routes}")

    # -- pass 2: relatedness links over existing tickets ------------------------
    print("== relatedness links (mention=confirmed, similarity=suspected) ==")
    shipped = dk.shipped_tickets()
    done_ts = {}
    conn = dk._connect()
    try:
        for s in shipped:
            row = conn.execute(
                """SELECT ts FROM ticket_events WHERE ticket_id=? AND
                   kind='transition' AND phase='done' ORDER BY id LIMIT 1""",
                (s["id"],)).fetchone()
            done_ts[s["id"]] = row["ts"] if row else None
    finally:
        conn.close()

    made = 0
    for t in dk.list_tickets():
        # candidates: shipped strictly before this ticket was raised
        prior = [s for s in shipped
                 if s["id"] != t["id"] and done_ts.get(s["id"])
                 and done_ts[s["id"]] < t["created_at"]]
        if not prior:
            continue
        prior_ids = {s["id"] for s in prior}
        text = f'{t["title"]} {t.get("description") or ""}'
        for m in dk._DKT_RE.finditer(text):
            tgt = int(m.group(1))
            if tgt in prior_ids:
                ln = dk.add_link(t["id"], tgt, source="mention",
                                 status="confirmed", note="Named in the ticket text")
                if ln:
                    made += 1
                    print(f"  {t['ref']} → DKT-{tgt} (mention, confirmed)")
        probe = dk._sim_terms(t["title"], t.get("description") or "",
                              t.get("acceptance_criteria") or "")
        scored = sorted(
            ((dk._cosine(probe, dk._sim_terms(s["title"], s["description"],
                                              s["acceptance_criteria"])), s)
             for s in prior), key=lambda x: -x[0])
        for score, s in scored[:2]:
            if score >= dk.SIMILARITY_THRESHOLD:
                ln = dk.add_link(t["id"], s["id"], source="similarity",
                                 status="suspected", score=round(score, 3))
                if ln and ln["status"] == "suspected":
                    made += 1
                    print(f"  {t['ref']} ~ {s['ref']} (similarity {score:.2f}, suspected)")
    print(f"links created/kept: {made}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
