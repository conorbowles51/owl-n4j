"""Files: container entries, verification and references (01 section 7, unit 1.5).

Runs in the ``indexing_files`` stage after reconciliation, reading record bodies from Postgres (no XML re-read).

- ``list_entries``: every non-skipped file under the report root as a ``phone_container_entries`` row
  (relative to the root, '/' separators), with digests where the container hash already read them (folders).
- ``verify_files``: each ``phone_files`` row gets one of seven outcomes (7.2), first matching rule wins, resuming
  from the first row with ``verified_at IS NULL`` (10.5).
- ``resolve_references``: the three attachment mechanisms (7.3) as ``phone_file_references`` rows; a repeated
  model id gives one row per candidate, suffixed ``#k`` and flagged ambiguous, none chosen silently.
"""
from __future__ import annotations

import hashlib
import json
import time

from app.phone import detect

EMPTY_MD5 = "d41d8cd98f00b204e9800998ecf8427e"
VERIFY_BATCH = 500

OUTCOME_TEXT = {
    "match": "Matches the fingerprint in the report.",
    "missing": "The report lists this file but it is not in the production.",
    "empty_placeholder": "The production contains an empty placeholder for this file. The report describes the "
                         "original, which was not included.",
    "size_mismatch": "The file in the production is a different size from the one the report describes. It may be "
                     "incomplete.",
    "mismatch": "The file in the production does not match the report's fingerprint. It is not the same file the "
                "report describes.",
    "no_hash": "The report gives no fingerprint for this file, so it cannot be checked.",
    "no_local_path": "The report gives no location for this file in the production.",
}


def norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def _under_root(relpath: str, root: str):
    if not root:
        return relpath
    if relpath.startswith(root + "/"):
        return relpath[len(root) + 1:]
    return None


def list_entries(conn, ctx, reporter=None) -> dict:
    """Write ``phone_container_entries`` for the report root (idempotent)."""
    source, root, ext = ctx["source"], ctx["root_path"], ctx["extraction_id"]
    members = ctx.get("members") or {}
    rows = []
    for rel, size in source.entries():
        if detect.skip_rule(rel) is not None:
            continue
        sub = _under_root(rel, root)
        if sub is None or sub == detect.V1_REPORT:
            continue
        m = members.get(rel)
        loc = _location(source, rel)
        rows.append((ext, sub, size, m[1] if m else None, m[2] if m else None,
                     ctx.get("container_id") if loc else None, *(loc or (None, None, None, None))))
    kept = True
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM phone_container_entries WHERE extraction_id = %s", (ext,))
            if cur.fetchone()[0] != len(rows):
                kept = False
                cur.execute("DELETE FROM phone_container_entries WHERE extraction_id = %s", (ext,))
                with cur.copy("COPY phone_container_entries (extraction_id, relpath, size_bytes, sha256, md5, "
                              "container_id, header_offset, compressed_size, compress_type, crc32) FROM STDIN") as cp:
                    for r in rows:
                        cp.write_row(r)
    ctx["entries"] = {r[1]: r[2] for r in rows}
    out = {"entries": len(rows)}
    if kept and any(r[6] is not None for r in rows):  # rows kept from an earlier run may lack the offsets
        out["offsets_recorded"] = record_member_offsets(conn, ext, ctx.get("container_id"), source, root)
    return out


def _location(source, rel):
    """(header offset, compressed size, method, CRC) for an archive member; None for a folder."""
    loc = getattr(source, "location", None)
    return loc(rel) if loc is not None else None


def record_member_offsets(conn, extraction_id, container_id, source, root) -> int:
    """Fill the archive position of every entry of one extraction that lacks it, from ``source`` (the archive
    ``container_id`` names). Idempotent; rows that already have a position are left alone. Returns rows filled.
    The capture calls it through ``list_entries``; it is also how entries written before positions were recorded
    are filled (``app.phone.backfill_offsets``)."""
    if getattr(source, "location", None) is None:
        return 0
    updates = []
    for rel, _size in source.entries():
        if detect.skip_rule(rel) is not None:
            continue
        sub = _under_root(rel, root)
        if sub is None or sub == detect.V1_REPORT:
            continue
        updates.append((container_id, *source.location(rel), extraction_id, sub))
    done = 0
    with conn.transaction():
        with conn.cursor() as cur:
            for i in range(0, len(updates), 2000):
                cur.executemany(
                    "UPDATE phone_container_entries SET container_id = %s, header_offset = %s, compressed_size = %s, "
                    "compress_type = %s, crc32 = %s WHERE extraction_id = %s AND relpath = %s AND "
                    "header_offset IS NULL", updates[i:i + 2000])
                done += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    return done


