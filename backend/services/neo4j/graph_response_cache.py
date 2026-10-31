"""Serve a graph-read response again, as its compressed bytes, while the graph database has committed nothing.

The Graph and Timeline pages of a large case read the whole case from the graph database on every visit
(BNB2, 31 Oct: the Timeline 16 pages and 25.8 s, the graph 10-12 s), although the graph rarely changes.
``cached_json`` keeps the final response body of one read for one set of parameters, gzip-compressed, and
serves those bytes again for as long as the database bookmark (its last committed transaction, see
graph_read_cache) is the one the body was read at. Any committed write anywhere in the graph database
advances the bookmark, so a body is never served for a state other than the one it was read from.

The caller does the access check before asking, on every request, and puts into ``key`` everything the
body depends on besides the graph: the case, the route's parameters, and anything read from PostgreSQL
(the significant-entity keys of the significant scope). Same-key reads in one process share one database
read (graph_read_cache's single flight). Each backend process keeps its own copies in memory, and every copy is
also saved on disk for the other processes and the next start.

The body is FastAPI's own encoding of the result (view_cache.json_response), so a response served from
here is byte-for-byte the one the route returned before, once decompressed.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from typing import Callable, Hashable

from fastapi.responses import Response

from services.neo4j.driver import driver
from services.neo4j.graph_read_cache import GraphReadCache, graph_database_marker

# BNB2's graph is 2.7 MB compressed and its Timeline 3.8 MB over 16 pages (measured 31 Oct).
# Saved on disk too (graph_read_cache ``saved_as``), under the code identity, the bookmark and the graph database's
# marker: the other worker and the next start serve a first visit from disk while the graph is the same, and the
# release's prepare (view_warmup) reads each Financial case's Graph and Timeline pages before the restart. Before,
# the first visit after a restart read the graph again: d5b330d1 /api/timeline 5.5 s and /api/graph 4.5 s server
# time (live 46cbf7f9, 31 Oct 18:24-18:25).
graph_responses = GraphReadCache(max_bytes=128 * 1024 * 1024, saved_as="graph-responses", marker=graph_database_marker)


def keys_digest(keys) -> str | None:
    """A short stand-in for a key list in a cache key (None stays None: no scope)."""
    if keys is None:
        return None
    return hashlib.sha256(json.dumps(list(keys), ensure_ascii=False).encode("utf-8")).hexdigest()


def _encode(result) -> bytes:
    from services.financial.view_cache import json_response
    try:
        body = json_response(result).body
    except ValueError as exc:
        # A value JSON cannot hold (NaN, infinity). FastAPI raised this after the route returned, a 500;
        # inside the route a ValueError would be answered as a 400, so it is not passed on as one.
        raise RuntimeError(f"The response could not be encoded as JSON: {exc}") from exc
    return gzip.compress(body, compresslevel=1)


def cached_json(key: Hashable, compute: Callable[[], object], accept_encoding: str | None) -> Response:
    """The JSON response for ``compute()``, from the saved bytes while the graph is unchanged."""
    with driver.session() as session:
        body = graph_responses.read(session, key, lambda: _encode(compute()))
    if "gzip" in (accept_encoding or ""):
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"},
        )
    return Response(content=gzip.decompress(body), media_type="application/json")


def warm(key: Hashable, compute: Callable[[], object]) -> int:
    """Read ``key`` into the saved copies as ``cached_json`` would (served from them when already there); returns
    the compressed size. For the release's prepare and the after-start warm-up (view_warmup)."""
    with driver.session() as session:
        return len(graph_responses.read(session, key, lambda: _encode(compute())))
