"""The passages behind graph connections and entities, for chat and agent answers (lx-retrieval B).

Graph expansion used to hand the model a neighbour's name, type and summary only. Every node and relationship the
evidence engine writes carries ``source_locations``: the evidence file, revision and chunk index where the claim was
read, with the quote and its character offsets (evidence-engine ``pipeline/write_graph.py``). This module turns those
locations into passages: the quote, the text around it from the same stored chunk, and the chunk's ``doc://`` cite.

A passage is used only when its quote is found in the stored chunk text of the same case, in an active revision.
Nothing is guessed: a location whose chunk is gone, retired or no longer holds the quote gives no passage, and the
count of such locations is reported in the stats.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

MAX_PASSAGES = 12  # passages behind connections and entities in one answer
MAX_LOCATIONS_PER_ITEM = 2  # passages per connection or entity
MAX_PER_CHUNK = 2  # passages from one stored chunk (a statement chunk sources many payments)
MAX_RELATIONSHIPS = 80  # connections whose provenance is read
MAX_ENTITIES = 20  # entities whose own provenance is read
WINDOW = 500  # characters of chunk text kept on each side of the quote

_STOP = {
    "the", "and", "for", "with", "from", "what", "who", "whom", "whose", "when", "where", "which", "were", "was",
    "did", "does", "have", "has", "had", "this", "that", "they", "them", "their", "there", "into", "about", "any",
    "all", "his", "her", "its", "are", "not", "between", "after", "before", "over", "under", "than", "then",
    "llc", "inc", "ltd", "corp", "company", "bank", "account", "phone", "payment", "payments", "street", "road",
}


def _words(text: Any) -> List[str]:
    return re.findall(r"[a-z0-9][a-z0-9'&.-]*", str(text or "").lower().replace("’", "'"))


def question_terms(question: str) -> set:
    terms = set()
    for word in _words(question):
        word = word.strip(".'-")
        if word.endswith("'s"):
            word = word[:-2]
        if len(word) >= 3 and word not in _STOP:
            terms.add(word)
    return terms


def is_named(name: Any, terms: set) -> bool:
    """The question names this entity: one distinctive word of its name (4+ letters, not a common word) is in it."""
    for word in _words(name):
        word = word.strip(".'-")
        if word.endswith("'s"):
            word = word[:-2]
        if len(word) >= 4 and word not in _STOP and word in terms:
            return True
    return False


def parse_locations(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def candidate_items(question: str, entity_results: List[Dict], graph_context: Dict) -> List[Dict[str, Any]]:
    """Connections and entities in the context, best first: those between entities the question names lead."""
    terms = question_terms(question)
    rank = {e.get("key"): i for i, e in enumerate(entity_results) if e.get("key")}
    names = {e.get("key"): e.get("name") for e in entity_results if e.get("key")}
    items: List[Dict[str, Any]] = []
    seen_pairs: set = set()
    for entity in graph_context.get("selected_entities", []) or []:
        a_key = entity.get("key")
        if not a_key:
            continue
        names.setdefault(a_key, entity.get("name"))
        a_named = is_named(entity.get("name"), terms)
        for conn in entity.get("connections", []) or []:
            b_key, rel = conn.get("key"), conn.get("relationship")
            if not b_key or not rel:
                continue
            pair = (min(a_key, b_key), max(a_key, b_key), rel)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            named = int(a_named) + int(is_named(conn.get("name"), terms))
            outgoing = conn.get("direction") == "outgoing"
            items.append({
                "kind": "relationship", "a": a_key, "b": b_key, "type": rel, "named": named,
                "source_name": entity.get("name") if outgoing else conn.get("name"),
                "target_name": conn.get("name") if outgoing else entity.get("name"),
                "order": (-named, -(int(a_key in rank) + int(b_key in rank)),
                          min(rank.get(a_key, 10 ** 6), rank.get(b_key, 10 ** 6))),
            })
    for key, name in names.items():
        named = int(is_named(name, terms))
        items.append({"kind": "entity", "key": key, "name": name, "named": named,
                      # a named entity's own passages come after connections between two named entities
                      "order": (-(named * 1.5), -1, rank.get(key, 10 ** 6))})
    items.sort(key=lambda item: item["order"])
    rels = [i for i in items if i["kind"] == "relationship"][:MAX_RELATIONSHIPS]
    ents = [i for i in items if i["kind"] == "entity"][:MAX_ENTITIES]
    kept = {id(i) for i in rels + ents}
    return [i for i in items if id(i) in kept]


def read_provenance(session, case_id: str, items: List[Dict[str, Any]]) -> None:
    """Attach each item's stored source locations (in place)."""
    pairs = [{"i": n, "a": i["a"], "b": i["b"], "t": i["type"]} for n, i in enumerate(items)
             if i["kind"] == "relationship"]
    keys = [i["key"] for i in items if i["kind"] == "entity"]
    if pairs:
        rows = session.run(
            "UNWIND $pairs AS p "
            "MATCH (a {key: p.a, case_id: $case_id})-[r]-(b {key: p.b, case_id: $case_id}) "
            "WHERE type(r) = p.t "
            "RETURN p.i AS i, collect(r.source_locations) AS locations",
            pairs=pairs, case_id=case_id)
        for row in rows:
            item = items[row["i"]]
            item["locations"] = [loc for value in row["locations"] or [] for loc in parse_locations(value)]
    if keys:
        by_key = {i["key"]: i for i in items if i["kind"] == "entity"}
        rows = session.run(
            "MATCH (n) WHERE n.key IN $keys AND n.case_id = $case_id "
            "RETURN n.key AS key, n.source_locations AS locations",
            keys=keys, case_id=case_id)
        for row in rows:
            if row["key"] in by_key:
                by_key[row["key"]]["locations"] = parse_locations(row["locations"])


