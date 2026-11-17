"""lx-overlaps: a graph entity or timeline event that carries coordinates is read as a place, so place_overlap can
pair it with a phone position or a payment's attached place. No database: the graph lookup and member facts are faked."""
from unittest import mock

from services import case_selections, theory_additions
from services.relations import rules
from services.relations.sources import DbSources


def _items(members, coords):
    facts = [{"ref": "%s:%s" % (m["type"], m["id"]), "label": m["id"], "date": "2024-05-03"} for m in members]
    with mock.patch.object(theory_additions, "member_facts", lambda db, case, ms: facts), \
            mock.patch.object(case_selections, "graph_places", lambda case, keys: {k: coords[k] for k in keys if k in coords}):
        return DbSources(None, "c").load_items(members)


def test_a_graph_location_and_a_timeline_event_with_coordinates_are_places():
    items = _items([{"type": "graph_entity", "id": "loc-1"}, {"type": "timeline_event", "id": "ev-1"},
                    {"type": "graph_entity", "id": "person-1"}],
                   {"loc-1": {"lat": 39.29, "lon": -76.61}, "ev-1": {"lat": 39.3, "lon": -76.6}})
    by = {i["id"]: i for i in items}
    assert by["loc-1"]["place"] == {"lat": 39.29, "lon": -76.61, "radius_m": 0.0, "source": "placed from the documents"}
    assert by["ev-1"]["place"]["lat"] == 39.3 and by["ev-1"]["at"].startswith("2024-05-03")
    assert "place" not in by["person-1"]


def test_without_the_graph_the_members_are_read_unplaced():
    facts = [{"ref": "graph_entity:loc-1", "label": "loc-1"}]

    def down(case, keys):
        raise RuntimeError("graph unreachable")
    with mock.patch.object(theory_additions, "member_facts", lambda db, case, ms: facts), \
            mock.patch.object(case_selections, "graph_places", down):
        items = DbSources(None, "c").load_items([{"type": "graph_entity", "id": "loc-1"}])
    assert "place" not in items[0]


def test_a_placed_graph_location_is_coarse_for_place_overlap():
    assert rules._fineness("placed from the documents") == 2