def outcome_for(local_path, declared_size, declared_md5, declared_sha256, disk):
    """01 section 7.2, first matching rule wins. ``disk`` is (size, md5, sha256) or None when absent."""
    if not local_path:
        return "no_local_path"
    if disk is None:
        return "missing"
    size, md5, sha = disk
    if size == 0 and (declared_size or 0) == 0 and declared_md5 and declared_md5.lower() != EMPTY_MD5:
        return "empty_placeholder"
    if declared_size is not None and size != declared_size:
        return "size_mismatch"
    if not declared_md5 and not declared_sha256:
        return "no_hash"
    if declared_md5 and md5 != declared_md5.lower():
        return "mismatch"
    if declared_sha256 and sha != declared_sha256.lower():
        return "mismatch"
    return "match"


def _disk(ctx, relpath):
    """(size, md5, sha256) of an entry under the root, hashing it when the container hash did not."""
    entries = ctx["entries"]
    if relpath not in entries:
        return None
    full = (ctx["root_path"] + "/" + relpath) if ctx["root_path"] else relpath
    m = (ctx.get("members") or {}).get(full)
    if m is not None:
        return m[0], m[2], m[1]
    sha, md5, n = hashlib.sha256(), hashlib.md5(), 0
    with ctx["source"].open(full) as fh:
        while True:
            b = fh.read(4 << 20)
            if not b:
                break
            sha.update(b)
            md5.update(b)
            n += len(b)
    return n, md5.hexdigest(), sha.hexdigest()


def _resolve_entry(ctx, local_path):
    """The entry a Local Path names: exact first, then case-insensitively (flagged)."""
    p = norm(local_path)
    if p in ctx["entries"]:
        return p, False
    folded = ctx.get("_folded")
    if folded is None:
        folded = ctx["_folded"] = {}
        for k in ctx["entries"]:
            folded.setdefault(k.lower(), []).append(k)
    hits = folded.get(p.lower(), [])
    if len(hits) == 1:
        return hits[0], True
    return None, False


def verify_files(conn, ctx, reporter=None) -> dict:
    ext = ctx["extraction_id"]
    if "entries" not in ctx:
        list_entries(conn, ctx)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*), count(verified_at) FROM phone_files WHERE extraction_id = %s", (ext,))
        total, done = cur.fetchone()
    case_only = 0
    last = 0.0
    while True:
        with conn.cursor() as cur:
            cur.execute("SELECT document_index, ordinal, local_path, declared_size, declared_md5, declared_sha256 "
                        "FROM phone_files WHERE extraction_id = %s AND verified_at IS NULL "
                        "ORDER BY document_index, ordinal LIMIT %s", (ext, VERIFY_BATCH))
            batch = cur.fetchall()
        if not batch:
            break
        updates = []
        for doc, ordinal, lp, dsize, dmd5, dsha in batch:
            rel, folded = _resolve_entry(ctx, lp) if lp else (None, False)
            disk = _disk(ctx, rel) if rel is not None else None
            if folded:
                case_only += 1
            outcome = outcome_for(lp, dsize, dmd5, dsha, disk)
            updates.append((rel, disk[0] if disk else None, disk[1] if disk else None, disk[2] if disk else None,
                            outcome, ext, doc, ordinal))
        with conn.transaction():
            with conn.cursor() as cur:
                cur.executemany("UPDATE phone_files SET disk_relpath = %s, disk_size = %s, disk_md5 = %s, "
                                "disk_sha256 = %s, outcome = %s, verified_at = now() WHERE extraction_id = %s AND "
                                "document_index = %s AND ordinal = %s", updates)
                cur.executemany("UPDATE phone_container_entries SET md5 = %s, sha256 = %s WHERE extraction_id = %s "
                                "AND relpath = %s AND sha256 IS NULL",
                                [(u[2], u[3], ext, u[0]) for u in updates if u[0] is not None and u[3]])
        done += len(batch)
        if reporter is not None and time.monotonic() - last >= 1.0:
            last = time.monotonic()
            reporter.stage("indexing_files", 0.75 + 0.15 * (done / total if total else 1),
                           "Checking nothing is missing: files %s of %s" % (format(done, ","), format(total, ",")),
                           {"files_checked": done, "files_total": total})
        if reporter is not None and reporter.should_stop():
            from app.phone.runner import StopRequested
            raise StopRequested()
    with conn.cursor() as cur:
        cur.execute("SELECT outcome, count(*) FROM phone_files WHERE extraction_id = %s GROUP BY outcome", (ext,))
        outcomes = dict(cur.fetchall())
    if case_only:
        _merge_flags(conn, ext, {"local_path_case_only_matches": case_only})
    if total and absent_count(outcomes) == total:
        _merge_flags(conn, ext, {"all_files_absent": total})
    return {"outcomes": outcomes, "files": total}


