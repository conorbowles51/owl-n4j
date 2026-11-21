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
            c.body_phones[F._body_key(r["body"])].add(r["phone"])
            c.body_copies[F._body_key(r["body"])] += 1
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


# ---- speed on a large case (followups 18 Nov: a dry run on Phone reference 1 ran 50 minutes without finishing) ----

def test_near_pairs_are_the_near_pairs_of_every_pair_in_the_same_order():
    import random
    from itertools import combinations
    rnd = random.Random(7)
    for lat0 in (0.0, 39.3, 64.1):
        rs = [{"ref": f"p{i}", "owner": rnd.choice("abc"),
               "place": {"lat": lat0 + rnd.uniform(-0.2, 0.2), "lon": -76.6 + rnd.uniform(-0.3, 0.3),
                         "radius_m": rnd.choice([5, 50, 400, 2000, None])}} for i in range(400)]
        old = [(x["ref"], y["ref"]) for x, y in combinations(rs, 2) if x["owner"] != y["owner"] and F._near(x, y)]
        new = [(x["ref"], y["ref"]) for x, y in F._near_pairs(rs) if x["owner"] != y["owner"] and F._near(x, y)]
        assert old and new == old


class _Held(F.FinderStore):
    """A FinderStore without a database: its database read is the same rules applied to a list."""
    def __init__(self, recs):
        self.photo_refs, self._held, self.reads, self.all, self.dedupe_memo = set(), None, 0, recs, {}

    def phone_records(self, people, windows, everyone):
        return super().phone_records(people, windows, everyone)


def _db_read(store, people, windows):
    store.reads += 1
    phones = {e for p in people for e in p["phones"]}
    out = []
    for r in store.all:
        hi_extra = timedelta(days=3) if r["kind"] == "payment_alert" else timedelta(0)
        if r["phone"] in phones and any(lo <= r["at"] <= hi + hi_extra for lo, hi in windows):
            out.append(dict(r))
    return out


def test_held_records_answer_a_weighing_as_the_database_does(monkeypatch):
    import random
    rnd = random.Random(3)
    t0 = at(NIGHTS[0], 0)
    kinds = ["message", "call", "position", "payment_alert"]
    recs = [{"ref": f"phone_record:{i}", "kind": rnd.choice(kinds), "at": t0 + timedelta(minutes=rnd.randint(0, 60 * 24 * 40)),
             "phone": rnd.choice(["pha", "phb", "phh"]), "owner": "a"} for i in range(3000)]
    st = _Held(recs)
    monkeypatch.setattr(F.CaseStore, "phone_records", lambda self, p, w, e: _db_read(self, p, w))
    everyone = list(PEOPLE.values())
    st.hold(recs, t0 - timedelta(days=1), t0 + timedelta(days=42), everyone)
    for _ in range(30):
        people = rnd.sample(everyone, rnd.randint(1, 3))
        windows = []
        for _ in range(rnd.randint(1, 6)):
            lo = t0 + timedelta(hours=rnd.randint(0, 24 * 38))
            windows.append((lo, lo + timedelta(hours=rnd.randint(1, 30))))
        reads = st.reads
        got = sorted(r["ref"] for r in st.phone_records(people, windows, everyone))
        assert st.reads == reads, "a window inside the held read went to the database"
        assert got == sorted(r["ref"] for r in _db_read(st, people, windows))
    # a window outside the held read, or other people, goes to the database
    reads = st.reads
    st.phone_records(everyone, [(t0 - timedelta(days=5), t0)], everyone)
    st.phone_records(everyone, [(t0, t0 + timedelta(hours=1))], everyone[:2])
    assert st.reads == reads + 2


