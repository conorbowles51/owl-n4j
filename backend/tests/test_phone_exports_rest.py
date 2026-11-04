"""03 section 12.2: the last three export sources, a Timeline phone lens, a collection and a dossier (07 6.4 item 14,
E-2, E-4, E-9). Invented data only: 555 numbers and made-up text. Needs the PostgreSQL phone template.

On the code before these sources were built, every create below was refused with "Exporting a … is not built yet."
"""
from __future__ import annotations

import io
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.phone_analysis_fixture import record
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone
from tests.test_phone_timeline_lens import _entry

pytestmark = needs_template
OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"


def _msg(instant, sender, recips, body, thread="t"):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, thread=thread, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming")


class _U:
    def __init__(self, uid):
        self.id = uid


@pytest.fixture
def world(tmp_path, monkeypatch):
    from postgres import link_types
    from services.phone import resolvers
    monkeypatch.setenv("LOUPE_PHONE_EXPORT_DIR", str(tmp_path))
    monkeypatch.setattr(link_types, "_RESOLVERS", {})
    resolvers.register()  # as main.py does at start-up; the registry is put back after the test
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            c.execute(text("UPDATE cases SET title = 'Synthetic export case' WHERE id = :c"), {"c": case})
            ext, evs = phone(c, case, device_zone="America/New_York", events=[
                # 11:30 PM Eastern on March 14 is 03:30 UTC on March 15 (the shifted-day failure, E-2)
                _msg(at(2023, 3, 15, 3, 30), ANA, [OWNER], "late on the fourteenth"),
                _msg(at(2023, 3, 15, 15), OWNER, [ANA], "synthetic reply"),
                _msg(at(2023, 3, 16, 9), BEN, [OWNER], "synthetic from Ben", thread="u")])
            _entry(c, case, ext, 100, "Location", at(2023, 3, 15, 16))
            _entry(c, case, ext, 101, "DeviceEvent", at(2023, 3, 15, 17))
            word = record(c, case, ext, 700, "DictionaryWord", texts=[("Word", "synthetic")])
            user = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
        yield {"engine": engine, "case": str(case), "other": str(other), "ext": str(ext), "evs": evs, "word": word,
               "user": user}


def _selection(w, records, words="Synthetic collection"):
    from services.phone.entry_export import store_selection
    with Session(w["engine"]) as db:
        sid, _, _ = store_selection(db, w["case"], [str(r) for r in records], words, _U(w["user"]))
        db.commit()
    return str(sid)


def _dossier(w, links, name="Synthetic Person"):
    did = uuid.uuid4()
    with w["engine"].begin() as c:
        c.execute(text("INSERT INTO case_profiles (id, case_id, profile_type, display_name, contacts, linkage_state, "
                       "status, needs_link_review, graph_entity_deleted, created_at, updated_at) VALUES (:i, :c, "
                       "'person', :n, '[]', 'unlinked', 'active', false, false, now(), now())"),
                  {"i": did, "c": w["case"], "n": name})
        for kind, target in links:
            c.execute(text("INSERT INTO dossier_links (id, dossier_id, case_id, target_type, target_id, "
                           "relationship_type, label, source_anchor, created_at, updated_at) VALUES (:i, :d, :c, :k, "
                           ":t, 'supports', 'synthetic', '{}', now(), now())"),
                      {"i": uuid.uuid4(), "d": did, "c": w["case"], "k": kind, "t": str(target)})
    return str(did)


def _freeze(w, source, ref, case=None):
    from services.phone import source_export
    with Session(w["engine"]) as db:
        return source_export.freeze_source(db, case or w["case"], source, ref, _U(w["user"]))


def _draw(w, source, filter_body, fmt="pdf"):
    from services.phone.exports import jobs
    with w["engine"].begin() as c:
        made = jobs.create(c, case_id=w["case"], user_id=w["user"], fmt=fmt, source=source, filter_body=filter_body,
                           options={"title": "Synthetic export"})
    done = jobs.run_pending(w["engine"])
    assert done and done[0]["state"] == "done", done
    with w["engine"].connect() as c:
        state = jobs.get(c, w["case"], made["export_id"])
        path = jobs.file_of(c, w["case"], made["export_id"]).storage_path
    return state, open(path, "rb").read()


def _pdf_text(data):
    pypdf = pytest.importorskip("pypdf")
    return "\n".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(data)).pages)


