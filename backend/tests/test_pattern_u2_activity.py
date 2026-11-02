"""04-U2 and 04-U3 (cb-pol items A and B): activity events, their strength, and attribution flags.

Synthetic phones only, built in the test (04 section 12). PostgreSQL tests are opt-in through
``LOUPE_TEST_PHONE_PG_TEMPLATE_URL`` (``tests/phone_pg.py``).
"""
from __future__ import annotations

import copy
import json
import os

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


def message(top, *, platform=None, deleted="Intact", confidence="High", other_reads=False, source=None):
    """An outgoing message: From party is the owner. Records top..top+2."""
    f = [fld("TimeStamp", ("TimeStamp", "2023-03-14T15:07:12-04:00")), refs("From", top + 1, kind="modelField"),
         refs("To", top + 2)]
    if platform:
        f.append(fld("Platform", ("Platform", platform)))
    if source:
        f.append(fld("Source", ("String", source)))
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
        v2["version"] = 2
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
