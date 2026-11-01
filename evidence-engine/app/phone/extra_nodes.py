"""Index the ``nodeInfo`` entries of each captured ``extraInfo`` (decision D24; 01 sections 1.8 and 1.9).

Each ``nodeInfo`` (``id``, ``name``, ``path``, ``tableName``, ``offset``, ``size``) names the source file a record or
file entry was read from. It becomes one ``phone_extra_info_nodes`` row, resolved to a tagged file:

1. ``tagged_file_id``: its ``id`` equals a tagged file's ``id``;
2. ``tagged_file_path``: otherwise, its ``path`` equals a tagged file's ``path`` attribute once both are put in one
   form (``path_key``: '\\' to '/', no leading '/', case-folded), when exactly one file has that form;
3. ``tagged_file_subpath``: otherwise, its path without its first segment has the form of exactly one tagged file's
   path. Measured on the server P01 (decision D38): every ``nodeInfo`` path there starts with one of 3 source
   names that no file path carries, and 19,940 of its 46,686 nodes match exactly one file once it is dropped;
4. ``unresolved`` otherwise. Several files with one form are not chosen between.

The body stays the capture; these rows are an index over it, rebuilt from the bodies on every run.
"""
from __future__ import annotations

from app.phone.files import walk_body
from app.phone.store import BufferedCopy

COLUMNS = ("extraction_id, document_index, extra_ordinal, body_path, node_id, node_name, node_path, table_name, "
           "node_offset, node_size, file_document_index, file_ordinal, resolution")


def path_key(p):
    if not p:
        return None
    return p.replace("\\", "/").lstrip("/").casefold()


def store_extra_nodes(conn, ctx, reporter=None) -> dict:
    ext = ctx["extraction_id"]
    with conn.cursor() as c:
        c.execute("SELECT count(*) FROM phone_extra_infos WHERE extraction_id = %s", (ext,))
        if not c.fetchone()[0]:
            return {"rows": 0}
        c.execute("SELECT source_file_id, document_index, ordinal, body->1->>'path' FROM phone_files "
                  "WHERE extraction_id = %s", (ext,))
        by_id, by_path = {}, {}
        for fid, doc, o, path in c.fetchall():
            if fid:
                by_id.setdefault(fid, []).append((doc, o))
            k = path_key(path)
            if k:
                by_path.setdefault(k, []).append((doc, o))
    stats = {"rows": 0, "tagged_file_id": 0, "tagged_file_path": 0, "tagged_file_subpath": 0, "unresolved": 0,
             "id_ambiguous": 0}
    with conn.transaction():
        with conn.cursor() as c:
            c.execute("DELETE FROM phone_extra_info_nodes WHERE extraction_id = %s", (ext,))
        cp = BufferedCopy(conn, "COPY phone_extra_info_nodes (%s) FROM STDIN" % COLUMNS)
        cur = conn.cursor(name="extra_nodes")
        cur.execute("SELECT document_index, ordinal, body FROM phone_extra_infos WHERE extraction_id = %s "
                    "ORDER BY document_index, ordinal", (ext,))
        while True:
            batch = cur.fetchmany(5000)
            if not batch:
                break
            for doc, ordinal, body in batch:
                for p, el in walk_body(body):
                    if el[0] != "nodeInfo":
                        continue
                    a = el[1] or {}
                    fdoc = fo = None
                    hits = by_id.get(a.get("id")) if a.get("id") else None
                    if hits:
                        resolution = "tagged_file_id"
                        if len(hits) == 1:
                            fdoc, fo = hits[0]
                        else:
                            stats["id_ambiguous"] += 1
                    else:
                        key = path_key(a.get("path"))
                        ph = by_path.get(key)
                        sub = by_path.get(key.split("/", 1)[1]) if key and "/" in key and not ph else None
                        if ph and len(ph) == 1:
                            resolution = "tagged_file_path"
                            fdoc, fo = ph[0]
                        elif sub and len(sub) == 1:
                            resolution = "tagged_file_subpath"
                            fdoc, fo = sub[0]
                        else:
                            resolution = "unresolved"
                    stats[resolution] += 1
                    stats["rows"] += 1
                    cp.write_row((ext, doc, ordinal, p, (a.get("id") or None) and a["id"][:128], a.get("name"),
                                  a.get("path"), (a.get("tableName") or None) and a["tableName"][:256],
                                  a.get("offset"), a.get("size"), fdoc, fo, resolution))
            cp.flush()
        cur.close()
    return stats
