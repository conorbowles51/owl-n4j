"""03 section 6.7 and MD-1: a thread header's attachment counts ("N attachments referenced, U not in the report")
and the Media grid scoped to the thread lists exactly the report's files those messages carried. Synthetic data."""
from __future__ import annotations

from sqlalchemy import text

from tests.phone_pg import needs_template
from tests.test_phone_media import LINKED, MISSING, world  # noqa: F401 - the synthetic phone with three files
from tests.test_phone_mappings import hooks  # noqa: F401

pytestmark = needs_template


def test_thread_header_counts_and_the_thread_scoped_media_grid_agree(world):  # noqa: F811
    from services.phone import media
    engine, case, other, ext = world
    with engine.begin() as c:
        c.execute(text("UPDATE phone_comm_events SET thread_key = 'synthetic-thread' WHERE extraction_id = :e"), {"e": ext})
        for mech, ref, doc, ordinal, res in (
                ("jumptarget", "synthetic-gone", 0, 9001, "tagged_file"),       # named in the report, not in the production
                ("jumptarget", "synthetic-nowhere.jpg", None, None, "unresolved"),  # in neither
                ("extracted_path_value", "chats/synthetic-loose.jpg", None, None, "container_entry"),  # folders only
                ("jumptarget", "synthetic-record", None, None, "model")):       # a record, not a file
            c.execute(text(
                "INSERT INTO phone_file_references (extraction_id, document_index, record_ordinal, body_path, mechanism, "
                "reference_text, file_document_index, file_ordinal, resolution, ambiguous) VALUES (:e, 0, 0, :b, :m, :r, "
                ":d, :o, :res, false)"), {"e": ext, "b": "b-" + ref, "m": mech, "r": ref, "d": doc, "o": ordinal, "res": res})
    with engine.connect() as c:
        got = media.thread_attachments(c, case, "synthetic-thread")
        grid = media.index(c, case, {"thread_key": "synthetic-thread"})
        items = media.window(c, case, {"thread_key": "synthetic-thread"})["items"]
        assert media.thread_attachments(c, other, "synthetic-thread")["referenced"] == 0
        assert media.index(c, other, {"thread_key": "synthetic-thread"})["total"] == 0
    assert (got["files"], got["not_in_report"], got["in_folders_only"], got["not_in_production"]) == (2, 1, 1, 1)
    assert got["referenced"] == 4
    assert got["words"] == ("4 attachments referenced, 1 not in the report, 1 only in the production's folders, "
                            "1 named in the report but not in the production")
    assert grid["total"] == got["files"] and grid["missing"] == 1
    assert sorted(i["file_uid"] for i in items) == sorted([LINKED, MISSING])
