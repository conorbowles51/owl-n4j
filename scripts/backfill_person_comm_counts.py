"""Denormalise per-Person comm counts + device span onto the Person nodes.

WHY (2026-05-25): the unified-contacts rollup counted each person's
calls/messages/emails live, per request, by traversing relationships. After
cross-phone identity unification some contacts have 70k+ relationships, and
counting ALL ~14.5k persons in one request blew past the transaction timeout —
which the code swallowed to 0 ("0 messages / 0 calls" on a key contact). Live
`count{}` doesn't use stored degree here (verified: ~2.8s for a 58k-msg node),
so per-request counting can't scale.

Fix: compute the counts ONCE here (batched via apoc.periodic.iterate, so each
batch commits independently and no single transaction times out) and store them
on the node. The rollup then reads properties — instant. We also store the
distinct set of report_keys the person's COMMS touch (`comm_report_keys`), so
the rollup's "per device" span reflects every phone a unified contact appears
on, not just their node's single home-report.

Maintenance: re-run after a bulk ingest or after identity merges (the merge
endpoint recomputes the survivor inline). Idempotent.

Run as conorbowles51 with the neo4j env:
  sudo -u conorbowles51 env NEO4J_URI=bolt://localhost:7687 NEO4J_USER=neo4j \
      NEO4J_PASSWORD=testpassword venv/bin/python scripts/backfill_person_comm_counts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.append(str(ROOT / "ingestion" / "scripts"))

from neo4j_client import Neo4jClient  # noqa: E402

CASE_ID = "43f1afb1-1d2b-4b3f-a832-19cd049c8a9e"

# Small batch size: high-degree nodes (phone owners with 70k+ rels) are
# expensive to traverse, so keep batches small enough that even a batch full of
# owners commits well within the transaction timeout.
BATCH = 100


def main() -> int:
    db = Neo4jClient()
    try:
        res = db.run_query(
            """
            CALL apoc.periodic.iterate(
              'MATCH (p:Person {case_id:$cid, source_type:"cellebrite"}) RETURN p',
              'SET p.comm_calls  = count{ (p)-[:CALLED]->() }   + count{ (p)<-[:CALLED_TO]-() },
                   p.comm_msgs   = count{ (p)-[:SENT_MESSAGE]->() },
                   p.comm_emails = count{ (p)-[:EMAILED]->() }  + count{ (p)<-[:SENT_TO]-() },
                   p.comm_report_keys = apoc.coll.toSet(
                     [ (p)-[:CALLED|CALLED_TO|SENT_MESSAGE|EMAILED|SENT_TO]-(x)
                       WHERE x.cellebrite_report_key IS NOT NULL | x.cellebrite_report_key ]
                     + [ (p)-[:PARTICIPATED_IN]->(:Communication)<-[:PART_OF]-(m:Communication)
                         WHERE m.cellebrite_report_key IS NOT NULL | m.cellebrite_report_key ]
                   )',
              {batchSize:$batch, parallel:false, params:{cid:$cid}}
            ) YIELD batches, total, failedOperations, errorMessages
            RETURN batches, total, failedOperations, errorMessages
            """,
            cid=CASE_ID, batch=BATCH,
        )
        row = res[0] if res else {}
        print(f"batches={row.get('batches')} persons={row.get('total')} "
              f"failed={row.get('failedOperations')} errors={row.get('errorMessages')}")
        # Sanity sample
        s = db.run_query(
            "MATCH (p:Person {key:'phone-12404291127', case_id:$cid}) "
            "RETURN p.comm_calls AS calls, p.comm_msgs AS msgs, p.comm_emails AS emails, "
            "size(coalesce(p.comm_report_keys,[])) AS devices",
            cid=CASE_ID,
        )
        if s:
            r = s[0]
            print(f"sample (Trabajo 444): calls={r['calls']} msgs={r['msgs']} "
                  f"emails={r['emails']} devices={r['devices']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
