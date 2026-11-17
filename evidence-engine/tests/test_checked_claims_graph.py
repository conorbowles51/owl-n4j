"""Claims that pass the later check ('Check them') join the graph on the nodes their file already made."""
import json

import pytest

from app.pipeline import write_graph as W
from app.services import checked_claims_graph as G
from app.services import claim_backfill
from app.services import neo4j_client

CASE = "cded78d0-e659-44cc-940d-d8f8c8012760"
FILE = "00000000-0000-0000-0000-0000000000f1"
RUN = claim_backfill.SYSTEM_DESCRIPTION
LOC = {"source_file": "lease.pdf", "page_start": 1}


def _claim(cid, kind, subject, **value):
    return {"id": cid, "evidence_file_id": FILE, "claim_type": kind, "subject_id": subject,
            "predicate": "RENTS" if kind == "relationship" else "verified_fact",
            "object_value": {"verification_run": RUN, **value}, "quote": f"quote {cid}", "source_location": LOC,
            "confidence": 0.9}


PASSED = [
    _claim("fact-new", "entity_fact", "E1", text="Travis Kell rents bay 4", importance=4),
    _claim("fact-dup", "entity_fact", "E1", text="Travis Kell is a mechanic"),
    _claim("link-new", "relationship", "E1", target_entity_id="E2", detail="bay 4"),
    _claim("link-lost", "relationship", "E1", target_entity_id="E9", detail="gone"),
    _claim("fact-lost", "entity_fact", "E7", text="no node"),
    _claim("in-graph", "entity_fact", "E2", text="already there"),
]
SUBJECTS = [("mention-e1", "E1"), ("mention-e2", "E2"), ("mention-e7", "E7")]
OLD_FACTS = json.dumps([{"text": "Travis Kell is a mechanic", "source_doc": "lease.pdf", "page": 1}])
NODES = [
    {"id": "n-kell", "name": "Travis Kell", "labels": ["Person"], "specific_type": "person", "description": "",
     "aliases": [], "verified_facts": OLD_FACTS, "claim_ids": ["mention-e1"]},
    {"id": "n-bay", "name": "Bay 4", "labels": ["Location"], "specific_type": "unit", "description": "",
     "aliases": [], "verified_facts": "[]", "claim_ids": ["mention-e2", "in-graph"]},
]


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _Db:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        sql = str(statement)
        if "status = 'verified'" in sql:
            assert params["run"] == RUN
            return _Rows(PASSED)
        return _Rows([{"id": cid, "f": FILE, "subject_id": subject} for cid, subject in SUBJECTS])


@pytest.fixture
def graph(monkeypatch):
    writes = {"queries": [], "links": None, "embedded": None}

    async def query(cypher, params=None):
        writes["queries"].append((cypher, params))
        if "RETURN n.id AS id, n.name" in cypher:
            return NODES
        if "-[r {case_id" in cypher:
            return [{"claim_ids": []}]
        if "SET n.verified_facts" in cypher:
            return [{"id": row["id"]} for row in params["rows"]]
        raise AssertionError(cypher)

    async def write_graph(entities, relationships, case_id, job_id, **kw):
        writes["links"] = (entities, relationships, case_id)

    async def embed(entities, case_id):
        writes["embedded"] = entities

    monkeypatch.setattr(neo4j_client, "execute_query", query)
    monkeypatch.setattr(W, "write_graph", write_graph)
    monkeypatch.setattr(W, "_embed_entities", embed)
    return writes


@pytest.mark.asyncio
async def test_passed_claims_join_their_nodes_through_the_graph_write(graph):
    outcome = await G.add_passed_claims(lambda: _Db(), CASE, apply=True)
    assert outcome.checked == 6 and outcome.already == 1
    assert outcome.facts_added == 1  # the duplicate text on the same file and page is not added twice
    assert outcome.links_added == 1
    assert dict(outcome.not_placed) == {G.NOT_PLACED_SUBJECT: 1, G.NOT_PLACED_TARGET: 1}

    [(cypher, params)] = [q for q in graph["queries"] if "SET n.verified_facts" in q[0]]
    assert "IngestionCaseWriteLock" in cypher and "n.verified_facts, '') = coalesce(row.previous" in cypher
    [row] = params["rows"]
    assert row["id"] == "n-kell" and row["previous"] == OLD_FACTS
    assert sorted(row["claim_ids"]) == ["fact-dup", "fact-new"]
    facts = json.loads(row["facts"])
    assert [f["text"] for f in facts] == ["Travis Kell is a mechanic", "Travis Kell rents bay 4"]  # old kept first
    assert facts[1]["verification_status"] == "verified" and facts[1]["quote"] == "quote fact-new"
    assert [e.id for e in graph["embedded"]] == ["n-kell"]  # search is updated for the node

    entities, [link], case_id = graph["links"]
    assert entities == [] and case_id == CASE
    assert (link.source_entity_id, link.target_entity_id, link.type) == ("n-kell", "n-bay", "RENTS")
    assert link.source_claim_ids == ["link-new"] and link.source_files == ["lease.pdf"]


@pytest.mark.asyncio
async def test_dry_run_counts_and_writes_nothing(graph):
    outcome = await G.add_passed_claims(lambda: _Db(), CASE, apply=False)
    assert outcome.facts_added == 1 and outcome.links_added == 1
    assert graph["links"] is None and not [q for q in graph["queries"] if "SET " in q[0]]


@pytest.mark.asyncio
async def test_a_node_changed_since_read_is_left_alone_and_counted(graph, monkeypatch):
    async def query(cypher, params=None):
        if "RETURN n.id AS id, n.name" in cypher:
            return NODES
        if "-[r {case_id" in cypher:
            return []
        return []  # the guard matched nothing: the node's facts changed meanwhile
    monkeypatch.setattr(neo4j_client, "execute_query", query)
    outcome = await G.add_passed_claims(lambda: _Db(), CASE, apply=True)
    assert outcome.facts_added == 0 and graph["embedded"] == []
    assert sum(outcome.not_placed.values()) == 4


@pytest.mark.asyncio
async def test_the_check_job_adds_what_passed_to_the_graph(monkeypatch):
    from app import worker
    calls = []

    async def check_case(factory, case_id, *, apply):
        calls.append(("check", case_id))
        return claim_backfill.CaseOutcome(case_id, 0)

    async def add(factory, case_id, *, apply):
        calls.append(("graph", case_id, apply))
        return G.Outcome(case_id)
    monkeypatch.setattr(claim_backfill, "check_case", check_case)
    monkeypatch.setattr(G, "add_passed_claims", add)
    await worker.check_unreviewed_claims({}, CASE)
    assert calls == [("check", CASE), ("graph", CASE, True)]
