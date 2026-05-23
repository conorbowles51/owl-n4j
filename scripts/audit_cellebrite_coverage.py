#!/usr/bin/env python3
"""
Cellebrite ingestion coverage audit.

Streaming pass over every Cellebrite UFED XML on disk. Produces a coverage
matrix that compares what the XMLs actually contain against:

  1. UFEDLib (https://github.com/SEilers/UFEDLib) — the open de-facto
     Cellebrite schema, 56 model classes. Tells us what types Cellebrite
     COULD emit on some device, even when they don't appear in our reports.
  2. Our ingestion's SUPPORTED_MODEL_TYPES + per-handler get_field calls,
     parsed directly from parser.py / neo4j_writer.py source. Tells us
     what we actually capture today.

Re-run after every new report upload to spot:
  - Model types appearing in data that we have no handler for
  - Properties present in data but dropped by our handlers
  - taggedFile metadata items we drop (EXIF, hashes, timestamps)
  - Schema drift across reports / devices

Usage:
    python3 scripts/audit_cellebrite_coverage.py

Outputs (relative to repo root):
    docs/cellebrite_coverage.md     human-readable report
    docs/cellebrite_coverage.json   programmatic data
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NS = "http://pa.cellebrite.com/report/2.0"
NS_BRACKET = f"{{{NS}}}"


# UFEDLib's complete model list (56 classes under UFEDLib/Models/*.cs).
# Source enumerated 2026-05-23 via GitHub API. Update if UFEDLib adds
# classes; cross-reference for known investigative-value types.
UFEDLIB_TYPES = {
    "ActivitySensorData", "ActivitySensorDataMeasurement",
    "ActivitySensorDataSample", "ApplicationUsage", "AppsUsageLog",
    "Attachment", "Autofill", "CalendarEntry", "Call", "CellTower",
    "Chat", "ChatActivity", "Contact", "ContactEntry", "ContactPhoto",
    "Cookie", "Coordinate", "CreditCard", "DeviceConnectivity",
    "DeviceEvent", "DeviceInfoEntry", "DictionaryWord", "EMail",
    "FileDownload", "FileUpload", "FinancialAccount", "FinancialAsset",
    "InstalledApplication", "InstantMessage", "Journey", "KeyValueModel",
    "Location", "LogEntry", "MailMessage", "Map", "MobileCard",
    "NetworkUsage", "Note", "Notification", "Organization", "Party",
    "Password", "PoweringEvent", "Price", "PublicTransportationTicket",
    "RecognizedDevice", "Recording", "SearchedItem", "SharedFile",
    "SIMData", "SocialMediaActivity", "StreetAddress", "TransferOfFunds",
    "User", "UserAccount", "VisitedPage", "VoiceMail", "WebBookmark",
    "WirelessNetwork",
}


def _ns(tag: str) -> str:
    return f"{NS_BRACKET}{tag}"


def _strip(tag: str) -> str:
    return tag[len(NS_BRACKET):] if tag.startswith(NS_BRACKET) else tag


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def find_reports(root: Path) -> list[Path]:
    """Find every Cellebrite UFED XML report under `root`.

    Filters:
      - File size > 1 MB (small XMLs are not full reports)
      - Skip /_staging/ (intermediate upload extracts)
      - Sniff first 4 KB for the Cellebrite namespace to avoid
        unrelated XML files in the case directories.
    """
    reports = []
    for p in root.rglob("*Report*.xml"):
        try:
            if p.stat().st_size < 1024 * 1024:
                continue
        except OSError:
            continue
        if "/_staging/" in str(p):
            continue
        try:
            with p.open("rb") as f:
                head = f.read(4096).decode("utf-8", errors="ignore")
        except OSError:
            continue
        if NS in head:
            reports.append(p)
    return sorted(reports)


# ---------------------------------------------------------------------------
# Per-report XML scan
# ---------------------------------------------------------------------------


def scan_report(xml_path: Path, log) -> dict:
    """One streaming pass over a Cellebrite report.

    Returns a dict carrying:
      - models: per top-level model_type, per-field totals + non-empty
                counts, plus nested-child structure
      - tagged_files: per metadata section, per item_name totals + non-empty
      - access_info_timestamps: which <timestamp name="X"> appear on <file>
      - total_files / total_models: report-wide totals
    """
    models = defaultdict(lambda: {
        "count": 0,
        "fields": defaultdict(lambda: {"total": 0, "non_empty": 0}),
        "children": Counter(),         # (field_name, child_type) -> count
        "multi_children": Counter(),   # (field_name, child_type) -> count
    })
    tagged = defaultdict(lambda: defaultdict(lambda: {"total": 0, "non_empty": 0}))
    access_ts: Counter[str] = Counter()

    in_decoded = False
    in_tagged = False
    model_depth = 0   # depth of <model> nesting; 1 == top-level
    total_files = 0
    total_models = 0
    progress_every = 5000

    # IMPORTANT: do NOT call elem.clear() on inner elements like <field> /
    # <value> on their end events — that wipes the parent <model>'s child
    # list before we can iterate it. Only clear at container boundaries
    # (top-level <model>, <file>, <decodedData>, <taggedFiles>) — those
    # cascade-free everything inside.
    for event, elem in ET.iterparse(str(xml_path), events=["start", "end"]):
        tag = _strip(elem.tag)

        if event == "start":
            if tag == "decodedData":
                in_decoded = True
            elif tag == "taggedFiles":
                in_tagged = True
            elif tag == "model":
                model_depth += 1
            continue

        # event == "end"
        if tag == "decodedData":
            in_decoded = False
            elem.clear()
            continue
        if tag == "taggedFiles":
            in_tagged = False
            elem.clear()
            continue

        if tag == "model":
            # Only audit top-level models (direct children of <modelType>).
            # Nested models inside modelField/multiModelField are captured
            # via the parent's children/multi_children counters below.
            if model_depth == 1 and in_decoded:
                mtype = elem.get("type", "?")
                m = models[mtype]
                m["count"] += 1
                for child in elem:
                    ctag = _strip(child.tag)
                    if ctag == "field":
                        fname = child.get("name", "?")
                        m["fields"][fname]["total"] += 1
                        val = child.find(_ns("value"))
                        if val is not None and val.text and val.text.strip():
                            m["fields"][fname]["non_empty"] += 1
                    elif ctag == "modelField":
                        fname = child.get("name", "?")
                        inner = child.find(_ns("model"))
                        ctype = inner.get("type", "?") if inner is not None else "?"
                        m["children"][(fname, ctype)] += 1
                    elif ctag == "multiModelField":
                        fname = child.get("name", "?")
                        for inner in child.findall(_ns("model")):
                            m["multi_children"][(fname, inner.get("type", "?"))] += 1
                total_models += 1
                if total_models % progress_every == 0:
                    log(f"    {total_models:,} models")
                # Cascade-free this whole top-level model subtree.
                elem.clear()
            model_depth -= 1
            continue

        if in_tagged and tag == "file":
            total_files += 1
            ai = elem.find(_ns("accessInfo"))
            if ai is not None:
                for ts in ai.findall(_ns("timestamp")):
                    access_ts[ts.get("name", "?")] += 1
            for meta in elem.findall(_ns("metadata")):
                section = meta.get("section", "?")
                for item in meta.findall(_ns("item")):
                    iname = item.get("name", "?")
                    tagged[section][iname]["total"] += 1
                    if item.text and item.text.strip():
                        tagged[section][iname]["non_empty"] += 1
            if total_files % progress_every == 0:
                log(f"    {total_files:,} files")
            elem.clear()
            continue
        # Deliberately no elem.clear() here for non-container ends.

    # Freeze defaultdicts for JSON serialization.
    return {
        "models": {
            mtype: {
                "count": m["count"],
                "fields": {k: dict(v) for k, v in m["fields"].items()},
                "children": {f"{f}|{t}": c for (f, t), c in m["children"].items()},
                "multi_children": {f"{f}|{t}": c for (f, t), c in m["multi_children"].items()},
            }
            for mtype, m in models.items()
        },
        "tagged_files": {s: {n: dict(v) for n, v in items.items()} for s, items in tagged.items()},
        "access_info_timestamps": dict(access_ts),
        "total_files": total_files,
        "total_models": total_models,
    }


# ---------------------------------------------------------------------------
# Static analysis of our own ingestion source
# ---------------------------------------------------------------------------


def parse_supported_types(parser_src: str) -> tuple[set[str], set[str]]:
    """Pull SUPPORTED_MODEL_TYPES and SKIPPED_MODEL_TYPES from parser.py source."""
    def _set(name: str) -> set[str]:
        m = re.search(rf'{name}\s*=\s*\{{(.*?)\}}', parser_src, re.S)
        if not m:
            return set()
        return set(re.findall(r'"([A-Za-z]+)"', m.group(1)))
    return _set("SUPPORTED_MODEL_TYPES"), _set("SKIPPED_MODEL_TYPES")


def parse_handler_dispatch(writer_src: str) -> dict[str, str]:
    """Parse the _get_handler dispatch table -> {ModelType: _handler_name}."""
    m = re.search(r'handlers\s*=\s*\{(.*?)\n        \}', writer_src, re.S)
    if not m:
        return {}
    return dict(re.findall(r'"([A-Za-z]+)":\s*self\.(_[a-z_]+)', m.group(1)))


def parse_handler_field_reads(writer_src: str) -> dict[str, dict]:
    """For every `def _write_X(self, model, ...)` and helper function in the
    writer, extract every field/nested-child the function reads.

    Recognises:
      - `model.get_field("F")` — direct field read
      - `model.model_fields.get("N")` / `model.model_fields["N"]` — nested single
      - `model.multi_model_fields.get("N")` / `[..]` — nested multi
      - `model.get_party("N")` / `model.get_parties("N")` — Party-aware nested reads
      - `self._extract_timestamp(model, prefer=("X","Y"))` — timestamp alias helper;
        contributes both the prefer-list AND the full `_TIMESTAMP_ALIASES` set
        (because the helper falls through to every known alias).
    """
    # Pull the timestamp alias master list out of the source so the audit
    # stays in sync with whatever the writer actually iterates.
    ts_aliases = set(re.findall(
        r'_TIMESTAMP_ALIASES\s*=\s*\((.*?)\)',
        writer_src, re.S,
    ))
    ts_alias_set: set[str] = set()
    if ts_aliases:
        for s in re.finditer(r'["\']([A-Za-z]+)["\']', list(ts_aliases)[0]):
            ts_alias_set.add(s.group(1))

    handlers: dict[str, dict] = {}
    matches = list(re.finditer(r'\n    def ([_a-zA-Z][_a-zA-Z0-9]*)\(', writer_src))
    for i, m in enumerate(matches):
        fname = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(writer_src)
        body = writer_src[start:end]
        fields = set(re.findall(r'model\.get_field\(\s*["\']([^"\']+)["\']', body))
        # If the handler calls _extract_timestamp it transitively reads
        # every alias the helper iterates. Credit them all.
        if "_extract_timestamp" in body:
            fields |= ts_alias_set
        nested = set(re.findall(
            r'model\.(?:model_fields|multi_model_fields)\.get\(\s*["\']([^"\']+)["\']|'
            r'model\.(?:model_fields|multi_model_fields)\[["\']([^"\']+)["\']\]|'
            r'model\.get_part(?:y|ies)\(\s*["\']([^"\']+)["\']',
            body))
        nested_flat = {n for tup in nested for n in tup if n}
        handlers[fname] = {"fields": fields, "nested": nested_flat}
    return handlers


def parse_tagged_file_items(parser_src: str) -> set[str]:
    """Extract every item_name our TaggedFile parser matches against."""
    # Limit to the parse_tagged_files function body.
    m = re.search(r'def parse_tagged_files.*?(?=\n    def |\Z)', parser_src, re.S)
    body = m.group(0) if m else parser_src
    items: set[str] = set()
    for s in re.finditer(r'item_name\s*==\s*["\']([^"\']+)["\']', body):
        items.add(s.group(1))
    for tup in re.finditer(r'item_name\s+in\s*\(([^)]+)\)', body):
        for s in re.finditer(r'["\']([^"\']+)["\']', tup.group(1)):
            items.add(s.group(1))
    return items


# ---------------------------------------------------------------------------
# Aggregation + rendering
# ---------------------------------------------------------------------------


def aggregate(per_report: dict) -> dict:
    """Sum per-report scans into one cross-report view."""
    agg_models = defaultdict(lambda: {
        "count": 0,
        "fields": defaultdict(lambda: {"total": 0, "non_empty": 0}),
        "children": Counter(),
        "multi_children": Counter(),
        "reports": set(),
    })
    agg_tagged = defaultdict(lambda: defaultdict(lambda: {"total": 0, "non_empty": 0}))
    agg_access_ts: Counter[str] = Counter()
    total_files = 0
    total_models = 0
    for path, r in per_report.items():
        rname = Path(path).name
        for mtype, m in r["models"].items():
            ag = agg_models[mtype]
            ag["count"] += m["count"]
            ag["reports"].add(rname)
            for fname, fdata in m["fields"].items():
                ag["fields"][fname]["total"] += fdata["total"]
                ag["fields"][fname]["non_empty"] += fdata["non_empty"]
            for key, c in m["children"].items():
                ag["children"][key] += c
            for key, c in m["multi_children"].items():
                ag["multi_children"][key] += c
        for section, items in r["tagged_files"].items():
            for iname, idata in items.items():
                agg_tagged[section][iname]["total"] += idata["total"]
                agg_tagged[section][iname]["non_empty"] += idata["non_empty"]
        for ts, c in r["access_info_timestamps"].items():
            agg_access_ts[ts] += c
        total_files += r["total_files"]
        total_models += r["total_models"]
    return {
        "models": {k: {
            "count": v["count"],
            "fields": {fn: dict(fd) for fn, fd in v["fields"].items()},
            "children": dict(v["children"]),
            "multi_children": dict(v["multi_children"]),
            "reports": sorted(v["reports"]),
        } for k, v in agg_models.items()},
        "tagged_files": {s: {n: dict(d) for n, d in items.items()} for s, items in agg_tagged.items()},
        "access_info_timestamps": dict(agg_access_ts),
        "total_files": total_files,
        "total_models": total_models,
    }


def render(agg: dict, per_report: dict, supported: set[str], skipped: set[str],
           dispatch: dict[str, str], handlers: dict[str, dict],
           captured_tf_items: set[str]) -> str:
    """Build a single markdown document. Sections, in order:
    1. Inventory + summary
    2. Coverage gap headlines (what's missing)
    3. Per-type coverage table
    4. Field coverage per top-instance type
    5. taggedFile metadata coverage
    """
    out: list[str] = []
    out.append("# Cellebrite Ingestion Coverage Audit")
    out.append("")
    out.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    out.append(f"Reports scanned: {len(per_report)}")
    out.append(f"Total top-level models seen: {agg['total_models']:,}")
    out.append(f"Total tagged files seen: {agg['total_files']:,}")
    out.append("")

    out.append("## Reports")
    out.append("")
    for path, r in per_report.items():
        out.append(f"- `{Path(path).name}` — {r['total_models']:,} models in "
                   f"{len(r['models'])} types, {r['total_files']:,} tagged files")
    out.append("")

    # ----- coverage gap headlines
    types_in_data = set(agg["models"].keys())
    out.append("## Coverage gap headlines")
    out.append("")

    missing_handlers = sorted(
        t for t in types_in_data
        if t not in dispatch and t not in skipped
    )
    out.append(f"**Types in our reports without a handler ({len(missing_handlers)}):**  ")
    out.append(", ".join(f"`{t}`" for t in missing_handlers) if missing_handlers else "_none_")
    out.append("")

    unknown_to_ufedlib = sorted(t for t in types_in_data if t not in UFEDLIB_TYPES)
    out.append(f"**Types in our reports NOT in UFEDLib's 56-class reference "
               f"(probably Cellebrite-newer or app-specific) ({len(unknown_to_ufedlib)}):**  ")
    out.append(", ".join(f"`{t}`" for t in unknown_to_ufedlib) if unknown_to_ufedlib else "_none_")
    out.append("")

    ufedlib_only = sorted(t for t in UFEDLIB_TYPES if t not in types_in_data and t not in supported)
    out.append(f"**Types UFEDLib supports but neither in our reports nor our SUPPORTED set "
               f"({len(ufedlib_only)}):**  ")
    out.append(", ".join(f"`{t}`" for t in ufedlib_only) if ufedlib_only else "_none_")
    out.append("")

    # ----- type coverage table
    out.append("## Per-type coverage")
    out.append("")
    out.append("| Type | Reports | Instances | UFEDLib | Supported | Handler | Fields seen | Fields captured | Coverage |")
    out.append("|---|---:|---:|:---:|:---:|:---:|---:|---:|---:|")

    all_types = sorted(set(types_in_data) | supported | UFEDLIB_TYPES)
    for mtype in all_types:
        m = agg["models"].get(mtype, {"count": 0, "fields": {}, "reports": []})
        in_data = mtype in types_in_data
        # Skip noise: only render types that exist somewhere meaningful.
        if not in_data and mtype not in supported and mtype not in UFEDLIB_TYPES:
            continue
        in_uf = "yes" if mtype in UFEDLIB_TYPES else "—"
        in_supp = ("skipped" if mtype in skipped else
                   "yes" if mtype in supported else "no")
        handler = dispatch.get(mtype, "")
        has_handler = "yes" if handler else "no"
        fields_seen = len(m["fields"])
        captured = 0
        if handler and handler in handlers:
            captured = len(handlers[handler]["fields"] & set(m["fields"].keys()))
        cov = f"{(100 * captured / fields_seen):.0f}%" if fields_seen else "—"
        reports = m.get("reports", [])
        out.append(f"| {mtype} | {len(reports)} | {m['count']:,} | {in_uf} | "
                   f"{in_supp} | {has_handler} | {fields_seen} | {captured} | {cov} |")
    out.append("")

    # ----- field-level coverage per type (top 25 by instance count)
    out.append("## Field coverage per type")
    out.append("")
    out.append("_Sorted by instance count, top 25 types. \"Captured\" = field is "
               "read by the handler dispatched to this type, OR by a helper "
               "(`_attachment_props`, `_message_provenance_props`, etc) — best "
               "effort static match, may underreport when helpers fan out._")
    out.append("")
    helper_fields: set[str] = set()
    helper_nested: set[str] = set()
    for name, h in handlers.items():
        if name.endswith("_props") or name == "_base_props" or name == "_extract_timestamp":
            helper_fields |= h["fields"]
            helper_nested |= h["nested"]

    sorted_types = sorted(agg["models"].items(), key=lambda kv: -kv[1]["count"])
    for mtype, m in sorted_types[:25]:
        handler = dispatch.get(mtype)
        cap_fields = handlers.get(handler, {}).get("fields", set()) | helper_fields
        cap_nested = handlers.get(handler, {}).get("nested", set()) | helper_nested
        out.append(f"### {mtype} ({m['count']:,} instances)")
        out.append("")
        if not handler:
            out.append(f"_No handler — all {len(m['fields'])} fields and "
                       f"{len(m['children']) + len(m['multi_children'])} nested "
                       "children silently dropped._")
            out.append("")
        out.append("| Field | Total | Non-empty | Captured |")
        out.append("|---|---:|---:|:---:|")
        for fname, fdata in sorted(m["fields"].items(), key=lambda kv: -kv[1]["non_empty"]):
            cap = "yes" if fname in cap_fields else "**no**"
            out.append(f"| {fname} | {fdata['total']:,} | {fdata['non_empty']:,} | {cap} |")
        out.append("")
        if m["children"] or m["multi_children"]:
            out.append("**Nested:**")
            out.append("")
            out.append("| Kind | Field | Child type | Count | Captured |")
            out.append("|---|---|---|---:|:---:|")
            for key, c in sorted(m["children"].items(), key=lambda kv: -kv[1]):
                fname, ctype = key.split("|", 1)
                cap = "yes" if fname in cap_nested else "**no**"
                out.append(f"| modelField | {fname} | {ctype} | {c:,} | {cap} |")
            for key, c in sorted(m["multi_children"].items(), key=lambda kv: -kv[1]):
                fname, ctype = key.split("|", 1)
                cap = "yes" if fname in cap_nested else "**no**"
                out.append(f"| multiModelField | {fname} | {ctype} | {c:,} | {cap} |")
            out.append("")

    # ----- taggedFile metadata coverage
    out.append("## TaggedFile metadata coverage")
    out.append("")
    out.append("_For each `<file>` inside `<taggedFiles>`, every `<metadata "
               "section=\"X\">` block's `<item name=\"Y\">` entries. \"Captured\" "
               "means parser.py's TaggedFile extractor matches this item_name._")
    out.append("")
    for section, items in sorted(agg["tagged_files"].items()):
        out.append(f"### Section: `{section}`")
        out.append("")
        out.append("| Item name | Total | Non-empty | Captured |")
        out.append("|---|---:|---:|:---:|")
        for iname, idata in sorted(items.items(), key=lambda kv: -kv[1]["non_empty"]):
            cap = "yes" if iname in captured_tf_items else "**no**"
            out.append(f"| {iname} | {idata['total']:,} | {idata['non_empty']:,} | {cap} |")
        out.append("")

    out.append("## `<accessInfo>` timestamps on files")
    out.append("")
    out.append("| Timestamp name | Count |")
    out.append("|---|---:|")
    for ts, c in sorted(agg["access_info_timestamps"].items(), key=lambda kv: -kv[1]):
        out.append(f"| {ts} | {c:,} |")
    out.append("")

    return "\n".join(out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    log = lambda m: print(m, flush=True)

    data_root = REPO_ROOT / "ingestion" / "data"
    reports = find_reports(data_root)
    if not reports:
        log(f"No Cellebrite XML reports found under {data_root}")
        return 1
    log(f"Discovered {len(reports)} report(s):")
    for r in reports:
        size_mb = r.stat().st_size / (1024 * 1024)
        log(f"  {r}  ({size_mb:.0f} MB)")

    parser_src = (REPO_ROOT / "ingestion/scripts/cellebrite/parser.py").read_text()
    writer_src = (REPO_ROOT / "ingestion/scripts/cellebrite/neo4j_writer.py").read_text()
    supported, skipped = parse_supported_types(parser_src)
    dispatch = parse_handler_dispatch(writer_src)
    handlers = parse_handler_field_reads(writer_src)
    captured_tf = parse_tagged_file_items(parser_src)
    log(f"\nIngestion code: {len(supported)} SUPPORTED types, "
        f"{len(skipped)} SKIPPED, {len(dispatch)} dispatched, "
        f"{len(handlers)} writer functions analysed, "
        f"{len(captured_tf)} taggedFile items recognised")

    per_report: dict = {}
    for r in reports:
        log(f"\nScanning {r.name}...")
        per_report[str(r)] = scan_report(r, log)
        log(f"  done — {per_report[str(r)]['total_models']:,} models, "
            f"{per_report[str(r)]['total_files']:,} files")

    agg = aggregate(per_report)

    out_dir = REPO_ROOT / "docs"
    out_dir.mkdir(exist_ok=True)
    md = render(agg, per_report, supported, skipped, dispatch, handlers, captured_tf)
    md_path = out_dir / "cellebrite_coverage.md"
    md_path.write_text(md)

    json_path = out_dir / "cellebrite_coverage.json"
    json_path.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "reports": [str(p) for p in reports],
        "supported_types": sorted(supported),
        "skipped_types": sorted(skipped),
        "dispatch": dispatch,
        "ufedlib_types": sorted(UFEDLIB_TYPES),
        "captured_tagged_file_items": sorted(captured_tf),
        "aggregate": agg,
        "per_report": per_report,
    }, indent=2, default=str))

    log(f"\nWrote {md_path}")
    log(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
