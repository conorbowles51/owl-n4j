"""One shared path: an item is embedded when it is new or its text changed, and removed when its source is gone.

``reconcile`` takes the case's current items for one area and compares each item's hash with the hash stored when it was
embedded. New or changed items are embedded (a change replaces the old vector, so only the current value is searched);
items no longer in the source are removed from the index and the vector store. Nothing here reads a source: the area
readers in ``sources`` yield ``Item`` objects, so a correction, a new statement or a delete reaches the index by the same
step that built it.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, Protocol

logger = logging.getLogger(__name__)

COLLECTION = "case_items"
PIECE_CHARS = 6000   # the document chunk size of the engine (evidence-engine chunk_embed.CHUNK_SIZE)
PIECE_OVERLAP = 800
BATCH = 64
MAX_TOKEN_WEIGHT = 8000  # the embedding model refuses an input of more than 8,192 tokens


def clamp(text: str, limit: int = MAX_TOKEN_WEIGHT) -> str:
    """The text cut so that it cannot pass the model's input limit. A character counts as one token, and as three when it
    is not ASCII (emoji and scripts the tokenizer splits into bytes): a safe upper bound, not a count. Only the vector's
    text is cut; the stored passage is whole."""
    weight = 0
    for i, ch in enumerate(text):
        weight += 1 if ord(ch) < 128 else 3
        if weight > limit:
            return text[:i]
    return text


@dataclass
class Item:
    area: str
    key: str                       # stable within the case and area
    text: str                      # what is embedded and word-searched
    title: str = ""
    cite: str = ""                 # citation key a hit opens: rec://, txn://, doc://, ...
    date: datetime | None = None
    person: str = ""               # names of people on the item, for the person filter
    extraction_id: str = ""
    as_read: bool = False          # text a model or parser read from a page, not a person's entry
    keep_text: bool = True         # False: the text lives elsewhere (phone conversation files)
    pieces: list[str] = field(default_factory=list)

    def digest(self) -> str:
        h = hashlib.sha256()
        h.update(json.dumps([self.text, self.title, self.cite, self.date.isoformat() if self.date else "", self.person,
                             self.extraction_id, self.as_read], ensure_ascii=False).encode())
        return h.hexdigest()


def normalize_key(file_name: str) -> str:
    """The engine's document key (evidence-engine chunk_embed.normalize_document_key)."""
    import re
    key = file_name.strip().lower()
    key = re.sub(r"[\s_]+", "-", key)
    key = re.sub(r"[^a-z0-9\-]", "", key)
    return re.sub(r"-+", "-", key).strip("-")


def split_pieces(text: str, size: int = PIECE_CHARS, overlap: int = PIECE_OVERLAP) -> list[str]:
    """Pieces of at most ``size`` characters, cut at a line or space where one is near, overlapping by ``overlap``."""
    if len(text) <= size:
        return [text]
    out, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = max(text.rfind("\n", start + size // 2, end), text.rfind(" ", start + size // 2, end))
            if cut > start:
                end = cut + 1
        out.append(text[start:end])
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return out


class Store(Protocol):
    def existing(self, case_id: str, area: str) -> dict[str, tuple[str, int]]: ...
    def put(self, case_id: str, area: str, items: list[Item], vectors: list[list[list[float]]]) -> None: ...
    def remove(self, case_id: str, area: str, keys: dict[str, int]) -> None: ...


def plan(existing: dict[str, tuple[str, int]], items: Iterable[Item]):
    """(to embed, keys to remove, unchanged count). ``existing`` maps key -> (hash, piece count)."""
    seen: dict[str, Item] = {}
    for item in items:
        seen[item.key] = item
    todo = [i for k, i in seen.items() if k not in existing or existing[k][0] != i.digest()]
    gone = {k: v[1] for k, v in existing.items() if k not in seen}
    return todo, gone, len(seen) - len(todo)


def reconcile(case_id: str, area: str, items: Iterable[Item], store: Store,
              embed: Callable[[list[str]], list[list[float]]], *, batch: int = BATCH,
              allow_remove: bool = True, should_stop: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Bring the index of one area in step with ``items``. Returns counts. A refused embedding call stops the run
    (``stopped`` holds the reason); what was embedded before it is kept and the rest is retried by the next run."""
    existing = store.existing(case_id, area)
    todo, gone, unchanged = plan(existing, items)
    out = {"area": area, "embedded": 0, "updated": 0, "removed": 0, "unchanged": unchanged, "stopped": None,
           "pending": 0, "chars": 0}
    for i in range(0, len(todo), batch):
        if should_stop is not None and should_stop():
            out["stopped"] = "paused for a release"
            out["pending"] = len(todo) - i
            break
        chunk = todo[i:i + batch]
        flat, spans = [], []
        for item in chunk:
            item.pieces = [p for p in split_pieces(item.text) if p.strip()] if item.text.strip() else []
            spans.append((len(flat), len(item.pieces)))
            flat.extend(item.pieces)
        try:
            vectors = embed(flat) if flat else []
            if len(vectors) != len(flat):
                raise RuntimeError("the embedding service returned %d vectors for %d texts" % (len(vectors), len(flat)))
        except Exception as exc:
            out["stopped"] = str(exc)[:300]
            out["pending"] = len(todo) - i
            logger.warning("embed_all %s %s stopped: %s", case_id, area, exc)
            break
        grouped = [vectors[a:a + n] for a, n in spans]
        # a text the service cannot take (None) fails that item only: it is counted, never stops the run
        bad = [it for it, v in zip(chunk, grouped) if it.pieces and any(x is None for x in v)]
        out["failed"] = out.get("failed", 0) + len(bad)
        for it in bad:
            logger.warning("embed_all %s %s item %s could not be embedded", case_id, area, it.key)
        ok = [(it, v) for it, v in zip(chunk, grouped) if it.pieces and not any(x is None for x in v)]
        if ok:
            store.put(case_id, area, [x[0] for x in ok], [x[1] for x in ok])
        for it, _ in ok:
            out["updated" if it.key in existing else "embedded"] += 1
            out["chars"] += len(it.text)
    if gone and allow_remove:  # removal needs no embedding: a delete reaches the index even while the service refuses
        store.remove(case_id, area, gone)
        out["removed"] = len(gone)
    return out
