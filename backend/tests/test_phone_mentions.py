"""Mentions in phone texts (lx-mentions): the word-rule reader, the rule checks per source and the outcome, the model
reader's guard on quoted words, and a person's correction kept beside Loupe's reading. Invented people and places."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services.mentions import checks as C, kinds as K, reader as R, service as S

UTC = timezone.utc
ZONE = "UTC"
HOME = (40.0, -75.0)
CABIN = (41.2, -75.9)   # about 150 km from HOME
MARKET = (40.01, -75.0)


def person(key, label, phones):
    return {"key": key, "label": label, "phones": phones, "names": [label], "numbers": set(), "handles": set(),
            "emails": set(), "accounts": [], "links": []}


PEOPLE = [person("ada", "Ada Quill", ["phA"]), person("ben", "Ben Rook", ["phB"]), person("cy", "Cy Noone", [])]


def at(d, h, m=0):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=UTC)


D = date(2025, 3, 5)  # a Wednesday


def pos(owner, when, lat, lon, rad=10.0, ref=None, media=False):
    return {"ref": ref or f"p:{owner}:{when.isoformat()}", "kind": "media_position" if media else "position", "at": when,
            "phone": "ph" + owner[0].upper(), "owner": owner, "place": {"lat": lat, "lon": lon, "radius_m": rad}}


class FakeData:
    def __init__(self, recs=(), pays=(), uses=None, homes=None, comms=(), docs=()):
        self.recs, self.pays, self.comms, self.docs = list(recs), list(pays), list(comms), list(docs)
        self.uses = uses or {}
        self.homes = homes if homes is not None else {"ada": {"lat": HOME[0], "lon": HOME[1], "radius_m": 150.0,
                                                            "how": "9 positions at night"}}

    def zone(self):
        return ZONE

    def people(self):
        return PEOPLE

    def known_places(self):
        return [{"name": "Gull Cabin", "match": "Gull Cabin", "lat": CABIN[0], "lon": CABIN[1], "radius_m": 300.0, "how": "labelled"}]

    def home(self, k):
        return self.homes.get(k)

    def work(self, k):
        return None

    def phone_records(self, people, lo, hi):
        return [r for r in self.recs if lo <= r["at"] <= hi]

    def activity(self, p, lo, hi):
        return [t for t, *_ in self.uses.get(p["key"], []) if lo <= t <= hi]

    def use_events(self, p, lo, hi):
        return [(t, c, "X") for t, c in self.uses.get(p["key"], []) if lo <= t <= hi]

    def last_position_before(self, p, t, hours=12):
        prev = [r for r in self.recs if r["kind"] == "position" and r["owner"] == p["key"] and r["at"] <= t]
        return prev[-1] if prev else None

    def payments(self, lo_day, hi_day):
        return [p for p in self.pays if lo_day <= p["day"] <= hi_day]

    def ledger_span(self):
        return (date(2025, 1, 1), date(2025, 6, 30))

    def comm_with_words(self, words, lo, hi, exclude_uid=None):
        return [c for c in self.comms if lo <= c["at"] <= hi and any(w.lower() in c["body"].lower() for w in words)]

    def documents_with_words(self, words):
        return [d for d in self.docs if any(w.lower() in d["content"].lower() for w in words)]


def pay(day, words, minor, holder="ADA QUILL"):
    return {"ref": f"financial_transaction:{words}:{day}", "day": day, "amount_minor": minor, "direction": "debit",
            "words": words, "holder": holder, "institution": "Test Bank"}


def read(body, when=None, speaker="ada", addressee=("ben",), known=None):
    return R.read_message(body, at=when or at(D, 19, 12), zone=ZONE, speaker=speaker, addressee=list(addressee),
                          people=PEOPLE, known=FakeData().known_places() if known is None else known)


def run(mention, data, when=None):
    return C.check(data, mention, {"at": (when or at(D, 19, 12)).isoformat(), "record_uid": "u1"})


# ---- reader ----------------------------------------------------------------------------------------------------

def test_a_trip_is_read_with_its_words_the_sender_and_a_forward_window():
    ms = read("Gull Cabin this weekend? I'll drive up Friday night")
    trip = [m for m in ms if m["kind"] == "travel"]
    assert len(trip) == 1
    m = trip[0]
    assert m["phrase"] == "I'll drive up Friday night" and m["who"] == ["ada"] and m["how"] == "driving"
    assert m["when"]["start"].startswith("2025-03-07T18:00") and m["when"]["end"].startswith("2025-03-08T04:00")
    assert m["read_by"] == K.READ_BY and m["reader"] == "rules"
    body = "Gull Cabin this weekend? I'll drive up Friday night"
    assert body[m["start"]:m["end"]] == m["phrase"]


def test_chatter_and_questions_that_assert_nothing_give_no_mention():
    for body in ("lol", "ok", "keep this between us", "did you get the package", "can you send the address again",
                 "that price is too high", "it is about the refunds"):
        assert read(body) == [], body


def test_a_named_place_on_the_map_is_located_and_one_off_it_is_kept_as_words():
    on = read("made it to Gull Cabin!")[0]
    assert on["kind"] == "travel" and on["where"]["located"] and on["where"]["lat"] == CABIN[0]
    off = read("at Marlow Fair, want anything?")[0]
    assert off["kind"] == "at_place" and off["where"] == {"name": "Marlow Fair", "words": "Marlow Fair", "located": False}


def test_you_makes_the_recipient_the_subject_and_money_reads_amounts_and_checks():
    trip = read("before you head up to the lake, leave me the key")[0]
    assert trip["kind"] == "travel" and trip["who"] == ["ben"]
    money = read("done, check 4410 goes out today")[0]
    assert money["kind"] == "money" and money["check_numbers"] == ["4410"]
    refund = read("Ben called about his $85.50 refund")[0]
    assert refund["amounts_minor"] == [8550]


def test_not_tonight_reads_the_next_time_named():
    m = read("not tonight, tomorrow works")[0]
    assert m["when"]["start"].startswith("2025-03-06T00:00")


def test_a_placeholder_label_never_names_a_person():
    people = [dict(person("x", "the user of Phone 9 (+15550000)", ["phX"]), names=[])]
    ms = R.read_message("the invoice goes out Friday", at=at(D, 12), zone=ZONE, speaker="x", addressee=[], people=people, known=[])
    assert ms and ms[0]["who"] == ["x"]


# ---- checks ----------------------------------------------------------------------------------------------------

def _trip(body="I'll drive up to Gull Cabin Friday night"):
    return read(body)[0]


def test_a_precise_position_at_the_place_and_a_payment_naming_it_fit_fairly_strongly():
    fri = date(2025, 3, 7)
    data = FakeData(recs=[pos("ada", at(fri, 22), *CABIN)], pays=[pay(date(2025, 3, 10), "GULL CABIN RENTALS", 38000)])
    res = run(_trip(), data)
    assert res["outcome"] == "fits_strongly" and res["label"] == "Fits, fairly strongly"
    srcs = {c["source"]: c["verdict"] for c in res["checks"]}
    assert srcs["places"] == "fits" and srcs["financial"] == "fits"
    assert "2 independent sources agree" == res["basis"]


def test_a_cell_tower_position_says_near_not_at_and_fits_only_weakly():
    fri = date(2025, 3, 7)
    data = FakeData(recs=[pos("ada", at(fri, 22), *CABIN, rad=2500.0)])
    res = run(_trip(), data)
    assert res["outcome"] == "fits_weakly"
    c = res["checks"][0]
    assert c["verdict"] == "fits_weakly" and "near" in c["text"] and "cell towers" in c["note"]


def test_precise_positions_far_from_the_place_contradict():
    fri = date(2025, 3, 7)
    data = FakeData(recs=[pos("ada", at(fri, 20), *HOME), pos("ada", at(fri, 23), *HOME)])
    res = run(_trip(), data)
    assert res["outcome"] == "contradicts"
    assert res["checks"][0]["source"] == "places" and "elsewhere" in res["checks"][0]["text"]


def test_no_positions_is_not_evidence_either_way():
    res = run(_trip(), FakeData())
    assert res["outcome"] == "cant_tell"
    assert any("positions" in w for w in res["would_test"])


def test_a_photo_place_is_never_counted_as_the_phone_position():
    fri = date(2025, 3, 7)
    data = FakeData(recs=[pos("ada", at(fri, 22), *CABIN, media=True)])
    res = run(_trip(), data)
    places = [c for c in res["checks"] if c["source"] == "places"]
    assert places and places[0]["verdict"] == "nothing"
    photos = [c for c in res["checks"] if c["source"] == "photos"]
    assert photos and photos[0]["verdict"] == "fits_weakly" and "camera" in photos[0]["note"]
    assert res["outcome"] == "fits_weakly"


def test_phone_was_off_is_contradicted_by_the_owner_using_it():
    sent = at(D, 21)
    m = read("phone was off, sorry", when=sent)[0]
    assert m["kind"] == "home_away"
    used = FakeData(uses={"ada": [(sent - timedelta(hours=2), "interaction"), (sent - timedelta(hours=1), "interaction")]})
    assert run(m, used, sent)["outcome"] == "contradicts"
    quiet = FakeData(uses={})
    res = run(m, quiet, sent)
    assert res["outcome"] == "fits_weakly" and "Absence" in res["checks"][0]["note"]


def test_phone_was_off_does_not_count_the_message_saying_so():
    """Sending "phone was off, sorry" is itself use of the phone: on a real case the only owner use in the window was
    that message, and with two passive records it made a contradiction out of the message itself."""
    sent = at(D, 21)
    m = read("phone was off, sorry", when=sent)[0]
    own = FakeData(uses={"ada": [(sent - timedelta(minutes=14), "passive"), (sent - timedelta(minutes=13), "passive"),
                                 (sent, "interaction"), (sent - timedelta(seconds=40), "interaction")]})
    res = run(m, own, sent)
    assert res["outcome"] != "contradicts"
    dev = [c for c in res["checks"] if c["source"] == "device"][0]
    assert dev["verdict"] == "context" and "sending of this message is left out" in dev["note"]


def test_in_bed_all_day_is_contradicted_by_precise_positions_away_from_home():
    sent = at(D, 8, 10)
    ms = read("Not coming in, in bed all day with this flu", when=sent)
    assert [x["kind"] for x in ms] == ["home_away", "home_away"]
    m = ms[1]
    assert m["phrase"] == "in bed all day with this flu"
    data = FakeData(recs=[pos("ada", at(D, 14, 5), 40.2, -75.0), pos("ada", at(D, 16, 50), 40.2, -75.0)])
    res = run(m, data, sent)
    assert res["outcome"] == "contradicts"


def test_a_check_number_in_the_ledger_fits_closely_and_a_missing_amount_is_not_a_contradiction():
    m = read("done, check 4410 goes out today", when=at(D, 15))[0]
    hit = run(m, FakeData(pays=[pay(D + timedelta(days=1), "CHECK 4410", 8500, "QUILL DENTAL PC")]), at(D, 15))
    assert hit["outcome"] == "fits_strongly" and "check 4410" in hit["checks"][0]["note"]
    miss = run(m, FakeData(), at(D, 15))
    assert miss["outcome"] == "cant_tell" and miss["checks"][0]["verdict"] == "nothing"


def test_meeting_contradicted_only_with_enough_positions_apart():
    m = read("see you at 7", when=at(D, 12))[0]
    assert m["kind"] == "meeting" and m["with"] == ["ben"]
    seven = at(D, 19)
    one_each = FakeData(recs=[pos("ada", seven, *HOME), pos("ben", seven, *CABIN)])
    assert run(m, one_each, at(D, 12))["outcome"] == "cant_tell"
    apart = FakeData(recs=[pos(k, seven + timedelta(minutes=i * 10), *(HOME if k == "ada" else CABIN)) for k in ("ada", "ben")
                           for i in range(3)])
    assert run(m, apart, at(D, 12))["outcome"] == "contradicts"
    together = FakeData(recs=[pos("ada", seven, *HOME), pos("ben", seven + timedelta(minutes=5), HOME[0] + 0.0005, HOME[1])])
    assert run(m, together, at(D, 12))["outcome"] == "fits_strongly"


def test_deleted_items_still_marked_deleted_on_a_phone_fit():
    m = read("delete the Brindle emails", when=at(D, 12))[0]
    assert m["kind"] == "deleted" and "Brindle" in m["words"]
    comms = [{"ref": "phone_record:e1", "kind": "email", "at": at(D, 9), "body": "Brindle invoice", "deleted": True}]
    res = run(m, FakeData(comms=comms), at(D, 12))
    assert res["outcome"] == "fits_strongly" and res["checks"][0]["source"] == "messages"


def test_outcome_rules():
    def c(src, v, strong=False):
        return C._chk(src, v, "t", strong=strong)
    assert C.outcome([c("places", "contradicts"), c("financial", "fits")])[0] == "contradicts"
    assert C.outcome([c("places", "contradicts_weakly")])[0] == "contradicts_weakly"
    assert C.outcome([c("places", "contradicts_weakly"), c("financial", "fits")])[0] == "cant_tell"
    assert C.outcome([c("places", "fits"), c("photos", "fits_weakly")])[0] == "fits_strongly"
    assert C.outcome([c("places", "fits_weakly"), c("device", "fits_weakly")])[0] == "fits_weakly"
    assert C.outcome([c("places", "context"), c("photos", "nothing")])[0] == "cant_tell"
    assert set(K.OUTCOME_LABELS) == set(K.OUTCOMES)


def test_every_reason_is_written_to_the_standard():
    from services import writing_standard
    fri = date(2025, 3, 7)
    data = FakeData(recs=[pos("ada", at(fri, 22), *CABIN, rad=2500.0)], pays=[pay(date(2025, 3, 10), "GULL CABIN RENTALS", 38000)])
    res = run(_trip(), data)
    texts = [res["why"], res["basis"]] + [x for ch in res["checks"] for x in (ch["text"], ch["note"])] + [h["how"] for h in K.HOW]
    for t in texts:
        assert not writing_standard.find_problems(t), (t, writing_standard.find_problems(t))


# ---- model reader ----------------------------------------------------------------------------------------------

def test_the_model_reader_drops_words_not_in_the_text_and_reads_times_by_rules(monkeypatch):
    from services.mentions import model_reader as MR
    reader = MR.ModelReader(None, zone=ZONE, people=PEOPLE, known=FakeData().known_places())
    reply = {0: [{"kind": "travel", "words": "I'll drive up Friday night", "about": "sender", "place_words": "Gull Cabin",
                  "time_words": "Friday night"},
                 {"kind": "meeting", "words": "met the mayor at noon", "about": "sender"},
                 {"kind": "invented", "words": "Gull Cabin"}]}
    monkeypatch.setattr(reader, "_call", lambda bodies: reply)
    t = {"record_uid": "u1", "body": "Gull Cabin this weekend? I'll drive up Friday night", "at": at(D, 19, 12),
         "speaker": "ada", "addressee": ["ben"]}
    got = reader.read_page([t])["u1"]
    assert len(got) == 1
    m = got[0]
    assert m["reader"] == "model" and m["where"]["located"] and m["when"]["start"].startswith("2025-03-07T18:00")
    assert t["body"][m["start"]:m["end"]] == m["phrase"]


def test_the_model_reader_builds_its_prompt_through_the_writing_standard(monkeypatch):
    from services import writing_standard
    from services.mentions import model_reader as MR
    seen = {}

    class Ctx:
        last_usage = {"prompt_tokens": 10, "completion_tokens": 5}
        system_context = None

        def call(self, prompt, temperature=0, json_mode=False):
            seen["system"], seen["prompt"] = self.system_context, prompt
            return json.dumps({"texts": [{"i": 0, "mentions": []}]})

    import services.llm_service as L
    monkeypatch.setattr(L.LLMService, "__init__", lambda self: None)
    monkeypatch.setattr(L.LLMService, "create_context", lambda self, *a, **k: Ctx())
    r = MR.ModelReader(None, zone=ZONE, people=PEOPLE, known=[])
    assert r._call(["on my way"]) == {0: []}
    assert writing_standard.MARKER in seen["system"] and r.calls == 1 and r.tokens_in == 10


# ---- a person's correction -------------------------------------------------------------------------------------

def test_a_correction_is_used_and_the_reading_stays_beside_it():
    row = SimpleNamespace(reading={"kind": "travel", "who": ["ada"], "when": {"start": "a", "end": "b"}},
                          corrected={"who": ["ben"]}, corrected_fields=["who"])
    eff = S.effective(row)
    assert eff["who"] == ["ben"] and eff["kind"] == "travel"
    assert row.reading["who"] == ["ada"]


def test_copies_of_one_message_share_a_copy_key_to_the_minute():
    a = S.copy_key("Made it  to Gull Cabin", at(D, 10, 0) + timedelta(seconds=5))
    b = S.copy_key("made it to gull cabin", at(D, 10, 0) + timedelta(seconds=40))
    assert a == b and a != S.copy_key("made it to gull cabin", at(D, 10, 2))


def test_the_evening_place_is_the_busiest_spot_with_enough_positions():
    from services.mentions.data import busiest_spot
    pts = [(40.2899, -76.8612)] * 6 + [(41.3, -77.6)] * 3
    spot = busiest_spot(pts, "Ada Quill", "between 7 pm and 6 am")
    assert spot and abs(spot["lat"] - 40.2899) < 1e-6 and spot["positions"] == 6 and "7 pm" in spot["how"]
    assert busiest_spot(pts[:4], "Ada Quill", "x") is None


def test_money_with_no_account_for_the_speaker_says_an_account_would_test_it():
    m = read("refunds cleared", when=at(D, 19))[0]
    res = run(m, FakeData(), at(D, 19))
    assert res["outcome"] == "cant_tell" and any("joined to a bank account" in w for w in res["would_test"])


def test_reading_a_phone_again_rechecks_the_mentions_it_already_holds(monkeypatch):
    """A stored mention found again is not duplicated; its outcome is worked out afresh from its effective values, so a
    rule change reaches mentions found before it, and a person's correction is what gets checked."""
    sent = at(D, 21)
    t = {"record_uid": "u1", "body": "phone was off, sorry", "at": sent, "speaker": "ada", "addressee": ["ben"], "kind": "message"}
    m = read(t["body"], when=sent)[0]
    stored = SimpleNamespace(record_uid="u1", start=m["start"], reading=m, corrected={"kind": "plan"}, context={"at": sent.isoformat()},
                             outcome="contradicts", result=None, checked_at=None)

    class Rows:
        def scalars(self):
            return [stored]

    added = []
    db = SimpleNamespace(execute=lambda *_a, **_k: Rows(), add=added.append)
    seen = []
    monkeypatch.setattr(S.C, "check", lambda data, mention, ctx: seen.append(mention["kind"]) or {"outcome": "cant_tell"})
    run = SimpleNamespace(case_id="c", reader="rules", extraction_id="e", id="r")
    n = S._read_page(db, FakeData(), run, [t], PEOPLE, ZONE, [], None)
    assert n == 1 and added == []   # found again, counted, not stored twice
    assert stored.outcome == "cant_tell" and stored.checked_at is not None and seen == ["plan"]
