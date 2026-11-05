"""04-U2 and 04-U3 (cb-pol items A and B): activity events, their strength, and attribution flags.

Synthetic phones only, built in the test (04 section 12). PostgreSQL tests are opt-in through
``LOUPE_TEST_PHONE_PG_TEMPLATE_URL`` (``tests/phone_pg.py``).
"""
from __future__ import annotations

import copy
import json
import os
import pytest

from sqlalchemy import text

from services.pattern_of_life import activity
from services.pattern_of_life import attribution as A
from services.phone import identities, registry, sweep
from services.phone.mappings import loader
from tests.phone_pg import fld, fresh_engine, make_case, make_extraction, model, needs_template, refs
from tests.test_phone_mappings import _shipped, hooks, write  # noqa: F401 (fixture)

SHIPPED = ["timestamp_meaning", "activity_strength", "attribution", "type"]
OWNER = "+12025550100"
OTHER = "+12025550143"


def ts(ordinal, body_path, field, mt, text_value="2023-03-14T15:07:12-04:00", offset="explicit"):
    from datetime import datetime, timezone
    inst = datetime(2023, 3, 14, 19, 7, 12, tzinfo=timezone.utc) if offset == "explicit" else None
    wall = None if offset == "explicit" else datetime(2023, 3, 14, 15, 7, 12)
    return {"o": ordinal, "bp": body_path, "mt": mt, "fn": field, "ot": text_value, "i": inst, "os": offset,
            "off": -240 if offset == "explicit" else None, "ft": None, "lw": wall}


def message(top, *, platform=None, deleted="Intact", confidence="High", other_reads=False, source=None, folder=None):
    """An outgoing message: From party is the owner. Records top..top+2."""
    f = [fld("TimeStamp", ("TimeStamp", "2023-03-14T15:07:12-04:00")), refs("From", top + 1, kind="modelField"),
         refs("To", top + 2)]
    if platform:
        f.append(fld("Platform", ("Platform", platform)))
    if source:
        f.append(fld("Source", ("String", source)))
    if folder:
        f.append(fld("Folder", ("String", folder)))
    msg = model("InstantMessage", f, deleted_state=deleted, decoding_confidence=confidence)
    sender = model("Party", [fld("Identifier", ("String", OWNER)), fld("Role", ("PartyRole", "From")),
                             fld("IsPhoneOwner", ("Boolean", "True"))])
    to_f = [fld("Identifier", ("String", OTHER)), fld("Role", ("PartyRole", "To")),
            fld("IsPhoneOwner", ("Boolean", "False"))]
    stamps = [ts(top, "0.0", "TimeStamp", "InstantMessage")]
    if other_reads:
        to_f.append(fld("DateRead", ("TimeStamp", "2023-03-14T15:09:00-04:00")))
        stamps.append(ts(top + 2, "3.0", "DateRead", "Party"))
    rec = model("Party", to_f)
    return [(top, None, top, msg), (top + 1, top, top, sender), (top + 2, top, top, rec)], stamps


def device_event(top, event_type, value=None, offset="explicit", user_mapping=None):
    f = [fld("StartTime", ("TimeStamp", "2023-03-14T15:07:12-04:00" if offset == "explicit"
                           else "2023-03-14T15:07:12.000")),
         fld("EventType", ("DeviceEventTypes", event_type))]
    if value is not None:
        f.append(fld("Value", ("String", value)))
    if user_mapping is not None:
        f.append(fld("UserMapping", ("DecodingSourceOptions", user_mapping)))
    return [(top, None, top, model("DeviceEvent", f))], [ts(top, "0.0", "StartTime", "DeviceEvent", offset=offset)]


def location(top, affiliation):
    f = [fld("TimeStamp", ("TimeStamp", "2023-03-14T15:07:12-04:00")),
         fld("DeviceLocationAffiliation", ("DeviceLocationAffiliation", affiliation))]
    return [(top, None, top, model("Location", f))], [ts(top, "0.0", "TimeStamp", "Location")]


def phone(c, case, parts, zone=None):
    records, stamps = [], []
    for r, s in parts:
        records += r
        stamps += s
    ext = make_extraction(c, case, records, timestamps=stamps, metadata={"MSISDN": OWNER})
    if zone:
        c.execute(text("UPDATE phone_extractions SET device_zone = :z WHERE id = :e"), {"z": zone, "e": ext})
    return ext


