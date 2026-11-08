"""07 section 4.7: the job tray's one list. Synthetic rows only. Needs the PostgreSQL template."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from tests.phone_pg import needs_template
from tests.test_phone_media import world  # noqa: F401 (fixture)
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)

pytestmark = needs_template


def _person(c, email):
    uid = uuid.uuid4()
    c.execute(text("INSERT INTO users (id, email, name, password_hash, global_role, is_active) VALUES "
                   "(:i, :e, 'Synthetic', 'x', 'guest', true)"), {"i": uid, "e": email})
    return SimpleNamespace(id=uid, email=email)


def _read(engine, case, user):
    from services.phone import job_list
    with engine.connect() as c:
        return job_list.read(c, case, user)


def _ids(out):
    return {j["id"].split(":")[0]: j for j in out["items"]}


def test_every_kind_is_listed_with_true_counts_and_a_reader_sees_only_their_own_together(world):
    from services.phone import derive, job_list
    engine, case, other, ext = world
    with engine.begin() as c:
        me, them = _person(c, "a@synthetic.invalid"), _person(c, "b@synthetic.invalid")
        c.execute(text("INSERT INTO jobs (id, case_id, file_name, file_path, status, progress, job_type, pipeline_state, "
                       "created_at, updated_at) VALUES (:i, :c, 'C3.ufdr', 'x', 'capturing', 0, 'phone_capture', "
                       "CAST(:p AS jsonb), now() at time zone 'utc', now() at time zone 'utc')"),
                  {"i": uuid.uuid4(), "c": str(case),
                   "p": '{"phone": {"stage": "records", "counts": {"records": 12}}}'})
        c.execute(text("INSERT INTO phone_exports (export_id, case_id, created_by, format, source, filter, options, state, "
                       "progress) VALUES (:i, :c, :u, 'pdf', 'stream', '{}', '{}', 'rendering', 0.25)"),
                  {"i": uuid.uuid4(), "c": case, "u": me.id})
        c.execute(text("INSERT INTO pol_colocation_run (id, case_id, subjects, params, status, requested_by, window_start, "
                       "window_end) VALUES (:i, :c, '[]', '{}', 'running', :u, now(), now())"),
                  {"i": uuid.uuid4(), "c": case, "u": me.email})
        c.execute(text("INSERT INTO phone_analysis_runs (id, case_id, approach, approach_version, parameters, "
                       "parameters_sha256, input_manifest, input_revision, status, requested_by, progress) VALUES (:i, :c, "
                       "'deletion_timeline', '1', '{}', :s, '{}', :s, 'running', 'x', "
                       "CAST('{\"read\": 40, \"total\": 100}' AS jsonb))"), {"i": uuid.uuid4(), "c": case, "s": "0" * 64})
        run = job_list.start_collect(c, case_id=case, user_id=me.id, target_words="a dossier", noun="messages", total=12345)
        job_list.report_collect(c, run_id=run, case_id=case, user_id=me.id, sent=5000, added=4990, skipped=10, refused=0,
                                refused_reason=None, finished=False, error=None)
    out = _read(engine, case, me)
    kinds = _ids(out)
    assert {"intake", "export", "together", "approach", "collect"} <= set(kinds)
    assert out["active"] is True and out["unavailable"] == []
    assert (kinds["approach"]["title"], kinds["approach"]["done"], kinds["approach"]["total"]) == ("Deleted and hidden", 40, 100)
    assert (kinds["export"]["done"], kinds["export"]["total"]) == (25, 100)
    assert (kinds["collect"]["done"], kinds["collect"]["total"], kinds["collect"]["state"]) == (5000, 12345, "running")
    assert kinds["intake"]["stage"] == "records" and kinds["intake"]["counts"] == {"records": 12}
    # Together and a bulk add belong to the person who asked
    assert not {"together", "collect"} & set(_ids(_read(engine, case, them)))
    assert _read(engine, other, me)["items"] == []


def test_idle_case_says_no_tab_need_keep_asking(world):
    engine, case, _, ext = world
    with engine.begin() as c:
        me = _person(c, "a@synthetic.invalid")
    out = _read(engine, case, me)
    assert out["active"] is False and all(j["state"] != "running" for j in out["items"])


def test_a_failure_is_named_and_a_silent_bulk_add_says_how_many_went(world):
    from services.phone import job_list
    engine, case, _, ext = world
    with engine.begin() as c:
        me = _person(c, "a@synthetic.invalid")
        c.execute(text("INSERT INTO phone_exports (export_id, case_id, created_by, format, source, filter, options, state, "
                       "error, finished_at) VALUES (:i, :c, :u, 'rsmf', 'stream', '{}', '{}', 'failed', "
                       "'The disk is full.', now())"), {"i": uuid.uuid4(), "c": case, "u": me.id})
        run = job_list.start_collect(c, case_id=case, user_id=me.id, target_words="a dossier", noun="messages", total=100)
        job_list.report_collect(c, run_id=run, case_id=case, user_id=me.id, sent=40, added=40, skipped=0, refused=0,
                                refused_reason=None, finished=False, error=None)
        c.execute(text("UPDATE phone_collect_runs SET updated_at = now() - interval '3 minutes'"))
    kinds = _ids(_read(engine, case, me))
    assert (kinds["export"]["state"], kinds["export"]["error"]) == ("failed", "The disk is full.")
    assert kinds["collect"]["state"] == "failed"
    assert "40 of 100 were sent; the rest were not added" in kinds["collect"]["error"]


def test_a_source_that_cannot_be_read_is_named_not_dropped(world, monkeypatch):
    from services.phone import job_list
    engine, case, _, ext = world
    with engine.begin() as c:
        me = _person(c, "a@synthetic.invalid")

    def broken(conn, *a):
        conn.execute(text("SELECT * FROM no_such_table"))

    monkeypatch.setattr(job_list, "SOURCES", (("exports", broken),) + job_list.SOURCES[3:])
    out = _read(engine, case, me)
    assert out["unavailable"] == ["exports"]


def test_a_cancelled_job_says_cancelled_not_done(world):
    engine, case, _, ext = world
    with engine.begin() as c:
        me = _person(c, "a@synthetic.invalid")
        c.execute(text("INSERT INTO phone_analysis_runs (id, case_id, approach, approach_version, parameters, "
                       "parameters_sha256, input_manifest, input_revision, status, requested_by, finished_at) VALUES (:i, "
                       ":c, 'deletion_timeline', '1', '{}', :s, '{}', :s, 'cancelled', 'x', now())"),
                  {"i": uuid.uuid4(), "c": case, "s": "0" * 64})
    run = _ids(_read(engine, case, me))["approach"]
    assert (run["state"], run["note"]) == ("cancelled", "Cancelled before it finished.")


def test_finished_jobs_past_the_limit_are_counted(world):
    from services.phone import job_list
    engine, case, _, ext = world
    with engine.begin() as c:
        me = _person(c, "a@synthetic.invalid")
        for _ in range(job_list.MOST_FINISHED + 3):
            c.execute(text("INSERT INTO phone_exports (export_id, case_id, created_by, format, source, filter, options, "
                           "state, finished_at) VALUES (:i, :c, :u, 'pdf', 'stream', '{}', '{}', 'done', now())"),
                      {"i": uuid.uuid4(), "c": case, "u": me.id})
    out = _read(engine, case, me)
    assert len([j for j in out["items"] if j["kind"] == "export"]) == job_list.MOST_FINISHED
    assert out["older_finished"] == 4  # the 3 exports over the limit and the fixture's own phone reading


def test_a_mark_is_kept_per_person_and_a_finished_add_is_not_reopened(world):
    from services.phone import job_list
    engine, case, _, ext = world
    with engine.begin() as c:
        me, them = _person(c, "a@synthetic.invalid"), _person(c, "b@synthetic.invalid")
        assert "first_phone_card_seen" in job_list.set_mark(c, me.id, "first_phone_card_seen")
        first = job_list.marks(c, me.id)
        assert job_list.set_mark(c, me.id, "first_phone_card_seen") == first
        assert job_list.marks(c, them.id) == {}
        run = job_list.start_collect(c, case_id=case, user_id=me.id, target_words="a note", noun="pairs", total=2)
        kw = dict(run_id=run, case_id=case, sent=2, added=2, skipped=0, refused=0, refused_reason=None, error=None)
        assert job_list.report_collect(c, user_id=them.id, finished=True, **kw) is False  # not their run
        assert job_list.report_collect(c, user_id=me.id, finished=True, **kw) is True
        assert job_list.report_collect(c, user_id=me.id, finished=True, **kw) is False


def test_flow_partners_are_busiest_first_and_read_only_this_case():
    from services.phone import graph_projection

    class Session:
        def run(self, query, **params):
            self.params = params
            return [{"key": "phone-identity:b", "name": "B", "volume": 9}, {"key": "phone-identity:c", "name": None, "volume": 1}]

    s = Session()
    out = graph_projection.flow_partners("case-1", "a", graph_session=s)
    assert s.params == {"case": "case-1", "key": "phone-identity:a"}
    assert [p["key"] for p in out["partners"]] == ["b", "c"] and out["total"] == 2


def test_has_position_keeps_only_files_whose_metadata_names_a_place(world):
    from services.phone import media
    engine, case, _, ext = world
    with engine.begin() as c:
        c.execute(text("UPDATE phone_files SET body = CAST(:b AS jsonb) WHERE extraction_id = :e AND ordinal = 9000"),
                  {"e": ext, "b": '["file", {}, null, [["metadata", {"section": "EXIF"}, null, '
                                  '[["item", {"name": "ExifEnumGPSLatitude"}, "12.5", null]]]]]'})
        c.execute(text("UPDATE phone_files SET body = CAST(:b AS jsonb) WHERE extraction_id = :e AND ordinal = 9001"),
                  {"e": ext, "b": '["file", {}, null, [["metadata", {"section": "EXIF"}, null, '
                                  '[["item", {"name": "ExifEnumGPSLatitude"}, "", null]]]]]'})
    with engine.connect() as c:
        whole = media.index(c, case, {"phones": [ext]})["total"]
        placed = media.index(c, case, {"phones": [ext], "has_position": True})["total"]
        rest = media.index(c, case, {"phones": [ext], "has_position": False})["total"]
        rows = media.window(c, case, {"phones": [ext], "has_position": True})["items"]
    assert placed == 1 and whole == placed + rest and len(rows) == 1
    # batch reading of the same scope takes the filter too: the Media page sends it (live 422 on the first release)
    from routers.phones import MediaScope, _batch_scope
    from services.phone import derive_batch
    scope = _batch_scope(case, MediaScope(has_position=True))
    assert scope == {"has_position": True}
    with engine.connect() as c:
        assert derive_batch.describe(c, case, "ocr", scope)["in_scope"] <= placed


def test_a_phone_read_a_while_ago_leaves_the_tray_sooner_than_a_persons_job(world):
    from services.phone import job_list
    engine, case, _, ext = world
    with engine.begin() as c:
        me = _person(c, "a@synthetic.invalid")
        c.execute(text("INSERT INTO phone_interpretation_progress (extraction_id, records_total, records_done, started_at, "
                       "updated_at, finished_at) VALUES (:e, 5, 5, now(), now(), now() - interval '2 hours') ON CONFLICT "
                       "(extraction_id) DO UPDATE SET finished_at = now() - interval '2 hours'"), {"e": ext})
    assert "interpretation" not in _ids(_read(engine, case, me))
    with engine.begin() as c:
        c.execute(text("UPDATE phone_interpretation_progress SET finished_at = now() - interval '10 minutes'"))
    assert "interpretation" in _ids(_read(engine, case, me))
