from datetime import datetime, timedelta, timezone

from services.relations import rules

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def item(ref, at, **kw):
    return {"ref": ref, "type": kw.pop("type", "financial_transaction"), "label": kw.pop("label", ref),
            "at": at.isoformat() if at else None, **kw}


BASE = {"period_days": 100, "days_with": {"financial_transaction": 10, "phone_message": 90}}


def test_time_proximity_orders_and_states_chance():
    a = item("m", T0, type="phone_message")
    b = item("p", T0 + timedelta(minutes=30))
    c, s = rules.time_proximity([a, b], BASE)
    assert c[0]["strength"] == "strong" and c[0]["detail"]["first"] == "m"
    assert "10 of 100 days" in c[0]["chance"]["words"] and "90 of 100" in c[0]["chance"]["words"]
    assert c[0]["chance"]["reading"] == "uncommon"


def test_day_precision_caps_at_moderate_and_far_is_searched_no_link():
    a = item("m", T0, type="phone_message")
    b = item("p", T0 + timedelta(minutes=5), precision="day")
    c, _ = rules.time_proximity([a, b], BASE)
    assert c[0]["strength"] == "moderate"
    far = item("q", T0 + timedelta(days=200))
    c, s = rules.time_proximity([a, far], BASE)
    assert not c and "31 days" in s[0]["searched"]


def test_shared_company_name_document_and_ledger():
    doc = item("d", None, type="evidence", identifiers=rules.extract_identifiers("Contract with Harbor Trading LLC."))
    pay = item("p", T0, names=["HARBOR TRADING LLC"])
    other = item("x", T0, names=["Someone Else"])
    c, s = rules.shared_identifiers([doc, pay, other], lambda k, v: {"count": 3, "base": 3200, "unit": "ledger rows"})
    assert len(c) == 1 and c[0]["strength"] == "strong" and "3 of 3,200 ledger rows" in c[0]["chance"]["words"]
    assert len(s) == 2  # the two pairs with the unrelated payment are searched, no link


def test_payment_and_meeting_sharing_nothing_is_no_link():
    meet = item("m", T0, type="phone_record", identifiers=[{"kind": "number", "value": "+1 555 010 2233"}])
    pay = item("p", T0 + timedelta(days=90), names=["Acme"])
    assert not rules.time_proximity([meet, pay], BASE)[0]
    c, s = rules.shared_identifiers([meet, pay], lambda k, v: None)
    assert not c and s


def test_place_overlap_busy_place_reads_as_chance():
    pl = {"lat": 51.5, "lon": -0.12, "radius_m": 50, "source": "wifi"}
    a = item("a", T0, type="phone_record", place=pl, phone="A")
    b = item("b", T0 + timedelta(minutes=5), type="phone_record", place=dict(pl, lat=51.5002), phone="B")
    stats = lambda lat, lon, r: {"phones_near": 4, "phones_total": 5, "days_at_place": {}, "days_active": {}}
    c, _ = rules.place_overlap([a, b], stats)
    assert c[0]["chance"]["reading"] == "ordinary" and "4 of 5 phones" in c[0]["chance"]["words"]
    assert c[0]["strength"] == "moderate" and "wifi" in " ".join(c[0]["reasons"])


def test_place_far_apart_is_no_link():
    a = item("a", T0, place={"lat": 51.5, "lon": -0.12, "radius_m": 20, "source": "gps"}, phone="A")
    b = item("b", T0, place={"lat": 52.5, "lon": -0.12, "radius_m": 20, "source": "gps"}, phone="B")
    c, s = rules.place_overlap([a, b], lambda *x: {})
    assert not c and s


def test_relay_chain():
    ev = [{"phone": "A", "at": T0.isoformat(), "counterpart": "C"},
          {"phone": "B", "at": (T0 + timedelta(minutes=3)).isoformat(), "counterpart": "C"},
          {"phone": "B", "at": (T0 + timedelta(hours=3)).isoformat(), "counterpart": "D"}]
    c, n = rules.relay_chains(ev, ["A", "B"])
    assert len(c) == 1 and c[0]["strength"] == "moderate" and n["events_read"] == 3
    assert not rules.relay_chains(ev, ["A"])[0]