# Outcomes of a file that is not in the production at all: listed but not there, or given no location to look in.
ABSENT_OUTCOMES = ("missing", "no_local_path")


def absent_count(outcomes) -> int:
    return sum(outcomes.get(k, 0) for k in ABSENT_OUTCOMES)


def absent_text(outcomes, total) -> str:
    """The job result's sentence when no listed file is in the production (P10's shape: the report and nothing else)."""
    missing, unplaced = outcomes.get("missing", 0), outcomes.get("no_local_path", 0)
    if not unplaced:
        return " None of the %s files the report lists is in the production; each is marked absent." % format(total, ",")
    return (" None of the %s files the report lists is in the production: %s %s missing and %s %s no location in the "
            "production. Each is marked absent." % (format(total, ","), format(missing, ","), "is" if missing == 1 else "are",
                                                    format(unplaced, ","), "has" if unplaced == 1 else "have"))


def _merge_flags(conn, ext, flags):
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute("UPDATE phone_extractions SET flags = flags || %s::jsonb WHERE id = %s",
                        (json.dumps(flags), ext))


# -- references ----------------------------------------------------------------------------------------------

def walk_body(body, path=""):
    """(body_path, element) for every element of a row body, markers skipped (01 section 6.4 positions)."""
    stack = [(body, path)]
    while stack:
        node, p = stack.pop()
        if not isinstance(node, list) or len(node) < 4 or not isinstance(node[0], str) or node[0][:1] == "@":
            continue
        yield p, node
        for i, c in enumerate(node[3] or ()):
            stack.append((c, (p + "." if p else "") + str(i)))


REFS_BATCH = 1000


def _scan_refs(body, top_dirs, entries):
    """Every reference-like element of one record body: (path, kind, text) with kind model, file, file_id or path."""
    for p, el in walk_body(body):
        tag, attrs = el[0], el[1] or {}
        if tag == "targetid" and el[2]:
            yield p, ("model" if (attrs.get("ismodel") or "").lower() == "true" else "file"), el[2]
        elif tag == "model" and attrs.get("file_id"):
            yield p, "file_id", attrs["file_id"]
        elif tag == "value" and el[2] and el[3] is None:
            v = norm(el[2])
            if "/" in v and v.split("/", 1)[0] in top_dirs:
                yield p, "path", el[2]


def _lookup(conn, sql, ext, keys):
    out = {}
    if keys:
        with conn.cursor() as cur:
            cur.execute(sql, (ext, list(keys)))
            for row in cur.fetchall():
                out.setdefault(row[0], []).append(row[1:])
    return out


