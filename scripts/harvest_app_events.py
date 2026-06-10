"""Backfill app-activity / provenance / movement events into the graph.

WHY (2026-05-25 coverage gap): a batch of top-level model types were never in
SUPPORTED_MODEL_TYPES, so the parser silently dropped them — ~45k useful events
across the case (the 2026-05-23 coverage audit predated the reports that carry
them). The MAIN PIPELINE IS NOW FIXED (handlers + SUPPORTED + event-center
surfacing), so fresh ingests capture every type below automatically — a new
case does NOT need this script. This remains the remediation tool for reports
ingested BEFORE that fix (or to re-verify any case). It streams each report,
dispatches ONLY the new types through the writer's handlers, and re-links them
— leaving all existing nodes (and the harvested geotags) untouched.

Types backfilled (-> node label):
  AppsUsageLog, ApplicationUsage -> AppSession      SocialMediaActivity
  ChatActivity   FileUpload   Journey   Note   DeviceConnectivity
  Cookie   LogEntry   ActivitySensorData -> MotionActivity (window summary)

Idempotent: per report it DELETEs the existing nodes of these labels (by
report_key) then rewrites them, so a re-run converges. After writing it runs
the CONTAINS sweep so the new nodes hang off the PhoneReport.

CASE-AGNOSTIC. The case is no longer hardcoded — pick targets via, in order:
  --case CASE_ID   one or more case ids (repeatable); reports are discovered
                   under ingestion/data/<CASE_ID>/.
  REPORT_PATH ...  explicit report files or dirs (positional); the case id is
                   derived from each path's ingestion/data/<CASE_ID>/ ancestor.
  (neither)        every case that currently has PhoneReport nodes in the graph.

--check : parity only. Per report, prints graph node counts per new label.

Run as conorbowles51 with the geocoder + neo4j env:
  sudo -u conorbowles51 env GEOCODER=geonames NEO4J_URI=bolt://localhost:7687 \
      NEO4J_USER=neo4j NEO4J_PASSWORD=testpassword \
      venv/bin/python scripts/harvest_app_events.py \
          [--check] [--case CASE_ID ...] [report_path ...]
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

DATA_ROOT = ROOT / "ingestion" / "data"

CHECK_ONLY = "--check" in sys.argv

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


def discover_report_xmls(case_dir: Path) -> list[Path]:
    re_parent = re.compile(r"Report(\s*\(\d+\))?$")
    return sorted(p for p in case_dir.rglob("*_Report.xml")
                  if re_parent.search(p.parent.name))


def case_id_from_path(p: Path) -> str | None:
    """Derive the case id from a report path's ingestion/data/<CASE_ID>/ ancestor."""
    try:
        rel = p.resolve().relative_to(DATA_ROOT.resolve())
    except ValueError:
        return None
    return rel.parts[0] if rel.parts else None


def discover_graph_cases(db: Neo4jClient) -> list[str]:
    """Every case that currently has PhoneReport nodes in the graph."""
    rows = db.run_query(
        "MATCH (pr:PhoneReport) RETURN DISTINCT pr.case_id AS cid ORDER BY cid"
    )
    return [r["cid"] for r in rows if r.get("cid")]


def report_key_for(parser) -> str:
    report = parser.parse_header()
    cn = report.case_info.case_number or "unknown"
    en = report.case_info.evidence_number or "unknown"
    return f"cellebrite-{cn}-{en}", report


def graph_counts(db: Neo4jClient, case_id: str, report_key: str) -> dict:
    out = {}
    for lbl in PHASE9_LABELS:
        rows = db.run_query(
            f"MATCH (n:`{lbl}` {{case_id:$cid, cellebrite_report_key:$rk}}) RETURN count(n) AS c",
            cid=case_id, rk=report_key,
        )
        c = int(rows[0]["c"]) if rows else 0
        if c:
            out[lbl] = c
    return out


def harvest_report(db: Neo4jClient, case_id: str, xml_path: Path) -> dict:
    parser = CellebriteXMLParser(xml_path)
    report_key, report = report_key_for(parser)

    if CHECK_ONLY:
        return {"report_key": report_key,
                "counts": graph_counts(db, case_id, report_key)}

    writer = CellebriteNeo4jWriter(db, case_id, report_key, report)
    # Link new events to the EXISTING phone owner (so USED/POSTED/etc resolve).
    rows = db.run_query(
        "MATCH (:PhoneReport {case_id:$cid, key:$rk})-[:BELONGS_TO]->(p:Person) RETURN p.key AS k LIMIT 1",
        cid=case_id, rk=report_key,
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
            cid=case_id, rk=report_key,
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
            "counts": graph_counts(db, case_id, report_key),
            "xml": {t: c for t, c in parser.xml_counts_by_type.items() if t in PHASE9_TYPES}}


def parse_args(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split argv into (--case ids, positional report paths). --check is global."""
    cases: list[str] = []
    paths: list[str] = []
    it = iter(argv)
    for a in it:
        if a == "--check":
            continue
        if a == "--case":
            nxt = next(it, None)
            if nxt is None:
                raise SystemExit("--case requires a CASE_ID value")
            cases.append(nxt)
        elif a.startswith("--case="):
            cases.append(a.split("=", 1)[1])
        elif a.startswith("--"):
            raise SystemExit(f"unknown flag: {a}")
        else:
            paths.append(a)
    return cases, paths


def build_worklist(db: Neo4jClient, cases: list[str], paths: list[str]) -> list[tuple[str, Path]]:
    """Resolve (case_id, report_xml) pairs from --case ids and explicit paths.

    Precedence: explicit paths AND/OR --case ids are unioned; if NEITHER is
    given, fall back to every case with PhoneReport nodes in the graph.
    """
    work: list[tuple[str, Path]] = []

    for a in paths:
        p = Path(a) if Path(a).is_absolute() else (Path.cwd() / a)
        found = list(p.rglob("*_Report.xml")) if p.is_dir() else [p]
        for xml in found:
            if not re.search(r"Report(\s*\(\d+\))?$", xml.parent.name):
                continue
            cid = case_id_from_path(xml)
            if not cid:
                print(f"  SKIP (cannot derive case id from path): {xml}")
                continue
            work.append((cid, xml))

    target_cases = cases or ([] if paths else discover_graph_cases(db))
    for cid in target_cases:
        case_dir = DATA_ROOT / cid
        if not case_dir.is_dir():
            print(f"  WARN: no data dir for case {cid} at {case_dir}")
            continue
        for xml in discover_report_xmls(case_dir):
            work.append((cid, xml))

    # Dedup, keep deterministic order.
    return sorted(set(work))


def main() -> int:
    print("MODE:", "CHECK (graph counts only)" if CHECK_ONLY else "BACKFILL")
    cases, paths = parse_args(sys.argv[1:])

    db = Neo4jClient()
    grand: dict[str, int] = {}
    try:
        worklist = build_worklist(db, cases, paths)
        multi_case = len({cid for cid, _ in worklist}) > 1
        print(f"Reports: {len(worklist)}"
              + (f" across {len({cid for cid, _ in worklist})} cases" if multi_case else ""))

        for case_id, x in worklist:
            r = harvest_report(db, case_id, x)
            prefix = f"[{case_id[:8]}] " if multi_case else ""
            label = prefix + x.parent.name[:46]
            if CHECK_ONLY:
                tot = sum(r["counts"].values())
                print(f"  {label:<58} {tot:>7} nodes  {r['counts']}")
            else:
                print(f"  {label:<58} written={r['written']}  graph={r['counts']}")
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
