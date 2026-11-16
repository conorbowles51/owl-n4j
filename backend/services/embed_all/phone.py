"""Phone conversations embedded by window, in the chunk collection chat already searches (lx-embedall B).

Neil, 16 Nov 2026: "Embed everything in the system." (This replaces the gate of docs/cellebrite/02 section 9.8: phone
text is embedded in every case, by default.) The windows are built from the thread documents of 02 section 9.7: runs of
consecutive lines of one thread up to ``WINDOW_CHARS`` characters, every line ending in its ``[rec://<record_uid>]``
link. Ids and metadata follow the engine's chunk keys (``<evidence_file_id>:<content_sha256>:chunk:<n>``), plus
``source_kind = "phone_text"``, ``extraction_id``, ``first_record_uid`` and ``last_record_uid``. The vector is made from
the lines without the links (a record id is no meaning); the stored passage keeps them.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from sqlalchemy import text

from services.phone.chat_retrieval import WINDOW_CHARS, _line_bounds

logger = logging.getLogger(__name__)

AREA = "phone_text"
EMBED_BATCH = 64
_REC = re.compile(r" \[rec://[0-9a-fA-F-]{36}\]")


def build_windows(name: str, content: str, source_locations: list, limit: int = WINDOW_CHARS) -> list[dict]:
    """Consecutive lines of one thread file grouped up to ``limit`` characters. Each window: ``text`` (lines with their
    record links), ``embed_text`` (the same without links, under the thread's name), character span and record uids."""
    bounds = _line_bounds(content)
    locs = sorted((l for l in (source_locations or []) if l.get("kind") in ("phone_record", "phone_transcript")
                   and l.get("record_uid") is not None), key=lambda l: int(l["start_char"]))
    lines, j = [], 0
    for i, (s, e) in enumerate(bounds):
        body = content[s:e]
        if not body.strip():
            continue
        uid = None
        while j < len(locs) and int(locs[j]["start_char"]) < s:
            j += 1
        k = j
        while k < len(locs) and int(locs[k]["start_char"]) <= e:
            if locs[k].get("field_path") in (None, "Body") or locs[k].get("kind") == "phone_transcript":
                uid = locs[k]["record_uid"]
                break
            k += 1
        lines.append((s, e, body, uid))
    out, cur, size = [], [], 0
    for ln in lines:
        add = len(ln[2]) + 1
        if cur and size + add > limit:
            out.append(cur)
            cur, size = [], 0
        cur.append(ln)
        size += add
    if cur:
        out.append(cur)
    windows = []
    for grp in out:
        uids = [g[3] for g in grp if g[3]]
        stored = "\n".join(("%s [rec://%s]" % (g[2], g[3])) if g[3] else g[2] for g in grp)
        windows.append({"text": stored, "embed_text": "%s\n%s" % (name, "\n".join(g[2] for g in grp)),
                        "start_char": grp[0][0], "end_char": grp[-1][1],
                        "first_record_uid": uids[0] if uids else None, "last_record_uid": uids[-1] if uids else None})
    return windows


FILES_SQL = """
SELECT f.id, f.original_filename, f.metadata ->> 'phone_extraction_id' AS ext, t.content_sha256
FROM evidence_files f JOIN evidence_document_texts t ON t.evidence_file_id = f.id
JOIN phone_extractions e ON e.id::text = f.metadata ->> 'phone_extraction_id' AND e.case_id = f.case_id AND e.standing = 'active'
WHERE f.case_id = :c AND f.source_type = 'phone_text' AND f.deleted_at IS NULL ORDER BY f.id
"""


def signature(conn, case_id) -> str:
    return str(conn.execute(text(
        "SELECT concat_ws('|', count(*), md5(coalesce(string_agg(t.content_sha256, ',' ORDER BY f.id), ''))) "
        "FROM evidence_files f JOIN evidence_document_texts t ON t.evidence_file_id = f.id JOIN phone_extractions e ON "
        "e.id::text = f.metadata ->> 'phone_extraction_id' AND e.case_id = f.case_id AND e.standing = 'active' WHERE "
        "f.case_id = :c AND f.source_type = 'phone_text' AND f.deleted_at IS NULL"), {"c": str(case_id)}).scalar() or "")


def _ids(file_id, sha, count):
    return ["%s:%s:chunk:%d" % (file_id, sha, n) for n in range(count)]


def sync(engine, case_id: str, collection, embed: Callable[[list[str]], list[list[float]]], *,
         max_files: int | None = None) -> dict[str, Any]:
    """Bring the phone windows of one case in step with its thread documents: new or changed files are embedded, the
    windows of a file whose text changed or that is gone are removed. Returns counts."""
    from services.embed_all.core import normalize_key
    out = {"area": AREA, "files": 0, "windows": 0, "removed_files": 0, "unchanged": 0, "stopped": None, "pending": 0}
    with engine.connect() as c:
        files = c.execute(text(FILES_SQL), {"c": str(case_id)}).fetchall()
        have = {r[0]: (r[1], r[2]) for r in c.execute(text(
            "SELECT item_key, text_hash, chunk_count FROM embed_items WHERE case_id = :c AND area = :a"),
            {"c": str(case_id), "a": AREA})}
    current = {str(f.id): f for f in files}
    todo = [f for k, f in current.items() if k not in have or have[k][0] != f.content_sha256]
    out["unchanged"] = len(current) - len(todo)
    gone = [k for k in have if k not in current]
    if max_files is not None:
        todo = todo[:max_files]
    for f in todo:
        with engine.connect() as c:
            row = c.execute(text("SELECT content, source_locations FROM evidence_document_texts WHERE evidence_file_id = :i"),
                            {"i": f.id}).one()
        wins = build_windows(f.original_filename, row.content, row.source_locations)
        vectors: list = []
        try:
            for i in range(0, len(wins), EMBED_BATCH):
                part = embed([w["embed_text"] for w in wins[i:i + EMBED_BATCH]])
                if len(part) != len(wins[i:i + EMBED_BATCH]):
                    raise RuntimeError("the embedding service returned %d vectors for %d texts" % (
                        len(part), len(wins[i:i + EMBED_BATCH])))
                vectors += part
        except Exception as exc:
            out["stopped"] = str(exc)[:300]
            out["pending"] = len(todo) - out["files"]
            break
        key = normalize_key(f.original_filename)
        ids, metas = [], []
        for n, w in enumerate(wins):
            ids.append("%s:%s:chunk:%d" % (f.id, f.content_sha256, n))
            meta = {"case_id": str(case_id), "doc_id": str(f.id), "doc_name": f.original_filename, "doc_key": key,
                    "evidence_file_id": str(f.id), "revision_id": f.content_sha256, "ingestion_state": "active",
                    "file_name": f.original_filename, "chunk_index": n, "start_char": w["start_char"],
                    "end_char": w["end_char"], "is_table": False, "source_kind": "phone_text",
                    "extraction_id": f.ext or ""}
            if w["first_record_uid"]:
                meta.update(first_record_uid=w["first_record_uid"], last_record_uid=w["last_record_uid"],
                            record_uid=w["first_record_uid"], url="rec://%s" % w["first_record_uid"])
            metas.append(meta)
        if ids:
            collection.upsert(ids=ids, embeddings=vectors, documents=[w["text"] for w in wins], metadatas=metas)
        if f.id and str(f.id) in have and have[str(f.id)][0] != f.content_sha256:
            collection.delete(ids=_ids(f.id, have[str(f.id)][0], have[str(f.id)][1]))
        with engine.begin() as c:
            c.execute(text(
                "INSERT INTO embed_items (case_id, area, item_key, text_hash, chunk_count, title, cite, extraction_id, "
                "embedded_at) VALUES (:c, :a, :k, :h, :n, :t, :ci, :x, now()) ON CONFLICT (case_id, area, item_key) DO "
                "UPDATE SET text_hash = EXCLUDED.text_hash, chunk_count = EXCLUDED.chunk_count, title = EXCLUDED.title, "
                "cite = EXCLUDED.cite, extraction_id = EXCLUDED.extraction_id, embedded_at = now()"),
                {"c": str(case_id), "a": AREA, "k": str(f.id), "h": f.content_sha256, "n": len(ids),
                 "t": f.original_filename, "ci": "", "x": f.ext})
        out["files"] += 1
        out["windows"] += len(ids)
    for k in gone:
        sha, count = have[k]
        for i in range(0, count, 500):
            collection.delete(ids=_ids(k, sha, count)[i:i + 500])
        with engine.begin() as c:
            c.execute(text("DELETE FROM embed_items WHERE case_id = :c AND area = :a AND item_key = :k"),
                      {"c": str(case_id), "a": AREA, "k": k})
        out["removed_files"] += 1
    return out