def test_a_records_key_holds_no_copy_of_its_text():
    """Phone reference 1: the key held the whole body a second time (half of a 6 GB read). Same words still fold."""
    import sys
    from services.corroborate.store import contact_dup_key
    when = at(NIGHTS[0], 21)
    body = "Long e-mail text. " * 800
    key = contact_dup_key("email", when, body, ["a", "b"])
    assert sum(sys.getsizeof(x) for x in key) < 1000
    assert key == contact_dup_key("email", when.replace(second=30), "  " + body.upper() + " ", ["b", "a"])
    assert key != contact_dup_key("email", when, body + "!", ["a", "b"])


def test_stock_phrases_read_the_records_once_and_keep_each_phrases_records(monkeypatch):
    """Phone reference 1, 18 Nov: one pass over every record per stock phrase (phrases x 251,780 records) held the
    finder past 10 minutes. One pass now; each phrase still lists its own records, at most 200."""
    phrases = ["running about ten minutes behind", "sent from my phone please excuse typos", "call me back"]
    recs = [msg(f"r{i}", "abz"[i % 3], "h", at(NIGHTS[0], 12), "  " + phrases[i % 3].upper() + " ")
            for i in range(900)] + [msg("x", "a", "b", at(NIGHTS[0], 13), "something else")]
    c = case(recs)

    class Q:
        def all(self):
            return [(p, 3, 300) for p in phrases]

    c.store = SimpleNamespace(q=lambda *a, **k: Q())
    calls = Counter()
    real = F._norm
    monkeypatch.setattr(F, "_norm", lambda b: (calls.update(["n"]), real(b))[1])
    out = F.stock_phrases(c)
    assert calls["n"] <= len(recs)
    assert c.stock == set(phrases)
    by = {o["key"]: o["refs"] for o in out}
    assert by["stock:call me back"] == [f"r{i}" for i in range(2, 900, 3)][:200]
    assert all(len(v) == 200 for v in by.values())


def test_a_phrase_is_counted_in_the_database_once_per_finder_run():
    """Phone reference 1, 18 Nov: each count reads 847 MB of text (5.4 s) and every weighing asked its phrases again."""
    asked = []

    class Q:
        def __init__(self, p):
            self.p = p

        def scalar(self):
            return len(self.p)

    st = object.__new__(F.FinderStore)
    st._phrase_n = {}
    st.q = lambda sql, **k: (asked.append(k["p"]), Q(k["p"]))[1]
    assert st.phrase_counts(["dock 3", "same as before"]) == {"dock 3": 8, "same as before": 16}
    assert st.phrase_counts(["same as before", "tonight"]) == {"same as before": 16, "tonight": 9}
    assert asked == ["%dock 3%", "%same as before%", "%tonight%"]


def test_many_phrases_are_counted_in_one_read_as_ilike_counts_them():
    """Phone reference 1, 18 Nov: 200 phrases of one weighing were 200 database scans of 847 MB (27 min). One read now,
    the same counts: ILIKE lower-cases both sides, ``_`` is any one character."""
    import re as _re
    bodies = ["Running ABOUT ten minutes behind", "see you at Dock_3", "see you at dock 3", None, "nothing", "on my way!"]
    phrases = ["about ten minutes", "at dock_3", "on my way", "not here", "you at"]
    reads = []

    class R:
        def __init__(self, rows):
            self.rows = rows

        def __iter__(self):
            return iter(self.rows)

    st = object.__new__(F.FinderStore)
    st._phrase_n, st.c = {}, {"c": "case"}
    st.q = lambda sql, **k: (reads.append("lower"), R([(p.lower(),) for p in k["ps"]]))[1]
    st.db = SimpleNamespace(execute=lambda sql, params, execution_options=None: (
        reads.append("bodies"), R([(b.lower(),) for b in bodies if b is not None]))[1])

    def ilike(b, ph):
        return b is not None and _re.search(".*".join([""]) + "".join("." if c == "_" else _re.escape(c) for c in ph),
                                            b.lower(), _re.DOTALL) is not None
    want = {ph: sum(ilike(b, ph) for b in bodies) for ph in phrases}
    assert want == {"about ten minutes": 1, "at dock_3": 2, "on my way": 1, "not here": 0, "you at": 2}
    assert st.phrase_counts(phrases) == want
    assert reads == ["lower", "bodies"]
    assert st.phrase_counts(["on my way"]) == {"on my way": 1} and reads == ["lower", "bodies"]


