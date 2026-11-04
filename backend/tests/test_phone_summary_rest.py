"""03 section 7.3 and 07 J-15 on the Phone summary: busiest weeks (each count the one its Conversations link lists),
Since you last looked (counts per change kind, a colleague's change counted and the viewer's own not), Export profile
as PDF through the export jobs (same renderer), and the export history a phone lists. Synthetic data only."""
from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from services.phone import streams
from services.phone.filters import StreamFilter
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

pytestmark = needs_template
OWNER, ANA = "phone:+12025550100", "phone:+12025550143"


def msg(instant, body="hello"):
    return dict(kind="message", instant=instant, body=body, direction="incoming", thread="t",
                parties=[(ANA, "sender", False, None, None), (OWNER, "recipient", True, None, None)])


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("LOUPE_PHONE_EXPORT_DIR", str(tmp_path))
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            # three messages in the week of Monday March 13, 2023, one in the week of March 20 (Eastern time)
            ext, _ = phone(c, case, device_zone="America/New_York", events=[
                msg(at(2023, 3, 13, 15)), msg(at(2023, 3, 14, 15)), msg(at(2023, 3, 20, 3, 30)),  # Sunday 19th, 11:30 PM Eastern
                msg(at(2023, 3, 21, 15))])
            c.execute(text("UPDATE cases SET title = 'Synthetic summary case' WHERE id = :c"), {"c": case})
            user = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
        yield {"engine": engine, "case": case, "ext": ext, "user": user}


def test_busiest_weeks_count_what_their_link_lists_in_the_display_zone(world):
    from services.phone import profile
    with world["engine"].connect() as c:
        p = profile.profile(c, str(world["case"]), world["ext"])
        weeks = p["busiest_weeks"]
        assert [(w["week"], w["events"]) for w in weeks] == [("2023-03-13", 3), ("2023-03-20", 1)]
        assert weeks[0]["link"].endswith("?from=2023-03-13&to=2023-03-19&notime=0")
        zone = streams.resolve_zone(c, StreamFilter.model_validate({"case_id": str(world["case"])}))["name"]
        assert zone  # the list the link opens: same days, dated only
        n = streams.shown_count(c, StreamFilter.model_validate({
            "case_id": str(world["case"]), "phones": [str(world["ext"])], "include_no_time": False,
            "from_instant": "2023-03-13T04:00:00Z", "to_instant": "2023-03-20T03:59:59.999Z"}))
        assert n == weeks[0]["events"]


def test_since_you_last_looked_counts_a_colleagues_change_and_not_my_own(world):
    from services.phone import profile
    eng, case, ext, me = world["engine"], world["case"], world["ext"], world["user"]
    with eng.connect() as c:  # the database's own clock, after the fixture's phone was made
        t0 = c.execute(text("SELECT clock_timestamp()")).scalar()
    with eng.begin() as c:
        colleague = uuid.uuid4()
        c.execute(text("INSERT INTO users (id, email, name, password_hash, global_role, is_active, created_at, "
                       "updated_at) VALUES (:u, :e, 'synthetic colleague', 'x', 'user', true, now(), now())"),
                  {"u": colleague, "e": "c%s@x.test" % colleague.hex[:8]})
        for actor in (colleague, me):
            c.execute(text(
                "INSERT INTO adjudications (id, case_id, subject_type, subject_id, decision, reason, before, after, "
                "actor_user_id, actor_name, actor_email, created_at, subject_sequence, reason_kind) VALUES (:i, :c, "
                "'phone_extraction', :e, 'confirm_phone_reading', 'synthetic', '{}', '{}', :a, 'synthetic', 's@x.test', now(), "
                "(SELECT coalesce(max(subject_sequence), 0) + 1 FROM adjudications WHERE subject_id = :e), 'standard')"),
                {"i": uuid.uuid4(), "c": case, "e": ext, "a": actor})
        phone(c, case, label="C9", events=[msg(at(2023, 4, 1))])  # a new phone
    with eng.connect() as c:
        s = profile.since_last_looked(c, case, ext, t0, me)
        assert s["counts"]["confirmations"] == 1 and s["counts"]["new_phones"] == 1
        assert s["counts"]["replaced"] == 0 and s["counts"]["links"] == 0 and not s["nothing"]
        assert "1 confirmation or correction by a colleague" in s["lines"] and "1 new phone" in s["lines"]
        later = profile.since_last_looked(c, case, ext, datetime.now(timezone.utc) + timedelta(seconds=5), me)
        assert later["nothing"] and later["lines"][0] == "0 new phones"


def test_export_profile_as_pdf_prints_the_summary_and_lists_in_the_phones_history(world):
    weasyprint = pytest.importorskip("weasyprint")  # noqa: F841
    pypdf = pytest.importorskip("pypdf")
    from services.phone import profile
    from services.phone.exports import jobs
    eng, case, ext = world["engine"], world["case"], world["ext"]
    with eng.begin() as c:
        with pytest.raises(jobs.ExportError, match="one phone"):
            jobs.create(c, case_id=case, user_id=world["user"], fmt="rsmf", source="phone_profile",
                        filter_body={"phones": [str(ext)]}, options={})
        other = make_case(c)
        with pytest.raises(jobs.ExportError, match="not in this case"):
            jobs.create(c, case_id=other, user_id=world["user"], fmt="pdf", source="phone_profile",
                        filter_body={"phones": [str(ext)]}, options={})
        made = jobs.create(c, case_id=case, user_id=world["user"], fmt="pdf", source="phone_profile",
                           filter_body={"phones": [str(ext)]}, options={})
    done = jobs.run_pending(eng)
    assert done and done[0]["state"] == "done", done
    with eng.connect() as c:
        path = jobs.file_of(c, case, made["export_id"]).storage_path
        p = profile.profile(c, str(case), ext)
        hist = jobs.history(c, case)
    words = "".join("\n".join(pg.extract_text() for pg in pypdf.PdfReader(io.BytesIO(open(path, "rb").read())).pages).split())
    for needed in (p["verdict"]["sentence"], "Busiest weeks", "Week of Monday, March 13, 2023: 3 messages and calls",
                   "What Loupe reads", "Synthetic summary case"):
        assert "".join(needed.split()) in words, needed
    mine = [h for h in hist if h["export_id"] == made["export_id"]]
    assert mine and mine[0]["source"] == "phone_profile" and mine[0]["phones"] == [str(ext)]
    assert mine[0]["file"]["filename"] == "phone-summary.pdf" or mine[0]["file"]["filename"].endswith(".pdf")
