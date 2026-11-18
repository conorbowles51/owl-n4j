"""lx-searchfix A and D: the agent's graph search goes through the case search and finds people by the names phones
save for them, by initials and by surname.

Measured on origin eae8b3cc (17 Nov, relevance gate): "Dee" and "D.O." missed Desmond Okafor (phones save him as
"Dee" and "D.O."), "Ruiz family" returned nothing. Every test here fails on that code: the tool called the graph's
name lookup with the words as typed.
"""
from __future__ import annotations

import contextlib
import importlib

import pytest

from services.case_search import net
from services.case_search import understand as U


def test_initials_are_read_as_a_name_and_match_a_persons_initials():
    assert "D.O." in U.names("Who is D.O.?")
    assert U.initials("D.O.") == "do" and U.initials("Dee") == ""
    assert U.name_initials("Desmond Okafor") == "do"


class _Conn:
    """The phone views: on one phone the identity is saved as "Dee", on another as "Desmond Okafor"."""

    def begin_nested(self):
        return contextlib.nullcontext()

    def execute(self, clause, params):
        sql = str(clause)

        class R(list):
            def fetchall(self):
                return list(self)

        class Row:
            def __init__(self, **kw):
                self.__dict__.update(kw)
        if "JOIN pv_identity j" in sql:
            return R([Row(name="Desmond Okafor", value_display="+1 410-555-0141", display_name=None),
                      Row(name="Dee", value_display="+1 410-555-0141", display_name=None)])
        if "pv_identity_name" in sql:
            return R([Row(name="Dee", value_display="+1 410-555-0141", kind="phone", linked=False)])
        return R([])


def test_a_saved_nickname_expands_to_the_other_names_the_phones_save_for_the_same_identity():
    ex = U.expansions(_Conn(), "c", "Who is Dee?")
    names = [e for e in ex if e["kind"] == "contact_name"]
    assert [e["term"] for e in names] == ["Desmond Okafor"]
    assert "suggested, not confirmed by a person" in names[0]["basis"]


class _Graph:
    PEOPLE = [{"key": "p1", "name": "Desmond Okafor"}, {"key": "p2", "name": "Mateo Ruiz"},
              {"key": "p3", "name": "Lucía Ruiz"}, {"key": "p4", "name": "Carla Ruiz"}, {"key": "p5", "name": "Paul Halloran"},
              {"key": "p6", "name": "Priya Halloran"}]
    OTHER = [{"key": "7ae67dee63ee", "name": "card sale m ruiz", "type": "Transaction"},
             {"key": "c1", "name": "Ruiz Auto & Tire", "type": "Company"}]

    def person_names(self, case_id):
        return list(self.PEOPLE)

    def search_nodes(self, p, limit=20, case_id=None):
        low = p.lower()
        out = [dict(n, type="Person") for n in self.PEOPLE if low in n["name"].lower()]
        out += [n for n in self.OTHER if low in n["name"].lower() or low in n["key"]]
        return out[:limit]


@pytest.fixture
def graph(monkeypatch):
    G = importlib.import_module("services.neo4j.graph_service")
    monkeypatch.setattr(G, "graph_service", _Graph())
    from services import vector_db_service as V

    class Vec:
        def search_entities(self, *a, **k):
            return []
    monkeypatch.setattr(V, "get_vector_db_service", lambda: Vec())


def _found(query, expansions=(), only_graph=True):
    words, _, _ = net._graph("c", query, U.names(query), [], embed_query=lambda q: [0.0], expansions=expansions,
                             only_graph=only_graph)
    return words


def test_dee_finds_desmond_okafor_through_the_name_another_phone_saves(graph):
    hits = _found("Dee", [{"name": "Dee", "term": "Desmond Okafor", "kind": "contact_name", "basis": "another name"}])
    assert [h["person"] for h in hits] == ["Desmond Okafor"]
    assert "another name" in hits[0]["found_by"]
    assert all("7ae67dee63ee" != h["key"] for h in hits)  # "dee" inside an id is not the name


def test_initials_find_the_person_with_those_initials(graph):
    hits = _found("D.O.")
    assert [h["person"] for h in hits] == ["Desmond Okafor"] and "initials" in hits[0]["found_by"]