def test_like_test_is_like():
    assert F._like_test("a_c")("xxabcx") and not F._like_test("a_c")("ac")
    assert F._like_test("50% off")("save 50 percent off") and F._like_test("a\\_b")("a_b") and not F._like_test("a\\_b")("axb")
    assert F._like_test("dock 3")("at dock 3.") and not F._like_test("dock 3")("dock  3")


def test_a_numbers_history_is_asked_once_per_finder_run():
    """Phone reference 1, 18 Nov: every weighing asked each person's number history again (34% of a weighing)."""
    asked = []
    when = at(NIGHTS[0], 9)

    class R:
        def fetchall(self):
            return [("u1", when, "e1")]

    st = object.__new__(F.FinderStore)
    st._number_hist, st.c = {}, {"c": "case"}
    st.q = lambda sql, **k: (asked.append((k["v"], k["b"])), R())[1]
    first = st.number_history("15551230000", when)
    first[0]["ref"] = "changed by a caller"
    assert st.number_history("15551230000", when) == [{"ref": "phone_record:u1", "at": when, "phone": "e1"}]
    st.number_history("15551239999", when)
    assert asked == [("15551230000", when), ("15551239999", when)]


def _grouped(rows):
    """``SELECT extraction_id, instant_utc, offset_status FROM pol_activity_event`` over (phone, instant[, status])."""
    return [(r[0], r[1], r[2] if len(r) > 2 else "explicit") for r in rows]


def test_held_activity_answers_as_the_database_does():
    """Phone reference 1, 18 Nov: every weighing asked each person's activity of the database (25% of a weighing)."""
    import random
    rnd = random.Random(4)
    base = at(NIGHTS[0], 0)
    rows = [(e, base + timedelta(minutes=rnd.randrange(0, 60 * 24 * 40))) for e in ("e1", "e2", "e3") for _ in range(400)]
    rows += [("e1", base + timedelta(days=5)), ("e2", base + timedelta(days=5))]  # the same instant on two phones
    reads = []

    class R:
        def __init__(self, rs):
            self.rs = rs

        def __iter__(self):
            return iter(self.rs)

    st = object.__new__(F.FinderStore)
    st._activity, st.c = None, {"c": "case"}
    st.db = SimpleNamespace(execute=lambda sql, params, execution_options=None: (reads.append(1), R(_grouped(rows)))[1])
    people = [{"key": "a", "phones": ["e1", "e2"]}, {"key": "b", "phones": ["e3"]}, {"key": "c", "phones": []}]

    def db_rule(ps, windows):
        out = {}
        for p in ps:
            if p["phones"]:
                out[p["key"]] = sorted({t for e, t in rows if e in p["phones"] and any(
                    lo - timedelta(hours=24) <= t <= hi + timedelta(hours=24) for lo, hi in windows)})
        return out
    for _ in range(5):
        ws = []
        for _ in range(rnd.randrange(1, 4)):
            lo = base + timedelta(hours=rnd.randrange(0, 24 * 40))
            ws.append((lo, lo + timedelta(hours=rnd.randrange(1, 30))))
        ws.append((base + timedelta(days=6), base + timedelta(days=6)))  # exactly a day after a held instant
        assert st.activity(people, ws) == db_rule(people, ws)
    assert reads == [1]