def events(c, ext):
    return {(r.record_type, r.time_field, r.ordinal): r for r in c.execute(text(
        "SELECT v.*, t.ordinal FROM pol_activity_event_v v JOIN phone_time_values t ON t.record_uid = v.record_uid "
        "AND t.field_name = split_part(v.time_field, '[', 1) AND t.extraction_id = v.extraction_id AND t.generation = "
        "(SELECT generation FROM phone_interpretation_state WHERE extraction_id = v.extraction_id) "
        "WHERE v.extraction_id = :e"), {"e": ext})}


def run(engine, ext):
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    with engine.begin() as c:
        return activity.build(c, ext)


def setup(hooks):
    _shipped(hooks, SHIPPED)
    identities.install()


@needs_template
def test_outgoing_message_is_a_strong_owner_interaction_and_web_platform_is_another_device(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [message(0), message(3, platform="Web"), message(6, platform="Mobile")])
        out = run(engine, ext)
        assert out["status"] == "ready"
        with engine.connect() as c:
            ev = events(c, ext)
            m = ev[("InstantMessage", "TimeStamp", 0)]
            assert (m.activity_class, m.actor, m.strength, m.class_basis) == ("interaction", "owner", "strong",
                                                                             "reviewed_mapping")
            assert m.activity_mapping_row == "activity_strength/catalogue/im-out-noplatform"
            assert m.class_level == "applied_unconfirmed"
            assert m.family == "messages" and m.counts_for == "owner"
            web = ev[("InstantMessage", "TimeStamp", 3)]
            assert (web.actor, web.strength) == ("other_device", "weak")
            assert "other_device_platform" in web.attribution_flags
            assert web.attribution_mapping_rows == ["attribution/catalogue/attr-im-web"]
            mob = ev[("InstantMessage", "TimeStamp", 6)]
            assert (mob.actor, mob.strength) == ("owner", "strong")
            calls = dict(c.execute(text(
                "SELECT rule_id, records_touched FROM phone_mapping_judgements WHERE extraction_id = :e AND "
                "rule_part IN ('activity','attribution')"), {"e": ext}).fetchall())
            assert calls["activity_strength/catalogue/im-out-noplatform"] == 1
            assert calls["activity_strength/catalogue/im-out-web"] == 1
            assert calls["attribution/catalogue/attr-im-web"] == 1


@needs_template
def test_a_recipient_reading_the_owners_message_is_the_counterparts_action(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [message(0, other_reads=True)])
        run(engine, ext)
        with engine.connect() as c:
            ev = events(c, ext)
            read = ev[("Party", "DateRead", 2)]
            assert read.actor == "counterpart" and read.counts_for == "counterpart"
            assert read.time_semantics == "counterpart_action"
            assert "counterpart" in read.attribution_flags
            assert read.strength == "strong"  # for the counterpart's subject; never counted for the owner
            ident = c.execute(text("SELECT identity_key FROM phone_identities WHERE id = :i"),
                              {"i": read.counterpart_identity_id}).scalar()
            assert ident == "phone:" + OTHER
            msg = ev[("InstantMessage", "TimeStamp", 0)]
            assert msg.counterpart_identity_id == read.counterpart_identity_id


@needs_template
def test_an_offset_less_time_is_flagged_and_never_strong(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [device_event(0, "DeviceLockStatus", "Unlocked", offset="absent"),
                                  device_event(1, "DeviceLockStatus", "Unlocked")], zone="America/New_York")
        run(engine, ext)
        with engine.connect() as c:
            ev = events(c, ext)
            absent = ev[("DeviceEvent", "StartTime", 0)]
            assert absent.offset_status == "absent" and absent.instant_basis == "device_zone"
            assert "offset_absent" in absent.attribution_flags
            assert absent.strength == "weak"
            assert absent.instant_utc.isoformat() == "2023-03-14T19:07:12+00:00"  # 15:07 in New York (EDT)
            explicit = ev[("DeviceEvent", "StartTime", 1)]
            assert (explicit.activity_class, explicit.strength) == ("interaction", "strong")
            assert explicit.stream_key == "DeviceEvent/-/DeviceLockStatus"
            assert explicit.value_key == "EventType=DeviceLockStatus;Value=Unlocked"


