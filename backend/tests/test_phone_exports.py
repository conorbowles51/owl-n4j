"""03 section 12 (E-1 to E-5, E-7, E-10; A9 to A12): the phone export PDF, drawn by the job from the screen's rows.

Invented data only: 555 numbers and made-up names and text. Needs the PostgreSQL phone template and WeasyPrint.
"""
from __future__ import annotations

import base64
import io
import uuid
from collections import Counter

import pytest
from sqlalchemy import text

from services.phone import streams
from services.phone.filters import StreamFilter
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.phone_streams_fixture import at, phone

weasyprint = pytest.importorskip("weasyprint")
pypdf = pytest.importorskip("pypdf")

pytestmark = needs_template
OWNER, ANA, BEN = "phone:+12025550100", "phone:+12025550143", "phone:+12025550188"
LONG = ("synthetic words in a very long message " * 4000)[:155838]
STYLED = "\U0001D4D9\U0001D4F8\U0001D4FC\U0001D4EE Ｊｏｓｅ Ⓙⓞⓢⓔ \U0001F600"
UNASSIGNED = "\U0010FFFD"


def msg(instant, sender, recips, body="hello", **kw):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, parties=parties,
                direction="outgoing" if sender == OWNER else "incoming", **kw)


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("LOUPE_PHONE_EXPORT_DIR", str(tmp_path))
    with fresh_engine() as engine:
        with engine.begin() as c:
            case, other = make_case(c), make_case(c)
            ext, _ = phone(c, case, device_zone="America/New_York", events=[
                # 11:30 PM Eastern on March 14 is 03:30 UTC on March 15 (the shifted-day failure, E-2)
                msg(at(2023, 3, 15, 3, 30), ANA, [OWNER], body="late on the fourteenth", thread="t"),
                msg(at(2023, 3, 15, 15), OWNER, [ANA], body=LONG, thread="t"),
                msg(at(2023, 3, 16, 12), ANA, [OWNER], body="%s and %s" % (STYLED, UNASSIGNED), thread="t",
                    level="applied_unconfirmed"),
                dict(kind="call", instant=at(2023, 3, 16, 13), body=None, thread=None, call_duration_s=42,
                     parties=[(OWNER, "caller", True, None, None), (BEN, "callee", False, None, None)])])
            user = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
        yield {"engine": engine, "case": case, "other": other, "ext": ext, "user": user, "dir": tmp_path}


def _export(w, filter_body=None, **options):
    from services.phone.exports import jobs
    body = filter_body or {"zone": {"mode": "case"}}
    with w["engine"].begin() as c:
        c.execute(text("UPDATE cases SET title = 'Synthetic export case' WHERE id = :c"), {"c": w["case"]})
        made = jobs.create(c, case_id=w["case"], user_id=w["user"], fmt="pdf", source="stream", filter_body=body,
                           options={"title": "Synthetic export", **options})
    done = jobs.run_pending(w["engine"])
    assert done and done[0]["state"] == "done", done
    with w["engine"].connect() as c:
        state = jobs.get(c, w["case"], made["export_id"])
        path = jobs.file_of(c, w["case"], made["export_id"]).storage_path
    data = open(path, "rb").read()
    reader = pypdf.PdfReader(io.BytesIO(data))
    return state, data, "\n".join(p.extract_text() for p in reader.pages)


def _flat(s):
    return "".join(s.split())


def test_e1_a_155838_character_message_is_complete_in_the_text_layer(world):
    import re
    state, data, txt = _export(world)
    # each page's footer, and page 1's list markers (drawn as separate runs), sit between the pages of the message
    body = re.sub(r"Page\d+of\d+", "", _flat(txt)).replace("\u2022", "")
    assert _flat(LONG) in body
    import hashlib
    assert state["file"]["sha256"] == hashlib.sha256(data).hexdigest() and state["file"]["size"] == len(data)


