#!/usr/bin/env python
"""One-shot cutover migration: old testing-hub user_items → Docket tickets.

The vanilla hub's bug/feature submissions (`user_items` in
data/testing-feedback.json) become Discussion-zone tickets, carrying their
comments onto the ticket timeline. Idempotent: a user_item whose id already
appears as some ticket's seed_user_item_id is skipped, so re-running after a
partial cutover is safe.

Run from the deployed checkout (so it writes that checkout's data/docket.db):

    cd backend && ../venv/bin/python ../docket/deploy/migrate_user_items.py

Optionally pass an explicit testing-feedback.json path as argv[1].
"""

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent.parent.parent / "backend"))

from services import docket_storage as dk  # noqa: E402


def main() -> int:
    fb_path = (Path(sys.argv[1]) if len(sys.argv) > 1
               else _HERE.parent.parent.parent / "data" / "testing-feedback.json")
    if not fb_path.exists():
        print(f"no hub data at {fb_path} — nothing to migrate")
        return 0
    data = json.loads(fb_path.read_text())
    items = data.get("user_items") or []
    comments = data.get("comments") or {}

    dk.init_db()
    existing = {t.get("seed_user_item_id") for t in dk.list_tickets()}
    migrated = skipped = 0
    for it in items:
        uid = it.get("id", "")
        if not uid or uid in existing:
            skipped += 1
            continue
        kind = it.get("kind") if it.get("kind") in ("bug", "feature") else "feature"
        author = (it.get("author") or "").strip().lower()
        t = dk.create_ticket(
            title=it.get("title", "").strip() or "(untitled hub item)",
            type=kind,
            description=it.get("body", ""),
            created_by=author,
            seed_user_item_id=uid,
        )
        dk.add_event(t["id"], "note", actor="system",
                     summary=f"Migrated from the old testing hub "
                             f"(originally raised {it.get('created_at', '?')[:10]})")
        for c in comments.get(uid) or []:
            dk.add_event(t["id"], "comment",
                         actor=(c.get("author") or "").strip().lower() or "system",
                         summary=c.get("text", ""))
        migrated += 1
        print(f"  {t['ref']} ← {uid[:40]}…  ({kind}, {author})")
    print(f"migrated {migrated}, skipped {skipped} (already present / no id)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
