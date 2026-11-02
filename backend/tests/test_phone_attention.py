"""A phone reading's readiness card is mirrored in the case attention feed (07 J-1 step 3). Synthetic rows."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from services import workspace_attention_service as feed
from tests.phone_pg import needs_template

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def job(status, phone, *, progress=0.4, paused=False, updated=NOW):
    return SimpleNamespace(id=uuid4(), file_name="Handset.zip", status=status, progress=progress, paused=paused,
                           pipeline_state={"phone": phone}, updated_at=updated)


def test_a_running_reading_names_its_step_and_opens_the_processing_panel():
    case = uuid4()
    c = feed.phone_candidate(case, job("capturing", {"stage": "capturing"}), now=NOW)
    assert (c.reason_code, c.title, c.summary) == ("phone_reading", "Getting Handset.zip ready", "Reading records, 40% done.")
    assert c.href == f"/cases/{case}/evidence?panel=processing"
    assert c.to_dict(rank=1)["reason_label"] == "Phone report being read"
    paused = feed.phone_candidate(case, job("pending", {"stage": "indexing_files"}, paused=True), now=NOW)
    assert paused.summary == "Checking nothing is missing: paused."


def test_finished_held_failed_and_cancelled_readings():
    case = uuid4()
    ready = feed.phone_candidate(case, job("completed", {"state": "captured", "message": "Every record was read."}),
                                 now=NOW)
    assert (ready.reason_code, ready.title, ready.summary) == ("phone_ready", "Handset.zip is ready",
                                                               "Every record was read.")
    held = feed.phone_candidate(case, job("failed", {"state": "reconciliation_failed", "message": "Held"}), now=NOW)
    protected = feed.phone_candidate(case, job("completed", {"state": "not_readable", "message": "Protected"}), now=NOW)
    assert held.reason_code == protected.reason_code == "phone_needs_attention" and held.priority_band == 1
    assert feed.phone_candidate(case, job("failed", {"cancelled": True}), now=NOW) is None
    old = job("completed", {"state": "captured"}, updated=NOW - timedelta(days=feed.MATERIAL_CHANGE_DAYS + 1))
    assert feed.phone_candidate(case, old, now=NOW) is None


def test_a_read_phone_says_conversations_are_ready_and_what_is_still_running():
    """07 J-1 step 4: once messages and calls are read the card says so, names what is still running with true
    counts, and opens the Phone summary. A second copy of a report already in the case keeps its own words."""
    case, ext = uuid4(), uuid4()
    done = {"state": "captured", "message": "Every record was read.", "extraction_id": str(ext)}
    c = feed.phone_candidate(case, job("completed", done), now=NOW, label="C3",
                             readiness={"interpreted": True, "documents": 300, "folded": 120})
    assert c.title == "C3 is ready"
    assert c.summary == "Conversations are ready. Still running: making its conversations searchable (120 of 300 done)."
    assert c.href == f"/cases/{case}/phones/{ext}"
    assert c.to_dict(rank=1)["metadata"]["action"] == {"label": "Open the phone summary", "href": c.href}
    finished = feed.phone_candidate(case, job("completed", done), now=NOW, label="C3",
                                    readiness={"interpreted": True, "documents": 300, "folded": 300})
    assert finished.summary == "Conversations are ready. Nothing is still running."
    reading = feed.phone_candidate(case, job("completed", done), now=NOW, label="C3",
                                   readiness={"interpreted": False, "documents": 0, "folded": 0})
    assert (reading.reason_code, reading.title, reading.summary) == (
        "phone_reading", "Getting C3 ready", "Every record was read. Reading messages and calls.")
    assert "action" not in reading.to_dict(rank=1)["metadata"]
    copy = feed.phone_candidate(case, job("completed", {**done, "already_in_case": True, "message": "Second copy."}),
                                now=NOW, label="C3", readiness={"interpreted": True, "documents": 1, "folded": 1})
    assert copy.summary == "Second copy." and "action" not in copy.to_dict(rank=1)["metadata"]


@needs_template
def test_the_feed_reads_readiness_from_the_database_per_phone():
    """The same card from PostgreSQL: a captured job whose phone is interpreted, with one conversation document
    folded and one not, and a copy of the same report. Synthetic rows only."""
    import hashlib
    import json

    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from services.search import document_folds
    from tests.phone_pg import fresh_engine, make_case
    from tests.phone_streams_fixture import phone
    with fresh_engine() as engine:
        with engine.begin() as c:
            case = make_case(c)
            ext, _ = phone(c, case, events=[])
            for n, body in enumerate(("first conversation", "second conversation")):
                fid = uuid4()
                c.execute(text(
                    "INSERT INTO evidence_files (id, case_id, original_filename, stored_path, size, sha256, status, "
                    "source_type, metadata, created_at, updated_at) VALUES (:i, :c, :n, :p, 1, '00', 'processed', "
                    "'phone_text', CAST(:m AS jsonb), now(), now())"),
                    {"i": fid, "c": case, "n": "t%d" % n, "p": "x/t%d" % n, "m": json.dumps({"phone_extraction_id": str(ext)})})
                c.execute(text(
                    "INSERT INTO evidence_document_texts (evidence_file_id, content, content_sha256, character_count, "
                    "source_locations, processing_manifest, extracted_at) VALUES (:i, :b, :h, 1, '[]', '{}', now())"),
                    {"i": fid, "b": body, "h": hashlib.sha256(body.encode()).hexdigest()})
                if n == 0:
                    document_folds.fold_one(c, fid, case, body, hashlib.sha256(body.encode()).hexdigest())
            for copy in (False, True):
                state = {"state": "captured", "message": "Second copy." if copy else "Read.",
                         "extraction_id": str(ext), **({"already_in_case": True} if copy else {})}
                c.execute(text(
                    "INSERT INTO jobs (id, case_id, file_name, status, job_type, pipeline_state, created_at, updated_at) "
                    "VALUES (:i, :c, 'Report.xml', 'completed', 'phone_capture', CAST(:p AS jsonb), now(), now())"),
                    {"i": uuid4(), "c": str(case), "p": json.dumps({"phone": state})})
        with Session(engine) as db:
            cards = feed._phone_candidates(db, case_id=case, now=datetime.now(timezone.utc))
    summaries = sorted(c.summary for c in cards)
    assert summaries == ["Conversations are ready. Still running: making its conversations searchable (1 of 2 done).",
                         "Second copy."]
    assert {c.title for c in cards} == {"C3 is ready"}