@needs_template
def test_rebuilding_twice_gives_identical_rows(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [message(0, other_reads=True), device_event(3, "DisplayOnOff", "On"),
                                  location(4, "Synced")])
        run(engine, ext)
        cols = ("record_uid, time_field, instant_utc, end_utc, activity_class, actor, physical, attribution_flags, "
                "counterpart_identity_id, stream_key, family, value_key, strength")

        def snap():
            with engine.connect() as c:
                return sorted(tuple(r) for r in c.execute(text(
                    "SELECT %s FROM pol_activity_event_v WHERE extraction_id = :e" % cols), {"e": ext}))
        first = snap()
        with engine.begin() as c:
            activity.build(c, ext)
        assert snap() == first and len(first) == 4


@needs_template
def test_a_nested_record_takes_its_roots_source(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [message(0, source="SyntheticApp", other_reads=True),
                                  message(3, other_reads=True), message(6, source="OtherApp", other_reads=True)])
        run(engine, ext)
        with engine.connect() as c:
            ev = events(c, ext)
            for top, src in ((0, "SyntheticApp"), (3, None), (6, "OtherApp")):
                read = ev[("Party", "DateRead", top + 2)]  # the recipient's read time, a record nested in the message
                assert read.source_app == src and read.stream_key == "Party/%s" % (src or "-")
                assert ev[("InstantMessage", "TimeStamp", top)].source_app == src


@needs_template
def test_a_new_mapping_version_reclassifies_without_reading_records_again(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [device_event(0, "DisplayOnOff", "On")])
        run(engine, ext)
        with engine.connect() as c:
            before = events(c, ext)[("DeviceEvent", "StartTime", 0)]
            assert (before.activity_class, before.strength) == ("device_state", "moderate")
            records_before = c.execute(text("SELECT count(*), sum(length(body::text)) FROM phone_records WHERE "
                                            "extraction_id = :e"), {"e": ext}).one()
        path = os.path.join(str(hooks), "activity_strength", "catalogue.json")
        content = json.load(open(path))
        v2 = copy.deepcopy(content)
        v2["version"] += 1
        for r in v2["body"]["rows"]:
            if r["row_id"] == "devev-display":
                r["outputs"]["class"] = "interaction"
        write(str(hooks), v2)
        loader.use_data_dir(str(hooks))  # reload
        with engine.connect() as c:
            assert dict(activity.stale(c))[ext] == "reclassify"
        out = activity.project_stale(engine)
        assert out[str(ext)]["status"] == "ready" and "fallback" not in out[str(ext)]
        assert out[str(ext)]["reclassified"] == 1
        assert out[str(ext)]["changed"] == 1  # one set-based write of the rows whose result moved
        with engine.begin() as c:
            again = activity.reclassify(c, ext)
        assert again["reclassified"] == 1 and again["changed"] == 0  # nothing moved, nothing written
        with engine.connect() as c:
            after = events(c, ext)[("DeviceEvent", "StartTime", 0)]
            assert (after.activity_class, after.strength) == ("interaction", "strong")
            assert after.id == before.id  # the same row, re-classified
            assert str(after.activity_mapping_version) != str(before.activity_mapping_version)
            assert c.execute(text("SELECT count(*), sum(length(body::text)) FROM phone_records WHERE "
                                  "extraction_id = :e"), {"e": ext}).one() == records_before
            assert activity.stale(c) == []
        # a new version that changes no result writes no event, and the event reads the new version (the view takes
        # it from the projection state)
        v3 = copy.deepcopy(v2)
        v3["version"] += 1
        write(str(hooks), v3)
        loader.use_data_dir(str(hooks))
        out = activity.project_stale(engine)
        assert out[str(ext)]["changed"] == 0
        with engine.connect() as c:
            now = events(c, ext)[("DeviceEvent", "StartTime", 0)]
            stored = c.execute(text("SELECT activity_mapping_version FROM pol_activity_event WHERE id = :i"),
                               {"i": now.id}).scalar()
            assert (now.activity_class, now.strength) == ("interaction", "strong")
            assert str(now.activity_mapping_version) not in (str(after.activity_mapping_version), str(stored))
            assert str(now.activity_mapping_version) == str(c.execute(text(
                "SELECT activity_mapping_version FROM pol_projection_state WHERE extraction_id = :e"), {"e": ext}).scalar())


