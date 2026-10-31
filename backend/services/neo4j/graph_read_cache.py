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
change what it receives. At most one read per key runs at a time in a process.
A call that finds the same read already running, from the same bookmark, waits
for it and takes a copy of its result, or its error when it failed, so a burst
of identical page loads costs one database read (an error is shared only when
the server ended the read at its time limit). A call whose bookmark differs
(something committed since that read started) waits for it to end and then
looks again, so it is never given a result older than its own bookmark.

Measured live (d5b330d1, 2026-10-30): when a read that callers had joined
failed, every one of them read for itself at once; the concurrent reads slowed
each other past the server's time limit, failed and were asked again, so the
case's financial graph answered 503 for hours (33 slow failures in 3 hours,
up to 894 s each) while one read alone takes about 7 s.

A cache made with ``saved_as`` also keeps each JSON result on disk (in the
Financial memo directory, under the code identity of the process that read it),
so the other worker and the next start find it while the bookmark is the same:
the release's warm-up reads it before the restart, and a first visit is served
from disk (d5b330d1 transactions: 7.8 s graph read, measured 2026-10-31). A
saved copy is used only for the exact key, code and bookmark it was read at, and
only after its size and sha256 match; results JSON cannot keep are never saved.
A bookmark is a transaction number: restoring an earlier backup hands the same
numbers out again for other contents. A restore stops and starts the database,
so each saved copy also records the database's id and last start time (``marker``)
and is used only while both are the same; with the marker unreadable nothing is
read from or written to disk.
"""

import hashlib
import json
import logging
import os
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


def _timed_out(exc: BaseException) -> bool:
    # As services.neo4j.driver.is_transaction_timeout, without opening the driver.
    return "TransactionTimedOut" in (getattr(exc, "code", None) or "")


class _Flight:
    def __init__(self, bookmark: Bookmark):
        self.bookmark = bookmark
        self.done = threading.Event()
        self.blob: Optional[bytes] = None
        self.error: Optional[BaseException] = None


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


# Saved graph reads, oldest removed first above this size.
MAX_SAVED_BYTES = 512 * 1024 * 1024
# The graph database's marker is read at most this often per cache (10-26 ms each, measured 2026-10-31); a change
# (a restart, as a restore needs) also empties the memory cache, whose entries are keyed by bookmark alone.
MARKER_SECONDS = 30
# One warning per this many seconds while the marker cannot be read (the graph database down, no password).
MARKER_WARNING_SECONDS = 600


class GraphReadCache:
    def __init__(self, max_bytes: int = 64 * 1024 * 1024, saved_as: Optional[str] = None,
                 marker: Optional[Callable[[], Optional[str]]] = None):
        self.max_bytes = max_bytes
        self.saved_as = saved_as
        self.marker = marker
        self._marker_seen: Optional[str] = None  # the last marker read
        self._marker_now: Optional[str] = None  # the last answer (None when unreadable), reused for MARKER_SECONDS
        self._marker_at = float("-inf")
        self._marker_warned = float("-inf")
        self._entries: "OrderedDict[Hashable, Tuple[Bookmark, bytes]]" = OrderedDict()
        self._flights: Dict[Hashable, _Flight] = {}
        self._bytes = 0
        self._lock = threading.Lock()
        self.stats = {"hit": 0, "joined": 0, "miss": 0, "saved": 0, "changed_during_read": 0, "too_large": 0,
                      "joined_failure": 0, "saved_hit": 0, "written": 0}

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

    def _saved_dir(self):
        """Where this cache's results outlive the process, with the code they were read by; (None, None) if not."""
        if self.saved_as is None or self.marker is None:
            return None, None
        from services.financial import view_cache
        directory, code = view_cache._memo_dir(), view_cache.code_identity()
        if directory is None or code is None:
            return None, None
        return directory / self.saved_as, code

    def _current_marker(self) -> Optional[str]:
        """The graph database's marker (id and last start), read at most every MARKER_SECONDS; None if there is no
        marker or it cannot be read. When it changed, the memory cache is emptied first. Never raises."""
        import time
        if self.marker is None:
            return None
        now = time.monotonic()
        with self._lock:
            if now - self._marker_at < MARKER_SECONDS:
                return self._marker_now
        try:
            marker = self.marker() or None
        except Exception:  # noqa: BLE001 - then nothing is read from or written to disk
            if now - self._marker_warned >= MARKER_WARNING_SECONDS:
                self._marker_warned = now
                logger.warning("Graph database marker unreadable; graph reads kept in memory only", exc_info=True)
            marker = None
        with self._lock:
            if marker is not None and self._marker_seen is not None and marker != self._marker_seen:
                logger.warning("The graph database was restarted (%s -> %s); graph reads kept so far dropped",
                               self._marker_seen, marker)
                self._entries.clear()
                self._bytes = 0
            if marker is not None:
                self._marker_seen = marker
            self._marker_now, self._marker_at = marker, now
            return marker

    @staticmethod
    def _saved_name(key, code) -> str:
        return hashlib.sha256(json.dumps([key, code], default=str, sort_keys=True).encode()).hexdigest() + ".graph"

    def _load_saved(self, key: Hashable, bookmark: Bookmark, marker: Optional[str]) -> Optional[bytes]:
        """The saved result of this key read by this code at exactly this bookmark and marker. Never raises."""
        directory, code = self._saved_dir()
        if directory is None or marker is None:
            return None
        try:
            with open(directory / self._saved_name(key, code), "rb") as saved:
                header = json.loads(saved.readline())
                # The header first: after a graph commit the old copy is not read whole to be refused.
                if (header.get("key") != json.loads(json.dumps(key, default=str)) or header.get("code") != code
                        or header.get("marker") != marker or header.get("bookmark") != list(bookmark)):
                    return None
                blob = saved.read()
            if (header.get("size") != len(blob) or header.get("sha256") != hashlib.sha256(blob).hexdigest()
                    or blob[:1] != b"J"):
                return None
            return blob
        except FileNotFoundError:
            return None
        except Exception:  # noqa: BLE001 - an unreadable copy is read again from the graph
            logger.warning("Saved graph read unreadable; reading it again", exc_info=True)
            return None

    def _save(self, key: Hashable, bookmark: Bookmark, blob: bytes, marker: Optional[str]) -> None:
        """Keep a JSON result on disk for the other workers and the next start, under the marker taken before it
        was read. Never raises."""
        directory, code = self._saved_dir()
        if directory is None or marker is None or blob[:1] != b"J" or len(blob) > MAX_SAVED_BYTES:
            return
        temporary = None
        try:
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = directory / self._saved_name(key, code)
            header = dict(key=json.loads(json.dumps(key, default=str)), code=code, marker=marker,
                          bookmark=list(bookmark), size=len(blob), sha256=hashlib.sha256(blob).hexdigest())
            temporary = path.with_name("%s.%d.%d.tmp" % (path.name, os.getpid(), threading.get_ident()))
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, "wb") as out:
                out.write(json.dumps(header, sort_keys=True).encode() + b"\n")
                out.write(blob)
            os.replace(temporary, path)
            temporary = None
            self._count("written")
            self._trim_saved(directory, keep=path)
        except Exception:  # noqa: BLE001 - the result stays reused in memory
            logger.warning("Could not save a graph read", exc_info=True)
            if temporary is not None:
                try:
                    temporary.unlink()
                except OSError:
                    pass

    @staticmethod
    def _trim_saved(directory, keep) -> None:
        import time
        files = []
        for entry in os.scandir(directory):
            try:
                info = entry.stat()
            except FileNotFoundError:
                continue
            if entry.name.endswith(".tmp"):
                if time.time() - info.st_mtime > 3600:
                    try:
                        os.unlink(entry.path)
                    except FileNotFoundError:  # another process removed it first
                        pass
                continue
            files.append((info.st_mtime, entry.path, info.st_size))
        total = sum(size for _, _, size in files)
        for _, path, size in sorted(files):
            if total <= MAX_SAVED_BYTES:
                break
            if path != str(keep):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
                total -= size

    def read(self, session, key: Hashable, compute: Callable[[], object]):
        """Return compute()'s result for the database's current state.

        compute must read only from the graph database through `session`;
        anything read from elsewhere must be added by the caller afterwards.
        """
        marker = self._current_marker()  # before the bookmark: a restart since empties the memory cache
        while True:
            before = graph_bookmark(session)
            blob = self._get(key, before)
            if blob is not None:
                self._count("hit")
                return _unpack(blob)
            with self._lock:
                flight = self._flights.get(key)
                if flight is None:
                    flight = _Flight(before)
                    self._flights[key] = flight
                    break
            flight.done.wait()
            if flight.bookmark != before:
                # A read from an older state ended; look again from now.
                continue
            if flight.blob is not None:
                self._count("joined")
                return _unpack(flight.blob)
            if flight.error is not None:
                # The same read from the same state failed; reading it again
                # alongside every other waiter is what made it fail.
                self._count("joined_failure")
                raise flight.error
            # The read could not be kept, or failed in a way of its own; read for itself.
            self._count("miss")
            return compute()
        try:
            saved = self._load_saved(key, before, marker)
            if saved is not None:
                value = _unpack(saved)
                flight.blob = saved
                self._put(key, before, saved)
                self._count("saved_hit")
                return value
            self._count("miss")
            value = compute()
            try:
                flight.blob = _pack(value)
                if graph_bookmark(session) == before:
                    self._put(key, before, flight.blob)
                    self._save(key, before, flight.blob, marker)
                else:
                    self._count("changed_during_read")
            except Exception:
                # The read itself succeeded; only keeping it failed.
                logger.exception("Could not keep a graph read for reuse")
                flight.blob = None
            return value
        except Exception as exc:
            # Only the server's time limit is shared: it is the load of many
            # identical reads. Any other failure (this session's connection, say)
            # leaves each waiter to read for itself.
            if _timed_out(exc):
                flight.error = exc
            raise
        finally:
            with self._lock:
                if self._flights.get(key) is flight:
                    del self._flights[key]
            flight.done.set()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._bytes = 0


def graph_database_marker() -> Optional[str]:
    """The home graph database's id and last start time (changed by any stop and start, which a restore needs).
    Read on a session of its own: an administration command's bookmark must not join a read's."""
    from neo4j import Query
    from services.neo4j.driver import driver
    with driver.session() as session:
        record = session.run(Query("SHOW HOME DATABASE YIELD databaseID, lastStartTime", timeout=5)).single()
    if record is None or not record["databaseID"] or record["lastStartTime"] is None:
        return None
    return "%s@%s" % (record["databaseID"], record["lastStartTime"].iso_format())


financial_graph_reads = GraphReadCache(saved_as="graph-reads", marker=graph_database_marker)