def test_a_family_query_lists_the_people_who_share_the_surname_first_and_says_so(graph):
    hits = _found("Ruiz family")
    people = [h["person"] for h in hits[:3]]
    assert sorted(people) == ["Carla Ruiz", "Lucía Ruiz", "Mateo Ruiz"], people
    assert all(h["found_by"] == "shares the surname Ruiz" for h in hits[:3])


def test_a_full_name_found_is_not_looked_up_by_its_parts_in_the_graph_search(graph):
    assert [h["person"] for h in _found("Priya Halloran")] == ["Priya Halloran"]
    # the case search over every kind still reads the parts, after the full name
    assert [h["person"] for h in _found("Priya Halloran", only_graph=False)] == ["Priya Halloran", "Paul Halloran"]


def test_the_agent_graph_tool_goes_through_the_case_search(monkeypatch):
    from services.agent import tools as T
    from services.case_search import service as CS
    seen = {}

    def ranked(conn, case_id, question, **kw):
        seen["kinds"] = kw.get("kinds")
        return {"candidates": [{"area": "graph", "cite": "entity://p1", "title": "Desmond Okafor (Person)",
                                "sources": ["graph names"], "found_by": "Dee: another name"},
                               {"area": "relationships", "cite": "/cases/c/graph", "title": "Okafor - Kell",
                                "text": "paid"}],
                "notes": [], "searched": ["graph"], "not_searched": [], "meaning_search": True}
    monkeypatch.setattr(CS, "ranked", ranked)
    monkeypatch.setattr(T.graph_service, "nodes_by_keys",
                        lambda keys, case_id: [{"key": "p1", "name": "Desmond Okafor", "type": "Person"}])
    monkeypatch.setattr(T.graph_service, "search_nodes", lambda **k: pytest.fail("the words-as-typed lookup ran"))

    @contextlib.contextmanager
    def session():
        class S:
            def connection(self):
                return None
        yield S()
    ctx = T.AgentToolContext(case_id="00000000-0000-0000-0000-0000000000aa", ledger_session_factory=session)
    tool = {t.name: t for t in T.make_agent_tools(ctx)}["search_graph_entities"]
    data = tool.invoke({"query": "Dee"})["data"]
    assert seen["kinds"] == ("graph",)
    assert data["entities"][0]["name"] == "Desmond Okafor" and data["entities"][0]["found_by"]
    assert data["total"] == 1 and data["connections_found"] == 1


def test_another_entity_sharing_a_word_of_the_name_found_comes_after_the_rest(monkeypatch):
    """Gate 18 Nov, second case: "Dorian Pell" listed Pell Hardware, found by meaning alone, at rank 6 of 25."""
    from services.agent import tools as T
    from services.case_search import service as CS
    meaning = [{"area": "graph", "key": "h1", "title": "PELL HARDWARE", "distance": 0.3, "area_rank": 1,
                "cite": "entity://h1", "sources": ["graph meaning"]},
               {"area": "graph", "key": "a1", "title": "Birchwood Terrace", "distance": 0.4, "area_rank": 2,
                "cite": "entity://a1", "sources": ["graph meaning"]}]
    net._tag_other_names(meaning, {"p1": {}}, {"Dorian Pell"})
    assert meaning[0]["other_name"] == "holds Pell of the name Dorian Pell, not the name"
    assert "other_name" not in meaning[1]

    def ranked(conn, case_id, question, **kw):
        return {"candidates": [dict(meaning[0]), {"area": "graph", "cite": "entity://p1", "title": "Dorian Pell"},
                               dict(meaning[1])],
                "notes": [], "searched": ["graph"], "not_searched": [], "meaning_search": True}
    monkeypatch.setattr(CS, "ranked", ranked)
    monkeypatch.setattr(T.graph_service, "nodes_by_keys",
                        lambda keys, case_id: [{"key": k, "name": k} for k in keys])

    @contextlib.contextmanager
    def session():
        class S:
            def connection(self):
                return None
        yield S()
    ctx = T.AgentToolContext(case_id="00000000-0000-0000-0000-0000000000aa", ledger_session_factory=session)
    tool = {t.name: t for t in T.make_agent_tools(ctx)}["search_graph_entities"]
    ents = tool.invoke({"query": "Dorian Pell"})["data"]["entities"]
    assert [e["key"] for e in ents] == ["p1", "a1", "h1"]
    assert ents[-1]["other_name"].startswith("holds Pell")