def test_e2_a_message_at_1130_pm_eastern_prints_under_the_same_day_as_on_screen(world):
    _, _, txt = _export(world)
    with world["engine"].connect() as c:
        f = StreamFilter.model_validate({"case_id": str(world["case"]), "zone": {"mode": "case"}})
        idx = streams.index_comm_events(c, f)
        w = streams.window_comm_events(c, f, snapshot_token=idx["snapshot"], day=idx["items"][0]["day"])
    first = idx["items"][0]
    header = "%s, %s" % (first["header"], first["zone_label"])
    assert first["day"] == "2023-03-14"
    row = next(r for r in w["items"] if r["body"] == "late on the fourteenth")
    flat = _flat(txt)
    assert _flat(header) in flat and _flat(row["time"]["full"]) in flat
    assert flat.index(_flat(header)) < flat.index(_flat("late on the fourteenth"))


def test_e3_decorative_letters_and_emoji_are_drawn_and_an_uncovered_code_point_is_a_token(world):
    from services.phone.exports import pdf
    missing = Counter()
    assert pdf.drawable(STYLED, missing) == STYLED and not missing  # every character has a bundled glyph
    state, _, txt = _export(world)
    assert "[U+10FFFD]" in txt and "Characters that could not be drawn" in txt
    assert state["counts"]["missing_characters"] == 1
    assert "1 character that no bundled font can draw prints as [U+...]" in " ".join(txt.split())


def test_e4_the_printed_rows_equal_the_stated_total_and_the_screen_total(world):
    state, _, txt = _export(world)
    with world["engine"].connect() as c:
        screen = streams.shown_count(c, StreamFilter.model_validate({"case_id": str(world["case"])}))
    assert _flat(txt).count("RecordC3-") == state["counts"]["total"] == screen == 4
    assert "All 3 messages and 1 call" in " ".join(txt.split())


def test_e5_and_e10_the_cover_says_what_is_left_out_and_how_many_rows_are_unconfirmed(world):
    _, _, txt = _export(world)
    words = " ".join(txt.split())
    assert "Saved passwords and card numbers left out." in words
    assert "1 of these 4 rows rely on readings not yet confirmed by a person" in words
    assert words.count("Mapped by the system, not yet confirmed") == 1  # on the one unconfirmed row


def test_e7_no_list_is_cut(world):
    with world["engine"].begin() as c:
        many = ["phone:+120255501%02d" % n for n in range(10, 50)]
        phone(c, world["case"], label="C8", events=[msg(at(2023, 3, 20, 9), k, [OWNER], body="from %s" % k[-2:],
                                                        thread="m") for k in many])
    state, _, txt = _export(world)
    flat = _flat(txt)
    assert all(_flat("+1 202-555-01%s" % k[-2:]) in flat for k in many)  # every participant in the appendix
    assert state["counts"]["total"] == 44


def test_unbuilt_formats_and_sources_are_refused_in_words_and_another_case_sees_nothing(world):
    from services.phone.exports import jobs
    with world["engine"].begin() as c:
        with pytest.raises(jobs.ExportError, match="An export is a PDF or an RSMF file"):
            jobs.create(c, case_id=world["case"], user_id=world["user"], fmt="docx", source="stream",
                        filter_body={}, options={})
        with pytest.raises(jobs.ExportError, match="not built yet"):
            jobs.create(c, case_id=world["case"], user_id=world["user"], fmt="pdf", source="slideshow",
                        filter_body={}, options={})
        made = jobs.create(c, case_id=world["case"], user_id=world["user"], fmt="pdf", source="stream",
                           filter_body={}, options={})
    with world["engine"].connect() as c:
        assert jobs.get(c, world["other"], made["export_id"]) is None
        assert jobs.file_of(c, world["other"], made["export_id"]) is None


