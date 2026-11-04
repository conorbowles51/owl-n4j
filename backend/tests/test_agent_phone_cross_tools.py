"""agent-phones A to C: the agent's phone and cross tools wrap the screens' own services and join phones to money.

Invented data only (555 numbers, a synthetic bank, a synthetic ledger). Opt-in PostgreSQL through
``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``. Every test fails on the code before agent-phones (the module did not exist).
"""
from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.agent import phone_cross_tools as X
from services.phone import link_edges as LE
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, ensure_identity, phone
from tests.test_phone_analysis_money_signals import Ledger, Phone, _run, directory  # noqa: F401
from tests.test_phone_analysis_money_signals import WHEN

pytestmark = needs_template
OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"
PAY_DAY = date(2023, 3, 14)


def msg(instant, sender, recips, body):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, thread="t1", parties=parties,
                direction="outgoing" if sender == OWNER else "incoming")


def dossier(c, case, name, entity_key, keys):
    did = uuid.uuid4()
    c.execute(text("INSERT INTO case_profiles (id, case_id, profile_type, display_name, contacts, linkage_state, "
                   "status, needs_link_review, graph_entity_deleted, canonical_entity_key, created_at, updated_at) "
                   "VALUES (:d, :c, 'person', :n, '[]', 'unlinked', 'active', false, false, :k, now(), now())"),
              {"d": did, "c": case, "n": name, "k": entity_key})
    for key in keys:
        c.execute(text("INSERT INTO phone_identity_links (case_id, identity_id, dossier_id, decision_id) VALUES "
                       "(:c, :i, :d, :x)"), {"c": case, "i": ensure_identity(c, case, key), "d": did,
                                             "x": uuid.uuid4()})
    return str(did)


@pytest.fixture
def world(monkeypatch):
    """One phone (owner Sam, C1) talking with Ana around a payment Sam's account made to Ana's party."""
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, evs = phone(c, case, label="C1", contacts={ANA: "Ana Synthetic", BEN: "Ben Synthetic"}, events=[
                msg(at(2023, 3, 14, 9), OWNER, [ANA], "sending the money for the car today"),
                msg(at(2023, 3, 14, 10), ANA, [OWNER], "got it, thanks for the car"),
                msg(at(2023, 3, 20, 10), ANA, [OWNER], "see you next week"),
                msg(at(2023, 3, 14, 11), BEN, [OWNER], "unrelated payment chat")])
            sam = dossier(c, case, "Sam Synthetic", "ent-sam", [OWNER])
            ana = dossier(c, case, "Ana Synthetic", "ent-ana", [ANA])
            L = Ledger(c, case)
            acct = L.account("Synthetic Bank", "XXXX-XXXX-1234")
            party_ana = str(uuid.uuid4())
            paid = L.txn(acct, 500_00, PAY_DAY)
            quiet = L.txn(acct, 70_00, date(2023, 3, 17))
            late = L.txn(acct, 30_00, date(2023, 4, 30))
            for t in (paid, quiet, late):
                c.execute(text("UPDATE financial_transactions SET description = 'CAR PURCHASE', metadata = "
                               "CAST(:m AS jsonb) WHERE id = :i"),
                          {"i": t, "m": '{"investigation_labels": {"counterparty_link": {"kind": "party", "id": "%s", '
                                        '"label": "Ana Synthetic"}}}' % party_ana})
        sides = {"ent-sam": {"parties": set(), "accounts": {str(acct)}},
                 "ent-ana": {"parties": {party_ana}, "accounts": set()}}
        # the reviewed holder and counterparty links (link_edges' own tests cover how they are read)
        monkeypatch.setattr(LE, "financial_sides", lambda s, c_, keys: {k: sides.get(k, {"parties": set(),
                                                                                         "accounts": set()})
                                                                        for k in keys if k})
        yield {"engine": engine, "case": case, "other": other, "ext": ext, "evs": evs, "sam": sam, "ana": ana,
               "acct": str(acct), "paid": str(paid), "quiet": str(quiet), "late": str(late)}