@needs_template
def test_a_new_owner_decision_re_resolves_the_counterparts(hooks):
    """A person's set_phone_owner decision after the build changes who the other person is: the projection is
    re-applied and the counterparts resolved against the decided owner, not left as built."""
    setup(hooks)
    saved = identities._hooks["owner_decision"]
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [message(0, other_reads=True)])
        run(engine, ext)
        with engine.connect() as c:
            ev = events(c, ext)
            assert ev[("InstantMessage", "TimeStamp", 0)].counterpart_identity_id is not None
            assert activity.stale(c) == []
        try:  # the person says the phone is OTHER's: OTHER is no longer anyone's counterpart on it
            identities.register_owner_decision(lambda conn, e: {"identity_keys": ["phone:" + OTHER],
                                                                "decision_id": "d1", "by": "A Person"}
                                               if str(e) == str(ext) else None)
            with engine.connect() as c:
                assert dict(activity.stale(c)).get(ext) == "reclassify"
            out = activity.project_stale(engine)
            assert out[str(ext)]["status"] == "ready" and out[str(ext)]["counterparts_resolved"] is True
            with engine.connect() as c:
                ev = events(c, ext)
                assert ev[("InstantMessage", "TimeStamp", 0)].counterpart_identity_id is None
                assert ev[("Party", "DateRead", 2)].counterpart_identity_id is None
                assert activity.stale(c) == []
            with engine.begin() as c:  # the same owner again: nothing to resolve
                assert activity.reclassify(c, ext)["counterparts_resolved"] is False
        finally:
            identities._hooks["owner_decision"] = saved
        with engine.connect() as c:  # the decision withdrawn: back to the computed owner and the built counterparts
            assert dict(activity.stale(c)).get(ext) == "reclassify"
        activity.project_stale(engine)
        with engine.connect() as c:
            ev = events(c, ext)
            ident = c.execute(text("SELECT identity_key FROM phone_identities WHERE id = :i"),
                              {"i": ev[("InstantMessage", "TimeStamp", 0)].counterpart_identity_id}).scalar()
            assert ident == "phone:" + OTHER


@needs_template
def test_an_event_that_no_longer_matches_a_row_shows_no_mapping_version(hooks):
    """A re-apply under which an event matches no activity row shows no row and no version, never the version of
    the row it matched before."""
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [device_event(0, "DisplayOnOff", "On")])
        run(engine, ext)
        with engine.connect() as c:
            before = events(c, ext)[("DeviceEvent", "StartTime", 0)]
            assert before.activity_mapping_row == "activity_strength/catalogue/devev-display"
            assert before.activity_mapping_version is not None
        path = os.path.join(str(hooks), "activity_strength", "catalogue.json")
        v2 = copy.deepcopy(json.load(open(path)))
        v2["version"] += 1
        v2["body"]["rows"] = [r for r in v2["body"]["rows"] if r["row_id"] != "devev-display"]
        write(str(hooks), v2)
        loader.use_data_dir(str(hooks))
        out = activity.project_stale(engine)
        assert out[str(ext)]["status"] == "ready" and "fallback" not in out[str(ext)]
        assert out[str(ext)]["changed"] == 1
        with engine.connect() as c:
            after = events(c, ext)[("DeviceEvent", "StartTime", 0)]
            assert after.id == before.id
            assert after.activity_mapping_row is None
            assert after.activity_mapping_version is None


# ---- U3: attribution flags ------------------------------------------------------------------------------------

@needs_template
def test_attribution_flags_synced_location_two_group_b_flags_and_decoding(hooks):
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [location(0, "Synced"), location(1, "Unknown"),
                                  message(2, deleted="Deleted", confidence="Medium"), message(5, deleted="Deleted"),
                                  device_event(8, "DeviceLockStatus", "Unlocked", user_mapping="Decoding"),
                                  device_event(9, "DeviceLockStatus", "Unlocked", user_mapping="OtherUser")])
        run(engine, ext)
        with engine.connect() as c:
            ev = events(c, ext)
            synced = ev[("Location", "TimeStamp", 0)]
            assert "synced_from_account" in synced.attribution_flags
            assert ev[("Location", "TimeStamp", 1)].attribution_flags == ["affiliation_unknown"]
            two_b = ev[("InstantMessage", "TimeStamp", 2)]
            assert set(two_b.attribution_flags) == {"deleted_record", "low_decoding_confidence"}
            assert two_b.strength == "weak"
            one_b = ev[("InstantMessage", "TimeStamp", 5)]
            assert one_b.attribution_flags == ["deleted_record"] and one_b.strength == "moderate"
            decoding = ev[("DeviceEvent", "StartTime", 8)]
            assert decoding.attribution_flags == [] and decoding.strength == "strong"
            other = ev[("DeviceEvent", "StartTime", 9)]
            assert other.attribution_flags == ["user_mapping_other"] and other.strength == "weak"
            # the Python twin of the view gives the same strength on every row
            for r in ev.values():
                assert A.strength(r.activity_class, r.actor, r.attribution_flags, r.time_semantics,
                                  r.offset_status, r.deleted_state, r.physical) == r.strength


