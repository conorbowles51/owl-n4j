"""Read a tool's LAVA output through the reviewed artefact mapping (05 section 17.3 point 3; mapping.json).

LAVA is the SQLite file the tools write: one table per artefact, column names snake_case, datetimes as integer
seconds since 1970 (UTC). Every artefact table is counted; the mapped ones are read row by row into
``{artefact, row_index, kind, instant, instant_text, values}`` where ``values`` holds each role's value (and which
column it came from) and the row as the tool wrote it. A role whose columns are all absent is listed under
``missing_roles``, never guessed.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3

_HERE = os.path.dirname(__file__)
MAPPING = json.load(open(os.path.join(_HERE, "mapping.json")))
VERSION = MAPPING["version"]


def _instant(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        secs = float(v)
        if secs > 1e14:      # microseconds
            secs /= 1e6
        elif secs > 1e11:    # milliseconds
            secs /= 1e3
        try:
            return dt.datetime.fromtimestamp(secs, tz=dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(v, str):
        try:
            t = dt.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    return None


def _raw(v):
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"blob_bytes": len(bytes(v))}
    return v


def read_lava(path: str, tool: str):
    """``(counts, rows)``: counts per artefact table (all of them) and per mapped kind, and the mapped rows."""
    spec = MAPPING["tools"].get(tool, {})
    uri = "file:%s?mode=ro" % path
    conn = sqlite3.connect(uri, uri=True)
    conn.text_factory = lambda b: b.decode("utf-8", "replace")
    counts = {"artefacts": {}, "mapped": {}, "missing_roles": {}, "mapping_version": VERSION}
    rows = []
    try:
        tables = [n for (n,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE "
                                             "'\\_%' ESCAPE '\\' ORDER BY name")]
        for t in tables:
            counts["artefacts"][t] = conn.execute('SELECT count(*) FROM "%s"' % t.replace('"', '""')).fetchone()[0]
        for artefact, m in spec.items():
            if artefact not in counts["artefacts"]:
                continue
            cols = [r[1] for r in conn.execute('PRAGMA table_info("%s")' % artefact.replace('"', '""'))]
            pick, missing = {}, []
            for role, cands in m["roles"].items():
                hit = next((c for c in cands if c in cols), None)
                if hit:
                    pick[role] = hit
                else:
                    missing.append(role)
            if missing:
                counts["missing_roles"][artefact] = missing
            n = 0
            cur = conn.execute('SELECT rowid, * FROM "%s"' % artefact.replace('"', '""'))
            names = [d[0] for d in cur.description]
            for rec in cur:
                raw = dict(zip(names[1:], (_raw(v) for v in rec[1:])))
                vals = {role: raw.get(col) for role, col in pick.items()}
                when = _instant(raw.get(pick["instant"])) if "instant" in pick else None
                rows.append({"artefact": artefact, "row_index": int(rec[0]), "kind": m["kind"], "natural_key": None,
                             "instant": when, "instant_text": None if "instant" not in pick else
                             (None if raw.get(pick["instant"]) is None else str(raw.get(pick["instant"]))),
                             "source_path": None,
                             "values": {"app": m["app"], "roles": vals, "columns": pick, "row": raw}})
                n += 1
            counts["mapped"][m["kind"]] = counts["mapped"].get(m["kind"], 0) + n
    finally:
        conn.close()
    return counts, rows
