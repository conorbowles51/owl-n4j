"""Entity meaning-search vectors follow edits (followups m11040658479405).

Before: PUT /api/graph/node/{key} and batch update changed the graph and never touched the entity's vector, so a
renamed entity was meaning-searched by its old words; the recovery backfill never looked at entity vectors.
"""
from unittest.mock import patch

import pytest

from services import entity_vectors as ev
from services import meaning_search


LOCO = {"name": "LOCO", "description": "Discussed as someone who might be deported.",
        "aliases": ["EL LOCO", "LOCO"],
        "verified_facts": '[{"text": "Participant referenced by name"}, {"text": "Reported as subject to deportation"}]',
        "summary": "## Background\n\nlong markdown that the engine never embeds"}


class FakeVectors:
    def __init__(self, stored=None):
        self.upserts = []
        self.stored = stored or {}
        outer = self

        class Collection:
            def get(self, where=None, include=None, limit=None, offset=0):
                rows = [(k, d, m) for k, (d, m) in outer.stored.items() if m.get("case_id") == where["case_id"]]
                rows = rows[offset:offset + limit]
                return {"ids": [r[0] for r in rows], "documents": [r[1] for r in rows],
                        "metadatas": [r[2] for r in rows]}

        self.entity_collection = Collection()

    def add_entity(self, entity_key, text, embedding, metadata=None):
        self.upserts.append((entity_key, text, dict(metadata or {})))


def test_text_is_the_engines_format_with_notes():
    assert ev.embedding_text("Person", LOCO) == (
        "Person: LOCO — Discussed as someone who might be deported. (aliases: EL LOCO, LOCO) "
        "Facts: Participant referenced by name; Reported as subject to deportation")
    with_notes = dict(LOCO, notes="Seen with the white van")
    assert ev.embedding_text("Person", with_notes).endswith(" Notes: Seen with the white van")


def test_stale_when_name_description_or_notes_is_not_in_the_stored_text():
    doc = ev.embedding_text("Person", LOCO)
    assert not ev.is_stale(doc, LOCO)
    assert not ev.is_stale(doc.upper(), LOCO)  # case only: not a change
    assert ev.is_stale(doc, dict(LOCO, name="Luis Ortega"))
    assert ev.is_stale(doc, dict(LOCO, description="Arrested on 3 March."))
    assert ev.is_stale(doc, dict(LOCO, notes="Seen with the white van"))
    assert not ev.is_stale(doc, dict(LOCO, summary="a different summary"))  # summary is not searched


def test_refresh_embeds_the_current_graph_text_with_case_metadata():
    vectors, calls = FakeVectors(), []
    nodes = {"k1": ("Person", dict(LOCO, name="Luis Ortega", specific_type="Associate")),
             "p1": ("PhoneIdentity", {"name": "Mum"})}
    out = ev.refresh_entities("case-a", ["k1", "p1", "gone"], vector_db=vectors,
                              embed=lambda t: calls.append(t) or [0.1],
                              read_nodes=lambda case_id, keys, **_: nodes)
    assert out == {"requested": 3, "embedded": 1, "skipped": 2, "stopped": None}
    assert calls == [ev.embedding_text("Person", nodes["k1"][1])]  # the phone node is never sent out
    key, text, meta = vectors.upserts[0]
    assert key == "k1" and text.startswith("Person: Luis Ortega — ")
    assert meta == {"category": "Person", "specific_type": "Associate", "name": "Luis Ortega",
                    "case_id": "case-a", "aliases": "EL LOCO,LOCO"}


def test_refresh_stops_at_the_first_refused_call():
    vectors = FakeVectors()

    def refused(_):
        raise RuntimeError("429 insufficient_quota")

    nodes = {"a": ("Person", {"name": "A"}), "b": ("Person", {"name": "B"})}
    out = ev.refresh_entities("c", ["a", "b"], vector_db=vectors, embed=refused,
                              read_nodes=lambda *a, **k: nodes)
    assert out["embedded"] == 0 and "insufficient_quota" in out["stopped"]
    assert vectors.upserts == []


def test_stale_keys_compares_every_vector_of_the_case_with_the_graph():
    current = ev.embedding_text("Person", LOCO)
    vectors = FakeVectors({
        "same": (current, {"case_id": "c", "category": "Person"}),
        "renamed": ("Person: Old Name — Discussed as someone who might be deported.", {"case_id": "c",
                                                                                       "category": "Person"}),
        "other-case": ("Person: Old Name", {"case_id": "x", "category": "Person"}),
        "phone": ("PhoneIdentity: Mum", {"case_id": "c", "category": "PhoneIdentity"}),
    })
    seen = {}

    def read(case_id, keys, labels_by_key=None):
        seen.update(labels_by_key or {})
        return {"same": ("Person", LOCO), "renamed": ("Person", dict(LOCO, name="New Name")),
                "phone": ("PhoneIdentity", {"name": "Mother"})}

    assert ev.stale_keys("c", vector_db=vectors, read_nodes=read) == ["renamed"]
    assert seen == {"same": "Person", "renamed": "Person", "phone": "PhoneIdentity"}  # read through label index