def test_strength_rules_without_a_database():
    s = A.strength
    assert s("interaction", "owner", [], "event_instant", "explicit", "Intact", False) == "strong"
    assert s("interaction", "owner", ["latest_only"], "latest_of_many", "explicit", "Intact", False) == "moderate"
    assert s("interaction", "owner", ["bucketed"], "aggregate_bucket", "explicit", "Intact", False) == "weak"
    assert s("interaction", "account", ["account_level"], "event_instant", "explicit", "Intact", False) == "moderate"
    assert s("device_state", "owner", [], "event_instant", "explicit", "Intact", False) == "moderate"
    assert s("device_state", "owner", ["deleted_record"], "event_instant", "explicit", "Deleted", False) == "weak"
    assert s("passive", "owner", [], "event_instant", "explicit", "Intact", True) == "weak"
    assert s("passive", "owner", [], "event_instant", "explicit", "Intact", False) == "none"
    assert s("unknown", "owner", [], "event_instant", "explicit", "Intact", False) == "none"
    assert A.context_flags(semantics="event_instant", offset_status="explicit", deleted_state="Intact",
                           decoding_confidence="High", actor="owner", user_mapping="Decoding") == []


# ---- 04 decision 22: wearable (M9) ------------------------------------------------------------------------------

def sensor(top, device_name=None, source_device_type=None):
    """A sensor record with one measurement and one sample (records top..top+2), as the 14 server reports nest them
    (ActivitySensorData.Measurements -> Measurement.Samples -> Sample, M9)."""
    f = [fld("From", ("TimeStamp", "2023-03-14T15:07:12-04:00")), fld("To", ("TimeStamp", "2023-03-14T16:07:12-04:00")),
         fld("Source", ("String", "Health"))]
    if device_name is not None:
        f.append(fld("DeviceName", ("String", device_name)))
    if source_device_type is not None:
        f.append(fld("SourceDeviceType", ("SampleSourceType", source_device_type)))
    f.append(refs("Measurements", top + 1))
    rec = model("ActivitySensorData", f)
    meas = model("ActivitySensorDataMeasurement", [fld("MeasuredVariableType", ("MeasuredVariableType", "Steps")),
                                                   refs("Samples", top + 2)])
    sample = model("ActivitySensorDataSample", [fld("DateSampled", ("TimeStamp", "2023-03-14T15:07:12-04:00")),
                                                fld("Quantity", ("Double", "12"))])
    return ([(top, None, top, rec), (top + 1, top, top, meas), (top + 2, top + 1, top, sample)],
            [ts(top, "0.0", "From", "ActivitySensorData"), ts(top + 2, "0.0", "DateSampled", "ActivitySensorDataSample")])


