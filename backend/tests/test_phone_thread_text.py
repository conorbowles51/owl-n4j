"""02 section 9.7: thread documents written from a phone's records. Search reaches them and a hit names its record;
evidence listings and evidence processing leave them out; a phone that leaves its case takes its documents with it.
Synthetic phones only."""
from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from postgres.models.evidence import EvidenceFile
from services import evidence_text_search_service as search
from services.financial.source_lineage import visible_evidence_condition
from services.phone import identities, readings, registry, sweep, thread_text
from tests.phone_pg import fresh_engine, make_case, needs_template
from tests.test_phone_identities import _call, _phone
from tests.test_phone_mappings import CALL, hooks, write  # noqa: F401 (fixture)

OWNER, OTHER = "+12025550100", "+12025550143"


def _docs(c, ext):
    return c.execute(text(
        "SELECT f.id, f.original_filename, f.status, t.content, t.source_locations FROM evidence_files f JOIN "
        "evidence_document_texts t ON t.evidence_file_id = f.id WHERE f.source_type = 'phone_text' AND "
        "f.metadata ->> 'phone_extraction_id' = :e ORDER BY f.id"), {"e": str(ext)}).fetchall()


@needs_template
def test_thread_documents_are_searchable_by_record_and_hidden_from_evidence_listings(hooks):
    write(str(hooks), CALL)
    identities.install()
    readings.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = _phone(c, case, [_call(0, [(OWNER, None, True), (OTHER, None, False)]),
                                   _call(3, [(OWNER, None, True), (OTHER, None, False)], direction="Incoming")],
                         metadata={"MSISDN": OWNER})
            c.execute(text(
                "INSERT INTO evidence_files (id, case_id, original_filename, stored_path, size, sha256, status, "
                "created_at, updated_at) VALUES (gen_random_uuid(), :c, 'synthetic.pdf', 'x/synthetic.pdf', 1, "
                "'00', 'processed', now(), now())"), {"c": case})
        assert sweep.interpret_one(engine, ext)["status"] == "done"
        built = thread_text.build_stale(engine)
        assert built[str(ext)]["written"] >= 1
        assert thread_text.build_stale(engine) == {}  # nothing changed, nothing rewritten
        with engine.connect() as c:
            docs = _docs(c, ext)
            uids = {str(r[0]) for r in c.execute(text("SELECT record_uid FROM pv_comm_event WHERE extraction_id = :e"),
                                                 {"e": ext})}
        assert docs and all(d.status == "processed" for d in docs)
        locs = [loc for d in docs for loc in d.source_locations]
        assert len(locs) == 2 and {loc["record_uid"] for loc in locs} == uids
        assert all(loc["kind"] == "phone_record" and loc["extraction_id"] == str(ext) for loc in locs)
        content = docs[0].content
        assert content.count("\n") == 1  # one line per call

        with Session(engine) as db:
            needle = content.split("\n")[0][-12:]
            found = search.search_case_text(db, case_id=case, query=needle, document_limit=10, document_offset=0)
            assert found["case_documents"] == 1  # the synthetic PDF; thread documents are not case documents
            assert found["searchable_documents"] <= found["case_documents"]
            hit_doc = next(d for d in found["documents"] if d["source_type"] == "phone_text")
            assert hit_doc["folder_path"] == "Phone conversations"
            hit = hit_doc["matches"][0]
            assert hit["location_kind"] == "phone_record" and hit["record_uid"] in uids
            assert hit["extraction_id"] == str(ext)
            # the API keeps what names the record (its response model would otherwise drop the keys)
            from routers.evidence import CaseTextSearchResponse, get_evidence_file
            api = CaseTextSearchResponse.model_validate(found).model_dump()
            api_doc = next(d for d in api["documents"] if d["source_type"] == "phone_text")
            assert api_doc["matches"][0]["record_uid"] == hit["record_uid"]
            assert api_doc["matches"][0]["location_kind"] == "phone_record"
            # the conversation opens as its text; there is no file on disk
            served = get_evidence_file(hit_doc["evidence_id"], user={}, db=db)
            assert served.media_type == "text/plain" and served.body.decode("utf-8") == content
            listed = db.execute(select(EvidenceFile.source_type).where(EvidenceFile.case_id == case,
                                                                       visible_evidence_condition())).scalars().all()
            assert listed and "phone_text" not in listed

        with engine.begin() as c:
            c.execute(text("UPDATE phone_extractions SET standing = 'superseded', superseded_at = now() WHERE id = :e"),
                      {"e": ext})
        assert thread_text.build_stale(engine)[str(ext)]["removed"] == len(docs)
        with engine.connect() as c:
            assert _docs(c, ext) == []


@needs_template
def test_evidence_processing_leaves_thread_documents_out_and_says_so(hooks):
    from services import evidence_processing_service as eps
    write(str(hooks), CALL)
    identities.install()
    readings.install()
    with fresh_engine() as engine:
        with engine.begin() as c:
            registry.apply_seed(c)
            case = make_case(c)
            ext = _phone(c, case, [_call(0, [(OWNER, None, True), (OTHER, None, False)])], metadata={"MSISDN": OWNER})
        sweep.interpret_one(engine, ext)
        thread_text.build_stale(engine)
        with engine.connect() as c:
            ids = [d.id for d in _docs(c, ext)]
        with Session(engine) as db:
            out = eps._prepare_files(db, case_id=case, file_ids=ids, force_reprocess=False, preparation_mode="full",
                                     requested_by_user_id=None, ingestion_request_id="synthetic")
        assert out["file_count"] == 0 and out["skipped_count"] == len(ids)
        assert "phone conversation text" in out["message"]