def _flat(s):
    return "".join(s.split())


# ---- collection (E-9) -------------------------------------------------------------------------------------------

def test_e9_a_collection_export_total_equals_the_collected_count(world):
    pytest.importorskip("weasyprint")
    w = world
    sid = _selection(w, [e["record_uid"] for e in w["evs"]])
    out = _freeze(w, "collection", {"selection_id": sid})
    # every member is a message: the export draws the collection itself, nothing new is stored
    assert out["selection_id"] == sid and out["collected"] == out["members"] == 3 and out["sentence"] is None
    assert out["words"] == "The collection “Synthetic collection”"
    with w["engine"].connect() as c:
        assert c.execute(text("SELECT count(*) FROM phone_selections")).scalar() == 1
    state, data = _draw(w, "collection", out["filter"])
    assert state["source"] == "collection" and state["counts"]["total"] == 3
    assert _flat(_pdf_text(data)).count("RecordC3-") == 3


def test_a_collection_member_that_is_not_a_message_is_counted_never_dropped_silently(world):
    w = world
    sid = _selection(w, [w["evs"][0]["record_uid"], w["word"]])
    out = _freeze(w, "collection", {"selection_id": sid})
    assert out["collected"] == 1 and out["members"] == 2 and out["selection_id"] != sid
    assert out["sentence"] == "Not in this export: 1 linked phone record that is not a message or call."


def test_a_collection_of_another_case_or_of_nothing_to_export_is_refused_with_the_reason(world):
    from services.phone import source_export
    w = world
    sid = _selection(w, [w["word"]])
    with pytest.raises(source_export.SourceExportError, match="not a message or call"):
        _freeze(w, "collection", {"selection_id": sid})
    with pytest.raises(LookupError, match="not in this case"):
        _freeze(w, "collection", {"selection_id": sid}, case=w["other"])
    with pytest.raises(LookupError, match="not in this case"):
        _freeze(w, "collection", {"selection_id": str(uuid.uuid4())})


# ---- dossier ----------------------------------------------------------------------------------------------------

def test_a_dossier_export_holds_its_record_links_and_selection_members_and_counts_the_rest(world):
    pytest.importorskip("weasyprint")
    w = world
    sid = _selection(w, [w["evs"][1]["record_uid"], w["evs"][2]["record_uid"]])
    did = _dossier(w, [("phone_record", w["evs"][0]["record_uid"]), ("phone_selection", sid),
                       ("phone_record", w["evs"][1]["record_uid"]),  # also in the selection: printed once
                       ("phone_record", w["word"]), ("phone_extraction", w["ext"])])
    out = _freeze(w, "dossier", {"dossier_id": did})
    assert out["collected"] == 3 and out["members"] == 4
    assert out["words"] == "The phone records of the dossier “Synthetic Person”"
    assert out["sentence"] == ("Not in this export: 1 phone; 1 linked phone record that is not a message or call.")
    state, data = _draw(w, "dossier", out["filter"])
    assert state["counts"]["total"] == 3 and _flat(_pdf_text(data)).count("RecordC3-") == 3


def test_a_dossier_with_no_phone_message_is_refused_and_its_other_content_is_named(world):
    from services.phone import source_export
    w = world
    did = _dossier(w, [("phone_extraction", w["ext"])])
    with w["engine"].begin() as c:
        c.execute(text("INSERT INTO dossier_interviews (id, dossier_id, case_id, participants, interviewer_user_ids, "
                       "status, created_at, updated_at) VALUES (:i, :d, :c, '[]', '[]', 'planned', now(), now())"),
                  {"i": uuid.uuid4(), "d": did, "c": w["case"]})
    with pytest.raises(source_export.SourceExportError) as exc:
        _freeze(w, "dossier", {"dossier_id": did})
    assert str(exc.value) == ("Not in this export: 1 phone. The dossier's 1 interview is not in a phone export, "
                              "which holds messages and calls only.")
    with pytest.raises(LookupError):
        _freeze(w, "dossier", {"dossier_id": did}, case=w["other"])


# ---- Timeline phone lens (E-4, E-2) -------------------------------------------------------------------------------

