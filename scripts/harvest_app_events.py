"""Backfill app-activity / provenance / movement events into the graph.

WHY (2026-05-25 coverage gap): a batch of top-level model types were never in
SUPPORTED_MODEL_TYPES, so the parser silently dropped them — ~45k useful events
across the case (the 2026-05-23 coverage audit predated the reports that carry
them). The pipeline is now fixed (handlers + SUPPORTED + event-center
surfacing), but the already-ingested reports need a backfill that does NOT
re-ingest everything. This streams each report, dispatches ONLY the new types
through the writer's handlers, and re-links them — leaving all existing nodes
(and the harvested geotags) untouched.

Types backfilled (-> node label):
  AppsUsageLog, ApplicationUsage -> AppSession      SocialMediaActivity
  ChatActivity   FileUpload   Journey   Note   DeviceConnectivity
  Cookie   LogEntry   ActivitySensorData -> MotionActivity (window summary)

Idempotent: per report it DELETEs the existing nodes of these labels (by
report_key) then rewrites them, so a re-run converges. After writing it runs
the CONTAINS sweep so the new nodes hang off the PhoneReport.

--check : parity only. Per report, prints graph node counts per new label.

Run as conorbowles51 with the geocoder + neo4j env:
  sudo -u conorbowles51 env GEOCODER=geonames NEO4J_URI=bolt://localhost:7687 \
      NEO4J_USER=neo4j NEO4J_PASSWORD=testpassword \
      venv/bin/python scripts/harvest_app_events.py [--check] [report_root ...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.append(str(ROOT / "ingestion" / "scripts"))

from cellebrite.parser import CellebriteXMLParser  # noqa: E402
from cellebrite.neo4j_writer import CellebriteNeo4jWriter  # noqa: E402
from neo4j_client import Neo4jClient  # noqa: E402

CASE_ID = "43f1afb1-1d2b-4b3f-a832-19cd049c8a9e"
CASE_DIR = ROOT / "ingestion" / "data" / CASE_ID

CHECK_ONLY = "--check" in sys.argv
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]

# Top-level model types this backfill dispatches (ApplicationUsage included so
# the deleted AppSession nodes are fully rebuilt, not just AppsUsageLog).
PHASE9_TYPES = {
    "AppsUsageLog", "ApplicationUsage", "SocialMediaActivity", "ChatActivity",
    "FileUpload", "Journey", "Note", "DeviceConnectivity", "Cookie",
    "LogEntry", "ActivitySensorData",
}
# Node labels these produce — deleted per report before rewrite (idempotent).
PHASE9_LABELS = [
    "AppSession", "SocialMediaActivity", "ChatActivity", "FileUpload",
    "Journey", "Note", "DeviceConnectivity", "Cookie", "LogEntry",
    "MotionActivity",
]


def discover_report_xmls() -> list[Path]:
    re_parent = re.compile(r"Report(\s*\(\d+\))?$")
    return sorted(p for p in CASE_DIR.rglob("*_Report.xml")
                  if re_parent.search(p.parent.name))


def report_key_for(parser) -> str:
    report = parser.parse_header()
    cn = report.case_info.case_number or "unknown"
    en = report.case_info.evidence_number or "unknown"
    return f"cellebrite-{cn}-{en}", report


def graph_counts(db: Neo4jClient, report_key: str) -> dict:
    out = {}
    for lbl in PHASE9_LABELS:
        rows = db.run_query(
            f"MATCH (n:`{lbl}` {{case_id:$cid, cellebrite_report_key:$rk}}) RETURN count(n) AS c",
            cid=CASE_ID, rk=report_key,
        )
        c = int(rows[0]["c"]) if rows else 0
        if c:
            out[lbl] = c
    return out


def harvest_report(db: Neo4jClient, xml_path: Path) -> dict:
    parser = CellebriteXMLParser(xml_path)
    report_key, report = report_key_for(parser)

    if CHECK_ONLY:
        return {"report_key": report_key, "counts": graph_counts(db, report_key)}

    writer = CellebriteNeo4jWriter(db, CASE_ID, report_key, report)
    # Link new events to the EXISTING phone owner (so USED/POSTED/etc resolve).
    rows = db.run_query(
        "MATCH (:PhoneReport {case_id:$cid, key:$rk})-[:BELONGS_TO]->(p:Person) RETURN p.key AS k LIMIT 1",
        cid=CASE_ID, rk=report_key,
    )
    if rows:
        writer._phone_owner_key = rows[0]["k"]

    # Delete existing Phase-9 nodes for this report so the rewrite is idempotent
    # (the handlers CREATE, so without this a re-run would duplicate). APOC
    # batched to keep the transaction small.
    for lbl in PHASE9_LABELS:
        db.run_query(
            """
            CALL apoc.periodic.iterate(
              'MATCH (n:`%s` {case_id:$cid, cellebrite_report_key:$rk}) RETURN n',
              'DETACH DELETE n',
              {batchSize:1000, parallel:false, params:{cid:$cid, rk:$rk}}
            ) YIELD batches RETURN batches
            """ % lbl,
            cid=CASE_ID, rk=report_key,
        )

    # Stream models; dispatch ONLY the Phase-9 types through their handlers.
    written = 0
    for batch in parser.stream_models(batch_size=500):
        for model in batch:
            # ChatActivity is nested under Chat > ActivityLog (never top-level),
            # so pull it from each Chat without recreating the chat node.
            if model.model_type == "Chat":
                acts = model.multi_model_fields.get("ActivityLog", []) or []
                if acts:
                    try:
                        writer._write_chat_activities(model)
                        written += len(acts)
                    except Exception as e:
                        print(f"    WARN ChatActivity in chat {model.model_id[:8]}: {e}")
                continue
            if model.model_type not in PHASE9_TYPES:
                continue
            handler = writer._get_handler(model.model_type)
            if not handler:
                continue
            try:
                handler(model)
                written += 1
            except Exception as e:
                print(f"    WARN {model.model_type} {model.model_id[:8]}: {e}")

    # Re-link the new nodes to the PhoneReport (CONTAINS); idempotent MERGE.
    writer.link_all_to_report()

    return {"report_key": report_key, "written": written,
            "counts": graph_counts(db, report_key),
            "xml": {t: c for t, c in parser.xml_counts_by_type.items() if t in PHASE9_TYPES}}


def main() -> int:
    print("MODE:", "CHECK (graph counts only)" if CHECK_ONLY else "BACKFILL")
    if ARGS:
        xmls = []
        for a in ARGS:
            root = (CASE_DIR / a) if not Path(a).is_absolute() else Path(a)
            found = list(root.rglob("*_Report.xml")) if root.is_dir() else [root]
            xmls += [p for p in found if re.search(r"Report(\s*\(\d+\))?$", p.parent.name)]
        xmls = sorted(set(xmls))
    else:
        xmls = discover_report_xmls()
    print(f"Reports: {len(xmls)}")

    db = Neo4jClient()
    grand = {}
    try:
        for x in xmls:
            r = harvest_report(db, x)
            label = x.parent.name[:46]
            if CHECK_ONLY:
                tot = sum(r["counts"].values())
                print(f"  {label:<48} {tot:>7} nodes  {r['counts']}")
            else:
                print(f"  {label:<48} written={r['written']}  graph={r['counts']}")
                if r.get("xml"):
                    print(f"       xml top-level: {r['xml']}")
            for lbl, c in r["counts"].items():
                grand[lbl] = grand.get(lbl, 0) + c
    finally:
        db.close()

    print("-" * 72)
    print("GRAND TOTAL per label:", grand)
    print("Total app/movement event nodes:", sum(grand.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
