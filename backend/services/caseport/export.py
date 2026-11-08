"""Build a package from a live case: PostgreSQL rows from one read-only snapshot, then the graph, vectors and files."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import inventory as I
from . import package as P
from . import stores as S

log = logging.getLogger(__name__)
UUID_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# Folders of a case that hold transfers in progress, not evidence.
SKIP_FOLDERS = frozenset({"_staging", "_uploads", "_resumable_uploads"})
TERMINAL_JOBS = ("completed", "failed", "cancelled", "canceled", "skipped")
STATEMENT = ("A complete copy of the case: evidence files, financial and phone records, the graph, stored readings, "
             "labels with their authors and status, notes, and the activity trail. It includes privileged material "
             "and any saved passwords and card numbers held in phone records.")


class ExportRefused(Exception):
    """The export cannot start or carry on, for a reason stated to the person asking."""


class Cancelled(Exception):
    pass


def psycopg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")


def app_sha() -> str:
    env = os.environ.get("LOUPE_APP_SHA")
    if env:
        return env
    try:
        return subprocess.run(["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 - a package from an unnumbered checkout says so
        return "unknown"


def schema_revision(conn) -> str:
    return conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]


def work_in_flight(conn, case_id) -> dict:
    """Processing that would leave the package half-way through a change."""
    out = {}
    n = conn.execute("SELECT count(*) FROM jobs WHERE case_id = %s AND lower(status::text) <> ALL(%s)",
                     (case_id, list(TERMINAL_JOBS))).fetchone()[0]
    if n:
        out["documents being processed"] = n
    n = conn.execute("SELECT count(*) FROM merge_jobs WHERE case_id = %s AND lower(status::text) NOT IN "
                     "('completed', 'failed', 'cancelled', 'canceled', 'done')", (case_id,)).fetchone()[0]
    if n:
        out["merges running"] = n
    n = conn.execute("SELECT count(*) FROM financial_import_batches WHERE case_id = %s AND lease_until > now()",
                     (case_id,)).fetchone()[0]
    if n:
        out["statement imports running"] = n
    return out


def evidence_paths(conn, case_id, evidence_root: Path):
    """(path inside the evidence root, path on disk, sha256 the case recorded or None) of every file of the case.

    The case folder is walked, and every file a row names is added, so a file outside the folder is carried too."""
    root = Path(evidence_root)
    recorded: dict = {}
    for stored, sha in conn.execute(
            "SELECT stored_path, sha256 FROM evidence_files WHERE case_id = %s AND stored_path IS NOT NULL", (case_id,)):
        if "://" in stored:   # phone-text://: a text held in the phone tables, no file
            continue
        path = Path(stored) if stored.startswith("/") else root / str(case_id) / stored
        recorded[str(path)] = sha
    seen = set()
    folder = root / str(case_id)
    for here, dirs, files in os.walk(folder):
        if Path(here) == folder:
            dirs[:] = [d for d in dirs if d not in SKIP_FOLDERS]
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(here, name)
            if os.path.isfile(full) and not os.path.islink(full):
                seen.add(full)
                yield os.path.relpath(full, root), full, recorded.get(full)
    for full, sha in recorded.items():
        if full not in seen:
            yield os.path.relpath(full, root), full, sha


def run_export(url, case_id, *, exporter, target, evidence_root, graph=None, vectors=None, progress=None,
               should_stop=None, whole=False) -> dict:
    """Write the package. ``exporter`` {"id","email","name"}; ``whole`` carries rows private to other people (super
    admin only). A failure or cancel removes everything written. Returns path, size, sha256, summary."""
    import psycopg
    case_id = str(case_id)
    progress = progress or (lambda **kw: None)
    should_stop = should_stop or (lambda: False)
    evidence_root = Path(evidence_root)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    def check():
        if should_stop():
            raise Cancelled()

    with psycopg.connect(psycopg_url(url), application_name="loupe-case-export", autocommit=False) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        case = conn.execute("SELECT row_to_json(c)::text FROM cases c WHERE id = %s", (case_id,)).fetchone()
        if case is None:
            raise ExportRefused("This case does not exist.")
        case_row = json.loads(case[0])
        if case_row.get("deleted_at"):
            raise ExportRefused("This case is in Deleted items. Restore it before exporting it.")
        busy = work_in_flight(conn, case_id)
        if busy:
            raise ExportRefused("Processing is running in this case: " +
                                ", ".join(f"{n} {what}" for what, n in busy.items()) +
                                ". Export it when that work has finished, so the copy is not caught half-way.")
        inv = I.classify(I.read_catalog(conn))
        stored = conn.execute("SELECT coalesce(sum(size), 0) FROM evidence_files WHERE case_id = %s",
                              (case_id,)).fetchone()[0]
        free = shutil.disk_usage(target.parent).free
        if int(stored) * 1.2 > free:
            raise ExportRefused(f"Not enough disk space: the evidence alone is {int(stored)} bytes and {free} are free.")
        writer = P.PackageWriter(target)
        try:
            summary = _write(conn, inv, writer, case_id, case_row, exporter, whole, evidence_root, graph, vectors,
                             progress, check)
            manifest = summary.pop("manifest")
            done = writer.finish(manifest)
        except BaseException:
            writer.abandon()
            raise
    return {**done, "summary": summary}


def _uuid_columns(inv, name):
    t = inv.tables[name]
    skip = set()
    for cols, target, _, _ in t.foreign_keys:
        if target == "users" or target in I.GLOBAL:
            skip.update(cols)
    return [c for c in t.columns if t.types[c] == "uuid" and c not in skip and c not in t.generated]


def _collect_ids(conn, inv, name, where, params, ids: set, keep: set):
    t = inv.tables[name]
    cols = _uuid_columns(inv, name)
    if not cols:
        return
    array = ", ".join(I._quote(c) for c in cols)
    for (value,) in conn.execute(
            f"SELECT DISTINCT x::text FROM (SELECT unnest(ARRAY[{array}]::uuid[]) AS x FROM {I._quote(name)} t "
            f"WHERE {where}) s WHERE x IS NOT NULL", params):
        ids.add(value)
    kept = [c for c in t.columns if t.types[c] == "uuid" and
            (c in I.KEEP_UUID_COLUMNS or any(c in fk[0] and fk[1] in I.GLOBAL for fk in t.foreign_keys))]
    if kept:
        array = ", ".join(I._quote(c) for c in kept)
        for (value,) in conn.execute(
                f"SELECT DISTINCT x::text FROM (SELECT unnest(ARRAY[{array}]::uuid[]) AS x FROM {I._quote(name)} t "
                f"WHERE {where}) s WHERE x IS NOT NULL", params):
            keep.add(value)


def _write(conn, inv, writer, case_id, case_row, exporter, whole, evidence_root, graph, vectors, progress, check):
    private_for = None if whole else str(exporter["id"])
    params = {"case": case_id, "me": str(exporter["id"])}
    tables_meta: dict = {}
    private_left: dict = {}
    ids: set = {case_id}
    keep: set = set()
    total = len(inv.case_tables) + 6

    part = writer.part()
    part.write_line(json.dumps(case_row, ensure_ascii=False))
    writer.add_part("pg/cases.jsonl.gz", part)

    for n, name in enumerate(inv.case_tables):
        check()
        progress(phase=f"Records: {name}", done=n, total=total)
        part = writer.part()
        sql = I.select_rows(inv, name, private_for=private_for)
        with conn.cursor() as cur:
            for i, (line,) in enumerate(cur.stream(sql, params)):
                part.write_line(line)
                if i % 2000 == 1999:
                    check()
        writer.add_part(f"pg/{name}.jsonl.gz", part)
        t = inv.tables[name]
        tables_meta[name] = {"columns": [c for c in t.columns if c not in t.generated]}
        where = I.scope_where(inv, name, "t", private_for=private_for)
        _collect_ids(conn, inv, name, where, params, ids, keep)
        if private_for is not None and name in I.OWNER_PRIVATE:
            everyone = conn.execute(f"SELECT count(*) FROM {I._quote(name)} t WHERE case_id = %s",
                                    (case_id,)).fetchone()[0]
            left = everyone - writer.parts[f"pg/{name}.jsonl.gz"]["rows"]
            if left:
                private_left[name] = left

    done = len(inv.case_tables)
    audit_head = conn.execute("SELECT entry_sha256 FROM financial_audit_events WHERE case_id = %s "
                              "ORDER BY sequence DESC LIMIT 1", (case_id,)).fetchone()

    check()
    progress(phase="Graph", done=done, total=total)
    graph_counts = {"nodes": 0, "relationships": 0, "crossing_cases": 0}
    if graph is not None:
        part = writer.part()
        for element_id, labels, props in graph.nodes(case_id):
            part.write_line(S.dumps({"i": element_id, "l": sorted(labels), "p": props}))
            for prop in ("key", "id"):
                if isinstance(props.get(prop), str):
                    ids.update(UUID_TEXT.findall(props[prop]))
        writer.add_part("neo4j/nodes.jsonl.gz", part)
        graph_counts["nodes"] = part.rows
        part = writer.part()
        for a, b, rel_type, props in graph.relationships(case_id):
            part.write_line(S.dumps({"a": a, "b": b, "t": rel_type, "p": props}))
            if isinstance(props.get("key"), str):
                ids.update(UUID_TEXT.findall(props["key"]))
        writer.add_part("neo4j/relationships.jsonl.gz", part)
        graph_counts["relationships"] = part.rows
        graph_counts["crossing_cases"] = graph.crossing(case_id)

    check()
    progress(phase="Vectors", done=done + 1, total=total)
    vector_counts = {}
    if vectors is not None:
        for collection in S.COLLECTIONS:
            part = writer.part()
            for row in vectors.rows(collection, case_id):
                part.write_line(S.dumps(row))
                ids.update(UUID_TEXT.findall(row["id"]))
            writer.add_part(f"vectors/{collection}.jsonl.gz", part)
            vector_counts[collection] = part.rows

    check()
    progress(phase="Evidence files", done=done + 2, total=total)
    index = writer.part()
    files = size = 0
    missing: list = []
    mismatched: list = []
    for rel, full, recorded in evidence_paths(conn, case_id, evidence_root):
        check()
        if not os.path.isfile(full):
            missing.append(rel)
            continue
        entry = writer.add_evidence("evidence/" + rel, Path(full))
        if recorded and recorded != entry["sha256"]:
            mismatched.append(rel)
        index.write_line(json.dumps({"path": rel, **entry, "recorded_sha256": recorded}, ensure_ascii=False))
        files += 1
        size += entry["size"]
        if files % 500 == 0:
            progress(phase=f"Evidence files: {files}", done=done + 2, total=total)
    writer.add_part("evidence-index.jsonl.gz", index)

    check()
    progress(phase="Reference rows and people", done=done + 3, total=total)
    all_ids = sorted(ids | keep)
    reference_counts = {}
    found_global: set = set()
    wanted_templates: set = set()
    for name in reversed(I.REFERENCE_TABLES):  # fields first: they name their template
        if name not in inv.tables:
            continue
        part = writer.part()
        extra = list(wanted_templates) if name == "case_context_templates" else []
        for line, row_id in conn.execute(
                f"SELECT row_to_json(t)::text, t.id::text FROM {I._quote(name)} t WHERE t.id = ANY(%s::uuid[]) ORDER BY t.id",
                (all_ids + extra,)):
            part.write_line(line)
            found_global.add(row_id)
            if name == "case_context_template_fields":
                wanted_templates.add(json.loads(line)["template_id"])
        writer.add_part(f"reference/{name}.jsonl.gz", part)
        reference_counts[name] = part.rows
    part = writer.part()
    versions = [i for i in found_global]
    if "phone_mapping_rows" in inv.tables:
        for (line,) in conn.execute("SELECT row_to_json(t)::text FROM phone_mapping_rows t "
                                    "WHERE t.mapping_version_id = ANY(%s::uuid[])", (versions,)):
            part.write_line(line)
    writer.add_part("reference/phone_mapping_rows.jsonl.gz", part)
    reference_counts["phone_mapping_rows"] = part.rows

    for column in ("owner_user_id", "created_by_user_id", "deleted_by_user_id"):
        if case_row.get(column):
            ids.add(case_row[column])
    part = writer.part()
    person_ids = set()
    for line, person in conn.execute(
            "SELECT json_build_object('id', id, 'email', email, 'name', name, 'is_active', is_active)::text, id::text "
            "FROM users WHERE id = ANY(%s::uuid[]) ORDER BY id",
            (sorted(ids | _user_columns(conn, inv, case_id, private_for, params)),)):
        part.write_line(line)
        person_ids.add(person)
    writer.add_part("people.jsonl.gz", part)

    part = writer.part()
    for value in sorted(ids - person_ids - found_global):
        part.write_line(value)
    for name, column in (("evidence_claims", "id"), ("snapshots", "id"), ("pol_analysis_snapshot", "id")):
        if name in inv.tables:
            where = I.scope_where(inv, name, "t", private_for=private_for)
            for (value,) in conn.execute(f"SELECT DISTINCT t.{column} FROM {I._quote(name)} t WHERE {where}", params):
                part.write_line(value)
    writer.add_part("ids.txt.gz", part)
    progress(phase="Finishing", done=done + 5, total=total)
    manifest = {
        "format": P.FORMAT, "format_version": P.FORMAT_VERSION, "schema_revision": schema_revision(conn),
        "app_sha": app_sha(), "created_at": datetime.now(timezone.utc).isoformat(), "host": socket.gethostname(),
        "source_case": {"id": case_id, "title": case_row.get("title")},
        "exported_by": {k: exporter.get(k) for k in ("id", "email", "name")},
        "carries_rows_private_to_others": bool(whole), "rows_private_to_others_left_out": private_left,
        "statement": STATEMENT, "evidence_root": str(evidence_root), "tables": tables_meta,
        "left_out": inv.left_out, "not_part_of_a_case": inv.global_tables, "record_only": list(I.RECORD_ONLY),
        "graph": graph_counts if graph is not None else None,
        "vectors": vector_counts if vectors is not None else None,
        "left_out_stores": {"engine working copies": "each document's copy in the engine's own folder; the original "
                            "is in the evidence files", "transfers": "folders of uploads in progress",
                            "generated": "page images, previews and the search caches, drawn again from the evidence"},
        "evidence": {"files": files, "bytes": size, "missing_from_disk": missing,
                     "differ_from_recorded_hash": mismatched},
        "financial_audit_head_sha256": audit_head[0] if audit_head else None,
    }
    summary = {"tables": len(inv.case_tables), "rows": sum(v["rows"] for k, v in writer.parts.items()
                                                           if k.startswith("pg/")),
               "graph": graph_counts, "vectors": vector_counts, "evidence_files": files, "evidence_bytes": size,
               "missing_from_disk": len(missing), "differ_from_recorded_hash": len(mismatched),
               "rows_private_to_others_left_out": private_left, "people": len(person_ids), "manifest": manifest}
    return summary


def _user_columns(conn, inv, case_id, private_for, params) -> set:
    """Every user a case row points at by foreign key (those columns are not in the id list)."""
    out: set = set()
    for name in inv.case_tables:
        t = inv.tables[name]
        cols = {c for cols, target, _, _ in t.foreign_keys if target == "users" for c in cols}
        if not cols:
            continue
        array = ", ".join(I._quote(c) for c in cols)
        where = I.scope_where(inv, name, "t", private_for=private_for)
        for (value,) in conn.execute(
                f"SELECT DISTINCT x::text FROM (SELECT unnest(ARRAY[{array}]::uuid[]) AS x FROM {I._quote(name)} t "
                f"WHERE {where}) s WHERE x IS NOT NULL", params):
            out.add(value)
    return out
