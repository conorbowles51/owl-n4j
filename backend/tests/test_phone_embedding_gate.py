"""02-U14 (02 sections 9.8 and 9.9): the embedding gate, chat's lexical phone retrieval and phone citation anchors.

With no per-case decision, no phone text reaches an embedding service: chat finds phone text by the folded search
over thread documents and reads it in full, each line citing its record; two messages from one thread are two
sources; another case's phone is never read; a Workspace theory citing a message stores a ``phone_record`` anchor
whose link opens the record. Invented data only.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from services.phone import chat_retrieval
from tests.phone_pg import fresh_engine, make_case, needs_template

OWNER, ANA = "phone:+12025550100", "phone:+12025550143"
NAMES = ("Synthetic Anabel", "+1 202-555-0143", "2025550143")


def _m(instant, sender, recips, body, thread="t1"):
    parties = [(sender, "sender", sender == OWNER, None, None)] + [(r, "recipient", r == OWNER, None, None)
                                                                    for r in recips]
    return dict(kind="message", instant=instant, body=body, thread=thread, parties=parties, app="WhatsApp",
                direction="outgoing" if sender == OWNER else "incoming")


def _build(engine):
    from services.phone import thread_text
    from services.search import document_folds
    from tests.phone_streams_fixture import at, phone
    with engine.begin() as c:
        case = make_case(c)
        ext, _ = phone(c, case, label="C1", contacts={ANA: "Synthetic Anabel"}, events=[
            _m(at(2023, 3, 2, 9), ANA, [OWNER], "The cargo leaves the harbour on Friday"),
            _m(at(2023, 3, 2, 10), OWNER, [ANA], "Fine, bring the papers"),
            _m(at(2023, 3, 3, 9), ANA, [OWNER], "Harbour master asked about the cargo again"),
            _m(at(2023, 3, 9, 9), ANA, [OWNER], "Lunch on Sunday?")])
    thread_text.build_stale(engine)
    document_folds.backfill(engine)
    return case, ext


@pytest.fixture
def no_embedding(monkeypatch):
    """Every embedding entry point records its payload; the test asserts none was called."""
    calls = []
    from services import embedding_service as es
    monkeypatch.setattr(es.EmbeddingService, "generate_embedding", lambda self, t, *a, **k: calls.append(t) or [0.0])
    if hasattr(es.EmbeddingService, "generate_embeddings_batch"):
        monkeypatch.setattr(es.EmbeddingService, "generate_embeddings_batch",
                            lambda self, ts, *a, **k: calls.extend(ts) or [[0.0] for _ in ts])
    return calls


def test_terms_drop_common_words_and_keep_numbers_and_phrases():
    ts = chat_retrieval.terms('What did they say about the "red van" and the harbour, call +1 (202) 555-0143?')
    assert ts[:2] == ["red van", "202 555 0143"]  # a number as the thread lines write it, folded
    assert "harbour" in ts and "the" not in ts and "what" not in ts


@needs_template
def test_chat_reads_phone_text_lexically_in_full_with_record_links_and_embeds_nothing(no_embedding):
    with fresh_engine() as engine:
        case, ext = _build(engine)
        with engine.begin() as c:
            other = make_case(c)
        with engine.connect() as c:
            found = chat_retrieval.windows(c, case, "What was said about the cargo at the harbour?")
            assert chat_retrieval.windows(c, other, "What was said about the cargo at the harbour?") == []
            assert chat_retrieval.windows(c, case, "What did (202) 555-0143 write?"), "a number typed another way"
            uids = {str(r[0]) for r in c.execute(text("SELECT record_uid FROM pv_comm_event WHERE extraction_id = :e"),
                                                 {"e": ext})}
        assert found, "the harbour messages are found"
        w = found[0]
        # read in full: the saved name and the words, no opaque label; every line cites its record
        assert "Synthetic Anabel" in w["text"] and "cargo leaves the harbour" in w["text"]
        assert w["text"].count("[rec://") == len(w["text"].splitlines())
        meta = w["metadata"]
        assert meta["source_kind"] == "phone_text" and meta["case_id"] == str(case)
        assert meta["extraction_id"] == str(ext) and meta["record_uid"] in uids
        assert {meta["first_record_uid"], meta["last_record_uid"]} <= uids
        assert len(w["text"]) <= chat_retrieval.WINDOW_CHARS + 60 * len(w["text"].splitlines())
        assert no_embedding == []

        # two messages of one thread are two sources, each with its record and link (02 9.9)
        from routers.chat import ChatSource
        from services.rag_service import RAGService
        two = [dict(w, metadata=dict(meta, record_uid=u, url="rec://%s" % u)) for u in sorted(uids)[:2]]
        sources = RAGService._build_sources(object.__new__(RAGService), two)
        assert [s["record_uid"] for s in sources] == sorted(uids)[:2]
        back = ChatSource(**sources[0]).model_dump()
        assert back["record_uid"] == sorted(uids)[0] and back["url"] == "rec://%s" % sorted(uids)[0]
        assert back["source_anchor"]["kind"] == "phone_record"


@needs_template
def test_a_workspace_theory_citing_a_message_gets_a_phone_record_anchor_that_opens_the_record():
    from sqlalchemy.orm import Session
    from postgres.models.evidence import EvidenceFile
    from services import workspace_ai_service as W
    with fresh_engine() as engine:
        case, ext = _build(engine)
        with engine.connect() as c:
            uid = str(c.execute(text("SELECT record_uid FROM pv_comm_event WHERE extraction_id = :e AND body LIKE "
                                     "'Lunch%'"), {"e": ext}).scalar())
        with Session(engine) as db:
            ids = W._thread_documents_for_record(db, case, uid)
            assert len(ids) == 1
            assert W._thread_documents_for_record(db, uuid.uuid4(), uid) == []  # another case reads nothing
            from sqlalchemy.orm import joinedload
            from sqlalchemy import select
            f = db.scalars(select(EvidenceFile).options(joinedload(EvidenceFile.document_text))
                           .where(EvidenceFile.id == ids[0])).unique().one()
            chunks = W._document_chunks(f, interview_id=None, preferred_anchor={"kind": "phone_record",
                                                                                 "record_uid": uid})
            assert chunks and chunks[0]["source_anchor"]["record_uid"] == uid
            assert chunks[0]["source_anchor"]["kind"] == "phone_record"
            assert "Lunch on Sunday" in chunks[0]["text"]
            by_terms = W._document_chunks(f, interview_id=None, preferred_anchor=None, terms=["harbour"])
            assert "harbour" in by_terms[0]["text"].lower()
            url = W._source_url(case, f.id, chunks[0]["source_anchor"])
            assert url == "/cases/%s/records/%s" % (case, uid)


def test_phone_graph_nodes_are_never_embedded(no_embedding, monkeypatch):
    from services.neo4j.entity_service import EntityService
    import services.vector_db_service as v
    monkeypatch.setattr(v, "get_vector_db_service", lambda: type("V", (), {"add_entity": lambda *a, **k: None})())
    EntityService._rebuild_entity_embedding({"key": "k", "type": "PhoneIdentity", "name": NAMES[0],
                                             "properties": {"name": NAMES[0]}}, "case")
    assert no_embedding == []
    EntityService._rebuild_entity_embedding({"key": "k", "type": "Person", "name": "Someone",
                                             "properties": {"name": "Someone"}}, "case")
    assert no_embedding == ["Someone"]  # the guard is only for phone nodes


@needs_template
def test_co10_theory_analysis_reads_a_linked_message_in_full_and_cites_its_record():
    """07 CO-10 / XF-7: a theory with a phone message linked gets that message, its words and saved names in full,
    as a source anchored to its record; another case's theory never reads it."""
    from sqlalchemy.orm import Session
    from postgres.models.workspace_entry import WorkspaceEntry, WorkspaceEntryLink
    from services import workspace_ai_service as W
    with fresh_engine() as engine:
        case, ext = _build(engine)
        with engine.connect() as c:
            uid = str(c.execute(text("SELECT record_uid FROM pv_comm_event WHERE extraction_id = :e AND body LIKE "
                                     "'Lunch%'"), {"e": ext}).scalar())
        with Session(engine) as db:
            theory = WorkspaceEntry(case_id=case, entry_type="theory", title="They met on Sunday",
                                    body="The two met for lunch on Sunday.", tags=[], migration_metadata={})
            db.add(theory)
            db.flush()
            db.add(WorkspaceEntryLink(entry_id=theory.id, case_id=case, target_type="phone_record", target_id=uid,
                                      relationship_type="supports", source_anchor={}, link_metadata={}))
            db.flush()
            sources, retrieval = W._theory_sources(db, case_id=case, theory=theory)
            cited = [s for s in sources if (s.get("source_anchor") or {}).get("record_uid") == uid]
            assert cited, "the linked message is a source"
            assert cited[0]["source_anchor"]["kind"] == "phone_record"
            assert "Lunch on Sunday" in cited[0]["text"] and "Synthetic Anabel" in cited[0]["text"]
            assert "existing_supports" in cited[0]["retrieval_roles"]
            assert retrieval["linked_evidence_ids"]
            db.rollback()