def test_e4_a_lens_export_prints_every_lens_entry_its_stated_total_and_the_screen_total(world):
    pytest.importorskip("weasyprint")
    from services.phone import timeline_lens
    from services.phone.exports import jobs
    w = world
    body = {"zone": {"mode": "case"}}
    with w["engine"].connect() as c:
        lens = timeline_lens.index(c, timeline_lens.TimelineLensFilter.model_validate({"case_id": w["case"], **body}))
        facts = jobs.describe_lens(c, w["case"], body)
    # 3 messages and the location; the device event is off by default and its number is stated (T-7)
    assert lens["total"] == facts["total"] == 4 and facts["messages"] == 3 and facts["other"] == 1
    state, data = _draw(w, "timeline_lens", body)
    words = " ".join(_pdf_text(data).split())
    assert state["source"] == "timeline_lens" and state["counts"]["total"] == 4
    assert _flat(words).count("RecordC3-") == 4
    assert "1 device event and sensor readings hidden." in words
    assert "Locations: Location" in words


def test_e2_a_lens_export_prints_the_late_message_under_the_lens_day_header(world):
    pytest.importorskip("weasyprint")
    from services.phone import timeline_lens
    w = world
    body = {"zone": {"mode": "case"}}
    with w["engine"].connect() as c:
        idx = timeline_lens.index(c, timeline_lens.TimelineLensFilter.model_validate({"case_id": w["case"], **body}))
    first = idx["items"][0]
    assert first["day"] == "2023-03-14"
    _, data = _draw(w, "timeline_lens", body)
    flat = _flat(_pdf_text(data))
    header = _flat("%s, %s" % (first["header"], first["zone_label"]))
    assert header in flat and flat.index(header) < flat.index(_flat("late on the fourteenth"))


def test_a_lens_rsmf_has_one_event_per_lens_entry_each_with_its_own_id(world):
    from services.phone.exports import rsmf
    w = world
    with w["engine"].begin() as c:  # a second event time on the location record: two lens entries, one record
        c.execute(text(
            "INSERT INTO phone_time_values (case_id, extraction_id, document_index, ordinal, record_uid, "
            "root_record_uid, locator, model_type, generation, time_uid, body_path, field_name, field_path, "
            "value_index, instant, original_text, offset_state, offset_present, effective_instant, is_event_time) "
            "SELECT case_id, extraction_id, document_index, ordinal, record_uid, root_record_uid, locator, model_type, "
            "generation, gen_random_uuid(), body_path, 'EndTime', 'EndTime', 0, instant + interval '1 hour', "
            "original_text, offset_state, offset_present, effective_instant + interval '1 hour', true FROM "
            "phone_time_values WHERE model_type = 'Location'"))
    state, data = _draw(w, "timeline_lens", {"lens_kinds": ["messages", "locations", "device"]}, fmt="rsmf")
    _, manifest, _ = rsmf.read(data)
    ids = [e["id"] for e in manifest["events"]]
    # 3 messages, the location at two times and the device event
    assert state["counts"]["total"] == len(ids) == state["counts"]["rsmf"]["events"] == 6
    assert len(set(ids)) == len(ids)


def test_a_lens_with_no_communication_kind_exports_its_other_entries(world):
    from services.phone.exports import jobs
    w = world
    with w["engine"].connect() as c:
        facts = jobs.describe_lens(c, w["case"], {"lens_kinds": ["locations"]})
        machine = jobs.describe_machine_text(c, w["case"], {"lens_kinds": ["locations"]}, lens=True)
    assert facts["total"] == 1 and facts["messages"] == 0 and facts["phones"] == 1
    assert machine["total"] == 0


def test_create_accepts_all_eight_sources_and_refuses_a_selection_source_without_its_selection(world):
    from services.phone.exports import jobs
    w = world
    assert set(jobs.BUILT_SOURCES) == {"stream", "timeline_lens", "collection", "finding", "dossier",
                                       "statement_check", "analysis_result", "incident_window"}
    with w["engine"].begin() as c:
        for source in ("collection", "dossier"):
            with pytest.raises(jobs.ExportError, match="exported through the selection of its phone records"):
                jobs.create(c, case_id=w["case"], user_id=w["user"], fmt="pdf", source=source, filter_body={},
                            options={})
        made = jobs.create(c, case_id=w["case"], user_id=w["user"], fmt="pdf", source="timeline_lens",
                           filter_body={"lens_kinds": ["messages"]}, options={})
        stored = c.execute(text("SELECT filter FROM phone_exports WHERE export_id = :i"),
                           {"i": made["export_id"]}).scalar()
    assert stored["lens_kinds"] == ["messages"]