def test_contact_and_money_between_is_the_graph_edge_with_every_payment_cited(world):
    with world["engine"].connect() as c:
        out = X.contact_and_money_between(c, world["case"], person_a="Sam Synthetic", person_b="Ana Synthetic")
        edge = LE.edges(c, world["case"], [{"dossier_id": world["sam"]}, {"dossier_id": world["ana"]}])["edges"][0]
    assert out["communication"] == edge["communication"] and LE.comm_total(edge["communication"], "messages") == 3
    usd = out["money"][0]
    assert (usd["currency"], usd["paid_ab_minor"], usd["payments_ab"]) == ("USD", 600_00, 3)
    assert usd["paid_ab"] == "USD 600.00"
    assert out["total_matching"] == 3 and {i["txn"] for i in out["items"]} == {
        "txn://%s" % world[k] for k in ("paid", "quiet", "late")}
    assert all(i["summed"] for i in out["items"])
    # the payment opens the Financial page on that row, as the ledger tools' links do
    assert all(i["financial_href"] == "/cases/%s/financial?view=transactions&payment=%s" % (
        world["case"], i["txn"][len("txn://"):]) for i in out["items"])


def test_a_person_of_another_case_is_not_in_this_case_in_the_same_words(world):
    with world["engine"].connect() as c:
        for out in (X.contact_and_money_between(c, world["other"], person_a="Sam Synthetic", person_b="Ana Synthetic"),
                    X.person_phones(c, world["other"], "Sam Synthetic"),
                    X.payment_conversation(c, world["other"], world["paid"]),
                    X.control_claim(c, world["other"], "Sam Synthetic", "1234", "2023-03-01", "2023-03-31"),
                    X.day_activity(c, world["other"], "2023-03-14", person="Sam Synthetic")):
            assert out["available"] is False and out["not_in_case"] is True, out
            assert out["reason"].startswith("Not in this case.") and out["items"] == []
            assert "car" not in str(out)


def test_person_phones_lists_the_linked_identities_with_names_and_counts(world):
    with world["engine"].connect() as c:
        out = X.person_phones(c, world["case"], "ana synthetic")
    assert out["person"]["name"] == "Ana Synthetic" and out["total_matching"] == 1
    item = out["items"][0]
    assert item["identity_key"] == ANA and item["messages_and_calls"] == 3
    assert item["names"] == [{"phone": "C1", "name": "Ana Synthetic"}]


def test_search_case_is_search_with_every_group_total(world):
    from services.search import search as S
    with world["engine"].connect() as c:
        out = X.search_case(c, world["case"], "car")
        screen = S.search(c, world["case"], "car")
    assert [(g["group"], g["total"]) for g in out["groups"]] == [(g["group"], g["total"]) for g in screen["groups"]]
    msgs = [i for i in out["items"] if i["group"] == "messages"]
    assert len(msgs) == 2 and all(i["rec"].startswith("rec://") for i in msgs)


def test_the_conversation_around_a_payment_is_the_day_plus_two_hours_between_the_two_people(world):
    with world["engine"].connect() as c:
        out = X.payment_conversation(c, world["case"], "txn://%s" % world["paid"])
    assert out["between"]["a"]["name"] == "Sam Synthetic" and out["between"]["b"]["name"] == "Ana Synthetic"
    assert out["anchor"]["basis"] == "ledger_day" and out["payment"]["description"] == "CAR PURCHASE"
    assert out["total_matching"] == 2 and out["outcome"] is None
    assert [i["rec"] for i in out["items"]] == ["rec://%s" % e["record_uid"] for e in world["evs"][:2]]
    assert "sending the money for the car" in out["items"][0]["text"]
    assert "unrelated" not in str(out["items"])   # Ben is not one of the two


def test_no_conversation_in_the_window_is_decided_by_the_records_with_its_reason(world):
    with world["engine"].connect() as c:
        out = X.payment_conversation(c, world["case"], world["quiet"])
    assert out["outcome"] == "no_conversation_in_window" and out["reason_code"] == "no_messages_in_window"
    assert out["items"] == [] and "3 messages" in out["reason"]
    with world["engine"].connect() as c:
        late = X.payment_conversation(c, world["case"], world["late"])
    assert late["reason_code"] == "outside_extraction_coverage" and "2023-03-14 to 2023-03-20" in late["reason"]