@needs_template
def test_a_sensor_record_naming_a_wearable_flags_it_and_its_samples_as_another_device(hooks):
    """M9 found no wearable on the 14 server reports; the rule reads the device name the sensor record carries and
    its samples take it from the record (a sample names no device). Fails on the old code: no row raised it."""
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [sensor(0, "Someone's apple WATCH"), sensor(3, "Pixel 7 Pro"), sensor(6),
                                  sensor(9, "Garmin Forerunner")])
        run(engine, ext)
        with engine.connect() as c:
            ev = events(c, ext)
            for top in (0, 9):
                rec, smp = ev[("ActivitySensorData", "From", top)], ev[("ActivitySensorDataSample", "DateSampled",
                                                                       top + 2)]
                # the record is an hourly bucket (bucketed); the sample is an instant: wearable is the only flag
                assert rec.attribution_flags == ["wearable", "bucketed"] and smp.attribution_flags == ["wearable"]
                assert (rec.strength, smp.strength) == ("none", "none")  # passive, not physical
                assert rec.attribution_mapping_rows == ["attribution/catalogue/attr-sensor-wearable"]
                assert smp.attribution_mapping_rows == ["attribution/catalogue/attr-sensor-sample-wearable"]
                assert (rec.actor, smp.actor) == ("other_device", "other_device")
                assert rec.activity_mapping_row == "activity_strength/catalogue/sensor-wearable"
            for top in (3, 6):  # a phone's own name, and no name: the phone recorded it
                rec, smp = ev[("ActivitySensorData", "From", top)], ev[("ActivitySensorDataSample", "DateSampled",
                                                                       top + 2)]
                assert "wearable" not in rec.attribution_flags and "wearable" not in smp.attribution_flags
                assert (rec.actor, smp.actor) == ("owner", "owner")
            calls = dict(c.execute(text(
                "SELECT rule_id, records_touched FROM phone_mapping_judgements WHERE extraction_id = :e AND "
                "rule_part = 'attribution'"), {"e": ext}).fetchall())
            assert calls["attribution/catalogue/attr-sensor-wearable"] == 2
            assert calls["attribution/catalogue/attr-sensor-sample-wearable"] == 2
            # the sample row names DeviceName, which only the sensor record has: the registry check reads it there
            assert [p for m in loader.loaded() for p in loader.registry_problems(c, m, requirements=False)] == []


def test_contains_any_matches_words_without_case_and_refuses_a_bad_value():
    from services.phone.mappings import rows as R
    row = {"row_id": "w", "type": "T", "field": "F", "predicates": [{"field": "DeviceName", "op": "contains_any",
                                                                     "value": ["Watch", "Oura"]}]}
    assert R.match([row], "T", "F", {"fields": {"DeviceName": ["my apple watch"]}}) is row
    assert R.match([row], "T", "F", {"fields": {"DeviceName": ["OURA ring"]}}) is row
    assert R.match([row], "T", "F", {"fields": {"DeviceName": ["iPhone"]}}) is None
    assert R.match([row], "T", "F", {"fields": {}}) is None
    absent = {"row_id": "a", "type": "T", "field": "F", "predicates": [{"field": "DeviceName", "op": "absent"}]}
    assert not R.could_both_match(row, absent)
    for bad in (None, [], "Watch", [""], [3]):
        with pytest.raises(loader.LoadError):
            R._domain({"field": "DeviceName", "op": "contains_any", "value": bad})


@needs_template
def test_a_new_mapping_version_leaves_one_open_reading_per_rule(hooks):
    """The projection's judgement calls are keyed by mapping version; after a new version the old version's open
    calls touch nothing, so the readings queue shows each rule once (fails on the old code: both versions counted)."""
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [location(0, "Unknown")])
        run(engine, ext)
        path = os.path.join(str(hooks), "attribution", "catalogue.json")
        v2 = copy.deepcopy(json.load(open(path)))
        v2["version"] += 1
        v2["review"]["basis"] += " (test version)"
        write(str(hooks), v2)
        loader.use_data_dir(str(hooks))
        activity.project_stale(engine)
        with engine.connect() as c:
            rows = c.execute(text(
                "SELECT rule_id, records_touched FROM phone_mapping_judgements WHERE extraction_id = :e AND "
                "rule_id = 'attribution/catalogue/attr-location-unknown' ORDER BY records_touched"),
                {"e": ext}).fetchall()
            assert [r.records_touched for r in rows] == [0, 1]


# ---- 04 decision 22: affiliation_unknown on a source known to sync (M5) ----------------------------------------

def place(top, source, affiliation=None):
    f = [fld("TimeStamp", ("TimeStamp", "2023-03-14T15:07:12-04:00")), fld("Source", ("String", source))]
    if affiliation is not None:
        f.append(fld("DeviceLocationAffiliation", ("DeviceLocationAffiliation", affiliation)))
    return [(top, None, top, model("Location", f))], [ts(top, "0.0", "TimeStamp", "Location")]


