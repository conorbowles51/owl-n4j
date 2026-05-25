"""Merge WhatsApp-JID Person nodes into their phone-number identities.

WHY (2026-05-25): WhatsApp/messaging JIDs are "<phone>@s.whatsapp.net" (or
"@c.us"). The writer's _generate_person_key saw the "@" and keyed them as
`email-<jid>` Person nodes — SEPARATE from the same person's `phone-<e164>`
node. So a contact's WhatsApp thread never merged with their SMS/calls. A key
contact had 72k WhatsApp messages stranded on an email-keyed node while her
phone node showed 465 (see WORKING.md). Case-wide this stranded 147k
relationships across 1,149 WhatsApp nodes.

The parser is now fixed for future ingests (JIDs key to phone). This backfills
the EXISTING graph: for each `email-<digits>@(s.whatsapp.net|c.us)` Person,
derive the phone key via the same normaliser, MERGE/create that phone Person,
and apoc.refactor.mergeNodes the WhatsApp node into it (relationships move +
dedup, phone identity survives). Idempotent — a re-run finds nothing left.

--check : report how many WhatsApp-JID nodes remain (0 after a successful run).

Run as conorbowles51 with the neo4j env:
  sudo -u conorbowles51 env NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j \
      NEO4J_PASSWORD=testpassword venv/bin/python scripts/merge_whatsapp_identities.py [--check]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.append(str(ROOT / "ingestion" / "scripts"))

from services.phone_normalise import person_key as phone_person_key  # noqa: E402
from neo4j_client import Neo4jClient  # noqa: E402

CHECK_ONLY = "--check" in sys.argv
JID_RE = re.compile(r"^email-(\+?\d{7,15})@(?:s\.whatsapp\.net|c\.us)$", re.IGNORECASE)


def main() -> int:
    db = Neo4jClient()
    try:
        rows = db.run_query(
            """
            MATCH (p:Person)
            WHERE p.key STARTS WITH 'email-'
              AND (p.key ENDS WITH '@s.whatsapp.net' OR p.key ENDS WITH '@c.us')
            RETURN p.key AS key, p.case_id AS case_id
            """
        )
        print(f"WhatsApp-JID Person nodes found: {len(rows)}")
        if CHECK_ONLY:
            print("CHECK only — no changes. (0 means fully merged.)")
            return 0

        merged = skipped = 0
        for row in rows:
            wakey = row["key"]
            cid = row["case_id"]
            m = JID_RE.match(wakey)
            if not m:
                skipped += 1
                continue
            # WhatsApp JIDs are full international E.164 digits (country code,
            # no '+') — parse as E.164, not region-US (which rejects every
            # non-US number). Prepend '+'.
            phkey = phone_person_key("+" + m.group(1).lstrip("+"), default_region="US")
            if not phkey or phkey == wakey:
                skipped += 1
                continue
            # MERGE/create the phone identity (seed name etc. from the WhatsApp
            # node if creating), then merge the WhatsApp node into it. discard =
            # keep the phone node's props; mergeRels dedups parallel edges.
            db.run_query(
                """
                MATCH (wa:Person {case_id:$cid, key:$wakey})
                MERGE (ph:Person {case_id:$cid, key:$phkey})
                  ON CREATE SET ph.id = randomUUID(), ph.name = wa.name,
                                ph.source_type = wa.source_type,
                                ph.cellebrite_report_key = wa.cellebrite_report_key,
                                ph:CbNode
                WITH ph, wa WHERE elementId(ph) <> elementId(wa)
                CALL apoc.refactor.mergeNodes([ph, wa],
                     {properties:'discard', mergeRels:true}) YIELD node
                RETURN node.key AS k
                """,
                cid=cid, wakey=wakey, phkey=phkey,
            )
            merged += 1
            if merged % 100 == 0:
                print(f"  merged {merged}/{len(rows)}...")

        print(f"DONE: merged {merged}, skipped {skipped} (non-numeric/invalid JIDs)")
        remaining = db.run_query(
            """
            MATCH (p:Person)
            WHERE p.key STARTS WITH 'email-'
              AND (p.key ENDS WITH '@s.whatsapp.net' OR p.key ENDS WITH '@c.us')
            RETURN count(p) AS c
            """
        )
        print(f"WhatsApp-JID nodes remaining: {int(remaining[0]['c']) if remaining else '?'}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
