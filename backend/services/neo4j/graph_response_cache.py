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
read (graph_read_cache's single flight). Each backend process keeps its own copies, in memory only.

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
from services.neo4j.graph_read_cache import GraphReadCache

# BNB2's graph is 2.7 MB compressed and its Timeline 3.8 MB over 16 pages (measured 31 Oct).
graph_responses = GraphReadCache(max_bytes=128 * 1024 * 1024)


def keys_digest(keys) -> str | None:
    """A short stand-in for a key list in a cache key (None stays None: no scope)."""
    if keys is None:
        return None
    return hashlib.sha256(json.dumps(list(keys), ensure_ascii=False).encode("utf-8")).hexdigest()


def _encode(result) -> bytes:
    from services.financial.view_cache import json_response
    return gzip.compress(json_response(result).body, compresslevel=1)


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
