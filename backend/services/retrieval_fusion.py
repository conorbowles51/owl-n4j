"""One ranked list of passages from every search an answer runs (lx-retrieval D).

Chat and agent answers search four ways: passages by meaning (chunk vectors), passages by the question's words (the
word fallback and phone message windows), the passages behind graph connections, and entities by meaning. Each has
its own score: a vector distance, a count of words matched, a place in the graph, and no common scale. The answer
used to sort them all by raw distance, so a phone window's invented distance competed with a vector's real one and
graph passages, having none, came last.

Reciprocal rank fusion (Cormack, Clarke and Buettcher, SIGIR 2009) needs only each list's order: a passage scores
``sum(1 / (K + rank))`` over the lists it appears in. The entity search orders the graph passages (the passages
behind its entities' connections), which count as one list.
Passages the person chose (selected documents, selected phone records) stay first, as before.

Distances: the chunk and entity collections the backend made first use Chroma's default space, squared L2 (measured
on live 15 Nov 2026: ``hnsw.space = l2`` for both). The evidence engine asks for cosine when it makes a collection,
but ``get_or_create`` keeps the existing space. Embeddings are unit vectors, so squared L2 = 2 - 2 cos.
``similarity`` turns a distance into cosine similarity in either space; the threshold is applied to that.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

K = 60  # the RRF constant of the paper; it damps the weight of the very first ranks


def collection_space(collection: Any) -> str:
    """The distance space of a Chroma collection: ``l2`` (Chroma's default), ``cosine`` or ``ip``."""
    for source in ("configuration_json", "_configuration_json"):
        conf = getattr(collection, source, None)
        if isinstance(conf, dict):
            space = (conf.get("hnsw") or {}).get("space") or (conf.get("hnsw_configuration") or {}).get("space")
            if space:
                return str(space)
    meta = getattr(collection, "metadata", None) or {}
    return str(meta.get("hnsw:space") or "l2")


def similarity(distance: Optional[float], space: str = "l2") -> Optional[float]:
    """Cosine similarity of unit vectors from a Chroma distance in ``space``."""
    if distance is None:
        return None
    if space == "cosine":
        return 1.0 - float(distance)
    if space == "ip":
        return 1.0 - float(distance)  # Chroma's ip distance is 1 - dot product
    return 1.0 - float(distance) / 2.0  # squared L2: 2 - 2 cos


def min_similarity(threshold: float) -> float:
    """The saved threshold is a maximum squared-L2 distance (the live space, typical 0.0-4.0; 2.0 = cos 0)."""
    return 1.0 - float(threshold) / 2.0


def _key(passage: Dict[str, Any]) -> str:
    return str(passage.get("id") or id(passage))


def _is_word(passage: Dict[str, Any]) -> bool:
    return bool(passage.get("_word_match")) or str(passage.get("id") or "").startswith("phone:")


def _pinned(passage: Dict[str, Any]) -> bool:
    return bool(passage.get("_doc_scoped")) or str(passage.get("id") or "").startswith("phone-selected:")


def fuse(
    chunk_results: List[Dict[str, Any]],
    graph_evidence: List[Dict[str, Any]],
    entity_results: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """(pinned passages, fused passages best first, stats). A graph passage from a chunk already found by meaning or
    words is folded into that chunk (its "source of" lines are kept, it adds no score), so one text is never sent
    twice."""
    pinned = [c for c in chunk_results if _pinned(c)]
    pinned.sort(key=lambda c: (not str(c.get("id") or "").startswith("phone-selected:"),
                               c.get("distance") if c.get("distance") is not None else float("inf")))
    rest = [c for c in chunk_results if not _pinned(c)]
    vector = sorted([c for c in rest if not _is_word(c) and c.get("distance") is not None],
                    key=lambda c: c["distance"])
    unscored = [c for c in rest if not _is_word(c) and c.get("distance") is None]
    words = [c for c in rest if _is_word(c)]
    words.sort(key=lambda c: c.get("distance") if c.get("distance") is not None else 0.0)  # stable for word hits

    by_chunk: Dict[str, Dict[str, Any]] = {}
    for c in pinned + rest:
        by_chunk.setdefault(_key(c), c)
    scores: Dict[str, float] = {}
    items: Dict[str, Dict[str, Any]] = {}

    def credit(passage: Dict[str, Any], rank: int) -> None:
        key = _key(passage)
        items.setdefault(key, passage)
        scores[key] = scores.get(key, 0.0) + 1.0 / (K + rank)

    for rank, c in enumerate(vector, 1):
        credit(c, rank)
    for rank, c in enumerate(words, 1):
        credit(c, rank)
    for rank, c in enumerate(unscored, 1):
        credit(c, rank + len(vector))

    entity_rank = {e.get("key"): i for i, e in enumerate(entity_results, 1) if e.get("key")}
    # A graph passage is ranked by the graph's order and by the entity search's order. One whose chunk the searches
    # also found carries that chunk's key: select() then names the connection on the chunk instead of sending the
    # text twice, and it adds no score to the chunk, so a chunk behind many connections never pushes out a closer
    # one (measured on the demo case: with that credit, the 12 April tow invoice fell out of "Where was Mateo Ruiz
    # on the nights of 12 April and 3 May 2024?").
    own = []
    for passage in graph_evidence:
        chunk_key = str(passage.get("id") or "").split("@", 1)[0]
        passage = dict(passage)
        if chunk_key in by_chunk:
            passage["_folds_into"] = chunk_key
        own.append(passage)
    # The graph's order already follows the entity search (services/graph_evidence.candidate_items: connections
    # between named entities, then by the entities' search ranks), so graph passages count as one list. Counted as
    # two (graph and entity), every graph passage outranked the best searched passage: on the demo case's "Which of
    # Travis Kell's proffer statements are contradicted?" the proffer itself fell to 12th and three live answers in
    # three stopped citing it.
    for rank, passage in enumerate(own, 1):
        credit(passage, rank)

    pinned_keys = {_key(c) for c in pinned}
    fused = [items[k] for k in sorted(scores, key=lambda k: -scores[k]) if k not in pinned_keys]
    for c in fused:
        c["_rrf"] = round(scores[_key(c)], 6)
    stats = {"method": "rrf", "k": K, "vector": len(vector), "words": len(words), "graph_evidence": len(graph_evidence),
             "entities": len(entity_rank), "pinned": len(pinned)}
    return pinned, fused, stats


def select(pinned: List[Dict[str, Any]], fused: List[Dict[str, Any]], top_searched: int,
           stats: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Pinned passages, then the fused order with at most ``top_searched`` searched passages. A graph passage takes
    no searched passage's place; when its chunk is kept it is named on that chunk ("source of") instead."""
    kept_searched = set()
    for c in fused:
        if not c.get("_graph_evidence") and len(kept_searched) < top_searched:
            kept_searched.add(_key(c))
    kept = {_key(c): c for c in pinned}
    kept.update({_key(c): c for c in fused if _key(c) in kept_searched})
    out = list(pinned)
    folded = 0
    for c in fused:
        if not c.get("_graph_evidence"):
            if _key(c) in kept_searched:
                out.append(c)
            continue
        target = kept.get(c.get("_folds_into") or "")
        if target is not None:
            about = target.setdefault("_about", [])
            if c.get("about") not in about:
                about.append(c.get("about"))
            folded += 1
        else:
            out.append(c)
    if stats is not None:
        stats["graph_evidence_folded"] = folded
    return out