def test_a_failed_drawing_keeps_the_choices_and_gives_a_reference(world, monkeypatch):
    from services.phone.exports import jobs, pdf

    def boom(doc):
        raise pdf.RenderStopped("synthetic failure")
    monkeypatch.setattr(pdf, "render_isolated", boom)
    with world["engine"].begin() as c:
        made = jobs.create(c, case_id=world["case"], user_id=world["user"], fmt="pdf", source="stream",
                           filter_body={}, options={"title": "kept"})
    assert jobs.run_pending(world["engine"])[0]["state"] == "failed"
    with world["engine"].connect() as c:
        state = jobs.get(c, world["case"], made["export_id"])
    assert state["state"] == "failed" and state["file"] is None and state["title"] == "kept"
    assert "Reference:" in state["error"]
    assert list(world["dir"].rglob("*")) == [] or not any(p.suffix == ".pdf" for p in world["dir"].rglob("*"))


def test_nothing_in_an_export_is_fetched_from_a_network():
    from services.phone.exports import pdf
    for url in ("http://example.invalid/x.png", "https://example.invalid/f.ttf", "file:///etc/hostname"):
        with pytest.raises(ValueError, match="only the bundled fonts"):
            pdf.local_only(url)
    doc, _ = pdf.build_html(title="t", case_name="c", generated="g", export_id="x", contains=[],
                            days=[("Day", [])], participants=[])
    assert "http" not in doc.replace("http-equiv", "")  # the HTML names no remote resource


def test_the_describe_counts_are_the_cover_counts(world):
    from services.phone.exports import jobs
    with world["engine"].connect() as c:
        d = jobs.describe(c, world["case"], {})
    assert (d["total"], d["messages"], d["calls"], d["unconfirmed"], d["phones"]) == (4, 3, 1, 1, 1)
    assert d["left_out"] == "Saved passwords and card numbers left out." and d["limits"] == []


def test_another_cases_filter_cannot_be_smuggled_in(world):
    from services.phone.exports import jobs
    with world["engine"].connect() as c:
        d = jobs.describe(c, world["other"], {"case_id": str(world["case"])})  # the route's case wins
    assert d["total"] == 0
    assert uuid.UUID(d["case_id"]) == world["other"]


SCRIPTS = {"Arabic": "مرحبا", "Hebrew": "שלום", "Thai": "สวัสดี",
           "Devanagari": "नमस्ते", "Han": "中文㐀", "Kana": "ひらがなカタ",
           "Hangul": "한글", "Cyrillic": "Привет", "Greek": "Γεια"}


def test_e3_common_scripts_are_drawn_not_printed_as_tokens():
    from services.phone.exports import pdf
    for name, sample in SCRIPTS.items():
        missing = Counter()
        assert pdf.drawable(sample, missing) == sample and not missing, name
    rows = [{"time": {"full": "t"}, "phone": {"label": "C1"}, "body": s, "record_uid": "r%d" % i}
            for i, s in enumerate(SCRIPTS.values())]
    doc, missing = pdf.build_html(title="t", case_name="c", generated="g", export_id="x", contains=[],
                                  days=[("Day", rows)], participants=[])
    assert not missing
    txt = "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf.render(doc))).pages)
    for name in ("Han", "Kana", "Hangul", "Cyrillic", "Greek", "Hebrew"):  # right-to-left text may extract reversed
        assert SCRIPTS[name] in txt or SCRIPTS[name][::-1] in txt, name


def test_a_render_that_stopped_twice_is_failed_with_a_reason_not_claimed_forever(world):
    from services.phone.exports import jobs
    with world["engine"].begin() as c:
        made = jobs.create(c, case_id=world["case"], user_id=world["user"], fmt="pdf", source="stream",
                           filter_body={}, options={})
        c.execute(text("UPDATE phone_exports SET state = 'rendering', attempts = 2, started_at = now() - interval "
                       "'3 hours' WHERE export_id = :i"), {"i": made["export_id"]})
    assert jobs.run_pending(world["engine"]) == []
    with world["engine"].connect() as c:
        state = jobs.get(c, world["case"], made["export_id"])
    assert state["state"] == "failed" and state["error"] == jobs.STOPPED


def test_a_pdf_too_large_for_its_memory_cap_fails_in_its_own_process(monkeypatch):
    from services.phone.exports import pdf
    monkeypatch.setattr(pdf, "RENDER_MEMORY_MB", 48)  # too little even to start: the child stops, this process lives
    with pytest.raises(pdf.RenderStopped, match="could not be drawn within 48 MB"):
        pdf.render_isolated("<p>x</p>")


