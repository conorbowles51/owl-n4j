"""Where embedded items live: vectors in the Chroma collection ``case_items``, their index in ``embed_items``."""
from __future__ import annotations

import logging
from datetime import timezone
from typing import Any, Callable

from sqlalchemy import text

from services.embed_all.core import COLLECTION, Item
from services.phone import fold as F

logger = logging.getLogger(__name__)


def _ts(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def folded(value: str) -> str:
    try:
        return F.fold(value or "")
    except Exception:
        return (value or "").casefold()


def case_items_collection():
    from services.vector_db_service import get_vector_db_service
    svc = get_vector_db_service()
    if not svc:
        raise RuntimeError("vector database unavailable")
    return svc.client.get_or_create_collection(name=COLLECTION, metadata={"description": "Everything in a case, by meaning"})


class PgChromaStore:
    def __init__(self, engine, collection=None):
        self.engine = engine
        self._collection = collection

    @property
    def collection(self):
        if self._collection is None:
            self._collection = case_items_collection()
        return self._collection

    def existing(self, case_id: str, area: str) -> dict[str, tuple[str, int]]:
        with self.engine.connect() as c:
            rows = c.execute(text("SELECT item_key, text_hash, chunk_count FROM embed_items WHERE case_id = :c AND "
                                  "area = :a"), {"c": case_id, "a": area}).fetchall()
        return {r[0]: (r[1], r[2]) for r in rows}

    @staticmethod
    def vector_id(area: str, key: str, n: int) -> str:
        return "%s:%s:%d" % (area, key, n)

    def put(self, case_id: str, area: str, items: list[Item], vectors: list[list[list[float]]]) -> None:
        old = self.existing(case_id, area)
        stale = []
        for it in items:
            if it.key in old:
                stale += [self.vector_id(area, it.key, n) for n in range(old[it.key][1])]
        ids, embs, docs, metas = [], [], [], []
        for it, vecs in zip(items, vectors):
            for n, (piece, vec) in enumerate(zip(it.pieces, vecs)):
                ids.append(self.vector_id(area, it.key, n))
                embs.append(vec)
                docs.append(piece)
                meta = {"case_id": case_id, "area": area, "item_key": it.key, "title": it.title[:300],
                        "cite": it.cite, "person": it.person[:500], "extraction_id": it.extraction_id,
                        "as_read": bool(it.as_read), "piece": n}
                if it.date is not None:
                    meta["item_ts"] = _ts(it.date)
                metas.append(meta)
        # new pieces first, then the pieces an older, longer text no longer has: a failure keeps the old value
        self.collection.upsert(ids=ids, embeddings=embs, documents=docs, metadatas=metas)
        keep = set(ids)
        drop = [i for i in stale if i not in keep]
        if drop:
            self.collection.delete(ids=drop)
        with self.engine.begin() as c:
            for it in items:
                c.execute(text(
                    "INSERT INTO embed_items (case_id, area, item_key, text_hash, chunk_count, title, cite, body, "
                    "body_folded, item_date, person, extraction_id, embedded_at) VALUES (:c, :a, :k, :h, :n, :t, :ci, "
                    ":b, :bf, :d, :p, :x, now()) ON CONFLICT (case_id, area, item_key) DO UPDATE SET "
                    "text_hash = EXCLUDED.text_hash, chunk_count = EXCLUDED.chunk_count, title = EXCLUDED.title, "
                    "cite = EXCLUDED.cite, body = EXCLUDED.body, body_folded = EXCLUDED.body_folded, "
                    "item_date = EXCLUDED.item_date, person = EXCLUDED.person, extraction_id = EXCLUDED.extraction_id, "
                    "embedded_at = now()"),
                    {"c": case_id, "a": area, "k": it.key, "h": it.digest(), "n": len(it.pieces), "t": it.title,
                     "ci": it.cite, "b": it.text if it.keep_text else None,
                     "bf": folded(it.text) if it.keep_text else None, "d": it.date, "p": it.person or None,
                     "x": it.extraction_id or None})

    def remove(self, case_id: str, area: str, keys: dict[str, int]) -> None:
        ids = [self.vector_id(area, k, n) for k, count in keys.items() for n in range(count)]
        for i in range(0, len(ids), 500):
            self.collection.delete(ids=ids[i:i + 500])
        with self.engine.begin() as c:
            for k in keys:
                c.execute(text("DELETE FROM embed_items WHERE case_id = :c AND area = :a AND item_key = :k"),
                          {"c": case_id, "a": area, "k": k})

    def remove_case(self, case_id: str) -> None:
        self.collection.delete(where={"case_id": case_id})
        with self.engine.begin() as c:
            c.execute(text("DELETE FROM embed_items WHERE case_id = :c"), {"c": case_id})