def test_batch_update_refreshes_only_keys_whose_searched_text_changed():
    updates = [{"key": "a", "property": "name", "value": "x"}, {"key": "b", "property": "latitude", "value": 1},
               {"key": "c", "property": "notes", "value": "n"}, {"key": "a", "property": "description", "value": "d"}]
    assert ev.keys_to_refresh(updates) == ["a", "c"]


def test_refresh_after_edit_runs_off_the_request():
    ran = []
    thread = ev.refresh_after_edit("c", ["k"], run=lambda case_id, keys: ran.append((case_id, keys)))
    thread.join(5)
    assert ran == [("c", ["k"])]
    assert ev.refresh_after_edit("c", []) is None and ev.refresh_after_edit(None, ["k"]) is None


def _call_update_node(fields):
    from routers import graph
    req = graph.UpdateNodeRequest(case_id="case-a", name="New Name")
    with patch.object(graph.neo4j_service, "update_graph_node", return_value={"updated_fields": fields,
                                                                              "changes": {}}), \
            patch.object(graph.system_log_service, "log"), \
            patch.object(graph.entity_vectors, "refresh_after_edit") as refresh:
        graph.update_node("node-1", req, user={"username": "tester"})
    return refresh


def test_editing_a_name_refreshes_the_entity_vector():
    refresh = _call_update_node(["name"])
    refresh.assert_called_once_with("case-a", ["node-1"])


def test_editing_a_date_does_not_call_the_embedding_service():
    _call_update_node(["date", "time"]).assert_not_called()


def test_batch_update_route_refreshes_changed_names():
    from routers import graph
    req = graph.BatchUpdateRequest(case_id="case-a", updates=[{"key": "a", "property": "name", "value": "x"}])
    with patch.object(graph.neo4j_service, "batch_update_entities", return_value=1), \
            patch.object(graph.system_log_service, "log"), \
            patch.object(graph.entity_vectors, "refresh_after_edit") as refresh:
        graph.batch_update_entities(req, user={"username": "tester"})
    refresh.assert_called_once_with("case-a", ["a"])


def _backfill(entities):
    logs = []
    out = meaning_search.run_gap_backfill(
        case_ids=["c1", "c2"], gap=lambda case_id, fresh=True: {"missing_evidence_file_ids": []},
        backfill=lambda **k: pytest.fail("no documents are missing"), log=lambda lvl, msg: logs.append(msg),
        lock=False, entities=entities,
        session_factory=lambda: pytest.fail("pending flag must stay set") if entities.stops else _Session())
    return out, logs


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        return None

    def commit(self):
        return None


class _Entities:
    def __init__(self, stops=False):
        self.stops, self.calls = stops, []

    def __call__(self, case_id, log=None):
        self.calls.append(case_id)
        return {"embedded": 0 if self.stops else 2, "stopped": "429 insufficient_quota" if self.stops else None}


def test_recovery_backfill_refreshes_stale_entity_vectors_of_every_case():
    entities = _Entities()
    out, logs = _backfill(entities)
    assert entities.calls == ["c1", "c2"] and out["entities_embedded"] == 4 and out["stopped"] is None
    assert "4 entity vector(s) refreshed" in logs[-1]


def test_recovery_backfill_stops_and_keeps_pending_when_an_entity_embed_is_refused():
    entities = _Entities(stops=True)
    out, _ = _backfill(entities)
    assert entities.calls == ["c1"] and out["stopped"].startswith("entity vectors: 429")


def test_restore_rebuild_uses_the_same_text():
    from services.neo4j.entity_service import EntityService
    vectors, calls = FakeVectors(), []
    with patch("services.vector_db_service.get_vector_db_service", return_value=vectors), \
            patch("services.embedding_service.EmbeddingService.generate_embedding",
                  lambda self, t: calls.append(t) or [0.0]):
        EntityService._rebuild_entity_embedding({"key": "k", "type": "Person", "name": "LOCO",
                                                 "properties": LOCO}, "case-a")
    assert calls == [ev.embedding_text("Person", LOCO)]
    assert vectors.upserts[0][2]["case_id"] == "case-a"
