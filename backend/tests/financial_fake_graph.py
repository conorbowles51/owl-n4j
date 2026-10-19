"""An in-memory stand-in for the Neo4j session, for the ledger graph follow-up.

It understands exactly the statements ``services.financial.projection`` and
``services.financial.graph_followup`` emit -- recognised by shape, not parsed --
and keeps transactions honest: writes are buffered and only become visible on
commit, so a rollback or a failure mid-plan leaves the graph as it was.
Anything it does not recognise raises, so a new statement cannot pass silently.
"""
from __future__ import annotations

import copy
import re
from contextlib import contextmanager

from neo4j import Query

from services.financial import graph_followup, projection

_NODE_MERGE = re.compile(r"^UNWIND \$rows AS row\nMERGE \(n:(\w+) \{case_id: \$case_id, key: row\.key\}\)")
_EDGE_MERGE = re.compile(r"^UNWIND \$rows AS row\nMATCH \(a:(\w+) .*\nMATCH \(b:(\w+) .*\nMERGE \(a\)-\[r:(\w+) ", re.S)
_EDGE_RETRACT = re.compile(r"^MATCH \(\)-\[r:(\w+)\]->\(\)\nWHERE r\.projected_from_ledger")
_NODE_RETRACT = re.compile(r"^MATCH \(n:(\w+) \{case_id: \$case_id\}\)\nWHERE n\.projected_from_ledger")


class _Result:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def consume(self):
        return None

    def single(self):
        return self._rows[0] if self._rows else None

    def data(self):
        return list(self._rows)


class FakeGraph:
    """Shared state; ``session()`` hands out sessions over it."""

    def __init__(self):
        self.nodes = {}       # (label, case_id, key) -> props
        self.edges = {}       # edge_key -> dict(type, start, end, props)
        self.markers = {}     # case_id -> props
        self.schema = set()
        self.writes = 0
        self.fail_on_statement = None   # predicate(cypher) -> bool
        self.unavailable = False
        self.on_statement = None        # callback(cypher) for tests
        self.amount_nodes = (0, 0)      # (total, tagged) for the preflight

    @contextmanager
    def session(self):
        if self.unavailable:
            raise ConnectionError("graph unavailable (test)")
        yield FakeSession(self)

    def count(self, label, case_id=None):
        return sum(1 for (l, c, _) in self.nodes if l == label and (case_id is None or c == str(case_id)))

    def edge_count(self, rel_type=None):
        return sum(1 for e in self.edges.values() if rel_type is None or e["type"] == rel_type)


class _State:
    def __init__(self, graph):
        self.nodes = copy.deepcopy(graph.nodes)
        self.edges = copy.deepcopy(graph.edges)
        self.markers = copy.deepcopy(graph.markers)