@needs_template
def test_a_location_with_no_affiliation_from_a_source_known_to_sync_is_not_known_to_be_this_device(hooks):
    """M5: Gmail Locations name their account (P11 618 of 1,236, P12 49 of 49) and carry no affiliation. Fails on the
    old code: only an affiliation of Unknown raised the flag."""
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [place(0, "Gmail"), place(1, "Gmail", "Extracted"), place(2, "Native Locations"),
                                  place(3, "Google Maps"), place(4, "Gmail", "Unknown")])
        run(engine, ext)
        with engine.connect() as c:
            ev = events(c, ext)
            for top in (0, 3):
                e = ev[("Location", "TimeStamp", top)]
                assert e.attribution_flags == ["affiliation_unknown"]
                assert e.attribution_mapping_rows == ["attribution/catalogue/attr-location-sync-source-no-affiliation"]
            assert ev[("Location", "TimeStamp", 1)].attribution_flags == []  # the report says this device recorded it
            assert ev[("Location", "TimeStamp", 2)].attribution_flags == []  # the device's own location store
            unknown = ev[("Location", "TimeStamp", 4)]  # an affiliation of Unknown keeps its own row
            assert unknown.attribution_mapping_rows == ["attribution/catalogue/attr-location-unknown"]


def _email(top, folder=None, status=None):
    f = [fld("TimeStamp", ("TimeStamp", "2023-03-14T15:07:12-04:00"))]
    if folder is not None:
        f.append(fld("Folder", ("String", folder)))
    if status is not None:
        f.append(fld("Status", ("MessageStatus", status)))
    return [(top, None, top, model("Email", f))], [ts(top, "0.0", "TimeStamp", "Email")]


def _app_usage(top, active):
    f = [fld("StartTime", ("TimeStamp", "2023-03-14T15:00:00-04:00")), fld("EndTime", ("TimeStamp", "2023-03-14T16:00:00-04:00")),
         fld("ActiveTime", ("TimeSpan", active))]
    return [(top, None, top, model("ApplicationUsage", f))], [ts(top, "0.0", "StartTime", "ApplicationUsage"),
                                                              ts(top, "1.0", "EndTime", "ApplicationUsage")]


@needs_template
def _party(ordinal, name, *, owner=None):
    f = [fld("Identifier", ("String", name)), fld("Role", ("PartyRole", "To"))]
    if owner is not None:
        f.append(fld("IsPhoneOwner", ("Boolean", "True" if owner else "False")))
    return model("Party", f)


def _mail(top, folder, status=None, *, sender_owner=None, to_owner=None):
    """A mail with its From and To parties, as the reports write them (one modelField, one multiModelField)."""
    f = [fld("TimeStamp", ("TimeStamp", "2023-03-14T15:07:12-04:00"))]
    if folder:
        f.append(fld("Folder", ("String", folder)))
    if status:
        f.append(fld("Status", ("MessageStatus", status)))
    f += [refs("From", top + 1, kind="modelField"), refs("To", top + 2)]
    return ([(top, None, top, model("Email", f)), (top + 1, top, top, _party(top + 1, "a@example.test", owner=sender_owner)),
             (top + 2, top, top, _party(top + 2, "b@example.test", owner=to_owner))],
            [ts(top, "0.0", "TimeStamp", "Email")])


def _chat(top, *to_marks, sender_owner=None):
    """A message with its From party and one To party per mark."""
    f = [fld("TimeStamp", ("TimeStamp", "2023-03-14T15:07:12-04:00")), refs("From", top + 1, kind="modelField"),
         refs("To", *[top + 2 + i for i in range(len(to_marks))])]
    rows = [(top, None, top, model("InstantMessage", f)), (top + 1, top, top, _party(top + 1, "a@example.test", owner=sender_owner))]
    rows += [(top + 2 + i, top, top, _party(top + 2 + i, "b%d@example.test" % i, owner=mark)) for i, mark in enumerate(to_marks)]
    return rows, [ts(top, "0.0", "TimeStamp", "InstantMessage")]


def test_message_direction_reads_a_sole_recipient_marked_as_the_owner(hooks):
    """04 decision 55, from followups m11050732008523. On the old code the row at 3 read unknown. Several To parties
    say nothing: on the 14 reports the owner listed among several is the sender in 984 of 985."""
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [_chat(0, None, sender_owner=True), _chat(3, True), _chat(6, True, False), _chat(10, False),
                                  _chat(13, True, sender_owner=True), _chat(16, None)])
        run(engine, ext)
        with engine.connect() as c:
            rows = c.execute(text(
                "SELECT ordinal, direction, direction_basis FROM phone_comm_events WHERE extraction_id = :e AND kind = "
                "'message' ORDER BY ordinal"), {"e": ext}).fetchall()
    assert [tuple(r)[1:] for r in rows] == [("outgoing", "sender_owner_flag"), ("incoming", "recipient_owner_flag"),
                                            ("unknown", None), ("unknown", None), ("outgoing", "sender_owner_flag"),
                                            ("unknown", None)]


