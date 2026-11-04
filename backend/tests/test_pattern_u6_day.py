"""04-U6 (cb-pol item D): the Day view and the lanes window.

Synthetic phones only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

import json
from datetime import timedelta

from services.pattern_of_life import day
from services.phone import registry
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_pattern_u4_availability import DAY, setup
from tests.test_pattern_u5_places import PlacePhone, build
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)


def _phone():
    p = PlacePhone()
    p.device_event(DAY + timedelta(hours=9), "DeviceLockStatus", "Unlocked")
    p.every(DAY + timedelta(hours=1), DAY + timedelta(hours=5), 20, p.device_event, "DisplayOnOff")
    p.incoming_message(DAY + timedelta(hours=10))
    p.location(DAY + timedelta(hours=11), accuracy=10)
    return p


@needs_template
def test_the_day_view_puts_every_item_in_its_lane_and_states_availability(hooks):
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = _phone().make(c, case)
        build(engine, ext)
        subj = json.dumps({"kind": "extraction", "extraction_id": str(ext)})
        with api_client(engine, case) as client:
            r = client.get("/api/pattern/%s/day" % case, params={"subject": subj, "date": DAY.date().isoformat(),
                                                                  "zone": "UTC"})
            assert r.status_code == 200, r.text
            out = r.json()
            t = out["totals"]
            assert t["interaction"] == 1 and t["device_state"] == 12 and t["communications"] == 1
            assert t["places"] == 1 and t["money"] == 0
            assert out["truncated"] is False and out["passive_as_hourly_counts"] is False
            assert out["flag_words"]["affiliation_unknown"] == "Not known whether this device recorded it."
            assert out["flag_words"]["wearable"] == "Recorded by a paired wearable."
            assert len(out["availability"][0]["hours"]) == 24
            words = {h["words"] for h in out["availability"][0]["hours"]}
            assert "No data" in words
            it = out["lanes"]["interaction"][0]
            assert it["record_uid"] and it["field"] == "StartTime" and it["phone"]
            msg = out["lanes"]["communications"][0]
            assert msg["parties"] and msg["parties"][0]["identifier"]
            # the phone's own side, implied when the record names no owner, is not listed as the other party
            assert all(p["role"] != "owner_implicit" for p in msg["parties"])
            w = client.get("/api/pattern/%s/window" % case, params={"at": (DAY + timedelta(hours=9)).isoformat(),
                                                                     "span": "1h", "zone": "UTC"}).json()
            assert w["phones_total"] == 1 and w["phones"][0]["totals"]["interaction"] == 1
            assert w["phones"][0]["totals"]["communications"] == 0  # 10:00 is outside 08:00 to 10:00
            ev = client.get("/api/pattern/%s/events" % case, params={
                "subject": subj, "start": DAY.isoformat(), "end": (DAY + timedelta(days=1)).isoformat()}).json()
            assert ev["total"] == ev["returned"] == sum(t[k] for k in ("interaction", "device_state", "passive",
                                                                        "others"))


@needs_template
def test_a_crowded_window_returns_passive_items_as_hourly_counts_and_says_so(hooks, monkeypatch):
    setup(hooks)
    monkeypatch.setattr(day, "PASSIVE_LIMIT", 3)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = _phone().make(c, case)
        build(engine, ext)
        with engine.connect() as c:
            out = day.window(c, [ext], {}, DAY, DAY + timedelta(days=1))
        assert out["passive_as_hourly_counts"] is True and "Show all" in out["limit_words"]
        assert out["totals"]["passive"] == sum(h["count"] for h in out["passive_hours"])
        assert out["totals"]["interaction"] == 1  # other lanes keep every item


@needs_template
def test_the_window_over_every_phone_uses_the_case_zone_and_says_on_what_basis(hooks):
    """The window covers several phones, so it is drawn in the case zone of 03 section 4.6, not the first phone's."""
    from sqlalchemy import text
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            _phone().make(c, case)
        at = (DAY + timedelta(hours=9)).isoformat()
        with api_client(engine, case) as client:
            unset = client.get("/api/pattern/%s/window" % case, params={"at": at, "span": "1h"}).json()
            assert unset["zone"] == "UTC" and unset["zone_basis"] == "utc_default"
            with engine.begin() as c:
                c.execute(text("INSERT INTO case_display_settings (case_id, time_zone, updated_by) SELECT id, "
                               "'America/New_York', owner_user_id FROM cases WHERE id = :c"), {"c": case})
            out = client.get("/api/pattern/%s/window" % case, params={"at": at, "span": "1h"}).json()
            assert out["zone"] == "America/New_York" and out["zone_basis"] == "case_setting"
            chosen = client.get("/api/pattern/%s/window" % case, params={"at": at, "span": "1h", "zone": "UTC"}).json()
            assert chosen["zone"] == "UTC" and chosen["zone_basis"] == "chosen"


