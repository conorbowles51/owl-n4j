"""A phone reading's readiness card is mirrored in the case attention feed (07 J-1 step 3). Synthetic rows."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from services import workspace_attention_service as feed

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
