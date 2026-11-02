"""04-U4 (cb-pol item C): data availability bands and the hourly rollup.

Synthetic phones only. Opt-in PostgreSQL through ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from services.pattern_of_life import activity, availability
from services.phone import identities, registry, sweep
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template, refs
from tests.test_phone_mappings import _shipped, hooks  # noqa: F401 (fixture)

SHIPPED = ["timestamp_meaning", "activity_strength", "attribution", "type"]
DAY = datetime(2023, 3, 14, tzinfo=timezone.utc)


def _stamp(ordinal, field, mt, when, body_path="0.0"):
    return {"o": ordinal, "bp": body_path, "mt": mt, "fn": field, "ot": when.isoformat(), "i": when,
            "os": "explicit", "off": 0, "ft": None, "lw": None}


class Phone:
    def __init__(self):
        self.records, self.stamps, self.o = [], [], 0

    def device_event(self, when, event_type, value=None):
        f = [fld("StartTime", ("TimeStamp", when.isoformat())), fld("EventType", ("DeviceEventTypes", event_type))]
        if value is not None:
            f.append(fld("Value", ("String", value)))
        self.records.append((self.o, None, self.o, model("DeviceEvent", f)))
        self.stamps.append(_stamp(self.o, "StartTime", "DeviceEvent", when))
        self.o += 1

    def incoming_message(self, when):
        top = self.o
        msg = model("InstantMessage", [fld("TimeStamp", ("TimeStamp", when.isoformat())),
                                       refs("From", top + 1, kind="modelField")])
        sender = model("Party", [fld("Identifier", ("String", "+12025550143")), fld("Role", ("PartyRole", "From")),
                                 fld("IsPhoneOwner", ("Boolean", "False"))])
        self.records += [(top, None, top, msg), (top + 1, top, top, sender)]
        self.stamps.append(_stamp(top, "TimeStamp", "InstantMessage", when))
        self.o += 2

    def every(self, start, end, minutes, fn, *args):
        t = start
        while t < end:
            fn(t, *args)
            t += timedelta(minutes=minutes)

    def make(self, c, case, extraction_start=None):
        ext = make_extraction(c, case, self.records, timestamps=self.stamps, metadata={"MSISDN": "+12025550100"})
        if extraction_start is not None:
            c.execute(text(
                "INSERT INTO phone_timestamps (extraction_id, document_index, owner_kind, owner_ordinal, body_path, "
                "model_type, field_name, value_type, original_text, instant, offset_state, parse_rule) VALUES "
                "(:e, 0, 'skeleton', 0, 'skeleton/0', NULL, 'DeviceInfoExtractionStartDateTime', 'TimeStamp', :t, :i, "
                "'explicit', 'synthetic')"), {"e": ext, "t": extraction_start.isoformat(), "i": extraction_start})
        return ext


def build(engine, ext):
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    with engine.begin() as c:
        activity.build(c, ext)
        return availability.compute(c, ext)


def states(engine, ext, start, hours):
    with engine.connect() as c:
        return {h["hour_utc"].hour: h["state"] for h in availability.hour_states(c, ext, start,
                                                                               start + timedelta(hours=hours))}


def setup(hooks):
    _shipped(hooks, SHIPPED)
    identities.install()


@needs_template
def test_a_night_of_screen_events_without_use_is_recording_and_a_night_without_events_is_no_data(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = Phone()
            p.every(DAY + timedelta(hours=12), DAY + timedelta(hours=14), 30, p.device_event, "DeviceLockStatus",
                    "Unlocked")  # unlocks elsewhere on the extraction
            night = DAY + timedelta(hours=23)
            p.every(night, night + timedelta(hours=8), 20, p.device_event, "DisplayOnOff")
            quiet = p.make(c, case)
            q = Phone()
            q.every(DAY + timedelta(hours=12), DAY + timedelta(hours=14), 30, q.device_event, "DeviceLockStatus",
                    "Unlocked")
            empty = q.make(c, case)
        build(engine, quiet)
        build(engine, empty)
        got = states(engine, quiet, night, 8)
        # the last hour's segment ends at 06:40, short of 50 minutes; the 7 hours before are each observed throughout
        assert [got[h] for h in (23, 0, 1, 2, 3, 4, 5)] == ["data_no_interaction"] * 7
        assert got[6] == "no_data"
        assert set(states(engine, empty, night, 8).values()) == {"no_data"}
        assert states(engine, quiet, DAY + timedelta(hours=12), 1)[12] == "interaction"
        with engine.connect() as c:
            sts = {s["stream_key"]: s for s in availability.streams(c, quiet)}
            assert sts["DeviceEvent/-/DeviceLockStatus"]["interaction_capable"] is True
            assert sts["DeviceEvent/-/DisplayOnOff"]["interaction_capable"] is False
            assert sts["DeviceEvent/-/DisplayOnOff"]["max_gap_s"] == 3600
            classes = dict(c.execute(text(
                "SELECT model_type || '/' || coalesce(activity_class, ''), count(*) FROM pv_timeline_entry WHERE "
                "extraction_id = :e GROUP BY 1"), {"e": quiet}).fetchall())
            assert classes == {"DeviceEvent/interaction": 4, "DeviceEvent/device_state": 24}  # 03-6 reads this
            pieces = availability.window_pieces(c, quiet, night, night + timedelta(hours=8))
            assert pieces[0]["state"] == "observed" and pieces[0]["streams"] == ["DeviceEvent/-/DisplayOnOff"]
            assert pieces[-1]["state"] == "no_data"


@needs_template
def test_power_on_without_off_is_an_inferred_switched_off_period(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = Phone()
            p.every(DAY, DAY + timedelta(hours=2), 20, p.device_event, "DisplayOnOff")  # last event 01:40
            p.device_event(DAY + timedelta(hours=6), "PowerEvent", "Power on")
            ext = p.make(c, case)
        out = build(engine, ext)
        assert out["powered_off_inferred"] == 1 and out["power_on_events"] == 1
        with engine.connect() as c:
            inferred = availability.bands(c, ext, DAY, DAY + timedelta(days=1), kinds=("powered_off_inferred",))
            assert [(b["start_utc"], b["end_utc"], b["inferred"]) for b in inferred] == [
                (DAY + timedelta(hours=1, minutes=40), DAY + timedelta(hours=6), True)]
        got = states(engine, ext, DAY, 7)
        assert [got[h] for h in (2, 3, 4, 5)] == ["powered_off_inferred"] * 4
        assert got[0] == "data_no_interaction"


@needs_template
def test_events_after_the_extraction_start_are_flagged_and_messages_never_observe(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            p = Phone()
            p.every(DAY, DAY + timedelta(hours=6), 10, p.incoming_message)  # a message every 10 minutes
            p.device_event(DAY + timedelta(days=2), "DisplayOnOff")
            ext = p.make(c, case, extraction_start=DAY + timedelta(days=1))
        out = build(engine, ext)
        assert out["events_after_extraction_start"] == 1
        assert set(states(engine, ext, DAY, 6).values()) == {"no_data"}  # 36 messages, no observation
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM pol_availability_band WHERE extraction_id = :e AND "
                                  "family = 'messages'"), {"e": ext}).scalar() == 0
            late = c.execute(text("SELECT attribution_flags FROM pol_activity_event WHERE extraction_id = :e AND "
                                  "record_type = 'DeviceEvent'"), {"e": ext}).scalar()
            assert "after_extraction_time" in late
        assert set(states(engine, ext, DAY + timedelta(days=1, hours=1), 3).values()) == {"after_extraction"}


@needs_template
def test_subjects_and_availability_over_http_and_a_phone_of_another_case_is_not_found(hooks):
    import json as _json
    from tests.pattern_pg import api_client
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case, other_case = make_case(c), make_case(c)
            p = Phone()
            p.every(DAY, DAY + timedelta(hours=2), 20, p.device_event, "DisplayOnOff")
            ext = p.make(c, case)
            q = Phone()
            q.device_event(DAY, "DisplayOnOff")
            foreign = q.make(c, other_case)
        build(engine, ext)
        with api_client(engine, case) as client:
            r = client.get("/api/pattern/%s/subjects" % case)
            assert r.status_code == 200
            body = r.json()
            assert body["total_extractions"] == 1 and body["extractions"][0]["projection_status"] == "ready"
            assert body["extractions"][0]["families"] == [{"family": "device_events", "events": 6,
                                                           "first": DAY.isoformat(),
                                                           "last": (DAY + timedelta(minutes=100)).isoformat()}]
            subj = _json.dumps({"kind": "extraction", "extraction_id": str(ext)})
            r = client.get("/api/pattern/%s/availability" % case, params={
                "subject": subj, "start": DAY.isoformat(), "end": (DAY + timedelta(hours=4)).isoformat()})
            assert r.status_code == 200
            ex = r.json()["extractions"][0]
            assert [p["state"] for p in ex["pieces"]] == ["observed", "no_data"]
            assert ex["selection"] == "The production does not state a selection."
            bad = _json.dumps({"kind": "extraction", "extraction_id": str(foreign)})
            assert client.get("/api/pattern/%s/availability" % case, params={
                "subject": bad, "start": DAY.isoformat(), "end": (DAY + timedelta(hours=4)).isoformat()}).status_code == 404
            assert client.get("/api/pattern/%s/availability" % case, params={
                "subject": "not json", "start": DAY.isoformat(), "end": DAY.isoformat()}).status_code == 400
            assert client.get("/api/pattern/%s/availability" % case, params={
                "subject": subj, "start": "2023-03-14T00:00:00", "end": DAY.isoformat()}).status_code == 400