def test_a_pairs_contact_and_a_persons_coverage_are_asked_once_per_finder_run():
    """Phone reference 1, 18 Nov: every weighing asked its pairs' contact (11%) and its people's coverage (8%) again."""
    from services.corroborate.store import CaseStore
    asked = []

    class R:
        def scalar(self):
            return 2

        def __iter__(self):
            return iter([])

    st = object.__new__(F.FinderStore)
    st._contact, st._cov, st.c, st._phone_days, st.set_aside = {}, {}, {"c": "case"}, {}, {}
    st.q = lambda sql, **k: (asked.append(sql[:30]), R())[1]
    st.phone_spans = lambda e: ([(at(NIGHTS[0], 0), at(NIGHTS[1], 0))], 0)
    st.document_rows = lambda fid: [{"at": at(NIGHTS[2], 5)}]
    a = {"key": "a", "phones": ["e1"], "numbers": ["1555"], "handles": [], "emails": [], "accounts": ["acc1"]}
    b = {"key": "b", "phones": ["e2"], "numbers": ["1666", "1777"], "handles": [], "emails": [], "accounts": []}
    assert st.contact_ever(a, b) == 4
    n = len(asked)
    assert st.contact_ever(a, dict(b, numbers=["1777", "1666"])) == 4 and len(asked) == n
    assert st.contact_ever(b, a) == 4 and len(asked) == 2 * n
    want = CaseStore.coverage(st, [a, b], ["d1"])
    asked.clear()
    first = st.coverage([a, b], ["d1"])
    assert first == want and list(first) == list(want)
    first["a"]["phone"].append("changed by a caller")
    n = len(asked)
    assert st.coverage([b, a], ["d1"]) == want and len(asked) == n


def test_the_detectors_reuse_each_records_body_key(monkeypatch):
    """Phone reference 1, 18 Nov: deletions and stock phrases normalised every body again (about 40 s a run)."""
    recs = [msg(f"r{i}", "abz"[i % 3], "h", at(NIGHTS[0], 12, i % 50), "Call me back  NOW", deleted=(i == 4))
            for i in range(30)]
    c = case(recs)
    c._bkey = {id(r): F._body_key(r["body"]) for r in recs}

    class Q:
        def all(self):
            return [("call me back now", 3, 30)]

    c.store = SimpleNamespace(q=lambda *a, **k: Q())
    calls = Counter()
    real = F._norm
    monkeypatch.setattr(F, "_norm", lambda b: (calls.update(["n"]), real(b))[1])
    out = F.stock_phrases(c)
    F.deletions(c)
    assert calls["n"] == 0
    assert out[0]["refs"] == [r["ref"] for r in recs]


def test_a_weighings_held_records_are_found_by_phone_not_by_reading_every_phone():
    """Phone reference 1, 18 Nov: choosing a weighing's held records read every phone's records in each window (27% of
    a weighing after the database reads were held). Other phones' records are not read at all now."""
    touched = Counter()

    class Watched(dict):
        def __getitem__(self, k):
            if getattr(self, "held", False):
                touched[k] += 1
            return dict.__getitem__(self, k)

    t0 = at(NIGHTS[0], 0)
    recs = [{"ref": f"phone_record:a{i}", "kind": "message", "at": t0 + timedelta(minutes=i), "phone": "pha", "owner": "a"}
            for i in range(50)]
    others = [Watched(ref=f"phone_record:h{i}", kind="message", at=t0 + timedelta(minutes=i), phone="phh", owner="h")
              for i in range(500)]
    st = _Held(recs + others)
    everyone = list(PEOPLE.values())
    st.hold(recs + others, t0 - timedelta(days=1), t0 + timedelta(days=2), everyone)
    for r in others:
        r.held = True
    got = st.phone_records([PEOPLE["a"]], [(t0, t0 + timedelta(minutes=20))], everyone)
    assert [r["ref"] for r in got] == [f"phone_record:a{i}" for i in range(21)]
    assert not touched