def test_a_purpose_reading_is_a_model_draft_and_a_quote_outside_the_window_is_refused(world):
    inside, outside = world["evs"][0]["record_uid"], world["evs"][2]["record_uid"]
    with world["engine"].connect() as c:
        out = X.draft_payment_purpose(c, world["case"], world["paid"], "consistent", ["rec://%s" % inside],
                                      "money for the car")
        assert out["status"] == X.MODEL_DRAFT and out["items"][0]["quoted"] == ["rec://%s" % inside]
        assert out["items"][0]["row_description"] == "CAR PURCHASE"
        with pytest.raises(ValueError, match="Not in the window"):
            X.draft_payment_purpose(c, world["case"], world["paid"], "consistent", ["rec://%s" % outside], "car")
        with pytest.raises(ValueError):
            X.draft_payment_purpose(c, world["case"], world["paid"], "no_conversation_in_window", [inside])


def test_day_activity_is_the_day_view_with_the_money_lane_and_no_time_on_a_payment(world):
    with world["engine"].connect() as c:
        out = X.day_activity(c, world["case"], "2023-03-14", person="Sam Synthetic", zone="UTC")
    assert out["totals"]["communications"] == 3 and out["totals"]["money"] == 1
    money = [i for i in out["items"] if i["lane"] == "money"]
    assert money[0]["txn"] == "txn://%s" % world["paid"] and "never a time of day" in money[0]["note"]
    assert "a card, not a person" in money[0]["note"]


def test_the_tools_are_registered_and_read_with_the_runs_case(world):
    from services.agent.tools import AgentToolContext, make_agent_tools

    @contextmanager
    def session():
        with Session(bind=world["engine"]) as s:
            yield s
    tools = {t.name: t for t in make_agent_tools(AgentToolContext(case_id=str(world["case"]),
                                                                  ledger_session_factory=session))}
    for name, _, _, _ in X.TOOLS:
        assert name in tools and "case_id" not in tools[name].args
    out = tools["get_contact_and_money_between"].invoke({"person_a": "Sam Synthetic", "person_b": "Ana Synthetic"})
    assert out["status"] == "success" and out["data"]["total_matching"] == 3
    gone = tools["get_person_phones"].invoke({"person": "Zed Elsewhere"})
    assert gone["data"]["not_in_case"] is True and gone["summary"].startswith("Not in this case.")


# ---- approach 1 and connection 3 -----------------------------------------------------------------------------------

def _money_case(engine, with_period=True):
    with engine.begin() as c:
        case = make_case(c)
        L = Ledger(c, case)
        acct = L.account("Synthetic Bank", "XXXX-XXXX-1234", statement=False)
        if with_period:
            L.period(acct, date(2024, 2, 1), date(2024, 2, 29), 0, 0)
        row = L.txn(acct, 1250, date(2024, 3, 5))
        dossier_id = uuid.uuid4()
        c.execute(text("INSERT INTO case_profiles (id, case_id, profile_type, display_name, contacts, linkage_state, "
                       "status, needs_link_review, graph_entity_deleted, created_at, updated_at) VALUES (:d, :c, "
                       "'person', 'Sam Synthetic', '[]', 'unlinked', 'active', false, false, now(), now())"),
                  {"d": dossier_id, "c": case})
    p = Phone()
    p.notification("test.synthbank.mobile", "Synthetic Bank: Purchase of $12.50 on card ending 1234")
    p.notification("test.synthbank.mobile", "Synthetic Bank: your one-time code is 482 913. Do not share it.",
                   when=WHEN - timedelta(minutes=2))
    p.simple("InstalledApplication", Identifier="test.twodollar.app", Name="Two Dollar")
    ext = p.make(engine, case)
    return case, ext, str(acct), str(row), str(dossier_id)


