"""Synchronous psycopg 3 writes for the phone capture (01 sections 5.1 and 5.5).

The DSN is derived locally from the engine's ``database_url``; the process environment is never changed and no
backend package is imported (decision D12). Rows go through ``COPY ... FROM STDIN``, one transaction per flush,
and the same transaction updates the document's capture cursor, so a flush is all-or-nothing and the cursor
names exactly what is stored.
"""
from __future__ import annotations

import json

import psycopg

from app.models import phone as tables
from app.phone.ids import file_uid

FLUSH_ROWS = 2000
FLUSH_BYTES = 16 * 1024 * 1024

KIND_TABLE = {"r": tables.phone_records, "f": tables.phone_files, "x": tables.phone_extra_infos}
KIND_COLUMNS = {
    "r": ["ordinal", "parent_ordinal", "top_ordinal", "depth", "model_type", "source_model_id", "deleted_state",
          "is_partial", "body"],
    "f": ["ordinal", "file_uid", "parent_ordinal", "source_file_id", "local_path", "declared_size", "declared_md5",
          "declared_sha256", "tags", "is_partial", "body"],
    "x": ["ordinal", "source_id", "info_type", "is_partial", "body"],
}
for _k, _cols in KIND_COLUMNS.items():  # the mirror names every column written
    assert set(_cols) <= set(tables.columns(KIND_TABLE[_k])), _k


def dsn_from_url(url: str) -> str:
    for prefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def connect(url: str):
    # autocommit: every write block below opens its own real transaction (``conn.transaction()``)
    return psycopg.connect(dsn_from_url(url), autocommit=True)


def dumps(body) -> str:
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


class CopySink:
    def __init__(self, conn, extraction_id, document_index, flush_rows=FLUSH_ROWS, flush_bytes=FLUSH_BYTES):
        self.conn = conn
        self.extraction_id = extraction_id
        self.document_index = document_index
        self.flush_rows = flush_rows
        self.flush_bytes = flush_bytes
        self.buf = {"r": [], "f": [], "x": []}
        self.nrows = 0
        self.nbytes = 0
        self.flushes = 0
        self.written = {"r": 0, "f": 0, "x": 0}

    def row(self, kind, row):
        body = dumps(row["body"])
        values = [self.extraction_id, self.document_index]
        for c in KIND_COLUMNS[kind]:
            if c == "file_uid":  # 02 section 1.2: the id a phone file is linked by
                values.append(str(file_uid(self.extraction_id, self.document_index, row["ordinal"])))
            else:
                values.append(body if c == "body" else row.get(c))
        self.buf[kind].append(values)
        self.nrows += 1
        self.nbytes += len(body)

    def flush_due(self):
        return self.nrows >= self.flush_rows or self.nbytes >= self.flush_bytes

    def flush(self, cursor):
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                for kind, rows in self.buf.items():
                    if not rows:
                        continue
                    cols = ", ".join(["extraction_id", "document_index"] + KIND_COLUMNS[kind])
                    with cur.copy("COPY %s (%s) FROM STDIN" % (KIND_TABLE[kind].name, cols)) as cp:
                        for values in rows:
                            cp.write_row(values)
                    self.written[kind] += len(rows)
                cur.execute("UPDATE phone_extraction_documents SET capture_cursor = %s "
                            "WHERE extraction_id = %s AND document_index = %s",
                            (json.dumps(cursor), self.extraction_id, self.document_index))
        self.buf = {"r": [], "f": [], "x": []}
        self.nrows = 0
        self.nbytes = 0
        self.flushes += 1


def prepare_resume(conn, extraction_id, document_index, cursor) -> dict:
    """Delete rows above the cursor (decision D26). Returns the number removed per kind."""
    removed = {}
    with conn.transaction():
        with conn.cursor() as cur:
            for kind, key in (("r", "record_ordinal"), ("f", "file_ordinal"), ("x", "extra_ordinal")):
                cur.execute("DELETE FROM %s WHERE extraction_id = %%s AND document_index = %%s AND ordinal > %%s"
                            % KIND_TABLE[kind].name, (extraction_id, document_index, int(cursor.get(key, 0))))
                removed[kind] = cur.rowcount
    return removed


class BufferedCopy:
    """COPY rows in batches. A COPY cannot run while a server-side cursor on the same connection is fetching, so
    rows are buffered and written between fetches."""

    def __init__(self, conn, sql, batch=5000):
        self.conn, self.sql, self.batch = conn, sql, batch
        self.rows = []
        self.written = 0

    def write_row(self, row):
        self.rows.append(row)
        if len(self.rows) >= self.batch:
            self.flush()

    def flush(self):
        if not self.rows:
            return
        with self.conn.cursor() as cur:
            with cur.copy(self.sql) as cp:
                for r in self.rows:
                    cp.write_row(r)
        self.written += len(self.rows)
        self.rows = []