def test_held_offsets_answer_as_the_database_does():
    """Phone reference 1, 18 Nov: every weighing counted the people's activity rows by offset status (11%)."""
    import random
    rnd = random.Random(5)
    base = at(NIGHTS[0], 0)
    rows = [(e, base + timedelta(minutes=rnd.randrange(0, 60 * 24 * 20)), rnd.choice(["explicit"] * 8 + ["absent", None]))
            for e in ("e1", "e2", "e3") for _ in range(300)]
    rows += [rows[0], rows[0], ("e1", rows[0][1], "absent")]  # the same instant held twice, and with another status

    class R:
        def __init__(self, rs):
            self.rs = rs

        def __iter__(self):
            return iter(self.rs)

    st = object.__new__(F.FinderStore)
    st._activity, st.c = None, {"c": "case"}
    st.db = SimpleNamespace(execute=lambda sql, params, execution_options=None: R(_grouped(rows)))

    def db_rule(phones, windows):
        lo, hi = min(w[0] for w in windows), max(w[1] for w in windows)
        return Counter(s_ for e, t, s_ in rows if e in phones and lo <= t <= hi)
    for _ in range(20):
        phones = rnd.sample(["e1", "e2", "e3", "e9"], rnd.randint(1, 3))
        ws = []
        for _ in range(rnd.randint(1, 3)):
            lo = base + timedelta(hours=rnd.randrange(0, 24 * 20))
            ws.append((lo, lo + timedelta(hours=rnd.randrange(0, 50))))
        assert st.offsets(phones, ws) == db_rule(phones, ws)
    assert st.offsets(["e1"], [(rows[0][1], rows[0][1])]) == db_rule(["e1"], [(rows[0][1], rows[0][1])])


def test_bucket_slices_timed_records_and_tests_only_day_only_ones(monkeypatch):
    """Phone reference 1, 18 Nov: bucket tested every record a day either side of each instance (18% of a weighing).
    Timed records are a slice now; the result is the same records in the same order."""
    import random
    from bisect import bisect_left, bisect_right
    from services.corroborate import signals as S
    rnd = random.Random(6)
    base = at(NIGHTS[0], 0)
    recs = [{"ref": f"r{i}", "kind": rnd.choice(["message", "call", "bank_row"]),
             "at": base + timedelta(minutes=rnd.randrange(0, 60 * 24 * 10)), "day_only": rnd.random() < 0.2}
            for i in range(2000)]
    recs += [dict(recs[5], ref="same-time")]
    insts = []
    for i in range(15):
        lo = base + timedelta(hours=rnd.randrange(0, 24 * 10))
        insts.append({"id": f"i{i}", "start": lo, "end": lo + timedelta(hours=rnd.randrange(0, 20)),
                      "money_end": lo + timedelta(hours=rnd.randrange(20, 80))})

    def old(recs, instances, kinds=None, *, money=False):
        pool = sorted((r for r in recs if kinds is None or r["kind"] in kinds), key=lambda r: r["at"])
        times = [r["at"] for r in pool]
        out = {}
        for inst in instances:
            end = inst["money_end"] if money else inst["end"]
            cand = pool[bisect_left(times, inst["start"] - timedelta(days=1)):bisect_right(times, end + timedelta(days=1))]
            out[inst["id"]] = [r for r in cand if M.in_window(r, inst, money=money)]
        return out
    for kinds, money in ((None, False), ({"message", "call"}, False), ({"bank_row"}, True), (None, True)):
        assert S.bucket(recs, insts, kinds, money=money) == old(recs, insts, kinds, money=money)
    tested = Counter()
    real = M.in_window
    monkeypatch.setattr(M, "in_window", lambda r, i, money=False: (tested.update([r.get("day_only")]), real(r, i, money=money))[1])
    S.bucket(recs, insts)
    assert not tested[False] and tested[True]


