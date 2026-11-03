"""07 5 Media (M-5): batch transcription and text reading of a Media scope, with true counts.

Synthetic files only (no bytes are read here: the readings are queued, counted and cancelled). Needs the PostgreSQL
template.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from tests.phone_pg import needs_template
from tests.test_phone_media import LINKED, world  # noqa: F401 (fixture)
from tests.test_phone_mappings import hooks  # noqa: F401 (fixture)

pytestmark = needs_template


def _files(engine, ext, rows):
    """rows: (category, outcome); returns the file uids in order."""
    out = []
    with engine.begin() as c:
        for i, (cat, outcome) in enumerate(rows):
            uid = str(uuid.uuid4())
            c.execute(text("INSERT INTO phone_files (extraction_id, document_index, ordinal, file_uid, local_path, "
                           "outcome, tags, body) VALUES (:e, 0, :o, :f, :p, :out, :t, CAST('[]' AS jsonb))"),
                      {"e": ext, "o": 9500 + i, "f": uid, "p": "voice/synthetic-%d.opus" % i, "out": outcome,
                       "t": cat})
            out.append(uid)
    return out


def test_m5_a_batch_queues_every_eligible_file_and_says_what_it_left_out(world):
    from services.phone import derive, derive_batch
    engine, case, other, ext = world
    a, b, c_, missing, empty, image = _files(engine, ext, [
        ("Audio", "match"), ("Audio", "match"), ("Video", "no_hash"), ("Audio", "missing"),
        ("Audio", "empty_placeholder"), ("Image", "match")])
    with engine.begin() as c:
        derive.request(c, case, a, "transcript")  # already asked for one at a time
    with engine.connect() as c:
        d = derive_batch.describe(c, case, "transcript", {})
    assert d["eligible"] == 2 and d["left_out"] == {"already_read": 1, "not_in_production": 1, "empty_placeholder": 1}
    assert d["noun"] == "voice notes and videos"
    with engine.begin() as c:
        made = derive_batch.create(c, case_id=case, kind="transcript", scope={}, scope_words="all phones",
                                   user_id=None)
    assert (made["total"], made["queued"], made["done"], made["state"]) == (2, 2, 0, "running")
    with engine.connect() as c:
        queued = {r[0] for r in c.execute(text("SELECT file_uid::text FROM phone_derived_texts WHERE batch_id = :b"),
                                          {"b": made["id"]})}
        assert queued == {b, c_}
        assert derive_batch.describe(c, case, "transcript", {})["eligible"] == 0
        assert derive_batch.status(c, other) == []  # another case sees nothing
    with engine.begin() as c, pytest.raises(derive_batch.BatchError, match="nothing was queued"):
        derive_batch.create(c, case_id=case, kind="transcript", scope={}, scope_words="", user_id=None)


def test_m5_a_reading_asked_for_one_at_a_time_is_drawn_before_the_batch(world):
    from services.phone import derive, derive_batch
    engine, case, _, ext = world
    a, b = _files(engine, ext, [("Audio", "match"), ("Audio", "match")])
    with engine.begin() as c:
        derive_batch.create(c, case_id=case, kind="transcript", scope={}, scope_words="", user_id=None)
    with engine.begin() as c:
        single = c.execute(text("INSERT INTO phone_derived_texts (id, case_id, extraction_id, file_uid, kind) VALUES "
                                "(gen_random_uuid(), :c, :e, :f, 'ocr') RETURNING id"),
                           {"c": case, "e": ext, "f": LINKED}).scalar()
    claimed = derive._claim(engine)
    assert claimed.id == single


def test_m5_counts_follow_the_rows_and_cancel_keeps_every_finished_reading(world):
    from services.phone import derive_batch
    engine, case, _, ext = world
    files = _files(engine, ext, [("Audio", "match")] * 4)
    with engine.begin() as c:
        made = derive_batch.create(c, case_id=case, kind="transcript", scope={}, scope_words="", user_id=None)
        c.execute(text("UPDATE phone_derived_texts SET state = 'done', text = 'SYNTHETIC', started_at = now(), "
                       "finished_at = now() WHERE batch_id = :b AND file_uid = :f"), {"b": made["id"], "f": files[0]})
        c.execute(text("UPDATE phone_derived_texts SET state = 'failed', error = 'x', started_at = now(), "
                       "finished_at = now() WHERE batch_id = :b AND file_uid = :f"), {"b": made["id"], "f": files[1]})
        c.execute(text("UPDATE phone_derived_texts SET state = 'running', started_at = now() WHERE batch_id = :b AND "
                       "file_uid = :f"), {"b": made["id"], "f": files[2]})
    with engine.connect() as c:
        [s] = derive_batch.status(c, case)
    assert (s["total"], s["done"], s["failed"], s["running"], s["queued"]) == (4, 1, 1, 1, 1)
    assert s["first_started_at"] and s["last_finished_at"] and s["state"] == "running"
    with engine.begin() as c:
        out = derive_batch.cancel(c, case, made["id"])
    assert (out["cancelled_count"], out["queued"], out["done"], out["running"]) == (1, 0, 1, 1)
    assert out["state"] == "running"  # the reading under way finishes
    with engine.begin() as c:
        c.execute(text("UPDATE phone_derived_texts SET state = 'done', finished_at = now() WHERE batch_id = :b AND "
                       "state = 'running'"), {"b": made["id"]})
    with engine.connect() as c:
        assert derive_batch.get(c, case, made["id"])["state"] == "cancelled"
        with pytest.raises(LookupError):
            derive_batch.cancel(c, world[2], made["id"])


def test_m5_the_scope_is_the_media_filter(world):
    from services.phone import derive_batch
    engine, case, _, ext = world
    _files(engine, ext, [("Audio", "match"), ("Image", "match"), ("Image", "match")])
    with engine.connect() as c:
        assert derive_batch.describe(c, case, "ocr", {})["eligible"] == 2
        assert derive_batch.describe(c, case, "ocr", {"phones": [str(uuid.uuid4())]})["eligible"] == 0
        assert derive_batch.describe(c, case, "transcript", {"categories": ["Image"]})["eligible"] == 0