def test_a_title_of_punctuation_still_names_the_file(world):
    state, _, _ = _export(world, title="?!.")
    assert state["file"]["filename"] == "phone-messages.pdf"


def test_sensitive_fields_stay_out_unless_the_option_is_ticked_and_the_cover_says_which(world):
    """03 section 3.10 and 12.2: Include sensitive fields. A synthetic saved value on one exported record."""
    with world["engine"].begin() as c:
        rec, gen = c.execute(text(
            "SELECT ev.record_uid, ev.generation FROM phone_comm_events ev WHERE ev.extraction_id = :e "
            "ORDER BY ev.sort_instant LIMIT 1"), {"e": world["ext"]}).first()
        c.execute(text(
            "INSERT INTO phone_texts (case_id, extraction_id, document_index, ordinal, record_uid, root_record_uid, "
            "locator, model_type, generation, text_uid, body_path, field_name, field_path, value_index, value, "
            "value_folded, effective_value, is_sensitive) VALUES (:c, :e, 0, 990001, :r, :r, 'sens', 'InstantMessage', "
            ":g, :t, '0', 'Password', 'Password', 0, 'synthetic-secret-1', 'synthetic-secret-1', 'synthetic-secret-1', "
            "true)"), {"c": world["case"], "e": world["ext"], "r": rec, "g": gen, "t": uuid.uuid4()})
    from services.phone.exports import jobs
    with world["engine"].connect() as c:
        assert jobs.describe(c, world["case"], {"zone": {"mode": "case"}})["sensitive_values"] == 1
    state, _, txt = _export(world)
    words = " ".join(txt.split())
    assert "synthetic-secret-1" not in _flat(txt)
    assert "Saved passwords and card numbers left out: 1 sensitive value on these rows is not printed." in words
    assert state["counts"]["sensitive_values"] == 1 and state["counts"]["sensitive_included"] is False
    state, _, txt = _export(world, include_sensitive=True)
    assert "SensitivefieldPassword:synthetic-secret-1" in _flat(txt)
    assert "Sensitive fields included, as the export option was ticked: 1 value" in " ".join(txt.split())
    assert state["counts"]["sensitive_included"] is True and state["counts"]["total"] == 4


def test_e8_the_preview_is_the_first_page_of_the_export(tmp_path, monkeypatch):
    """07 test E-8: the same formatter draws both; only the export's id line and the minute it was made may differ."""
    import fitz

    from services.phone.exports import jobs
    from tests.phone_pg import fresh_engine, make_case
    from tests.phone_streams_fixture import at, phone
    monkeypatch.setenv("LOUPE_PHONE_EXPORT_DIR", str(tmp_path))
    A, B = "phone:+12025550143", "phone:+12025550100"
    events = [dict(kind="message", instant=at(2023, 3, 14, 12, i), body="invented line %d" % i, direction="incoming",
                   thread="t", parties=[(A, "sender", False, None, None), (B, "recipient", True, None, None)])
              for i in range(60)]
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, _ = phone(c, case, events=events)
            user = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar()
            out = jobs.create(c, case_id=case, user_id=user, fmt="pdf", source="stream",
                              filter_body={"phones": [str(ext)]}, options={"title": "Preview check"})
        jobs.run_pending(engine)
        with engine.connect() as c:
            path = jobs.file_of(c, case, out["export_id"]).storage_path
        got = jobs.preview(engine, case, user, "stream", {"phones": [str(ext)]}, {"title": "Preview check"})
        with fitz.open(path) as doc:
            whole = doc[0].get_text()
            pages = len(doc)
        keep = lambda t: [x for x in t.splitlines() if not x.startswith(("Generated by", "Export ", "Page "))]
        assert pages > 1 and got["rows"] == 60
        assert keep(got["text"]) == keep(whole)
        assert base64.b64decode(got["image"]).startswith(b"\x89PNG")