def resolve_references(conn, ctx, reporter=None) -> dict:
    """Links from records to files, records and container entries (01 section 7). Records are read in batches and
    only the ids and paths a batch names are looked up, so memory does not grow with the number of records (P14:
    967,543 records held as one id map peaked 476 MiB above the stage's start)."""
    ext = ctx["extraction_id"]
    if "entries" not in ctx:
        list_entries(conn, ctx)
    entries = ctx["entries"]
    top_dirs = {e.split("/", 1)[0] for e in entries if "/" in e}
    conflicts = []
    stats = {"jumptarget_file": 0, "jumptarget_file_resolved": 0, "jumptarget_model": 0, "file_id_attribute": 0,
             "file_id_attribute_resolved": 0, "extracted_path_value": 0, "extracted_path_value_resolved": 0,
             "ambiguous": 0}
    n_rows = 0
    after = (-1, -1)
    with conn.transaction():
        with conn.cursor() as c:
            c.execute("DELETE FROM phone_file_references WHERE extraction_id = %s", (ext,))
        while True:
            with conn.cursor() as cur:
                cur.execute("SELECT document_index, ordinal, body FROM phone_records WHERE extraction_id = %s AND "
                            "(document_index, ordinal) > (%s, %s) ORDER BY document_index, ordinal LIMIT %s",
                            (ext, after[0], after[1], REFS_BATCH))
                batch = cur.fetchall()
            if not batch:
                break
            after = (batch[-1][0], batch[-1][1])
            found = [(doc, ordinal, list(_scan_refs(body, top_dirs, entries))) for doc, ordinal, body in batch]
            del batch
            model_ids = {t for _, _, refs in found for _, k, t in refs if k == "model"}
            file_ids = {t for _, _, refs in found for _, k, t in refs if k in ("file", "file_id")}
            models = _lookup(conn, "SELECT source_model_id, document_index, ordinal FROM phone_records WHERE "
                                   "extraction_id = %s AND source_model_id = ANY(%s) ORDER BY document_index, ordinal",
                             ext, model_ids)
            files = _lookup(conn, "SELECT source_file_id, document_index, ordinal, disk_sha256 FROM phone_files WHERE "
                                  "extraction_id = %s AND source_file_id = ANY(%s) ORDER BY document_index, ordinal",
                            ext, file_ids)
            rows = []
            for doc, ordinal, refs in found:
                record_rows = []
                for p, kind, ref in refs:
                    if kind == "model":
                        stats["jumptarget_model"] += 1
                        cands = models.get(ref, [])
                        if not cands:
                            record_rows.append((doc, ordinal, p, "jumptarget", ref, None, None, None, "unresolved",
                                                False))
                        for k, (mdoc, mo) in enumerate(cands):
                            amb = len(cands) > 1
                            stats["ambiguous"] += amb
                            record_rows.append((doc, ordinal, p + ("#%d" % k if amb else ""), "jumptarget", ref,
                                                mdoc, mo, None, "model", amb))
                    elif kind == "file":
                        stats["jumptarget_file"] += 1
                        record_rows.extend(_file_refs(doc, ordinal, p, "jumptarget", ref, files, stats,
                                                      "jumptarget_file_resolved"))
                    elif kind == "file_id":
                        stats["file_id_attribute"] += 1
                        record_rows.extend(_file_refs(doc, ordinal, p, "file_id_attribute", ref, files, stats,
                                                      "file_id_attribute_resolved"))
                    else:
                        v = norm(ref)
                        stats["extracted_path_value"] += 1
                        if v in entries:
                            stats["extracted_path_value_resolved"] += 1
                            record_rows.append((doc, ordinal, p, "extracted_path_value", ref, None, None, v,
                                                "container_entry", False))
                        else:
                            record_rows.append((doc, ordinal, p, "extracted_path_value", ref, None, None, None,
                                                "unresolved", False))
                rows.append((doc, ordinal, record_rows))
            paths = {r[7] for _, _, rr in rows for r in rr if r[8] == "container_entry"}
            entry_sha = {k: v[0][0] for k, v in _lookup(
                conn, "SELECT relpath, sha256 FROM phone_container_entries WHERE extraction_id = %s AND "
                      "relpath = ANY(%s)", ext, paths).items()}
            out = []
            for doc, ordinal, record_rows in rows:
                shas = {}
                for r in record_rows:
                    sha = None
                    if r[8] == "tagged_file":
                        sha = next((f[2] for f in files.get(r[4], []) if (f[0], f[1]) == (r[5], r[6])), None)
                    elif r[8] == "container_entry":
                        sha = entry_sha.get(r[7])
                    if sha:
                        shas.setdefault(sha, set()).add(r[3])
                if len(shas) > 1 and len(set().union(*shas.values())) > 1:
                    conflicts.append("%s/%d/r%d" % (ext, doc, ordinal))
                out.extend((ext,) + r for r in record_rows)
            if out:
                with conn.cursor() as c:
                    with c.copy("COPY phone_file_references (extraction_id, document_index, record_ordinal, "
                                "body_path, mechanism, reference_text, file_document_index, file_ordinal, "
                                "container_relpath, resolution, ambiguous) FROM STDIN") as cp:
                        for r in out:
                            cp.write_row(r)
            n_rows += len(out)
            if reporter is not None and reporter.should_stop():
                from app.phone.runner import StopRequested
                raise StopRequested()
    if conflicts:
        _merge_flags(conn, ext, {"attachment_reference_conflict": conflicts})
    stats["rows"] = n_rows
    stats["conflicts"] = len(conflicts)
    return stats


def _file_refs(doc, ordinal, p, mechanism, ref, files, stats, resolved_key):
    cands = files.get(ref, [])
    if not cands:
        return [(doc, ordinal, p, mechanism, ref, None, None, None, "unresolved", False)]
    stats[resolved_key] += 1
    amb = len(cands) > 1
    return [(doc, ordinal, p + ("#%d" % k if amb else ""), mechanism, ref, fd, fo, None, "tagged_file", amb)
            for k, (fd, fo, _) in enumerate(cands)]
