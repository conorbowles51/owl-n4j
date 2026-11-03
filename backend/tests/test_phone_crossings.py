"""Crossings (docs/cellebrite/07 section 7.2): XF-1 a payment to the phones' activity around it, XF-2 a Graph person
to Conversations, XF-8 a phone contact to the payments of the account it is the reference of. Every count equals the
Conversations count for the URL it opens. Invented data only; needs the PostgreSQL template."""
from __future__ import annotations

import json
import uuid
from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.phone import crossings as X
from services.phone import money_presence
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, ensure_identity, phone
from tests.test_phone_analysis_money_signals import Ledger

pytestmark = needs_template
OWNER, ANA, ANA2, BEN = "phone:+12025550100", "phone:+12025550143", "email:ana@synthetic.test", "phone:+12025550188"
PARTY = str(uuid.uuid4())


def msg(instant, sender, recips, body="hello"):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties, thread="t",
                direction="outgoing" if sender == OWNER else "incoming")


@pytest.fixture
def world():
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            phone(c, case, label="C1", contacts={ANA: "Ana Synthetic"}, events=[
                msg(at(2023, 3, 13, 23), ANA, [OWNER], "the evening before"),   # 1 day before
                msg(at(2023, 3, 14, 9), OWNER, [ANA], "sending it now"),        # same day
                msg(at(2023, 3, 14, 10), ANA2, [OWNER], "got it, by email"),    # same day, her other identity
                msg(at(2023, 3, 15, 9), ANA, [OWNER], "thanks"),                # 1 day after
                msg(at(2023, 3, 17, 9), ANA, [OWNER], "outside the window"),
                msg(at(2023, 3, 14, 11), BEN, [OWNER], "someone else")])
            dossier = uuid.uuid4()
            c.execute(text("INSERT INTO case_profiles (id, case_id, profile_type, display_name, contacts, "
                           "canonical_entity_key, linkage_state, status, needs_link_review, graph_entity_deleted, "
                           "created_at, updated_at) VALUES (:d, :c, 'person', 'Ana Synthetic', '[]', 'ent-ana', "
                           "'linked', 'active', false, false, now(), now())"), {"d": dossier, "c": case})
            for key in (ANA, ANA2):
                c.execute(text("INSERT INTO phone_identity_links (case_id, identity_id, dossier_id, decision_id) "
                               "VALUES (:c, :i, :d, :x)"), {"c": case, "i": ensure_identity(c, case, key),
                                                           "d": dossier, "x": uuid.uuid4()})
            ledger = Ledger(c, case)
            own = ledger.account("Synthetic Bank", "****1111")
            theirs = ledger.account("Synthetic Pay", "ana-pay", holder="Ana Synthetic", statement=False)
            # Ana's payment-service account is referenced by her number; her party is linked to her graph entity
            c.execute(text("UPDATE financial_accounts SET metadata = CAST(:m AS jsonb) WHERE id = :a"), {
                "a": theirs, "m": json.dumps({"identity_review": {
                    "identifiers": [{"kind": "phone_number", "value": "(202) 555-0143"}],
                    "entity_links": [{"party_id": PARTY, "entity_key": "ent-ana"}]}})})
            paid = ledger.txn(own, 250_00, date(2023, 3, 14))
            c.execute(text("UPDATE financial_transactions SET metadata = CAST(:m AS jsonb) WHERE id = :i"), {
                "i": paid, "m": json.dumps({"investigation_labels": {"counterparty_link": {
                    "kind": "party", "id": PARTY, "label": "Ana Synthetic"}}})})
            unlinked = ledger.txn(own, 9_00, date(2023, 3, 14))
            c.execute(text("UPDATE financial_transactions SET counterparty_raw = 'Corner Shop', metadata = "
                           "CAST(:m AS jsonb) WHERE id = :i"), {"i": unlinked, "m": json.dumps({
                               "investigation_labels": {"counterparty_link": {
                                   "kind": "party", "id": str(uuid.uuid4()), "label": "Corner Shop"}}})})
            on_theirs = ledger.txn(theirs, 250_00, date(2023, 3, 14), direction="credit")
        yield {"engine": engine, "case": case, "dossier": dossier, "paid": paid, "unlinked": unlinked,
               "theirs": theirs, "on_theirs": on_theirs}


def _screen(conn, case, href):
    """The Conversations count for an href: the stream filter the page builds from that URL."""
    q = {k: v[0] for k, v in parse_qs(urlparse(href).query).items()}
    zone = X._zone(conn, case)
    from_day = date.fromisoformat(q["from"]) if "from" in q else None
    to_day = date.fromisoformat(q["to"]) if "to" in q else None
    f, again = X.conversations_scope(case, q["people"].split(","), from_day, to_day, zone)
    assert again == href
    return X.count(conn, f)


def test_xf1_activity_around_a_payment_is_its_linked_people_by_day_and_equals_conversations(world):
    with Session(world["engine"]) as db:
        out = X.payment_activity(db, world["case"], world["paid"])
        assert out["state"] == "linked" and [p["name"] for p in out["people"]] == ["Ana Synthetic"]
        assert out["identity_keys"] == sorted([ANA, ANA2])
        assert [(d["words"], d["date"], d["count"]) for d in out["days"]] == [
            ("1 day before", "2023-03-13", 1), ("same day", "2023-03-14", 2), ("1 day after", "2023-03-15", 1)]
        assert out["total"] == 4
        conn = db.connection()
        for d in out["days"]:
            assert _screen(conn, world["case"], d["conversations_href"]) == d["count"]
        assert _screen(conn, world["case"], out["conversations_href"]) == out["total"]
        q = parse_qs(urlparse(out["conversations_href"]).query)
        assert q["from"] == ["2023-03-13"] and q["to"] == ["2023-03-15"]
        words = json.dumps(out)
        assert ":00" not in out["sentence"] and "AM" not in words and "PM" not in words  # never a time of day