def test_matches_and_leads_are_approach_ones_results_with_the_ledger_half(directory):  # noqa: F811
    with fresh_engine() as engine:
        case, ext, acct, row, _ = _money_case(engine)
        run_id, items = _run(engine, case, {"phase": "1a"})
        with engine.connect() as c:
            m = X.money_signal_matches(c, case)
            leads = X.money_signal_leads(c, case)
    assert m["run_id"] == str(run_id) and m["total_matching"] == 1
    hit = m["items"][0]
    assert hit["outcome"] == "corroborated" and hit["ledger_rows"][0]["txn"] == "txn://%s" % row
    assert hit["rec"].startswith("rec://") and hit["proof_class"] == "p4"
    by = {(i["institution"], i["account"]): i for i in leads["items"]}
    other = by[("Two Dollar Exchange", None)]
    assert other["ledger"] == "missing_account"
    held = by[("Synthetic Bank", "ending 1234")]
    # the alert falls in March 2024; the only statement held covers February: a missing period
    assert held["ledger"] == "missing_period" and held["uncovered_months"] == ["2024-03"]
    assert "—" not in str(leads)


def test_a_control_claim_is_two_evidenced_links_a_model_draft_and_never_a_holder_finding(directory,  # noqa: F811
                                                                                       monkeypatch):
    from services.pattern_of_life import subjects
    from services.phone import identities as I
    with fresh_engine() as engine:
        case, ext, acct, row, did = _money_case(engine)
        _run(engine, case, {"phase": "1a"})
        with engine.begin() as c:
            oid = ensure_identity(c, case, OWNER)
            c.execute(text("INSERT INTO phone_identity_links (case_id, identity_id, dossier_id, decision_id) VALUES "
                           "(:c, :i, :d, :x)"), {"c": case, "i": oid, "d": did, "x": uuid.uuid4()})
        linked = {"on": True}
        monkeypatch.setattr(subjects, "dossiers", lambda conn, c_, exts=None: [
            {"kind": "dossier", "dossier_id": did, "name": "Sam Synthetic",
             "extraction_ids": [str(ext)] if linked["on"] else []}])
        monkeypatch.setattr(I, "owner", lambda conn, e: {"owner_identity_keys": [OWNER], "owner_basis": "extracted"})
        with engine.connect() as c:
            out = X.control_claim(c, case, "Sam Synthetic", "1234", "2024-03-01", "2024-03-31")
            kinds = sorted(s["kind"] for s in out["items"] if s["link"] == "account_to_device")
            assert out["established"] is True and out["status"] == X.MODEL_DRAFT
            assert out["claim"].startswith("Sam Synthetic had the means to operate the Synthetic Bank account "
                                           "ending 1234 from 2024-03-01 to 2024-03-31")
            assert "never a finding that the person is the account holder" in out["not_a_holder_finding"]
            assert kinds == ["alert", "code"]
            code = next(s for s in out["items"] if s["kind"] == "code")
            # the code's digits appear in no text the tool returns (ids are random hex and may hold any digits)
            import re as _re
            texts = " ".join(str(v) for s in out["items"] for k, v in s.items() if k not in ("rec", "extraction_id",
                                                                                         "result_id", "at"))
            assert not _re.search(r"482\D?913", texts + " " + out["claim"]) and "••• •••" in code["quote"]
            assert "482" not in code["quote"] and "913" not in code["quote"]
            assert all(s["correlated_group"].startswith("handset") for s in out["items"]
                       if s["link"] == "account_to_device")
            person = [s for s in out["items"] if s["link"] == "device_to_person"]
            assert [s["kind"] for s in person] == ["owner_identity"]
            assert "not independent" in out["correlated_strands"]
            # outside the alert's month: nothing ties the account to the phone, the chain does not hold
            off = X.control_claim(c, case, "Sam Synthetic", "1234", "2024-05-01", "2024-05-31")
            assert off["established"] is False and "nothing ties the account" in off["limitation"]
            linked["on"] = False
            none = X.control_claim(c, case, "Sam Synthetic", "1234", "2024-03-01", "2024-03-31")
            assert none["established"] is False and none["chain"] == []


# ---- pattern of life ------------------------------------------------------------------------------------------------

