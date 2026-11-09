"""07 section 6.3, CO-8 and CO-15: a link's state is worked out when it is shown and the stored link is never
rewritten. Synthetic phones only; every change runs through the real decision and re-read path."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from postgres import link_types
from services import workspace_attention_service as attention
from services.phone import link_states as S
from services.phone import corrections, resolvers, sweep
from services.phone import readings
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_phone_readings import _actor, _call_id, _setup, review  # noqa: F401 (fixture)
from tests.test_phone_corrections import T0, _message, _uid, phone  # noqa: F401 (fixture)
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)


class Who:
    def __init__(self, uid, name="Synthetic Reviewer", email="s@x.test"):
        self.id, self.user_id, self.name, self.email = uid, uid, name, email


def _entry(c, case, user):
    eid = uuid.uuid4()
    c.execute(text("INSERT INTO workspace_entries (id, case_id, entry_type, title, body) VALUES (:i, :c, 'finding', "
                   "'Synthetic finding', 'Synthetic body')"), {"i": eid, "c": case})
    return eid


def _link(c, case, entry, user, target_type, target_id):
    """A link stored as the collect paths store it: the mapping versions the resolver reports now."""
    resolvers.register()
    target = link_types.resolve_phone_target(c, case, target_type, str(target_id))
    lid = uuid.uuid4()
    c.execute(text(
        "INSERT INTO workspace_entry_links (id, entry_id, case_id, target_type, target_id, target_label, relationship, "
        "source_anchor, metadata, created_by_user_id) VALUES (:i, :e, :c, :t, :ti, 'Synthetic label', 'supports', "
        "CAST(:a AS jsonb), '{}', :u)"), {"i": lid, "e": entry, "c": case, "t": target_type, "ti": str(target_id),
                                          "a": json.dumps(link_types.phone_anchor(target, None)), "u": user})
    return str(lid)


def _stored(c, lid):
    return tuple(c.execute(text("SELECT target_type, target_id, target_label, relationship, source_anchor, metadata, "
                                "created_by_user_id, created_at, updated_at FROM workspace_entry_links WHERE id = :i"),
                           {"i": lid}).one())


def _calls(c, ext):
    return [str(r) for r in c.execute(text("SELECT record_uid FROM pv_record WHERE extraction_id = :e AND model_type = "
                                           "'Call' ORDER BY record_uid"), {"e": ext}).scalars()]


def _correct_sender(engine, case, ext, actor):
    with Session(engine) as db:
        readings.correct(db, case, _call_id(db.connection(), ext, "Call.role.From"), choice_id="role:callee",
                         reason="the from side is the far end on this handset", actor=actor)
        db.commit()
    assert sweep.interpret_one(engine, ext)["status"] == "done"


@needs_template
def test_co15_correcting_a_sender_mapping_flags_every_link_and_changes_no_stored_link(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            entry = _entry(c, case, user)
            links = [_link(c, case, entry, user, "phone_record", r) for r in calls[:2]]
            before = [_stored(c, lid) for lid in links]
        _correct_sender(engine, case, ext, actor)
        with engine.connect() as c:
            found = S.of_container(c, case, "entry", entry, user)
            assert sorted(found) == sorted(links)
            for lid in links:
                state = found[lid]
                assert "reading_changed" in state["states"] and state["needs_choice"] and state["can_choose"]
                sender = next(i for i in state["reading_changed"]["items"] if i["field"] == "sender")
                assert sender["was"] == "+12025550100" and sender["now"] is None
                assert sender["words"].startswith("Sender was +12025550100, now not recorded, by Synthetic Reviewer on ")
                assert state["reading_changed"]["items"][0] == sender  # the sender leads, the attention item says it
                other = next(i for i in state["reading_changed"]["items"] if i["field"] == "recipients")
                assert other["words"].startswith("Recipients were ")
            assert [_stored(c, lid) for lid in links] == before  # 6.3: the stored link is never rewritten
            # the third call is collected by nothing: no change row, however many records the correction touched
            assert c.execute(text("SELECT count(DISTINCT record_uid) FROM phone_reading_changes")).scalar() == 2
            feed = S.outstanding(c, case, user)
            assert (feed["links"], feed["records"]) == (2, 2)  # one item with the true count, not one per link


@needs_template
def test_a_link_collected_after_the_change_is_active_and_a_new_reading_with_no_change_flags_nothing(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            entry = _entry(c, case, user)
            early = _link(c, case, entry, user, "phone_record", calls[0])
        _correct_sender(engine, case, ext, actor)
        with engine.begin() as c:
            late = _link(c, case, entry, user, "phone_record", calls[1])
        with engine.connect() as c:
            found = S.of_container(c, case, "entry", entry, user)
        assert "reading_changed" in found[early]["states"] and "reading_changed" not in found[late]["states"]
        assert found[late]["needs_choice"] is False


@needs_template
def test_a_thread_link_counts_its_changed_records(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            entry = _entry(c, case, user)
            key = c.execute(text("SELECT thread_key FROM pv_comm_event WHERE extraction_id = :e LIMIT 1"),
                            {"e": ext}).scalar()
            lid = _link(c, case, entry, user, "phone_thread", key)
            n = c.execute(text("SELECT count(*) FROM pv_comm_event WHERE thread_key = :k"), {"k": key}).scalar()
        _correct_sender(engine, case, ext, actor)
        with engine.connect() as c:
            state = S.of_container(c, case, "entry", entry, user)[lid]
        assert state["records"] == n and state["reading_changed"]["records"] == n


@needs_template
def test_keep_records_who_and_when_leaves_the_link_alone_and_a_later_change_asks_again(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            entry = _entry(c, case, user)
            lid = _link(c, case, entry, user, "phone_record", calls[0])
            before = _stored(c, lid)
        _correct_sender(engine, case, ext, actor)
        with Session(engine) as db:
            state = S.of_container(db.connection(), case, "entry", entry, user)[lid]
            with pytest.raises(S.Changed):
                S.choose(db, case_id=case, link_kind="entry", link_id=lid, choice="keep",
                         through_seq=state["through_seq"] - 1, user=Who(user))
            db.rollback()
            with pytest.raises(S.NotYours):
                S.choose(db, case_id=case, link_kind="entry", link_id=lid, choice="keep",
                         through_seq=state["through_seq"], user=Who(uuid.uuid4(), "Someone Else"))
            db.rollback()
            out = S.choose(db, case_id=case, link_kind="entry", link_id=lid, choice="keep",
                           through_seq=state["through_seq"], user=Who(user))
            assert out["choice"] == "keep" and out["removed"] is False
        with engine.connect() as c:
            assert _stored(c, lid) == before
            row = c.execute(text("SELECT choice, chosen_by, chosen_by_user_id, target_id FROM phone_link_choices")).one()
            assert tuple(row) == ("keep", "Synthetic Reviewer", user, calls[0])
            state = S.of_container(c, case, "entry", entry, user)[lid]
            assert state["states"] == ["reading_changed"] and state["needs_choice"] is False  # both values stay shown
            assert state["kept"]["by"] == "Synthetic Reviewer" and S.outstanding(c, case, user) is None
            assert c.execute(text("SELECT count(*) FROM manual_changes WHERE kind = 'phone_link_choice'")).scalar() == 1


@needs_template
def test_remove_goes_through_the_entry_removal_path_and_keeps_its_record(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            c.execute(text("UPDATE users SET name = 'Synthetic Reviewer' WHERE id = :u"), {"u": user})
            entry = _entry(c, case, user)
            lid = _link(c, case, entry, user, "phone_record", calls[0])
            version = c.execute(text("SELECT version FROM workspace_entries WHERE id = :i"), {"i": entry}).scalar()
        _correct_sender(engine, case, ext, actor)
        with Session(engine) as db:
            from postgres.models.user import User
            person = db.get(User, user)
            state = S.of_container(db.connection(), case, "entry", entry, user)[lid]
            S.choose(db, case_id=case, link_kind="entry", link_id=lid, choice="remove",
                     through_seq=state["through_seq"], user=person, expected_version=version)
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM workspace_entry_links WHERE id = :i"), {"i": lid}).scalar() == 0
            assert c.execute(text("SELECT event_type FROM workspace_entry_events WHERE entry_id = :e AND event_type = "
                                  "'link_removed'"), {"e": entry}).scalar() == "link_removed"
            assert c.execute(text("SELECT choice FROM phone_link_choices WHERE link_id = :i"), {"i": lid}).scalar() == "remove"


@needs_template
def test_co8_a_corrected_record_shows_both_values_and_an_earlier_correction_is_not_since_collected(phone):
    engine, case, ext, actor = phone
    with engine.begin() as c:
        uid, user = _uid(c, ext), actor.user_id
        entry = _entry(c, case, user)
        lid = _link(c, case, entry, user, "phone_record", uid)
        before = _stored(c, lid)
    with Session(engine) as db:
        corrections.correct_value(db, case_id=case, record_uid=uid, field_path="Body",
                                  corrected_text="synthetic corrected words", reason="misread", actor=actor)
        db.commit()
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    with engine.begin() as c:
        found = S.of_container(c, case, "entry", entry, user)[lid]
        item = found["corrected"]["items"][0]
        assert (item["was"], item["now"], item["by"]) == ("synthetic original words", "synthetic corrected words",
                                                          "Synthetic Reviewer")
        assert found["states"] == ["corrected"]  # a value correction is corrected, not a changed reading
        assert c.execute(text("SELECT count(*) FROM phone_reading_changes")).scalar() == 0
        assert _stored(c, lid) == before
        # only the corrected value is read elsewhere
        assert c.execute(text("SELECT body FROM pv_comm_event WHERE record_uid = :r"), {"r": uid}).scalar() == \
            "synthetic corrected words"
        # a link made after the correction collected the corrected value
        c.execute(text("DELETE FROM workspace_entry_links WHERE id = :i"), {"i": lid})
        again = _link(c, case, entry, user, "phone_record", uid)
        assert S.of_container(c, case, "entry", entry, user)[again]["states"] == []
    with Session(engine) as db:  # undone: as collected again
        corrections.correct_value(db, case_id=case, record_uid=uid, field_path="Body",
                                  corrected_text="synthetic original words", reason="undo", actor=actor)
        db.commit()
    with engine.connect() as c:
        assert S.of_container(c, case, "entry", entry, user)[again]["corrected"]["count"] == 1  # now differs from then


@needs_template
def test_the_attention_feed_gives_the_adder_one_item_with_the_true_count_and_nobody_else(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            entry = _entry(c, case, user)
            for r in calls:
                _link(c, case, entry, user, "phone_record", r)
        _correct_sender(engine, case, ext, actor)
        with Session(engine) as db:
            items = attention._link_state_candidates(db, case_id=case, user=Who(user))
            assert len(items) == 1
            assert items[0].metadata == {"links": 3, "records": 3}
            assert items[0].reason_code == "phone_link_reading_changed"
            assert "3 records" in items[0].title and "3 links" in items[0].title
            assert attention._link_state_candidates(db, case_id=case, user=Who(uuid.uuid4())) == []


@needs_template
def test_a_link_from_before_changes_were_recorded_says_what_changed_was_not_kept(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            entry = _entry(c, case, user)
            lid = _link(c, case, entry, user, "phone_record", calls[0])
            c.execute(text("UPDATE phone_interpretation_state SET reading_changes_since = generation + 1 WHERE "
                           "extraction_id = :e"), {"e": ext})
        with engine.connect() as c:
            state = S.of_container(c, case, "entry", entry, user)[lid]
        assert state["states"] == [] and "not kept" in state["reread"]["words"]


@needs_template
def test_a_finding_of_many_links_costs_a_fixed_number_of_queries(review):
    from sqlalchemy import event
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            one, three = _entry(c, case, user), _entry(c, case, user)
            _link(c, case, one, user, "phone_record", calls[0])
            for r in calls:
                _link(c, case, three, user, "phone_record", r)
        _correct_sender(engine, case, ext, actor)
        counts = []
        with engine.connect() as c:
            for entry in (one, three):
                seen = []
                listener = lambda *a: seen.append(a[2])  # noqa: E731
                event.listen(engine, "before_cursor_execute", listener)
                S.of_container(c, case, "entry", entry, user)
                event.remove(engine, "before_cursor_execute", listener)
                counts.append(len(seen))
        assert counts[0] == counts[1]


@needs_template
def test_a_linked_copy_the_lists_do_not_show_is_set_aside_with_the_record_they_show(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)  # three equal calls: one event found three times
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            entry = _entry(c, case, user)
            links = [_link(c, case, entry, user, "phone_record", r) for r in calls]
        with engine.connect() as c:
            found = S.of_container(c, case, "entry", entry, user)
        shown = [lid for lid in links if found[lid]["set_aside"] is None]
        assert len(shown) == 1 and found[shown[0]]["states"] == []  # the copy the lists show is not set aside
        kept = found[shown[0]]["target_id"]
        for lid in set(links) - set(shown):
            assert found[lid]["states"] == ["set_aside"] and found[lid]["set_aside"]["shown_record_uid"] == kept


@needs_template
def test_co8_the_export_of_a_finding_carries_both_values_on_the_row_and_says_how_many(phone, monkeypatch):
    from services.phone import entry_export
    from services.phone.exports import jobs, pdf
    engine, case, ext, actor = phone
    with engine.begin() as c:
        uid, user = _uid(c, ext), actor.user_id
        entry = _entry(c, case, user)
        _link(c, case, entry, user, "phone_record", uid)
    with Session(engine) as db:
        corrections.correct_value(db, case_id=case, record_uid=uid, field_path="Body",
                                  corrected_text="synthetic corrected words", reason="misread", actor=actor)
        db.commit()
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    with Session(engine) as db:
        frozen = entry_export.freeze_entry(db, case, entry, Who(user))
    with engine.begin() as c:
        out = jobs.create(c, case_id=case, user_id=user, fmt="pdf", source="finding", filter_body=frozen["filter"],
                          options={})
    built = {}

    def capture(**kw):
        built.update(kw)
        return "<html></html>", {}
    monkeypatch.setattr(pdf, "build_html", capture)
    monkeypatch.setattr(pdf, "render_isolated", lambda doc: b"%PDF-synthetic")
    jobs.draw(engine, out["export_id"])
    rows = [r for _, day in built["days"] for r in day]
    assert len(rows) == 1 and rows[0]["body"] == "synthetic corrected words"  # only the corrected value is read
    note = rows[0]["link_notes"][0]
    assert note.startswith("Corrected since collected. Body: as collected synthetic original words, now synthetic "
                           "corrected words, corrected by Synthetic Reviewer on ")
    assert "1 of these 1 rows changed since they were collected (corrected, read differently or set aside as a " \
           "duplicate); each such row shows what changed." in built["contains"]
    html = pdf._row_html(rows[0], {})
    assert "as collected synthetic original words" in html


@needs_template
def test_a_selection_link_is_flagged_for_the_records_it_holds_with_the_true_count(review):
    from services.phone import entry_export
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            entry = _entry(c, case, user)
        with Session(engine) as db:
            sid, _, _ = entry_export.store_selection(db, str(case), calls[:2], "two synthetic calls", Who(user))
            db.commit()
        with engine.begin() as c:
            lid = _link(c, case, entry, user, "phone_selection", sid)
            c.execute(text("INSERT INTO collection_memberships (id, case_id, container_type, container_id, link_id, "
                           "record_id) VALUES (:i, :c, 'entry', :o, :l, :r)"),
                      [{"i": uuid.uuid4(), "c": case, "o": str(entry), "l": lid, "r": r} for r in calls[:2]])
        _correct_sender(engine, case, ext, actor)
        with engine.connect() as c:
            state = S.of_container(c, case, "entry", entry, user)[lid]
            assert state["records"] == 2 and state["reading_changed"]["records"] == 2 and state["needs_choice"]
            assert c.execute(text("SELECT count(DISTINCT record_uid) FROM phone_reading_changes")).scalar() == 2
            notes = S.export_notes(c, case, sid)  # a collection export carries the state of the links holding it
            assert sorted(notes) == sorted(calls[:2])


@needs_template
def test_an_rsmf_export_prints_every_note_because_its_rows_hold_the_originals_only(phone, monkeypatch):
    from services.phone import entry_export
    from services.phone.exports import jobs
    engine, case, ext, actor = phone
    with engine.begin() as c:
        uid, user = _uid(c, ext), actor.user_id
        entry = _entry(c, case, user)
        _link(c, case, entry, user, "phone_record", uid)
    with Session(engine) as db:
        corrections.correct_value(db, case_id=case, record_uid=uid, field_path="Body", corrected_text="synthetic new",
                                  reason="misread", actor=actor)
        db.commit()
    assert sweep.interpret_one(engine, ext)["status"] == "done"
    with Session(engine) as db:
        frozen = entry_export.freeze_entry(db, case, entry, Who(user))
    with engine.begin() as c:
        out = jobs.create(c, case_id=case, user_id=user, fmt="rsmf", source="finding", filter_body=frozen["filter"],
                          options={})
    seen = {}

    def capture(engine_, e, export_id, options, contains, days):
        seen["contains"] = contains
        return b"synthetic", {}
    monkeypatch.setattr(jobs, "_rsmf", capture)
    jobs.draw(engine, out["export_id"])
    assert any(line.startswith("Record %s: Corrected since collected." % uid) for line in seen["contains"])


def _dossier(c, case, user):
    did = uuid.uuid4()
    c.execute(text("INSERT INTO case_profiles (id, case_id, profile_type, display_name, contacts, linkage_state, status, "
                   "needs_link_review, graph_entity_deleted) VALUES (:i, :c, 'person', 'Synthetic dossier', '[]', "
                   "'unlinked', 'active', false, false)"), {"i": did, "c": case})
    return did


def _interview_link(c, case, dossier, user, target_type, target_id):
    interview, lid = uuid.uuid4(), uuid.uuid4()
    c.execute(text("INSERT INTO dossier_interviews (id, dossier_id, case_id, participants, status, created_by_user_id) "
                   "VALUES (:i, :d, :c, '[]', 'draft', :u)"), {"i": interview, "d": dossier, "c": case, "u": user})
    resolvers.register()
    target = link_types.resolve_phone_target(c, case, target_type, str(target_id))
    c.execute(text("INSERT INTO dossier_interview_evidence_links (id, interview_id, case_id, target_type, target_id, "
                   "source_anchor) VALUES (:i, :v, :c, :t, :ti, CAST(:a AS jsonb))"),
              {"i": lid, "v": interview, "c": case, "t": target_type, "ti": str(target_id),
               "a": json.dumps(link_types.phone_anchor(target, None))})
    return str(lid)


def _kept_link(c, case, entry, user, ext, uids):
    """A kept result linked as the keep path stores it: the records and the readings live in the snapshot only."""
    from services.pattern_of_life import snapshots
    snap = {"kind": "analysis_result", "record_ids": [str(u) for u in uids],
            "mapping_versions": snapshots.mapping_versions(c, str(case), [str(ext)]),
            "window": {"start": None, "end": None}, "summary_counts": {"records": len(uids)}}
    sid, lid = "pa_%s" % uuid.uuid4().hex, uuid.uuid4()
    c.execute(text("INSERT INTO pol_analysis_snapshot (id, case_id, kind, label, snapshot, record_count) VALUES (:i, :c, "
                   "'analysis_result', 'Kept', CAST(:s AS jsonb), :n)"),
              {"i": sid, "c": str(case), "s": json.dumps(snap, default=str), "n": len(uids)})
    c.execute(text(
        "INSERT INTO workspace_entry_links (id, entry_id, case_id, target_type, target_id, target_label, relationship, "
        "source_anchor, metadata, created_by_user_id) VALUES (:i, :e, :c, 'phone_analysis', :ti, 'Kept', 'supports', "
        "'{}', '{}', :u)"), {"i": lid, "e": entry, "c": case, "ti": sid, "u": user})
    return str(lid)


@needs_template
def test_a_kept_result_is_flagged_for_the_records_its_snapshot_holds_with_the_true_count(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            entry = _entry(c, case, user)
            lid = _kept_link(c, case, entry, user, ext, calls[:2])
        _correct_sender(engine, case, ext, actor)
        with engine.connect() as c:
            # the change is noted only because the kept result's records count as collected
            assert c.execute(text("SELECT count(DISTINCT record_uid) FROM phone_reading_changes")).scalar() == 2
            state = S.of_container(c, case, "entry", entry, user)[lid]
            assert "reading_changed" in state["states"] and state["needs_choice"] and state["can_remove"]
            assert (state["records"], state["reading_changed"]["records"]) == (2, 2)


@needs_template
def test_a_kept_after_the_change_is_not_flagged(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            entry = _entry(c, case, user)
            _kept_link(c, case, entry, user, ext, calls[:2])
        _correct_sender(engine, case, ext, actor)
        with engine.begin() as c:
            later = _kept_link(c, case, entry, user, ext, calls[:2])
        with engine.connect() as c:
            assert S.of_container(c, case, "entry", entry, user)[later]["states"] == []


@needs_template
def test_an_interview_evidence_link_shows_its_state_and_is_removed_by_editing_the_interview(review):
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            dossier = _dossier(c, case, user)
            lid = _interview_link(c, case, dossier, user, "phone_record", calls[0])
        _correct_sender(engine, case, ext, actor)
        with engine.connect() as c:
            state = S.of_container(c, case, "dossier", dossier, user)[lid]
            assert state["link_kind"] == "interview" and "reading_changed" in state["states"]
            assert state["needs_choice"] and state["can_choose"] and not state["can_remove"]
            assert S.outstanding(c, case, user)["links"] == 1
        with Session(engine) as db:
            with pytest.raises(S.LinkStateError, match="editing the interview"):
                S.choose(db, case_id=case, link_kind="interview", link_id=lid, choice="remove",
                         through_seq=state["through_seq"], user=Who(user))
        with Session(engine) as db:
            assert S.choose(db, case_id=case, link_kind="interview", link_id=lid, choice="keep",
                            through_seq=state["through_seq"], user=Who(user))["choice"] == "keep"


@needs_template
def test_the_agent_reads_a_link_state_on_casework_and_a_dossier_with_the_note_to_say_so(review):
    from services.agent import casework_tools
    with fresh_engine() as engine:
        case, ext, actor = _setup(engine)
        with engine.begin() as c:
            calls, user = _calls(c, ext), actor.user_id
            entry = _entry(c, case, user)
            flagged = _link(c, case, entry, user, "phone_record", calls[0])
            dossier = _dossier(c, case, user)
            on_interview = _interview_link(c, case, dossier, user, "phone_record", calls[1])
        _correct_sender(engine, case, ext, actor)
        with engine.begin() as c:
            unchanged = _link(c, case, entry, user, "phone_record", calls[1])  # collected after the change
        with Session(engine) as db:
            out = casework_tools.casework(db, case)
            links = {l["id"]: l for l in out["items"][0]["links"]}
            state = links[flagged]["link_state"]
            assert state["states"] == ["reading_changed"] and state["records_read_differently"] == 1
            assert state["words"][0].startswith("Reading changed since collected. Sender was +12025550100, now not ")
            assert "reading_changed" not in (links[unchanged].get("link_state") or {}).get("states", [])
            assert out["link_states"].startswith("Links with link_state here: ")
            read = casework_tools.dossier(db, case, str(dossier))
            evidence = read["items"][0]["interviews"][0]["evidence"][0]
            assert evidence["id"] == on_interview and "reading_changed" in evidence["link_state"]["states"]
            assert read["link_states"]