def test_xf1_an_unlinked_payee_says_so_and_can_get_a_dossier(world):
    from postgres.models.user import User
    with Session(world["engine"]) as db:
        out = X.payment_activity(db, world["case"], world["unlinked"])
        assert out["state"] == "unlinked" and out["sentence"] == X.UNLINKED_PAYEE
        assert out["payee_dossier_offer"] is True
        owner = db.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": world["case"]}).scalar()
        made = X.create_payee_dossier(db, world["case"], world["unlinked"], db.get(User, owner))
        assert made["display_name"] == "Corner Shop" and made["dossier_type"] == "person"
        assert made["linkage_state"] == "unlinked" and "Payee on payments" in made["summary"]
        with pytest.raises(X.NotInCase):
            X.payment_activity(db, uuid.uuid4(), world["paid"])
        db.rollback()


def test_xf2_a_graph_person_opens_conversations_with_the_same_count(world):
    with Session(world["engine"]) as db:
        conn = db.connection()
        for kw in ({"dossier_id": world["dossier"]}, {"entity_key": "ent-ana"}):
            out = X.person_activity(conn, world["case"], **kw)
            assert out["state"] == "linked" and out["total"] == 5
            assert _screen(conn, world["case"], out["conversations_href"]) == 5
        none = X.person_activity(conn, world["case"], entity_key="ent-nobody")
        assert none["state"] == "unlinked" and none["total"] is None


def test_xf8_a_phone_contact_suggests_the_payments_of_the_account_it_references_and_changes_nothing(world):
    with Session(world["engine"]) as db:
        before = db.execute(text("SELECT count(*), max(updated_at) FROM financial_transactions WHERE case_id = :c"),
                            {"c": world["case"]}).one()
        out = X.counterparty_suggestions(db, world["case"], ANA)
        assert out["state"] == "suggested" and out["status"] == "Suggested, not reviewed"
        assert [a["account_id"] for a in out["accounts"]] == [str(world["theirs"])]
        assert out["payment_total"] == 1 and out["payments"][0]["id"] == str(world["on_theirs"])
        assert out["payments"][0]["href"].endswith("financial?payment=%s" % world["on_theirs"])
        assert out["sentence"].startswith("Suggested, not reviewed: 1 payment on 1 account")
        assert X.counterparty_suggestions(db, world["case"], BEN)["state"] == "none"
        after = db.execute(text("SELECT count(*), max(updated_at) FROM financial_transactions WHERE case_id = :c"),
                           {"c": world["case"]}).one()
        assert tuple(before) == tuple(after)


def test_sa3_sa8_phones_only_says_what_is_absent_and_a_ledger_added_later_lights_the_crossings(world):
    with world["engine"].begin() as c:
        case = make_case(c)
        phone(c, case, label="C1", contacts={ANA: "Ana Synthetic"}, events=[msg(at(2023, 3, 14, 9), ANA, [OWNER])])
    with Session(world["engine"]) as db:
        out = X.counterparty_suggestions(db, case, ANA)
        assert out["state"] == "no_financial_records" and out["sentence"] == money_presence.NO_FINANCIAL_RECORDS
        assert "0 payments" not in json.dumps(out)
    # SA-8 second part: a ledger added afterwards works with no re-reading of the phone
    with world["engine"].begin() as c:
        ledger = Ledger(c, case)
        acct = ledger.account("Synthetic Pay", "ana-pay", holder="Ana Synthetic", statement=False)
        c.execute(text("UPDATE financial_accounts SET metadata = CAST(:m AS jsonb) WHERE id = :a"), {
            "a": acct, "m": json.dumps({"identity_review": {"identifiers": [
                {"kind": "phone_number", "value": "+1 202 555 0143"}]}})})
        ledger.txn(acct, 5_00, date(2023, 3, 14))
        gen_before = c.execute(text("SELECT generation FROM phone_interpretation_state WHERE case_id = :c"),
                               {"c": case}).scalar()
    with Session(world["engine"]) as db:
        out = X.counterparty_suggestions(db, case, ANA)
        assert out["state"] == "suggested" and out["payment_total"] == 1
        assert db.execute(text("SELECT generation FROM phone_interpretation_state WHERE case_id = :c"),
                          {"c": case}).scalar() == gen_before


def test_xf4_a_timeline_period_per_phone_equals_the_lens_lanes_and_conversations(world):
    from services.phone import timeline_lens as TL
    with Session(world["engine"]) as db:
        conn = db.connection()
        out = X.period_activity(conn, world["case"], date(2023, 3, 13), date(2023, 3, 15))
        assert out["total"] == 5 and len(out["phones"]) == 1      # the 17th is outside; Ben's 14th is inside
        p = out["phones"][0]
        q = parse_qs(urlparse(p["conversations_href"]).query)
        assert q == {"phones": [p["extraction_id"]], "from": ["2023-03-13"], "to": ["2023-03-15"]}
        f, again = X.conversations_scope(world["case"], [], date(2023, 3, 13), date(2023, 3, 15), out["zone"],
                                         phones=[p["extraction_id"]])
        assert again == p["conversations_href"] and X.count(conn, f) == p["count"] == 5
        lens = TL.index(conn, TL.TimelineLensFilter.model_validate(out["lens_filter"]))
        assert {l["key"]: l["count"] for l in lens["lanes"]} == {p["extraction_id"]: 5}
        with pytest.raises(ValueError):
            X.period_activity(conn, world["case"], date(2023, 3, 15), date(2023, 3, 13))
