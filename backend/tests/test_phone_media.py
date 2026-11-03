"""03 section 8.5 (M-1, M-2, M-4): Media. Synthetic phone, invented file names. Needs the PostgreSQL template."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.phone import identities, readings, registry, sweep
from tests.phone_pg import fld, fresh_engine, make_case, model, needs_template
from tests.test_phone_identities import _call, _phone
from tests.test_phone_mappings import CALL, hooks, write  # noqa: F401 (fixture)

OWNER, OTHER = "+12025550100", "+12025550143"
LINKED, MISSING, LOOSE = ("00000000-0000-4000-8000-00000000a001", "00000000-0000-4000-8000-00000000a002",
                          "00000000-0000-4000-8000-00000000a003")
pytestmark = needs_template


@pytest.fixture
def world(hooks):
    write(str(hooks), CALL)
    identities.install()
    readings.install()
    recs, stamps = _call(0, [(OWNER, None, True), (OTHER, None, False)])
    recs.append((3, 0, 0, model("Attachment", [fld("Filename", ("String", "synthetic-a.jpg"))])))
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case, other = make_case(c), make_case(c)
            ext = _phone(c, case, [(recs, stamps)], metadata={"MSISDN": OWNER})
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        with engine.begin() as c:
            for ordinal, uid, path, outcome in ((9000, LINKED, "chats/synthetic-a.jpg", "match"),
                                                (9001, MISSING, "photos/synthetic-gone.jpg", "missing"),
                                                (9002, LOOSE, "contacts/synthetic-c.vcf", "no_hash")):
                c.execute(text(
                    "INSERT INTO phone_files (extraction_id, document_index, ordinal, file_uid, local_path, outcome, "
                    "body) VALUES (:e, 0, :o, :f, :p, :out, CAST('[]' AS jsonb))"),
                    {"e": ext, "o": ordinal, "f": uid, "p": path, "out": outcome})
            # M-1: linked only through the Attachment record's extracted path
            c.execute(text(
                "INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, mechanism, "
                "reference_text, file_document_index, file_ordinal, resolution, ambiguous) VALUES (:e, 0, 3, 'f', "
                "'extracted_path_value', 'chats/synthetic-a.jpg', 0, 9000, 'container_entry', false)"), {"e": ext})
        yield engine, case, other, ext


def test_m4_the_grid_total_equals_the_phone_summary_file_count(world):
    from services.phone import media, profile
    engine, case, _, ext = world
    with engine.connect() as c:
        idx = media.index(c, case, {"phones": [ext]})
        p = profile.profile(c, case, ext)
        files_total = c.execute(text("SELECT count(*) FROM pv_file WHERE extraction_id = :e"), {"e": ext}).scalar()
    assert idx["total"] == files_total == 3
    assert p["files"]["total"] == idx["total"]
    assert idx["no_time_count"] == 2 and idx["missing"] == 1


def test_m1_a_file_linked_only_by_the_attachment_extracted_path_shows_its_message(world):
    from services.phone import media
    engine, case, _, ext = world
    with engine.connect() as c:
        d = media.detail(c, case, LINKED)
        call = str(c.execute(text("SELECT record_uid FROM pv_comm_event WHERE extraction_id = :e"), {"e": ext}).scalar_one())
    assert d["message_count"] == 1 and len(d["messages"]) == 1
    m = d["messages"][0]
    assert m["mechanism"] == "attachment_extracted_path" and m["message_record_uid"] == call and m["kind"] == "call"
    with engine.connect() as c:
        w = media.window(c, case, {"phones": [ext]})
    first = w["items"][0]
    assert first["file_uid"] == LINKED and first["taken_or_sent"]["basis"] == "message_time"


def test_m2_a_file_absent_from_the_production_is_counted_and_says_so_not_a_broken_image(world):
    from services.phone import media
    engine, case, other, ext = world
    with engine.connect() as c:
        w = media.window(c, case, {"verification": ["missing"]})
        d = media.detail(c, case, MISSING)
        assert media.detail(c, other, MISSING) is None  # another case sees nothing
    assert [i["file_uid"] for i in w["items"]] == [MISSING]
    item = w["items"][0]
    assert item["missing"] and item["thumbnail_url"] is None
    assert item["verification_words"] == d["missing_words"] == "The report refers to a file that is not in the production."


def test_a_folder_file_is_read_in_place_and_a_missing_one_is_refused_in_words(world, tmp_path, monkeypatch):
    from services.phone import media
    engine, case, _, ext = world
    monkeypatch.setattr("config.EVIDENCE_DATA_ROOT", str(tmp_path))
    (tmp_path / str(case) / "up" / "root" / "chats").mkdir(parents=True)
    (tmp_path / str(case) / "up" / "root" / "chats" / "synthetic-a.jpg").write_bytes(b"synthetic bytes")
    with engine.begin() as c:
        c.execute(text("UPDATE phone_files SET disk_relpath = 'chats/synthetic-a.jpg', disk_size = 15 WHERE file_uid = :f"),
                  {"f": LINKED})
        cid = c.execute(text("SELECT first_container_id FROM phone_extractions WHERE id = :e"), {"e": ext}).scalar()
        c.execute(text("UPDATE phone_extraction_containers SET container_kind = 'folder', stored_path = 'up' WHERE id = :i"),
                  {"i": cid})
        c.execute(text("DELETE FROM phone_extraction_container_links WHERE extraction_id = :e"), {"e": ext})
        c.execute(text("INSERT INTO phone_extraction_container_links (extraction_id, container_id, root_path) VALUES "
                       "(:e, :i, 'root')"), {"e": ext, "i": cid})
    with engine.connect() as c:
        name, size, opener = media.content(c, case, LINKED)
        with opener() as fh:
            assert fh.read() == b"synthetic bytes" and name == "synthetic-a.jpg" and size == 15
        with pytest.raises(media.ContentRefused, match="not in the production"):
            media.content(c, case, MISSING)