def test_xf7_search_hit_to_finding_to_export_and_theory_analysis_with_the_same_records():
    """07 XF-7 (and CO-12): Search hits added to a finding (the Add to… batch path) export with the collected count as
    the export's total; a theory holding them is read by Workspace AI with every record cited; nothing of another
    case or another entry comes in, and links that are not messages are named as not exported."""
    from sqlalchemy.orm import Session
    from postgres.models.user import User
    from postgres.models.workspace_entry import WorkspaceEntry
    from services import workspace_ai_service as W
    from services import workspace_entry_service as entries
    from services.phone import entry_export
    from services.phone.exports import jobs
    from services.phone import resolvers
    from services.search import search as S
    resolvers.register()
    with fresh_engine() as engine:
        case, ext = _build(engine)
        with Session(engine) as db:
            hits = S.search(db.connection(), case, "cargo", groups=("messages",))["groups"][0]
            uids = [h["record_uid"] for h in hits["items"]]
            assert len(uids) == 2
            owner = db.get(User, db.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"),
                                            {"c": case}).scalar())
            made = {}
            for kind in ("finding", "theory"):
                eid = uuid.UUID(entries.create_entry(db, case_id=case, current_user=owner, entry_type=kind,
                                                     title="Cargo on Friday", body="The cargo left on Friday.")["id"])
                links = [{"target_type": "phone_record", "target_id": u, "target_label": "hit",
                          "relationship": "supports", "source_anchor": {"origin": "search"}} for u in uids]
                links.append({"target_type": "phone_identity", "target_id": ANA, "target_label": "Ana",
                              "relationship": "context", "source_anchor": {}})
                r = entries.batch_add_entry_links(db, case_id=case, entry_id=eid, current_user=owner, links=links,
                                                  rationale="Added from Search")
                assert r["added"] == 3
                made[kind] = eid
            out = entry_export.freeze_entry(db, case, made["finding"], owner)
            assert out["collected"] == 2 and out["sentence"] == "Not in this export: 1 person on the phones."
            facts = jobs.describe(db.connection(), case, out["filter"])
            assert facts["total"] == out["collected"] == facts["messages"]
            created = jobs.create(db.connection(), case_id=case, user_id=owner.id, fmt="pdf", source="finding",
                                  filter_body=out["filter"], options={"title": "Cargo"})
            assert created["export_id"]
            with pytest.raises(jobs.ExportError):
                jobs.create(db.connection(), case_id=case, user_id=owner.id, fmt="pdf", source="finding",
                            filter_body={"case_id": str(case)}, options={})
            with pytest.raises(LookupError):
                entry_export.freeze_entry(db, uuid.uuid4(), made["finding"], owner)
            theory = db.get(WorkspaceEntry, made["theory"])
            sources, _ = W._theory_sources(db, case_id=case, theory=theory)
            cited = {u for s in sources for u in (s.get("source_anchor") or {}).get("record_uids") or []}
            assert set(uids) <= cited          # both linked messages share one window; each is cited by its record
            db.rollback()