@needs_template
def test_a_messages_other_parties_are_listed_senders_first_and_the_phones_own_side_is_not(hooks):
    from tests.pattern_pg import api_client
    from tests.phone_pg import fld, make_extraction, model, refs
    from tests.test_pattern_u4_availability import _stamp
    setup(hooks)
    records, stamps = [], []
    for n in range(5):  # five messages: each order of uuids is a fresh chance for the old ordering to differ
        top, when = n * 3, DAY + timedelta(hours=9, minutes=n)
        records += [(top, None, top, model("InstantMessage", [fld("TimeStamp", ("TimeStamp", when.isoformat())),
                                                               refs("From", top + 1, kind="modelField"),
                                                               refs("To", top + 2)])),
                    (top + 1, top, top, model("Party", [fld("Identifier", ("String", "+1202555014%d" % n)),
                                                        fld("Role", ("PartyRole", "From")),
                                                        fld("IsPhoneOwner", ("Boolean", "False"))])),
                    (top + 2, top, top, model("Party", [fld("Identifier", ("String", "+1202555015%d" % n)),
                                                        fld("Role", ("PartyRole", "To")),
                                                        fld("IsPhoneOwner", ("Boolean", "False"))]))]
        stamps.append(_stamp(top, "TimeStamp", "InstantMessage", when))
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = make_extraction(c, case, records, timestamps=stamps, metadata={"MSISDN": "+12025550100"})
        build(engine, ext)
        with api_client(engine, case) as client:
            out = client.get("/api/pattern/%s/day" % case, params={
                "subject": json.dumps({"kind": "extraction", "extraction_id": str(ext)}),
                "date": DAY.date().isoformat(), "zone": "UTC"}).json()
        msgs = out["lanes"]["communications"]
        assert len(msgs) == 5
        for m in msgs:
            assert [p["role"] for p in m["parties"]] == ["sender", "recipient"], m["parties"]


@needs_template
def test_a_payment_with_a_date_and_no_time_opens_its_whole_day_in_the_case_zone(hooks):
    """07 J-5 failure state: a date-only anchor opens the whole calendar day (in the case zone), never a time of day."""
    from sqlalchemy import text
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            _phone().make(c, case)
            c.execute(text("INSERT INTO case_display_settings (case_id, time_zone, updated_by) SELECT id, "
                           "'America/New_York', owner_user_id FROM cases WHERE id = :c"), {"c": case})
        with api_client(engine, case) as client:
            w = client.get("/api/pattern/%s/window" % case, params={"span": "day", "day": "2023-11-08"}).json()
            assert w["date_only"] == "2023-11-08" and w["span"] == "day" and w["zone"] == "America/New_York"
            assert w["start"].startswith("2023-11-08T00:00:00") and w["start"].endswith("-05:00")
            assert w["end"].startswith("2023-11-09T00:00:00")
            # a day the clocks change is 25 hours long, still from midnight to midnight
            dst = client.get("/api/pattern/%s/window" % case, params={"span": "day", "day": "2023-11-05"}).json()
            assert dst["start"].endswith("-04:00") and dst["end"].endswith("-05:00")
            assert client.get("/api/pattern/%s/window" % case, params={"span": "day", "day": "8 Nov"}).status_code == 400
            timed = client.get("/api/pattern/%s/window" % case, params={"at": DAY.isoformat(), "span": "1h"}).json()
            assert timed["date_only"] is None


@needs_template
def test_an_hour_holding_only_a_notification_never_reads_no_data_and_the_item_says_its_family(hooks):
    """cb-crossev m110311471222822 (live d9945277, 2023-11-08): a bank alert at 10:00 is a record of the phone; the
    hour stays not-observed (notifications never establish recording, 04 5.3 step 4) but is never called "No data"."""
    from services.pattern_of_life import availability
    from tests.test_pattern_u4_availability import _stamp
    from tests.phone_pg import fld, model
    setup(hooks)
    p = _phone()
    when = DAY + timedelta(hours=14)
    p.records.append((p.o, None, p.o, model("Notification", [fld("TimeStamp", ("TimeStamp", when.isoformat())),
                                                              fld("Body", ("String", "You paid 390.02 USD"))])))
    p.stamps.append(_stamp(p.o, "TimeStamp", "Notification", when))
    p.o += 1
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = p.make(c, case)
        build(engine, ext)
        with engine.connect() as c:
            out = day.window(c, [ext], {}, DAY, DAY + timedelta(days=1))
        hours = {h["hour_utc"].hour: h for h in out["availability"][0]["hours"]}
        assert hours[14]["state"] == "no_data" and hours[14]["has_records"] is True
        assert hours[14]["words"] == availability.RECORDS_NO_RECORDING_WORDS
        assert hours[20]["words"] == "No data" and hours[20]["has_records"] is False
        note = [i for i in out["lanes"]["passive"] if i["record_type"] == "Notification"]
        assert len(note) == 1 and note[0]["family"] == "notifications"