def test_shared_silence_ordinary_night_is_faint():
    def day(d, hours):
        return [T0.replace(hour=h) + timedelta(days=d) for h in hours]
    a = sum((day(d, range(8, 21)) for d in range(5)), [])
    b = sum((day(d, range(9, 22)) for d in range(5)), [])
    c, n = rules.shared_silence({"A": a, "B": b})
    assert len(c) == 1 and c[0]["strength"] == "faint" and c[0]["detail"]["count"] > 1


def test_sequence_names_the_order():
    items = [item("m1", T0, type="phone_message", label="message"), item("m", T0 + timedelta(hours=20), type="phone_record", label="meeting"),
             item("p", T0 + timedelta(days=1, hours=20), label="payment")]
    s = rules.sequences(items, BASE)
    assert s and "message then meeting then payment" in s[0]["reasons"][0]


def test_a_one_off_meeting_at_a_busy_place_is_weak_and_reads_as_chance():
    pl = {"lat": 39.3105, "lon": -76.7448, "radius_m": 15, "source": "device_location"}
    a = item("a", T0, type="phone_record", place=pl, phone="A")
    b = item("b", T0 + timedelta(minutes=3), type="phone_record", place=dict(pl, radius_m=25), phone="B")
    stats = lambda lat, lon, r: {"phones_near": 2, "phones_total": 6, "days_at_place": {}, "days_active": {}}
    once = lambda pa, pb: {"days_together": 1, "days_both_active": 113}
    c, _ = rules.place_overlap([a, b], stats, pair_stats=once)
    assert c[0]["strength"] == "weak" and c[0]["chance"]["reading"] == "ordinary"
    assert "1 of the 113 days" in c[0]["chance"]["words"]
    often = lambda pa, pb: {"days_together": 5, "days_both_active": 40}
    c, _ = rules.place_overlap([a, b], stats, pair_stats=often)
    assert c[0]["strength"] == "strong" and c[0]["chance"]["reading"] != "ordinary"


def test_a_date_only_item_never_claims_an_order_within_its_day():
    msg = item("m", T0, type="phone_message")
    pay = item("p", T0 - timedelta(hours=5), precision="day", label="payment")
    c, _ = rules.time_proximity([msg, pay], BASE)
    assert "comes first" not in c[0]["reasons"][0] and "first" not in c[0]["detail"]
    assert "order within a day is not in the records" in " ".join(c[0]["reasons"])
    seq = rules.sequences([item("a", T0, type="phone_message", label="msg"), pay,
                           item("c", T0 + timedelta(hours=30), type="phone_record", label="meeting")], BASE)
    assert "date only" in seq[0]["reasons"][0]


def test_two_phone_positions_are_compared_by_place_never_by_time_taken():
    a = item("a", T0, type="phone_record", time_kind="phone_location", phone="A")
    b = item("b", T0 + timedelta(minutes=15), type="phone_record", time_kind="phone_location", phone="B")
    c, s = rules.time_proximity([a, b], BASE)
    assert not c and "compared by place" in s[0]["searched"]


def test_a_whatsapp_address_is_a_number_not_an_email():
    found = rules.extract_identifiers("from 14105550121@s.whatsapp.net and ann@example.org")
    assert {(f["kind"], f["value"]) for f in found} == {("number", "14105550121"), ("email", "ann@example.org")}


def test_two_positions_of_one_phone_are_a_stay_not_an_overlap():
    pl = {"lat": 39.3, "lon": -76.7, "radius_m": 10, "source": "device_location"}
    a = item("a", T0, type="phone_record", place=pl, phone="A")
    b = item("b", T0 + timedelta(hours=5), type="phone_record", place=pl, phone="A")
    c, s = rules.place_overlap([a, b], lambda *x: {})
    assert not c and "same phone" in s[0]["searched"]