def test_mail_direction_reads_the_owner_mark_on_either_side_then_status_then_folder(hooks):
    """04 decision 54, from followups m11050526143420. On the old code every one of these reads unknown except the two
    with a From mark: on the reference phones no From party states the mark, the To party does."""
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [_mail(0, "Weekly", sender_owner=True), _mail(3, "Weekly", sender_owner=False),
                                  _mail(6, "Inbox, Updates", to_owner=True), _mail(9, "Weekly", "Sent", to_owner=True),
                                  _mail(12, "Inbox, Promos"), _mail(15, "Outbox"), _mail(18, "Weekly")])
        run(engine, ext)
        with engine.connect() as c:
            rows = c.execute(text(
                "SELECT ordinal, direction, direction_basis FROM phone_comm_events WHERE extraction_id = :e AND kind = "
                "'email' ORDER BY ordinal"), {"e": ext}).fetchall()
            implied = dict(c.execute(text(
                "SELECT ordinal, implied_role FROM phone_participations WHERE extraction_id = :e AND role = "
                "'owner_implicit'"), {"e": ext}).fetchall())
            ev = events(c, ext)
    assert [tuple(r)[1:] for r in rows] == [("outgoing", "sender_owner_flag"), ("incoming", "sender_owner_flag"),
                                            ("incoming", "recipient_owner_flag"), ("outgoing", "status_field"),
                                            ("incoming", "folder_name"), ("outgoing", "folder_name"), ("unknown", None)]
    assert implied[12] == "recipient" and implied[15] == "sender" and implied[18] is None  # the owner side follows
    cls = {k[2]: v.activity_class for k, v in ev.items()}
    assert cls[0] == cls[9] == cls[15] == "interaction"  # an owner mail in an unusual folder used to read passive
    assert cls[3] == cls[6] == cls[12] == "passive"


def test_sent_mail_and_app_use_count_as_use_and_mail_in_the_inbox_does_not(hooks):
    """04 sections 3.2 and M2. Fails on the old code: every Email and ApplicationUsage fell to default_unknown."""
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [_email(0, "[Gmail]/Sent Mail", "Sent"), _email(1, "INBOX", "Unread"), _email(2, "Outbox"),
                                  _email(3), _email(4, "[Gmail]/Drafts"), _app_usage(5, "00:12:40"), _app_usage(6, "00:00:00")])
        run(engine, ext)
        with engine.connect() as c:
            ev = events(c, ext)
        got = {k[2]: (v.activity_class, v.actor, v.strength, v.activity_mapping_row.rsplit("/", 1)[1] if v.activity_mapping_row else None)
               for k, v in ev.items()}
    assert got[0] == ("interaction", "owner", "strong", "email-outgoing")
    assert got[1] == ("passive", "owner", "none", "email-incoming")
    assert got[2] == ("interaction", "owner", "strong", "email-outgoing")
    assert got[3][0] == "unknown" and got[3][3] == "email-nofolder"
    assert got[4] == ("interaction", "owner", "none", "email-outgoing")  # a draft's time is not established
    assert got[5] == ("interaction", "owner", "weak", "appusage-summary-active")  # a summary period, so weak
    assert got[6] == ("unknown", "unknown", "none", None)
    assert len(ev) == 7  # EndTime is the end of the StartTime event, not an event of its own


@needs_template
def test_a_message_draft_is_composed_by_the_owner_at_a_time_not_established(hooks):
    """04 section 3.2 Folder Draft. Fails on the old code: a draft read as a strong sent message."""
    setup(hooks)
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = phone(c, case, [message(0, platform="Mobile"), message(3, platform="Mobile", folder="Draft")])
        run(engine, ext)
        with engine.connect() as c:
            ev = events(c, ext)
        sent, draft = ev[("InstantMessage", "TimeStamp", 0)], ev[("InstantMessage", "TimeStamp", 3)]
        assert (sent.activity_class, sent.actor, sent.strength) == ("interaction", "owner", "strong")
        assert (draft.activity_class, draft.actor, draft.strength) == ("interaction", "owner", "none")
        assert draft.time_semantics == "unknown"