def test_together_apart_is_the_stored_runs_rule_and_writes_nothing(hooks_places):
    from services.pattern_of_life import colocation
    engine, case, ea, eb, a, b = hooks_places
    with engine.begin() as c:
        rid = colocation.create_run(c, case, {"kind": "extraction", "extraction_id": ea},
                                    {"kind": "extraction", "extraction_id": eb}, [ea], [eb], a, b,
                                    dict(colocation.DEFAULT_PARAMS), "t@x.test")
        stored = colocation.execute_run(c, rid)
        runs = c.execute(text("SELECT count(*) FROM pol_colocation_run")).scalar()
    with engine.connect() as c:
        out = X.together_apart(c, case, a.isoformat(), b.isoformat(), phone_a=ea, phone_b=eb, limit=100)
        assert c.execute(text("SELECT count(*) FROM pol_colocation_run")).scalar() == runs
    assert out["counts"] == stored and out["total_matching"] == stored["pairs"] > 0
    assert out["label"] == X.PLACE_LABEL


@pytest.fixture
def hooks_places(hooks):  # noqa: F811
    from services.phone import registry
    from tests.test_pattern_u4_availability import DAY, setup
    from tests.test_pattern_u5_places import PlacePhone, build
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            exts = []
            for shift in (0.0, 0.0005):
                p = PlacePhone()
                from tests.test_pattern_u5_places import LAT, LON
                for m in range(0, 60, 10):
                    p.location(DAY + timedelta(hours=20, minutes=m), lat=LAT + shift, lon=LON, accuracy=10)
                exts.append(p.make(c, case))
        for e in exts:
            build(engine, e)
        yield engine, case, str(exts[0]), str(exts[1]), DAY + timedelta(hours=19), DAY + timedelta(hours=22)


from tests.test_phone_mappings import hooks  # noqa: E402,F401  (fixture)


def test_evaluate_statement_is_the_checks_outcome_computed_and_not_stored(hooks_places):
    from services.financial.decisions import Actor
    from services.pattern_of_life import evaluation
    from tests.test_pattern_u11_claims import confirmed
    from tests.test_pattern_u5_places import LAT, LON
    engine, case, ea, eb, a, b = hooks_places
    with engine.begin() as c:
        uid = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar_one()
        me = Actor(name="Test Person", email="t@x.test", user_id=uid)
        subj = {"kind": "extraction", "extraction_id": ea}
        home = confirmed(c, case, me, "at_place", subj, a, b, place={"lat": LAT, "lon": LON, "radius_m": 50})
        later = confirmed(c, case, me, "at_place", subj, a + timedelta(days=4), b + timedelta(days=4),
                          place={"lat": LAT, "lon": LON, "radius_m": 50})
    with engine.connect() as c:
        out = X.statement_check(c, case, home["id"])
        stored = c.execute(text("SELECT count(*) FROM pol_claim_evaluation")).scalar()
        late = X.statement_check(c, case, later["id"])
        expect = evaluation.compute(c, evaluation.claims.get(c, str(case), uuid.UUID(str(home["id"])), raw=True))
        gone = X.statement_check(c, make_case_ro(c), home["id"])
    assert stored == 0
    assert out["outcome"] == expect["outcome"] == "supported" and out["total_matching"] == len(expect["items"])
    assert all(i["rec"].startswith("rec://") for i in out["items"] if i["role"] == "supporting")
    assert late["outcome"] == "no_record" and late["no_record_reason"] == "outside_coverage"
    assert gone["not_in_case"] is True


def make_case_ro(c):
    return uuid.uuid4()   # a case id nothing belongs to


def test_analysis_results_and_map_summary_wrap_their_services(world):
    from services.phone import map as phone_map
    with world["engine"].connect() as c:
        none = X.analysis_results(c, world["case"], "relationships")
        assert none["total_matching"] == 0 and "has not been run" in none["coverage"]
        with pytest.raises(ValueError):
            X.analysis_results(c, world["case"], "money_signals")
        m = X.phone_map_summary(c, world["case"])
        s = phone_map.summary(c, world["case"], {"phones": [], "source_kinds": [], "affiliations": [],
                                                  "from_instant": None, "to_instant": None, "include_no_time": True})
    assert m["positioned"] == s["positioned"] and m["total_matching"] == s["total"]
    assert "not cell-site opinion" in m["note"]
