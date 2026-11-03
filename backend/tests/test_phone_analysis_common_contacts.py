"""05-S16a, approach 14 common contacts (05 section 16a.8). Invented data only."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from services.phone_analysis import common_contacts as C
from services.phone_analysis import framework as F
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import GEN, at, ensure_identity, phone

A, B = "phone:+12025550100", "phone:+12025550200"
X, Y, Z = "phone:+12025550111", "phone:+12025550122", "phone:+12025550133"


@pytest.fixture
def engine():
    with fresh_engine() as e:
        yield e


def call(t, me, other):
    return dict(kind="call", instant=t, body=None, thread=None, call_duration_s=30,
                parties=[(me, "caller", True, None, None), (other, "callee", False, None, None)])


def msg(t, sender, to, owner):
    return dict(kind="message", instant=t, body="synthetic", thread="t",
                parties=[(sender, "sender", sender == owner, None, None), (to, "recipient", to == owner, None, None)])


def _card(c, case, ext, key):
    iid = ensure_identity(c, case, key)
    card = uuid.uuid4()
    c.execute(text(
        "INSERT INTO phone_identity_sightings (sighting_uid, case_id, extraction_id, identity_id, identity_key, "
        "record_uid, root_record_uid, card_record_uid, card_type, field_path, identifier_raw, context, generation) "
        "VALUES (:s, :c, :e, :i, :k, :r, :r, :r, 'Contact', 'Entries', 'x', 'listed_on_card', :g)"),
        {"s": uuid.uuid4(), "c": case, "e": ext, "i": iid, "k": key, "r": card, "g": GEN})
    return str(card)


@needs_template
def test_common_contacts_from_both_sides(engine):
    """16a.8 tests 1 to 3: A calls X and B messages X: X listed with both counts; Y called only by A is not listed;
    a message from B to Z held only on Z's phone counts as seen on the other phone; X2 saved on A's phone with no
    communication there, and in contact with B, is "saved, no contact seen"."""
    X2 = "phone:+12025550144"
    with engine.begin() as c:
        case = make_case(c)
        pa, _ = phone(c, case, label="C1", owner=A, events=[call(at(2023, 1, 2, 9), A, X), call(at(2023, 1, 3, 9), A, Y),
                                                           call(at(2023, 1, 4, 9), A, Z)])
        pb, _ = phone(c, case, label="C2", owner=B, events=[msg(at(2023, 1, 5, 9), B, X, B),
                                                           msg(at(2023, 1, 6, 9), B, X2, B)])
        pz, _ = phone(c, case, label="C3", owner=Z, events=[msg(at(2023, 1, 7, 9), B, Z, Z)])
        card = _card(c, case, pa, X2)
    with engine.connect() as c:
        res, counts = C.analyse(c, case, {})
    ab = [r for r in res if sorted(r["measures"]["phones"]) == ["C1", "C2"]]
    by = {r["measures"]["contact"]: r for r in ab}
    assert set(by) == {X, Z, X2}
    x = by[X]
    sides = {x["measures"]["owner_a"]: "a", x["measures"]["owner_b"]: "b"}
    assert x["kind"] == "common_contact" and x["measures"]["a"]["total"] == 1 and x["measures"]["b"]["total"] == 1
    z = by[Z]
    assert z["kind"] == "common_contact" and z["measures"][sides["C2"]]["seen_on_other_phone"] == 1
    assert z["measures"]["contact_owns_phone"] is True
    s = by[X2]
    assert s["kind"] == "saved_no_contact" and s["measures"][sides["C1"]]["saved"] == 1
    assert s["measures"][sides["C1"]]["total"] == 0
    assert any(r["record_uid"] == card for r in s["records"])
    assert counts["owners"] == 3


@needs_template
def test_runs_through_the_framework_with_unique_keys(engine):
    """One record can be the first contact of two owner pairs: each result carries its own pair anchor."""
    F.register(C)
    with engine.begin() as c:
        case = make_case(c)
        phone(c, case, label="C1", owner=A, events=[call(at(2023, 1, 2, 9), A, X)])
        phone(c, case, label="C2", owner=B, events=[call(at(2023, 1, 3, 9), B, X)])
        phone(c, case, label="C3", owner=Z, events=[call(at(2023, 1, 4, 9), Z, X)])
        run, _ = F.request_run(c, case, "common_contacts", None, "synthetic@example.org")
    assert F.execute(engine, uuid.UUID(run["id"]))["status"] == "completed"
    with engine.connect() as c:
        page = F.results(c, case, run["id"], kind="common_contact")
    assert page["total"] == 3
    assert all(i["label"] == F.LEAD_LABEL for i in page["items"])