def _execute(graph: FakeGraph, state, cypher, params):
    if isinstance(cypher, Query):
        cypher = cypher.text
    if graph.on_statement is not None:
        graph.on_statement(cypher)
    if graph.fail_on_statement is not None and graph.fail_on_statement(cypher):
        raise RuntimeError("graph write failed (test)")
    case = params.get("case_id")
    if cypher.startswith("CREATE CONSTRAINT") or cypher.startswith("CREATE INDEX"):
        graph.schema.add(cypher.split(" ")[2])
        return _Result()
    if cypher.startswith("SHOW INDEXES"):
        return _Result([dict(name=n) for n in sorted(graph.schema)])
    if cypher == projection.PREFLIGHT_CYPHER:
        total, tagged = graph.amount_nodes
        return _Result([dict(total_amount_nodes=total, tagged_amount_nodes=tagged)])
    if cypher == graph_followup._LOCK_MARKER:
        marker = state.markers.setdefault(case, {})
        marker["system_node"] = True
        marker["projection_lock"] = marker.get("projection_lock", 0) + 1
        return _Result([dict(digest=marker.get("digest"), ledger_fingerprint=marker.get("ledger_fingerprint"),
                             status=marker.get("status"))])
    if cypher == graph_followup._COMPLETE_MARKER:
        marker = state.markers[case]
        for key in ("last_error", "failed_attempts", "last_failed_at", "next_attempt_at"):
            marker.pop(key, None)
        marker.update(status="current", digest=params["digest"], ledger_fingerprint=params["fingerprint"],
                      transaction_count=params["transaction_count"], node_count=params["node_count"],
                      edge_count=params["edge_count"], refusal_count=params["refusal_count"],
                      completed_at="2026-10-02T00:00:00Z")
        graph.writes += 1
        return _Result()
    if cypher == graph_followup._RECORD_FAILURE:
        marker = state.markers.setdefault(case, {})
        marker.update(status="retrying", last_error=params["error"], failed_attempts=params["attempts"],
                      next_attempt_at="later")
        graph.writes += 1
        return _Result()
    if cypher == graph_followup._READ_MARKER:
        marker = state.markers.get(case)
        if marker is None:
            return _Result()
        return _Result([dict(status=marker.get("status"), digest=marker.get("digest"),
                             ledger_fingerprint=marker.get("ledger_fingerprint"),
                             transaction_count=marker.get("transaction_count"),
                             refusal_count=marker.get("refusal_count"), completed_at=marker.get("completed_at"),
                             last_error=marker.get("last_error"), failed_attempts=marker.get("failed_attempts"),
                             next_attempt_at=marker.get("next_attempt_at"))])
    if cypher == graph_followup._ALL_MARKERS:
        return _Result([dict(case_id=c, ledger_fingerprint=m.get("ledger_fingerprint"))
                        for c, m in sorted(state.markers.items())])
    match = _NODE_MERGE.match(cypher)
    if match:
        for row in params["rows"]:
            props = state.nodes.setdefault((match.group(1), case, row["key"]), {})
            props.update(row["props"])
        graph.writes += 1
        return _Result()
    match = _EDGE_MERGE.match(cypher)
    if match:
        start_label, end_label, rel_type = match.groups()
        for row in params["rows"]:
            start, end = (start_label, case, row["start_key"]), (end_label, case, row["end_key"])
            if start not in state.nodes or end not in state.nodes:
                continue  # MATCH found nothing: no edge, exactly as Neo4j would
            edge = state.edges.setdefault(row["edge_key"], dict(type=rel_type, start=start, end=end, props={}))
            edge["props"].update(row["props"])
        graph.writes += 1
        return _Result()
    match = _EDGE_RETRACT.match(cypher)
    if match:
        for key, edge in list(state.edges.items()):
            p = edge["props"]
            if (edge["type"] == match.group(1) and p.get("projected_from_ledger") and p.get("case_id") == case
                    and p.get("projection_digest") != params["digest"]):
                del state.edges[key]
        return _Result()
    match = _NODE_RETRACT.match(cypher)
    if match:
        for node_id, props in list(state.nodes.items()):
            if (node_id[0] == match.group(1) and node_id[1] == case and props.get("projected_from_ledger")
                    and props.get("projection_digest") != params["digest"]):
                del state.nodes[node_id]
                for key, edge in list(state.edges.items()):
                    if node_id in (edge["start"], edge["end"]):
                        del state.edges[key]
        return _Result()
    raise AssertionError("FakeGraph does not recognise this statement:\n" + cypher)


class FakeTransaction:
    def __init__(self, graph):
        self.graph = graph
        self.state = _State(graph)
        self.closed = False

    def run(self, cypher, parameters=None, **kwargs):
        return _execute(self.graph, self.state, cypher, {**(parameters or {}), **kwargs})

    def commit(self):
        self.graph.nodes, self.graph.edges, self.graph.markers = self.state.nodes, self.state.edges, self.state.markers
        self.closed = True

    def rollback(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False


class FakeSession:
    def __init__(self, graph):
        self.graph = graph

    def run(self, cypher, parameters=None, **kwargs):
        # Auto-commit: apply against a private copy and publish it.
        state = _State(self.graph)
        result = _execute(self.graph, state, cypher, {**(parameters or {}), **kwargs})
        self.graph.nodes, self.graph.edges, self.graph.markers = state.nodes, state.edges, state.markers
        return result

    def begin_transaction(self, timeout=None):
        return FakeTransaction(self.graph)