def chunk_id(location: Dict[str, Any]) -> Optional[str]:
    doc, revision, index = (location.get("source_document_id"), location.get("revision_id"),
                            location.get("chunk_index"))
    if not doc or not revision or index is None:
        return None
    return "%s:%s:chunk:%s" % (doc, revision, index)


def read_chunks(collection, case_id: str, ids: Iterable[str]) -> Dict[str, Tuple[str, Dict[str, Any]]]:
    """Stored chunk text and metadata by id: only chunks of this case in an active revision."""
    ids = [i for i in dict.fromkeys(ids) if i]
    if not ids or collection is None:
        return {}
    got = collection.get(ids=ids, include=["documents", "metadatas"])
    out = {}
    for cid, text, meta in zip(got.get("ids") or [], got.get("documents") or [], got.get("metadatas") or []):
        meta = meta or {}
        if str(meta.get("case_id")) != str(case_id):
            continue
        if meta.get("ingestion_state") not in (None, "", "active"):
            continue
        out[cid] = (text or "", meta)
    return out


def _find(text: str, quote: str, location: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    if not quote:
        return None
    start, end = location.get("quote_start_char"), location.get("quote_end_char")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text) and text[start:end] == quote:
        return start, end
    at = text.find(quote)
    if at >= 0:
        return at, at + len(quote)
    at = text.lower().find(quote.lower())
    if at >= 0:
        return at, at + len(quote)
    return None


def window(text: str, span: Tuple[int, int], size: int = WINDOW) -> str:
    start, end = max(0, span[0] - size), min(len(text), span[1] + size)
    if start > 0:
        space = text.find(" ", start, span[0])
        start = space + 1 if space >= 0 else start
    if end < len(text):
        space = text.rfind(" ", span[1], end)
        end = space if space > 0 else end
    return ("..." if start > 0 else "") + text[start:end].strip() + ("..." if end < len(text) else "")


def evidence_passages(
    question: str,
    entity_results: List[Dict],
    graph_context: Dict,
    case_id: str,
    *,
    session_factory: Callable[[], Any],
    collection,
    limit: int = MAX_PASSAGES,
    stats: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Passages behind the connections and entities in the context, in the order of ``candidate_items``.

    Each passage has the chunk-result shape (``id``, ``text``, ``metadata``) plus ``about`` (the connection or entity
    it is the source of), ``quote`` and ``cite``.
    """
    from services.case_citations import chunk_cite

    stats = stats if stats is not None else {}
    items = candidate_items(question, entity_results, graph_context)
    stats.update(candidates=len(items), passages=0, locations=0, unresolved_locations=0)
    if not items or not case_id or collection is None:
        return []
    with session_factory() as session:
        read_provenance(session, case_id, items)
    wanted = [chunk_id(loc) for item in items for loc in item.get("locations", [])[:MAX_LOCATIONS_PER_ITEM * 3]]
    chunks = read_chunks(collection, case_id, wanted)
    passages: List[Dict[str, Any]] = []
    seen: set = set()
    per_chunk: Dict[str, int] = {}
    for item in items:
        used = 0
        for loc in item.get("locations", []):
            if used >= MAX_LOCATIONS_PER_ITEM or len(passages) >= limit:
                break
            stats["locations"] += 1
            cid = chunk_id(loc)
            stored = chunks.get(cid) if cid else None
            quote = str(loc.get("quote") or "").strip()
            span = _find(stored[0], quote, loc) if stored else None
            if not span:
                stats["unresolved_locations"] += 1
                continue
            text, meta = stored
            dedupe = (cid, span[0] // 200)
            if dedupe in seen or per_chunk.get(cid, 0) >= MAX_PER_CHUNK:
                stats["same_chunk_skipped"] = stats.get("same_chunk_skipped", 0) + 1
                used += 1
                continue
            seen.add(dedupe)
            per_chunk[cid] = per_chunk.get(cid, 0) + 1
            page = loc.get("page_start")
            meta = dict(meta)
            if isinstance(page, int) and page >= 1:
                meta["page_start"] = page
                meta["page_end"] = loc.get("page_end") if isinstance(loc.get("page_end"), int) else page
            meta.setdefault("filename", meta.get("doc_name") or meta.get("file_name") or loc.get("source_file"))
            if item["kind"] == "relationship":
                about = "%s -[%s]-> %s" % (item["source_name"], item["type"], item["target_name"])
            else:
                about = str(item["name"])
            passages.append({
                "id": "%s@%d" % (cid, span[0]), "text": window(text, span), "metadata": meta,
                "distance": None, "quote": text[span[0]:span[1]], "about": about,
                "about_kind": item["kind"], "named": item["named"], "cite": chunk_cite(meta),
                "about_keys": [item["a"], item["b"]] if item["kind"] == "relationship" else [item["key"]],
                "_graph_evidence": True,
            })
            used += 1
        if len(passages) >= limit:
            break
    stats["passages"] = len(passages)
    return passages
