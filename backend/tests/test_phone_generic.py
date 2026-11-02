"""02-U4: generic interpretation by value role (02 section 5), with the sweep's generation swap (5.7)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from services.phone import generic, ids, registry, sweep
from tests.phone_pg import (corpus_connection, fld, fresh_engine, make_case, make_extraction, model, needs_corpus,
                            needs_template, refs)

T1 = datetime(2023, 3, 14, 19, 7, 12, tzinfo=timezone.utc)


def stamp(ordinal, body_path, field, mt, *, instant=T1, offset_state="explicit", text_="2023-03-14T15:07:12-04:00"):
    return {"o": ordinal, "bp": body_path, "mt": mt, "fn": field, "ot": text_, "i": instant, "os": offset_state,
            "off": -240 if offset_state == "explicit" else None,
            "ft": "3/14/2023 3:07:12 PM(UTC-4)", "lw": None if offset_state == "explicit" else T1.replace(tzinfo=None)}


@pytest.mark.parametrize("parent,container,role_value,owner,direction,expected", [
    ("InstantMessage", "From", None, False, None, ("sender", "container", [])),
    ("InstantMessage", "From", "To", False, None, ("sender", "container", ["role_conflict"])),
    ("InstantMessage", "To", "General", True, None, ("recipient", "container", [])),
    ("InstantMessage", "To", "From", True, None, ("recipient", "container", ["role_conflict"])),
    ("Email", "Cc", None, None, None, ("cc", "container", [])),
    ("Call", "Parties", "From", True, "Outgoing", ("caller", "role", [])),
    ("Call", "Parties", "To", False, "Outgoing", ("callee", "role", [])),
    ("Call", "Parties", None, True, "Outgoing", ("caller", "direction_inferred", [])),
    ("Call", "Parties", None, False, "Incoming", ("caller", "direction_inferred", [])),
    ("Call", "Parties", "General", True, "Incoming", ("callee", "direction_inferred", [])),
    ("Call", "Parties", None, None, "Incoming", ("unknown", "direction_inferred", [])),
    ("Chat", "Participants", "General", True, None, ("participant", "container", [])),
    ("ChatActivity", "Participant", None, None, None, ("activity_subject", "container", [])),
    ("CalendarEntry", "Attendees", None, None, None, ("attendee", "container", [])),
    ("SocialMediaActivity", "Author", "General", None, None, ("author", "container", [])),
    ("FileUpload", "Owner", None, None, None, ("owner_of_item", "container", [])),
    ("ForwardedMessageData", "OriginalSender", None, None, None, ("original_sender", "container", [])),
    ("ZzzUnknown", "Folk", None, None, None, ("party:Folk", "container", [])),
])
def test_participant_roles_follow_5_3(parent, container, role_value, owner, direction, expected):
    assert generic.participant_role(parent, container, role_value, owner, direction) == expected


def _unknown_type_extraction(c, case):
    unknown = model("ZzzUnknown", [fld("Seen", ("TimeStamp", "2023-03-14T15:07:12-04:00")),
                                   fld("Note", ("String", "synthetic note")),
                                   ["modelField", {"name": "Spot"}, None, [["@", 1]]],
                                   refs("Folk", 2)])
    coord = model("Coordinate", [fld("Latitude", ("Double", "38.9")), fld("Longitude", ("Double", "-77.03"))])
    party = model("Party", [fld("Identifier", ("String", "+12025550143")), fld("Name", ("String", "Synthetic A")),
                            fld("IsPhoneOwner", ("Boolean", "False"))])
    offsetless = model("ZzzUnknown", [fld("Seen", ("TimeStamp", "2023-03-14T15:07:12"))])
    return make_extraction(c, case, [(0, None, 0, unknown), (1, 0, 0, coord), (2, 0, 0, party),
                                     (3, None, 3, offsetless)],
                           timestamps=[stamp(0, "0.0", "Seen", "ZzzUnknown"),
                                       stamp(3, "0.0", "Seen", "ZzzUnknown", instant=None, offset_state="absent",
                                             text_="2023-03-14T15:07:12")])


@needs_template
def test_a_type_absent_from_all_code_reaches_the_timeline_the_map_and_participants():
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = _unknown_type_extraction(c, case)
        out = sweep.interpret_one(engine, ext)
        assert out["status"] == "done" and out["generation"] == 1
        uid = ids.record_uid(ext, 0, 0)
        with engine.connect() as c:
            tl = c.execute(text("SELECT model_type, field_path, instant, summary FROM pv_timeline_entry WHERE "
                                "record_uid = :u"), {"u": uid}).fetchall()
            assert [(r[0], r[1], r[2]) for r in tl] == [("ZzzUnknown", "Seen", T1)]
            assert tl[0][3] == "ZzzUnknown synthetic note"
            pt = c.execute(text("SELECT lat, lon, source_kind, accuracy_basis, instant, time_field FROM "
                                "pv_location_point WHERE record_uid = :u"), {"u": uid}).one()
            assert tuple(pt) == (38.9, -77.03, "other:ZzzUnknown", "none", T1, "Seen")
            part = c.execute(text("SELECT role, role_basis, identifier_raw, name_in_record, is_phone_owner FROM "
                                  "phone_participations WHERE record_uid = :u"), {"u": uid}).one()
            assert tuple(part) == ("party:Folk", "container", "+12025550143", "Synthetic A", False)
            # the offset-less value has no instant although its formatted text carries an offset (4.1)
            ol = c.execute(text("SELECT instant, machine_instant, offset_present, original_text FROM pv_time "
                                "WHERE record_uid = :u"), {"u": ids.record_uid(ext, 0, 3)}).one()
            assert ol[0] is None and ol[1] is None and ol[2] is False
            texts = c.execute(text("SELECT value, value_folded, field_path FROM pv_text WHERE record_uid = :u "
                                   "ORDER BY field_path"), {"u": uid}).fetchall()
            assert ("synthetic note", "synthetic note", "Note") in [tuple(t) for t in texts]
            party_texts = c.execute(text("SELECT value, value_folded, field_path FROM pv_text WHERE record_uid = :u"),
                                    {"u": ids.record_uid(ext, 0, 2)}).fetchall()
            assert ("Synthetic A", "synthetic a", "Folk[0].Name") in [tuple(t) for t in party_texts]
            for table in generic.DERIVED_TABLES:
                assert c.execute(text("SELECT count(*) FROM %s WHERE record_uid IS NULL" % table)).scalar() == 0


@needs_template
def test_a_second_pass_writes_the_next_generation_and_removes_the_previous_one():
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            ext = _unknown_type_extraction(c, make_case(c))
        first = sweep.interpret_one(engine, ext)
        assert sweep.interpret_one(engine, ext)["status"] == "current"
        with engine.begin() as c:  # a new interpreter version makes the extraction stale again
            c.execute(text("UPDATE phone_interpretation_state SET interpreter_version = 'old' WHERE "
                           "extraction_id = :e"), {"e": ext})
        assert [str(x) for x in sweep.candidates(engine.connect())] == [str(ext)]
        second = sweep.interpret_one(engine, ext)
        assert second["generation"] == 2 and second["deleted_previous"] > 0
        with engine.connect() as c:
            for table in generic.DERIVED_TABLES:
                gens = {r[0] for r in c.execute(text("SELECT DISTINCT generation FROM %s WHERE extraction_id = :e"
                                                     % table), {"e": ext})}
                assert gens <= {2}
        assert {k: v for k, v in first.items() if k.startswith("rows:")} == \
               {k: v for k, v in second.items() if k.startswith("rows:")}


@needs_template
def test_a_superseded_extraction_keeps_its_rows_but_leaves_the_views():
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            ext = _unknown_type_extraction(c, make_case(c))
        sweep.interpret_one(engine, ext)
        with engine.begin() as c:
            c.execute(text("UPDATE phone_extractions SET standing = 'superseded' WHERE id = :e"), {"e": ext})
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM pv_timeline_entry WHERE extraction_id = :e"), {"e": ext}).scalar() == 0
            assert c.execute(text("SELECT count(*) FROM phone_time_values WHERE extraction_id = :e"), {"e": ext}).scalar() == 2


@needs_template
def test_a_document_whose_check_differs_is_held():
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            ext = _unknown_type_extraction(c, make_case(c))
            c.execute(text("INSERT INTO phone_reconciliations (id, extraction_id, document_index, counter_version, "
                           "result, source_totals, captured_totals, differences, difference_count) VALUES "
                           "(gen_random_uuid(), :e, 0, 'x', 'differs', '{}', '{}', '[]', 1)"), {"e": ext})
        assert sweep.interpret_one(engine, ext)["status"] == "held"
        with engine.connect() as c:
            assert c.execute(text("SELECT status FROM phone_interpretation_state WHERE extraction_id = :e"),
                             {"e": ext}).scalar() == "held"
            assert c.execute(text("SELECT count(*) FROM phone_time_values WHERE extraction_id = :e"), {"e": ext}).scalar() == 0


# ---- corpus (server captures; counts only) -----------------------------------------------------------------

def _by_records(c, n):
    return c.execute(text("SELECT id FROM phone_extractions WHERE record_count = :n AND capture_state = 'captured' "
                          "LIMIT 1"), {"n": n}).scalar()


@needs_corpus
@pytest.mark.parametrize("label,records,times,points,by_parent,unplaced_locations", [
    ("C3", 71045, 22881, 31, {"Location": 31}, 0),
    ("C9", 14005, 5218, 9, {"Location": 7, "WirelessNetwork": 2}, 0),
    ("C8 server (P02)", 73608, 59673, 38, {"Location": 35, "WirelessNetwork": 3}, 171),
])
def test_corpus_counts(label, records, times, points, by_parent, unplaced_locations):
    with corpus_connection() as c:
        registry.apply_seed(c)
        ext = _by_records(c, records)
        if ext is None:
            pytest.skip("%s is not captured in this database" % label)
        out = generic.interpret(c, ext, 9999)
        assert out["time_values"] == times
        assert out["time_values"] == c.execute(text(
            "SELECT count(*) FROM phone_timestamps WHERE extraction_id = :e AND owner_kind = 'record'"), {"e": ext}).scalar()
        assert out.get("points", 0) == points
        assert {k.split(":", 1)[1]: v for k, v in out.items() if k.startswith("points:")} == by_parent
        assert out.get("unplaced:no_coordinate:Location", 0) == unplaced_locations
        assert out.get("orphan_records", 0) == 0
        nested_parties = c.execute(text("SELECT count(*) FROM phone_records WHERE extraction_id = :e AND "
                                        "model_type = 'Party' AND parent_ordinal IS NOT NULL"), {"e": ext}).scalar()
        assert out["participations"] == nested_parties
        if label == "C3":
            assert nested_parties == 7504
            fmt = dict(c.execute(text("SELECT producer_format, count(*) FROM phone_time_values WHERE extraction_id = :e "
                                      "AND generation = 9999 GROUP BY 1"), {"e": ext}).fetchall())
            assert fmt == {"TimeStampKnown": 22859, "DateTimeOnly": 21, "DateOnly": 1}
            assert c.execute(text("SELECT count(*) FROM phone_time_values WHERE extraction_id = :e AND generation = 9999 "
                                  "AND offset_present = false AND instant IS NOT NULL"), {"e": ext}).scalar() == 0


@needs_corpus
def test_device_zone_is_the_device_setting_and_the_examiner_zone_is_kept_apart():
    with corpus_connection() as c:
        c3, c9 = _by_records(c, 71045), _by_records(c, 14005)
        if not (c3 and c9):
            pytest.skip("C3 and C9 are not both captured in this database")
        z = {e: c.execute(text("SELECT device_zone, flags FROM phone_extractions WHERE id = :e"), {"e": e}).one()
             for e in (c3, c9)}
        assert z[c3][0] is None and sweep.examiner_zone(z[c3][1]) == "Africa/Abidjan"
        assert z[c9][0] == "America/New_York"
