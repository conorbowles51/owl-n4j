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
# WhatsApp/messaging JID: the part before @ is the full international number.
JID_RE = re.compile(r"^email-(\+?\d{7,15})@(?:s\.whatsapp\.net|c\.us)$", re.IGNORECASE)
# App-id / other non-phone key ending in a digit run (e.g.
# telephone-number-14438221188, participant-12023902247, whatsapp-12404291127).
# Facebook/Instagram/Telegram IDs also end in digits but libphonenumber rejects
# them (verified), so the person_key validation below is the real gate.
TRAILING_RE = re.compile(r"-(\+?\d{7,15})$")


def candidate_phone_key(key: str) -> str | None:
    """Return the phone-* key this identity should resolve to, or None.

    Gated entirely by libphonenumber (person_key) so app-internal IDs
    (facebook-messenger-100…, telegram-…, instagram-…) — which end in digits
    but are NOT phone numbers — return None and are never merged."""
    m = JID_RE.match(key)
    if m:
        # JIDs carry the full E.164 number — prepend '+'.
        return phone_person_key("+" + m.group(1).lstrip("+"), default_region="US")
    if not key.startswith("email-"):
        m = TRAILING_RE.search(key)
        if m:
            # App-id numbers: conservative region-US parse (no forced '+'), so
            # only unambiguous real phones validate; ambiguous IDs stay put.
            return phone_person_key(m.group(1), default_region="US")
    return None


def main() -> int:
    db = Neo4jClient()
    try:
        rows = db.run_query(
            """
            MATCH (p:Person)
            WHERE NOT p.key STARTS WITH 'phone-'
            RETURN p.key AS key, p.case_id AS case_id
            """
        )
        print(f"Non-phone Person nodes scanned: {len(rows)}")
        if CHECK_ONLY:
            cands = sum(1 for r in rows if candidate_phone_key(r["key"]) and candidate_phone_key(r["key"]) != r["key"])
            print(f"CHECK only — {cands} would merge to a phone identity (0 = fully resolved).")
            return 0

        merged = skipped = 0
        for row in rows:
            wakey = row["key"]
            cid = row["case_id"]
            phkey = candidate_phone_key(wakey)
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

        print(f"DONE: merged {merged} into phone identities, "
              f"skipped {skipped} (not phone-resolvable: app IDs / emails / names / invalid formats)")
        remaining = db.run_query(
            """
            MATCH (p:Person) WHERE NOT p.key STARTS WITH 'phone-'
              AND p.key =~ '(?i)email-\\+?[0-9]{7,15}@(s\\.whatsapp\\.net|c\\.us)'
            RETURN count(p) AS c
            """
        )
        print(f"Phone-resolvable JID nodes still unmerged: {int(remaining[0]['c']) if remaining else '?'}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
