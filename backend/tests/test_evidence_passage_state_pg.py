"""A kept quote's link state on PostgreSQL, through the same call the finding and dossier sheets make (lx-textbench D)."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text

from services.phone import link_states as S
from tests.phone_pg import fresh_engine, make_case, needs_template

pytestmark = needs_template
ANCHOR = dict(kind="text_passage", quote="Wire", page_number=2, text_version="b" * 64, start_char=18, end_char=22)


@pytest.fixture()
def world():
    for engine in fresh_engine():
        with engine.begin() as conn:
            case_id = make_case(conn)
            owner = conn.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case_id}).scalar()
            file_id, entry_id, link_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            conn.execute(text(
                "INSERT INTO evidence_files (id, case_id, original_filename, stored_path, size, sha256, status) "
                "VALUES (:f, :c, 's.pdf', '/tmp/s.pdf', 1, :s, 'processed')"), {"f": file_id, "c": case_id, "s": "a" * 64})
            conn.execute(text(
                "INSERT INTO evidence_document_texts (evidence_file_id, content, content_sha256, character_count, "
                "source_locations) VALUES (:f, 'text', :v, 4, '[]')"), {"f": file_id, "v": "b" * 64})
            conn.execute(text(
                "INSERT INTO workspace_entries (id, case_id, entry_type, body, tags, review_state, author_user_id, "
                "version, migration_metadata, needs_migration_review) "
                "VALUES (:e, :c, 'note', 'b', '[]', 'accepted', :u, 1, '{}', false)"),
                {"e": entry_id, "c": case_id, "u": owner})
            conn.execute(text(
                "INSERT INTO workspace_entry_links (id, entry_id, case_id, target_type, target_id, relationship_type, "
                "source_anchor, link_metadata, created_by_user_id) VALUES (:l, :e, :c, 'evidence_passage', :t, "
                "'unclassified', CAST(:a AS jsonb), '{}', :u)"),
                {"l": link_id, "e": entry_id, "c": case_id, "t": f"{file_id}:bbbb:18:22", "u": owner,
                 "a": json.dumps({**ANCHOR, "evidence_file_id": str(file_id)})})
        yield engine, case_id, entry_id, link_id, file_id, owner


def test_a_quote_says_when_its_document_was_read_again(world):
    engine, case_id, entry_id, link_id, file_id, owner = world
    with engine.connect() as conn:
        same = S.of_container(conn, case_id, "entry", entry_id, owner)
    assert same[str(link_id)]["reread"] is None
    assert same[str(link_id)]["target_type"] == "evidence_passage"
    with engine.begin() as conn:
        conn.execute(text("UPDATE evidence_document_texts SET content_sha256 = :v, extracted_at = '2026-11-03T10:00:00Z' "
                          "WHERE evidence_file_id = :f"), {"v": "c" * 64, "f": file_id})
    with engine.connect() as conn:
        changed = S.of_container(conn, case_id, "entry", entry_id, owner)
    assert "read again after this quote was taken, on 3 November 2026" in changed[str(link_id)]["reread"]["words"]
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM evidence_document_texts WHERE evidence_file_id = :f"), {"f": file_id})
    with engine.connect() as conn:
        gone = S.of_container(conn, case_id, "entry", entry_id, owner)
    assert "no longer held" in gone[str(link_id)]["reread"]["words"]