class _Conn:
    """A connection that answers the activity and stock-phrase reads, and names who asked."""
    def __init__(self, who, asked, fail=False):
        self.who, self.asked, self.fail = who, asked, fail

    def execute(self, sql, params=None, execution_options=None):
        q = str(sql)
        self.asked.append((self.who, "activity" if "pol_activity_event" in q else "texts" if q == F.TEXTS_SQL else
                           "stock" if "phone_comm_events" in q else q))
        if self.fail:
            raise RuntimeError("connection dropped")
        t = datetime(2025, 3, 7, 21, tzinfo=timezone.utc)
        if "pol_activity_event" in q:
            return iter([("e1", t, "explicit"), ("e1", t, "explicit"), ("e1", t + timedelta(minutes=5), "assumed")])
        if q == F.TEXTS_SQL:
            return iter([("cash is in the van",), ("",), ("the van ok",)])
        return iter([("sent from my phone", 3, 40)])

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _bg_store(fail):
    asked: list = []
    st = F.FinderStore.__new__(F.FinderStore)
    st.c, st._activity, st._bg = {"c": "case-1"}, None, None
    session = _Conn("session", asked)
    session.get_bind = lambda: SimpleNamespace(connect=lambda: _Conn("background", asked, fail))
    st.db = session
    st.q = lambda sql, **k: session.execute(sql, {**st.c, **k})
    return st, asked


def test_the_case_wide_reads_run_on_their_own_connection_and_give_the_inline_answer():
    """Phone reference 1, 18 Nov: the activity read (27 s) and the stock-phrase count (70 s) only wait on the
    database; they now run beside the case read. A failed background read is made inline, with the same answer."""
    st, asked = _bg_store(fail=False)
    st.start_reads()
    st._hold_activity()
    rows = st.stock_rows()
    st.held_texts()
    assert sorted(asked) == [("background", "activity"), ("background", "stock"), ("background", "texts")]  # never the session
    ts, cum, other = st._activity["e1"]
    assert len(ts) == 2 and list(cum) == [0, 2, 3] and list(other) == ["assumed"]
    assert rows == [("sent from my phone", 3, 40)]

    inline, asked2 = _bg_store(fail=True)
    inline.start_reads()
    inline._hold_activity()
    assert inline.stock_rows() == rows and inline._activity == st._activity
    assert inline.held_texts() is None
    assert sorted(asked2) == [("background", "activity"), ("background", "texts"), ("session", "activity"),
                              ("session", "stock")]


def test_a_chunk_is_counted_as_each_text_tested_alone():
    """Fails on the code before: no ``_count_chunk`` (each text was tested phrase by phrase in Python)."""
    import random
    rnd = random.Random(7)
    words = ["cash", "is", "in", "the", "van", "dock", "3", "tonight", "same", "as", "before", "ok"]
    bodies = [" ".join(rnd.choice(words) for _ in range(rnd.randint(0, 30))) for _ in range(400)]
    bodies += ["cash is in", "the van", "", "cash is in the van cash is in the van", "50% off_now \\ ok"]
    lows = ["cash is in", "the van", "in the van", "is in the van cash", "", "50% off", "off_now", "c_sh",
            "van cash", "never said", "ok\x00cash"]
    tests = [F._like_test(lo) for lo in lows]
    want = [sum(1 for b in bodies if t(b)) for t in tests]
    for size in (1, 3, 50, len(bodies)):
        got = [0] * len(lows)
        for k in range(0, len(bodies), size):
            F._count_chunk(bodies[k:k + size], lows, tests, got)
        assert got == want, size
    # a phrase across the end of one text and the start of the next is in neither
    got = [0]
    F._count_chunk(["the cash", "is in"], ["cash is"], [F._like_test("cash is")], got)
    assert got == [0]


