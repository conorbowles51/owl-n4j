"""The lead finder (lx-leads D): each detector finds its pattern on invented records and leaves ordinary ones; a
photo place is never a position; stock words are set aside, never shared wording; the key nights come from the
strongest relay; and "Is this person connected at all?" with nothing linking the person is "No link found"."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from services.corroborate import engine, model as M
from services.leads import finder as F
from tests.corroborate_world import INCIDENTS, FakeStore

UTC = timezone.utc
NIGHTS = [date(2025, 3, 7) + timedelta(days=7 * n) for n in range(4)]
PEOPLE = {k: {"key": k, "label": v, "phones": [f"ph{k}"], "accounts": [], "names": [v]}
          for k, v in {"a": "Ann", "b": "Bob", "h": "Hub", "z": "Zed"}.items()}


def at(d, h, m=0):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=UTC)


def msg(ref, owner, other, when, body="hi", deleted=False):
    return {"ref": ref, "kind": "message", "at": when, "phone": f"ph{owner}", "owner": owner, "parties": [other],
            "body": body, "sender": owner, "deleted": deleted}


def pos(ref, owner, when, lat=51.5, lon=-0.1, kind="position"):
    return {"ref": ref, "kind": kind, "at": when, "phone": f"ph{owner}", "owner": owner,
            "place": {"lat": lat, "lon": lon, "radius_m": 20}}


def case(recs):
    c = object.__new__(F.Case)
    c.store, c.zone, c.people, c.recs = None, M.tz("UTC"), PEOPLE, recs
    c.stock, c.photo_places, c.phones = set(), 0, sorted({r["phone"] for r in recs if r.get("phone")})
    c.body_phones, c.body_copies = defaultdict(set), Counter()
    for r in recs:
        if r.get("body"):
            c.body_phones[F._norm(r["body"])].add(r["phone"])
            c.body_copies[F._norm(r["body"])] += 1
    return c


def test_contact_through_a_third_number_on_three_nights_is_a_relay_lead_and_on_two_is_not():
    recs = []
    for i, d in enumerate(NIGHTS[:3]):
        recs += [msg(f"x{i}", "h", "a", at(d, 22)), msg(f"y{i}", "h", "b", at(d, 22, 6))]
    found = F.relays(case(recs))
    assert len(found) == 1 and found[0]["people"] == ["h", "a", "b"]
    assert found[0]["detail"]["nights"] == [d.isoformat() for d in NIGHTS[:3]]
    assert "within 6 minutes" in found[0]["title"] and "on 3 nights" in found[0]["title"]
    assert F.relays(case(recs[:4])) == []
    late = recs[:4] + [msg("x9", "h", "a", at(NIGHTS[2], 22)), msg("y9", "h", "b", at(NIGHTS[2], 22, 11))]
    assert F.relays(case(late)) == []  # 11 minutes apart is outside the engine's relay window


def test_a_photo_place_is_never_a_position():
    raw = [pos("phone_record:p", "a", at(NIGHTS[0], 23)), pos("phone_record:q", "b", at(NIGHTS[0], 23))]
    recs = F.photo_places_as_media(raw, {"phone_record:p"})
    assert {r["ref"]: r["kind"] for r in recs} == {"phone_record:p": "media_position", "phone_record:q": "position"}
    assert recs[0]["photo_place"] is True


def test_same_place_on_three_nights_is_a_place_lead_and_photo_places_never_make_one():
    recs = []
    for i, d in enumerate(NIGHTS[:3]):
        recs += [pos(f"a{i}", "a", at(d, 23)), pos(f"b{i}", "b", at(d, 23, 40))]
    found = [c for c in F.places(case(recs)) if c["family"] == "place"]
    assert len(found) == 1 and found[0]["people"] == ["a", "b"] and len(found[0]["detail"]["nights"]) == 3
    photos = [dict(r, kind="media_position") if r["owner"] == "b" else r for r in recs]
    assert F.places(case(photos)) == []


def test_together_once_is_a_lead_for_the_engine_to_weigh():
    recs = [pos("a", "a", at(NIGHTS[0], 11, 20)), pos("z", "z", at(NIGHTS[0], 11, 30))]
    found = F.places(case(recs))
    assert [c["family"] for c in found] == ["once"] and "once" in found[0]["title"]


def test_stock_words_are_never_shared_wording_and_a_message_and_its_answer_are_one_lead():
    keys = {d: f"k{i}" for i, d in enumerate(NIGHTS[:3])}
    recs = []
    for i, d in enumerate(NIGHTS[:3]):
        recs += [msg(f"t{i}", "a", "b", at(d, 16, 10), "tonight. same as before"),
                 msg(f"o{i}", "b", "a", at(d, 16, 14), "ok. dock 3 again?"),
                 msg(f"s{i}", "a", "b", at(d, 17), "running about ten minutes behind")]
    c = case(recs)
    c.stock = {"running about ten minutes behind"}
    found = F.words(c, keys, set())
    assert len(found) == 1
    assert "“tonight. same as before”" in found[0]["title"] and "“ok. dock 3 again?”" in found[0]["title"]
    assert not any(r.startswith("s") for r in found[0]["refs"])


def test_a_rare_message_deleted_on_one_phone_and_kept_on_another_is_found_and_a_common_one_is_not():
    when = at(NIGHTS[0], 23, 42)
    recs = [msg("d", "a", "b", when, "left something in the truck", deleted=True),
            msg("k", "b", "a", when, "left something in the truck")]
    found = F.deletions(case(recs))
    assert len(found) == 1 and found[0]["refs"] == ["d", "k"] and "deleted on Ann's phone, still on Bob's" in found[0]["title"]
    common = recs + [msg(f"c{i}", "z", "a", at(NIGHTS[1], 9, i), "left something in the truck") for i in range(3)]
    assert F.deletions(case(common)) == []


def test_key_nights_are_the_strongest_relays_nights_plus_stated_dates():
    c = case([msg(f"x{i}", "h", "a", at(d, 22)) for i, d in enumerate(NIGHTS)])
    strong = {"family": "relay", "refs": ["x0", "x1"], "detail": {"nights": [NIGHTS[0].isoformat(), NIGHTS[1].isoformat()]}}
    weak = {"family": "relay", "refs": ["x2"], "detail": {"nights": [NIGHTS[2].isoformat()]}}
    keys = F.key_nights(c, [(strong, {"level": {"key": "strong"}}), (weak, {"level": {"key": "possible"}})],
                        [NIGHTS[3]])
    assert sorted(keys) == [NIGHTS[0], NIGHTS[1], NIGHTS[3]] and keys[NIGHTS[0]] == "x0"


def _row(kind, label, inc_present, inc_of, ord_present, ord_of, **extra):
    return {"link_kind": kind, "label": label, "weight": "full", "people": ["dan", "ann"],
            "incident": {"present": inc_present, "of": inc_of}, "ordinary": {"present": ord_present, "of": ord_of},
            **extra}


def test_a_person_nothing_links_is_no_link_found_when_asked_if_they_are_connected():
    from services.corroborate import levels
    instances = [{"id": f"i{n}", "side": "incident"} for n in range(5)] + \
        [{"id": f"o{n}", "side": "ordinary"} for n in range(20)]
    grid = [_row("activity", "all phones active within the same 30 minutes", 4, 5, 2, 20, context=True),
            _row("contact", "contact between any of them", 0, 5, 0, 20),
            _row("absence", "Dan's phone silent for 4 hours or more", 0, 5, 9, 20)]
    comparison = {"words": "Compared with the other days.", "incident_noun": "instances asked about",
                  "ordinary_noun": "ordinary days", "kind": "same_people_ordinary"}
    asked = levels.decide(grid, instances, comparison, [], question_kind="connected", missing=[])
    assert asked["key"] == "no_link_found" and asked["rule"] == "nothing_links_the_person"
    # the same records asked "does this happen every time?" keep the rule they had: the overlap is what was picked
    every = levels.decide(grid, instances, comparison, [], question_kind="every_time", missing=[])
    assert every["key"] == "coincidence" and every["rule"] == "overlap_only"


def test_cash_just_under_the_threshold_is_weighed_against_the_key_nights_it_follows():
    deposits = [{"ref": f"d{i}", "kind": "payment", "at": at(d + timedelta(days=3), 10), "owner": "a", "parties": [],
                 "amount_minor": 990000 - i * 100, "cash_deposit": True} for i, d in enumerate(NIGHTS[:3])]
    keys = {d: f"k{i}" for i, d in enumerate(NIGHTS)}
    found = F.cash_splits(case(deposits), keys)
    assert len(found) == 1
    # the three key nights each followed by a deposit are in the question; the fourth, with none after it, is not
    assert found[0]["refs"][:3] == ["k0", "k1", "k2"] and "k3" not in found[0]["refs"]
    assert "each within 4 days after a key night" in found[0]["title"]
    late = [dict(r, at=r["at"] + timedelta(days=2)) for r in deposits]  # 5 days after each night
    assert not any(r.startswith("k") for r in F.cash_splits(case(late), keys)[0]["refs"])


def test_a_deletion_another_phone_kept_is_a_signal_compared_with_ordinary_days():
    from datetime import time as dtime
    from services.corroborate import signals as S
    zone = M.tz("UTC")
    days = [date(2025, 6, 1) + timedelta(days=n) for n in range(6)]
    inst = [M.make_instance(d, dtime(18), timedelta(hours=8), zone, "incident" if n == 0 else "ordinary", "UTC")
            for n, d in enumerate(days)]

    def copy(ref, owner, deleted, when, key):
        return {**msg(ref, owner, "b" if owner == "a" else "a", when, body="left it in the truck", deleted=deleted),
                "dup_key": key}
    recs, _ = M.dedupe([copy("a1", "a", True, at(days[0], 20), "k1"), copy("b1", "b", False, at(days[0], 20), "k1"),
                        copy("a2", "a", False, at(days[2], 20), "k2"), copy("b2", "b", False, at(days[2], 20), "k2")])
    assert len(recs) == 2  # each message held on both phones still counts once
    rows = S.deletion_rows(PEOPLE, recs, inst)
    assert [r["id"] for r in rows] == ["deleted:a:b"]  # Bob kept his copy; Ann's phone deleted hers
    assert rows[0]["people"] == ["a", "b"]  # a deletion is between the two, so one instance can weigh it
    assert rows[0]["link_kind"] == "absence" and {k for k, v in rows[0]["cells"].items() if v == "present"} == {days[0].isoformat()}
    assert sorted(rows[0]["records"][days[0].isoformat()]) == ["a1", "b1"]
    json.dumps([{k: r[k] for k in ("deleted_by", "kept_by") if k in r} for r in recs])  # plain lists, never sets


def test_payments_the_alerts_show_and_the_bank_rows_do_not_are_cant_tell_with_what_is_missing():
    from services.corroborate import levels

    def pay(ref, kind, d, amount=50000):
        return {"ref": ref, "kind": kind, "at": at(d, 9), "owner": "a", "parties": ["b"], "amount_minor": amount,
                "dup_key": ("pay", "a", ("b",), amount, d)}
    march, may = date(2025, 3, 8), date(2025, 5, 3)
    recs = [pay("t1", "payment", march), pay("al1", "payment_alert", march),   # March: the bank row confirms it
            pay("al2", "payment_alert", may), pay("al3", "payment_alert", may + timedelta(days=14)),
            pay("al4", "payment_alert", may, amount=990000)]                  # never confirmed anywhere: left out
    c = case(recs)
    c.people = {**PEOPLE, "a": {**PEOPLE["a"], "accounts": ["acc1"]}}
    found = F.statement_gaps(c, ledger_months={"a": {"2025-03", "2025-05"}})
    assert [g["key"] for g in found] == ["gap:a:2025-05"]
    assert found[0]["refs"] == ["al2", "al3"] and found[0]["days"] == ["2025-05-03", "2025-05-17"]
    assert "Part of the statement is missing" in found[0]["summary"]
    assert "May payments: the alerts show $500.00 from Ann on 3 May, 17 May" in found[0]["title"]
    whole = F.statement_gaps(c, ledger_months={"a": {"2025-03"}})
    assert "May statement is not in the case" in whole[0]["summary"]
    lv = levels.records_missing(found[0]["missing"])
    assert lv["key"] == "cant_tell" and lv["sentence"].startswith("Can't tell: too little data. Missing: Ann's bank rows")
    c.people = PEOPLE  # a payer with no account in the case: nothing is missing from a statement
    assert F.statement_gaps(c, ledger_months={}) == []
