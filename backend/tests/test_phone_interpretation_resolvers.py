"""Stage C link resolvers (phone_record, phone_thread, phone_identity) and the external-processing check (02 sections
1.2, 8.8, 9.8; lx-collect m110107155825999, cb-capture m110114384716005). Synthetic phones only."""
from __future__ import annotations

import types

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from postgres import link_types
from services.financial.decisions import Actor
from services.phone import external_processing, readings, registry, resolvers, sweep
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_phone_mappings import CALL, call_extraction, hooks, write  # noqa: F401 (fixture)


@pytest.fixture
def interpreted(hooks):
    write(str(hooks), CALL)
    readings.install()
    resolvers.register()
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case, other = make_case(c), make_case(c)
            ext = call_extraction(c, case, label="C1")
            far = call_extraction(c, other, label="C1")
        for e in (ext, far):
            assert sweep.interpret_one(engine, e)["status"] == "done"
        yield engine, case, other, ext


def _one(conn, sql, **kw):
    return conn.execute(text(sql), kw).first()


@needs_template
def test_a_record_resolves_in_its_case_only_with_the_versions_it_was_read_with(interpreted):
    engine, case, other, ext = interpreted
    with Session(engine) as db:
        uid = _one(db.connection(), "SELECT record_uid FROM pv_record WHERE extraction_id = :e AND model_type = 'Call' "
                                    "ORDER BY ordinal LIMIT 1", e=ext)[0]
        t = link_types.resolve_phone_target(db, case, "phone_record", str(uid))
        assert t.metadata["extraction_id"] == str(ext) and t.metadata["model_type"] == "Call"
        assert t.mapping_versions["generation"] == 1 and t.mapping_versions["interpretation_level"]
        with pytest.raises(link_types.LinkTargetError, match="not found in this case"):
            link_types.resolve_phone_target(db, other, "phone_record", str(uid))
        with pytest.raises(link_types.LinkTargetError, match="not found in this case"):
            link_types.resolve_phone_target(db, case, "phone_record", "not-a-uuid")
        db.execute(text("UPDATE phone_extractions SET standing = 'superseded' WHERE id = :e"), {"e": ext})
        with pytest.raises(link_types.LinkTargetError, match="replaced"):
            link_types.resolve_phone_target(db, case, "phone_record", str(uid))
        db.rollback()


@needs_template
def test_a_thread_and_an_identity_resolve_by_key_and_never_across_cases(interpreted):
    engine, case, other, ext = interpreted
    with Session(engine) as db:
        key = _one(db.connection(), "SELECT thread_key FROM pv_thread WHERE extraction_id = :e LIMIT 1", e=ext)
        if key is not None:
            t = link_types.resolve_phone_target(db, case, "phone_thread", key[0])
            assert t.metadata["extraction_id"] == str(ext)
            with pytest.raises(link_types.LinkTargetError):
                link_types.resolve_phone_target(db, other, "phone_thread", key[0])
        n = _one(db.connection(), "SELECT count(*) FROM phone_identities WHERE case_id = :c", c=case)[0]
        if n:
            ik = _one(db.connection(), "SELECT identity_key FROM phone_identities WHERE case_id = :c AND "
                                       "sighting_count > 0 ORDER BY 1 LIMIT 1", c=case)[0]
            t = link_types.resolve_phone_target(db, case, "phone_identity", ik)
            assert t.metadata["identity_key"] == ik and t.mapping_versions["phones"]
        # the same key in a case where it was never seen is not found
        with pytest.raises(link_types.LinkTargetError, match="not found in this case"):
            link_types.resolve_phone_target(db, other, "phone_identity", "phone:+12025550199")


@needs_template
def test_a_phone_file_is_processed_only_when_its_report_allows_it(interpreted, monkeypatch, tmp_path):
    from services import manual_changes
    monkeypatch.setattr(manual_changes, "INBOX", tmp_path / "inbox.jsonl")  # never the real feed inbox
    engine, case, _, ext = interpreted
    with Session(engine) as db:
        uid, email = _one(db.connection(), "SELECT u.id, u.email FROM users u JOIN cases k ON k.owner_user_id = u.id "
                                           "WHERE k.id = :c", c=case)
        actor = Actor(name="Synthetic Owner", email=email, user_id=uid)
        f = types.SimpleNamespace(source_type="phone_file", case_id=case, metadata_={"extraction_id": str(ext)})
        assert external_processing.check(db, case, f) is False  # no decision: not allowed
        assert external_processing.check(db, case, types.SimpleNamespace(metadata_={})) is False
        with pytest.raises(external_processing.ExternalProcessingError, match="reason in your own words"):
            external_processing.decide(db, case_id=case, extraction_id=ext, allow=True, reason=" ", actor=actor)
        external_processing.decide(db, case_id=case, extraction_id=ext, allow=True,
                                   reason="synthetic: transcription is needed", actor=actor)
        assert external_processing.check(db, case, f) is True
        external_processing.decide(db, case_id=case, extraction_id=ext, allow=False, reason="synthetic: withdrawn",
                                   actor=actor)
        assert external_processing.check(db, case, f) is False  # the latest decision stands
        st = external_processing.state(db.connection(), case, ext)
        assert st["external_processing"] is False and st["decided_by"] == "Synthetic Owner"
        assert db.connection().execute(text(
            "SELECT count(*) FROM manual_changes WHERE case_id = :c AND kind = 'phone_external_processing'"),
            {"c": case}).scalar() == 2  # one feed line per decision
        db.rollback()


def test_install_registers_the_check():
    from services import phone_files
    saved = phone_files._external_processing_check
    try:
        external_processing.install()
        assert phone_files.external_processing_check_registered()
    finally:
        phone_files.register_external_processing_check(saved)