def test_phrases_are_counted_from_the_texts_read_once_as_the_database_counts_them():
    """Fails on the code before: no held texts, so every batch of new phrases read all the case's texts again (Phone
    reference 1, 20 Nov: 892 MB per read, 2 streams and 7 one-phrase counts, 167 s of a run)."""
    import random
    rnd = random.Random(11)
    words = ["cash", "is", "in", "the", "van", "dock", "3", "tonight", "café", "naïve", "ok", "😀", "ß"]
    bodies = [" ".join(rnd.choice(words) for _ in range(rnd.randint(0, 25))) for _ in range(500)]
    bodies += ["cash is in", "", "café ok café", "50% off_now \\ ok", "😀😀 the van"]
    lows = ["cash is in", "the van", "café ok", "naïve", "😀 the", "", "50% off", "off_now", "c_sh", "caf_",
            "van cash", "never said", "ß ok", "é"]
    tests = [F._like_test(lo) for lo in lows]
    want = [sum(1 for b in bodies if t(b)) for t in tests]
    for size in (1, 7, len(bodies)):
        got = [0] * len(lows)
        for k in range(0, len(bodies), size):
            packed, count = F._pack(bodies[k:k + size])
            F._count_packed(F.zlib.decompress(packed), count, lows, tests, got)
        assert got == want, size
    got = [0]
    F._count_packed(F.zlib.decompress(F._pack(["the cash", "is in"])[0]), 2, ["cash is"], [F._like_test("cash is")], got)
    assert got == [0]

    # a run holding the texts asks the database only to lower-case the phrases, never to count them
    st, asked = _bg_store(fail=False)
    st._phrase_n = {}
    st.start_reads()
    st.q = lambda sql, **k: (asked.append(("session", sql)), iter([(p.lower(),) for p in k["ps"]]))[1]
    assert st.phrase_counts(["The Van", "cash", "nothing"]) == {"The Van": 2, "cash": 1, "nothing": 0}
    assert st.phrase_counts(["cash", "OK"]) == {"cash": 1, "OK": 1}
    assert all("unnest" in q for w, q in asked if w == "session") and \
        sum(1 for w, _ in asked if w == "session") == 2 and ("background", "texts") in asked


def test_the_statement_files_outside_the_ledger_are_read_once_per_run(monkeypatch):
    """Fails on the code before: each weighing read them again (Phone reference 1, 20 Nov: 110 reads a run)."""
    from services.corroborate.store import CaseStore
    reads = []
    monkeypatch.setattr(CaseStore, "statement_files_outside_ledger", lambda self: reads.append(1) or ["a.pdf (x)"])
    st = F.FinderStore.__new__(F.FinderStore)
    st._statements_outside = None
    first = st.statement_files_outside_ledger()
    first.append("changed by a caller")
    assert st.statement_files_outside_ledger() == ["a.pdf (x)"] and len(reads) == 1


def test_norm_folds_whitespace_as_split_does():
    """Fails on the code before only by being slow; the folding must stay exactly ``split``'s."""
    import sys
    spaces = "".join(chr(c) for c in range(sys.maxunicode + 1) if chr(c).isspace())
    for body in ["", "  a  b ", "A B\x1cC\xa0D", spaces + "Straße" + spaces + "x" + spaces, None, "ΣΑΣ\t\n ok"]:
        assert F._norm(body) == " ".join(str(body or "").split()).casefold()


def test_no_photo_places_leaves_the_records_as_they_are():
    recs = [{"kind": "position", "ref": "phone_record:a"}, {"kind": "message", "ref": "phone_record:b"}]
    assert F.photo_places_as_media(recs, set()) is recs and recs[0]["kind"] == "position"
    assert F.photo_places_as_media(recs, {"phone_record:a"})[0]["kind"] == "media_position"


def test_a_kind_of_row_filters_a_weighings_records_once():
    """Fails on the code before: no ``_only`` (each pair's rows filtered the whole weighing's records again)."""
    from services.corroborate import signals as S
    recs = [{"kind": k, "ref": str(i), "at": datetime(2025, 6, 1, tzinfo=timezone.utc) + timedelta(minutes=i)}
            for i, k in enumerate(["position", "message", "payment", "position"] * 5)]
    a = S._only(recs, "pos", lambda r: r["kind"] == "position")
    assert a is S._only(recs, "pos", lambda r: True)  # the same list for the same records and name
    assert a == [r for r in recs if r["kind"] == "position"]
    assert S._only(list(recs), "pos", lambda r: r["kind"] == "message") != a  # another list is filtered anew

