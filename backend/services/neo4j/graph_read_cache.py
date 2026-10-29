"""Reuse a graph read while the graph database has committed nothing since.

The key of every saved result is the database bookmark: the identifier of the
last committed transaction, which the server returns with every read. Any
committed write anywhere in the database, from any process, advances it (a
read, a rolled-back write or a write that changes nothing does not), so a saved
result is only ever served for exactly the database state it was read from.
A result is saved only when the bookmark is the same before and after the
read, i.e. nothing committed while it was being read.

Measured on neo4j 5.26: the bookmark of a read taken after any write was
acknowledged to its client is never older than that write, also while another
large write is being committed (141 checks during 1.6-4.6 s commits, 0 older).

Results are kept compressed and handed out as fresh copies, so a caller may
change what it receives. A call that finds the same read already running, from
the same bookmark, waits for it and takes a copy of its result, so a burst of
identical page loads costs one database read. A call whose bookmark differs
(something committed since that read started) reads for itself.
"""

import logging
import pickle
import threading
import zlib
from collections import OrderedDict
from typing import Callable, Dict, Hashable, Optional, Tuple

import orjson

logger = logging.getLogger(__name__)

Bookmark = Tuple[str, ...]


def graph_bookmark(session) -> Bookmark:
    """The database's last committed transaction, as seen by this session now."""
    session.run("RETURN 1").consume()
    return tuple(sorted(session.last_bookmarks().raw_values))


class _Flight:
    def __init__(self, bookmark: Bookmark):
        self.bookmark = bookmark
        self.done = threading.Event()
        self.blob: Optional[bytes] = None


_JSON_SCALARS = (str, int, float, bool, type(None))


def _json_native(value) -> bool:
    """True when JSON keeps every value exactly: only dicts with str keys, lists,
    str, int, finite float, bool and None (a tuple or a driver type would change)."""
    stack = [value]
    while stack:
        item = stack.pop()
        kind = type(item)
        if kind is dict:
            for key, inner in item.items():
                if type(key) is not str:
                    return False
                stack.append(inner)
        elif kind is list:
            stack.extend(item)
        elif kind is float:
            if item != item or item in (float("inf"), float("-inf")):
                return False
        elif kind not in _JSON_SCALARS:
            return False
    return True


def _pack(value) -> bytes:
    # orjson reads and writes a large row list several times faster than pickle
    # (d5b330d1 transactions: pickle 8 s to save, about 2 s to read back), and
    # keeps int, float and str exactly; anything else is pickled.
    if _json_native(value):
        return b"J" + zlib.compress(orjson.dumps(value), 1)
    return b"P" + zlib.compress(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL), 1)


def _unpack(blob: bytes):
    data = zlib.decompress(blob[1:])
    return orjson.loads(data) if blob[:1] == b"J" else pickle.loads(data)


class GraphReadCache:
    def __init__(self, max_bytes: int = 64 * 1024 * 1024):
        self.max_bytes = max_bytes
        self._entries: "OrderedDict[Hashable, Tuple[Bookmark, bytes]]" = OrderedDict()
        self._flights: Dict[Hashable, _Flight] = {}
        self._bytes = 0
        self._lock = threading.Lock()
        self.stats = {"hit": 0, "joined": 0, "miss": 0, "saved": 0, "changed_during_read": 0, "too_large": 0}

    def _count(self, name: str) -> None:
        with self._lock:
            self.stats[name] += 1

    def _get(self, key: Hashable, bookmark: Bookmark) -> Optional[bytes]:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry[0] != bookmark:
                return None
            self._entries.move_to_end(key)
            return entry[1]

    def _put(self, key: Hashable, bookmark: Bookmark, blob: bytes) -> None:
        with self._lock:
            if len(blob) > self.max_bytes:
                self.stats["too_large"] += 1
                return
            old = self._entries.pop(key, None)
            if old is not None:
                self._bytes -= len(old[1])
            self._entries[key] = (bookmark, blob)
            self._bytes += len(blob)
            while self._bytes > self.max_bytes:
                _, (_, dropped) = self._entries.popitem(last=False)
                self._bytes -= len(dropped)
            self.stats["saved"] += 1

    def read(self, session, key: Hashable, compute: Callable[[], object]):
        """Return compute()'s result for the database's current state.

        compute must read only from the graph database through `session`;
        anything read from elsewhere must be added by the caller afterwards.
        """
        before = graph_bookmark(session)
        blob = self._get(key, before)
        if blob is not None:
            self._count("hit")
            return _unpack(blob)
        with self._lock:
            flight = self._flights.get(key)
            joined = flight is not None and flight.bookmark == before
            if not joined:
                flight = _Flight(before)
                self._flights[key] = flight
        if joined:
            flight.done.wait()
            if flight.blob is not None:
                self._count("joined")
                return _unpack(flight.blob)
            # The read it waited for failed; read for itself.
            self._count("miss")
            return compute()
        self._count("miss")
        try:
            value = compute()
            try:
                flight.blob = _pack(value)
                if graph_bookmark(session) == before:
                    self._put(key, before, flight.blob)
                else:
                    self._count("changed_during_read")
            except Exception:
                # The read itself succeeded; only keeping it failed.
                logger.exception("Could not keep a graph read for reuse")
                flight.blob = None
            return value
        finally:
            with self._lock:
                if self._flights.get(key) is flight:
                    del self._flights[key]
            flight.done.set()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._bytes = 0


financial_graph_reads = GraphReadCache()
