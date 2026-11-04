"""Documents stay searchable when meaning search fails (lx-docsearch B-E).

On live since 2026-10-28 every embedding call failed with OpenAI's 429 "insufficient quota": the agent's
search_documents raised (the workflows reported "not examined" and listed documents instead), chat's chunk and
entity search returned an empty context without saying so, and the AI settings page showed "Search embeddings:
Ready". Each test here fails on the code before this change.
"""
from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres.base import Base
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceFolder
from services import meaning_search

QUOTA = ("Error code: 429 - {'error': {'message': 'You have no credits remaining.', 'type': "
         "'insufficient_quota', 'code': 'credit_balance_exhausted'}}")
QUOTA_REASON = "the search service (OpenAI) has no credits left: 429 insufficient quota"


class QuotaError(Exception):
    status_code = 429


class QuotaEmbeddings:
    calls = 0

    def generate_embedding(self, text):
        QuotaEmbeddings.calls += 1
        raise QuotaError(QUOTA)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True,
                                    connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine, tables=[EvidenceFolder.__table__, EvidenceFile.__table__,
                                                      EvidenceDocumentText.__table__])
        with self.engine.begin() as conn:
            conn.execute(text("""CREATE TABLE service_health_states (service varchar PRIMARY KEY, status varchar,
                reason_code varchar, reason text, down_since timestamp, last_failure_at timestamp,
                last_success_at timestamp, failures_since_down integer NOT NULL DEFAULT 0,
                backfill_pending boolean NOT NULL DEFAULT 0, updated_at timestamp)"""))
            conn.execute(text("CREATE TABLE cost_records (id integer PRIMARY KEY, operation_kind varchar, "
                              "created_at timestamp)"))
        self.Session = sessionmaker(bind=self.engine, future=True, expire_on_commit=False)
        self.case_id = uuid4()
        with self.Session() as db:
            self.tender = self._doc(db, "tender-award.pdf", "The tender for the depot closed on 3 May. The award "
                                    "went to Northgate Ltd on 9 May.", pages=True)
            self.receipt = self._doc(db, "receipt-0412.pdf", "Receipt: dinner for four, total 412.50, Northgate.")
            self.scan = self._doc(db, "scan-no-text.jpg", None)
            self.other = self._doc(db, "other-case.pdf", "tender award Northgate", case_id=uuid4())
            db.commit()

    def tearDown(self):
        self.engine.dispose()
        meaning_search._gap_cache.clear()

    def _doc(self, db, name, content, *, pages=False, case_id=None, source_type=None):
        evidence = EvidenceFile(id=uuid4(), case_id=case_id or self.case_id, original_filename=name,
                                stored_path="/nonexistent/%s" % name, size=1, sha256="a" * 64, status="processed",
                                source_type=source_type)
        db.add(evidence)
        if content is not None:
            locations = [{"start_char": 0, "end_char": 40, "page_number": 1},
                         {"start_char": 40, "end_char": len(content), "page_number": 2}] if pages else []
            db.add(EvidenceDocumentText(evidence_file_id=evidence.id, content=content, content_sha256="b" * 64,
                                        character_count=len(content), source_locations=locations))
        return evidence

    @contextmanager
    def session(self):
        with self.Session() as db:
            yield db


class WordSearchTests(Fixture):
    def test_terms_drop_stopwords_and_keep_amounts(self):
        self.assertEqual(meaning_search.search_terms("the tender and award dates")[0], ["tender", "award", "dates"])
        self.assertEqual(meaning_search.search_terms("receipt for 412.50")[0], ["receipt", "412.50"])
        many = " ".join("word%d" % i for i in range(12))
        terms, not_searched = meaning_search.search_terms(many)
        self.assertEqual(len(terms), meaning_search.MAX_TERMS)
        self.assertEqual(len(not_searched), 12 - meaning_search.MAX_TERMS)  # stated, never dropped silently

    def test_ranked_by_terms_held_paged_with_totals_and_case_scoped(self):
        with self.Session() as db:
            first = meaning_search.word_search_documents(db, case_id=self.case_id, query="tender Northgate",
                                                         limit=1, offset=0)
            second = meaning_search.word_search_documents(db, case_id=self.case_id, query="tender Northgate",
                                                          limit=1, offset=1)
        self.assertEqual(first["total_documents"], 2)  # the other case's document is never searched
        self.assertEqual(first["documents"][0]["filename"], "tender-award.pdf")  # holds both terms
        self.assertEqual(first["next_offset"], 1)
        self.assertEqual(second["documents"][0]["filename"], "receipt-0412.pdf")
        self.assertIsNone(second["next_offset"])
        self.assertEqual((first["searchable_documents"], first["case_documents"]), (2, 3))


class AgentSearchDocumentsTests(Fixture):
    def _tools(self):
        from services.agent.tools import AgentToolContext, make_agent_tools
        context = AgentToolContext(case_id=str(self.case_id), ledger_session_factory=self.session)
        return {tool.name: tool for tool in make_agent_tools(context)}

    def test_quota_error_falls_back_to_word_search_and_says_so(self):
        tools = self._tools()
        with patch("services.agent.tools.get_vector_db_service", return_value=object()), patch(
                "services.vector_db_service.get_vector_db_health", return_value={"available": True}), patch(
                "services.embedding_service.embedding_service", QuotaEmbeddings()):
            result = tools["search_documents"].invoke({"query": "the tender and award dates", "limit": 5})
        self.assertEqual(result["status"], "success")
        data = result["data"]
        self.assertEqual(data["search"], "word")
        self.assertEqual(data["note"], "Meaning search unavailable (%s); searched the words instead: 2 of 3 "
                                       "documents searchable." % QUOTA_REASON)
        self.assertTrue(result["summary"].startswith(data["note"]))
        self.assertIn("1 document(s) have no stored text", result["summary"])
        self.assertEqual({r["filename"] for r in data["results"]}, {"tender-award.pdf"})
        self.assertTrue(all("not a meaning match" in r["match"] for r in data["results"]))
        self.assertEqual(data["total"], 1)
        self.assertIn(2, {r["page"] for r in data["results"]})  # "award" sits on page 2
        # each word hit carries its doc:// citation: the file by id at the hit's page (agent-citations)
        self.assertTrue(all(r["cite"] == "doc://%s/%s" % (r["evidence_file_id"], r["page"]) if r.get("page")
                            else r["cite"] == "doc://%s" % r["evidence_file_id"] for r in data["results"]))

        # The run record names what was not meaning-searched.
        from services.agent.run_record import call_facts, returned_items
        from services.agent.run_record_export import _search_coverage_rows
        facts = call_facts("search_documents", {"query": "x"}, result, None)
        self.assertEqual(facts["search_coverage"]["search"], "word")
        self.assertTrue(facts["available"])
        items, _ = returned_items(data)
        self.assertEqual({i["kind"] for i in items}, {"document"})
        rows = _search_coverage_rows({"sequence": 1, "name": "search_documents",
                                      "search_coverage": facts["search_coverage"]})
        self.assertEqual([r["clipped by"] for r in rows], ["meaning search unavailable", "no stored text"])
        self.assertIn("Nothing was meaning-searched", rows[0]["detail"])

    def test_meaning_search_states_documents_without_a_vector(self):
        class Collection:
            def get(self, where, include, limit, offset):
                if offset:
                    return {"ids": [], "metadatas": []}
                return {"ids": ["c1", "c2"], "metadatas": [
                    {"case_id": where["case_id"], "evidence_file_id": str(tender_id), "ingestion_state": "active"},
                    {"case_id": where["case_id"], "evidence_file_id": str(receipt_id), "ingestion_state": "draft"}]}

        tender_id, receipt_id = self.tender.id, self.receipt.id

        class Vectors:
            chunk_collection = Collection()

            def search_chunks(self, embedding, top_k, filter_metadata):
                return [{"id": "c1", "text": "tender", "metadata": {"doc_name": "tender-award.pdf"},
                         "distance": 0.2}]

        class Embeddings:
            def generate_embedding(self, text):
                return [0.1]

        tools = self._tools()
        with patch("services.agent.tools.get_vector_db_service", return_value=Vectors()), patch(
                "services.vector_db_service.get_vector_db_health", return_value={"available": True}), patch(
                "services.embedding_service.embedding_service", Embeddings()):
            result = tools["search_documents"].invoke({"query": "tender"})
        self.assertEqual(result["data"]["search"], "meaning")
        self.assertEqual(result["data"]["vector_gap"]["documents_without_vector"], 1)  # the draft is not searched
        self.assertIn("1 of 2 documents with text in this case have no meaning-search vector", result["summary"])


class ChatFallbackTests(Fixture):
    def _rag(self):
        from services.rag_service import RAGService
        return RAGService.__new__(RAGService)

    def test_embedding_error_gives_word_hits_never_a_silent_empty_context(self):
        import services.rag_service as rag

        class Vectors:
            def count_chunks(self):
                return 5

        debug = {}
        with patch.object(rag, "embedding_service", QuotaEmbeddings()), patch.object(
                rag, "vector_db_service", Vectors()), patch.object(rag, "VECTOR_DB_AVAILABLE", True), patch(
                "postgres.session.get_background_session", self.session):
            chunks = self._rag()._retrieve_chunks("When was the tender award?", str(self.case_id), debug_log=debug)
            context = self._rag()._build_context(chunks, [], {"selected_entities": []}, None, None) \
                if hasattr(self._rag(), "_build_context") else None
            sources = self._rag()._build_sources(chunks)
        self.assertTrue(chunks)
        self.assertEqual({c["metadata"]["doc_name"] for c in chunks}, {"tender-award.pdf"})
        self.assertEqual(debug["chunk_search"]["source"], "word")
        self.assertIn("Meaning search unavailable (%s); searched the words instead: 2 of 3 documents searchable."
                      % QUOTA_REASON, debug["search_notes"])
        self.assertEqual(sources[0]["filename"], "tender-award.pdf")
        if context is not None:
            self.assertIn("Found by word search", context if isinstance(context, str) else str(context))

    def test_entity_search_falls_back_to_the_name_search(self):
        import services.rag_service as rag

        rag_service = self._rag()
        searched = []

        def search_nodes(term, limit, case_id):
            searched.append(term)
            return [{"key": "northgate-ltd"}] if term.lower() == "northgate" else []

        debug = {}
        with patch.object(rag, "embedding_service", QuotaEmbeddings()), patch.object(
                rag, "VECTOR_DB_AVAILABLE", True), patch.object(rag, "ENTITY_SEARCH_ENABLED", True), patch(
                "services.neo4j.graph_service.graph_service.search_nodes", side_effect=search_nodes), patch.object(
                type(rag_service), "_get_entity_nodes_from_neo4j",
                lambda self, keys, case_id=None: [{"key": k, "name": "Northgate Ltd"} for k in keys]):
            entities = rag_service._retrieve_entities("Who is Northgate?", str(self.case_id), debug_log=debug)
        self.assertEqual([e["key"] for e in entities], ["northgate-ltd"])
        self.assertEqual(debug["entity_search"]["source"], "name")
        self.assertIn("Entities were found by name instead of by meaning: 1 matched.", debug["search_notes"])


class ReviewFindingTests(Fixture):
    def test_a_repeated_file_name_never_hides_a_document_with_no_vector(self):
        with self.Session() as db:
            twin = self._doc(db, "tender-award.pdf", "a second file with the same name")
            db.commit()
        tender_id = str(self.tender.id)

        class Collection:
            def get(self, where, include, limit, offset):
                if offset:
                    return {"ids": [], "metadatas": []}
                return {"ids": ["c1"], "metadatas": [{"case_id": where["case_id"], "evidence_file_id": tender_id,
                                                     "doc_name": "tender-award.pdf"}]}

        with self.Session() as db:
            gap = meaning_search.vector_gap(str(self.case_id), db=db, collection=Collection(), fresh=True)
        self.assertIn(str(twin.id), gap["missing_evidence_file_ids"])
        self.assertNotIn(tender_id, gap["missing_evidence_file_ids"])

    def test_chat_scope_searches_the_selected_documents_themselves(self):
        import services.rag_service as rag
        debug = {}
        with patch.object(rag, "CHUNK_SEARCH_TOP_K", 1), patch(
                "postgres.session.get_background_session", self.session):
            chunks = rag.RAGService.__new__(rag.RAGService)._retrieve_chunks_by_words(
                "Northgate tender", str(self.case_id), doc_keys=[rag._document_key("receipt-0412.pdf")],
                debug_log=debug, strict_doc_scope=True, failure=("quota", QUOTA_REASON))
        # case-wide, the receipt ranks second and a top-1 cut would drop it; the scope is searched itself
        self.assertEqual({c["metadata"]["doc_name"] for c in chunks}, {"receipt-0412.pdf"})

    def test_entity_keys_rank_by_terms_held_and_report_the_total(self):
        rows = {"northgate": [{"key": "a"}, {"key": "b"}], "depot": [{"key": "b"}, {"key": "c"}]}
        keys, total = meaning_search.word_search_entity_keys(
            "Northgate depot", case_id="c", limit=2,
            search_nodes=lambda term, limit, case_id: rows.get(term.lower(), []))
        self.assertEqual(keys[0], "b")  # holds both terms
        self.assertEqual(total, 3)


class HealthTests(Fixture):
    def test_down_since_the_first_failure_and_recovery_starts_the_backfill(self):
        started = []
        meaning_search._memo.update(status=None, checked_pending=False)
        meaning_search.record_failure(QuotaError(QUOTA), session_factory=self.session)
        with self.Session() as db:
            first = db.execute(text("SELECT down_since FROM service_health_states")).scalar()
        meaning_search.record_failure(QuotaError(QUOTA), session_factory=self.session)
        with self.Session() as db:
            health = meaning_search.health(db=db)
        self.assertEqual(health["status"], "down")
        self.assertEqual(health["reason"], QUOTA_REASON)
        self.assertEqual(health["failures_since_down"], 2)
        # No call that worked was seen before the first recorded failure: its time is not the outage start.
        self.assertIsNone(health["down_since"])
        self.assertFalse(health["down_since_known"])
        self.assertEqual(str(health["first_recorded_failure_at"]).replace("T", " ")[:19],
                         str(first).replace("T", " ")[:19])

        meaning_search.record_success(session_factory=self.session, start_backfill=lambda: started.append(1))
        with self.Session() as db:
            health = meaning_search.health(db=db)
        self.assertEqual(health["status"], "up")
        self.assertIsNone(health["reason"])
        self.assertTrue(health["backfill_pending"])
        self.assertEqual(started, [1])
        meaning_search._memo.update(status=None, checked_pending=False)

    def test_state_kept_from_mid_outage_never_shows_its_first_row_as_the_start(self):
        """followups m11040828134070: live said 'Failing since 4 Nov 06:42' while every call was refused since 28 Oct."""
        meaning_search._memo.update(status=None, checked_pending=False)
        with self.Session() as db:
            db.execute(text("INSERT INTO cost_records (id, operation_kind, created_at) "
                            "VALUES (1, 'embedding', '2026-10-27 18:42:49')"))
            db.commit()
        meaning_search.record_failure(QuotaError(QUOTA), session_factory=self.session)
        with self.Session() as db:
            health = meaning_search.health(db=db)
        self.assertIsNone(health["down_since"])
        self.assertFalse(health["down_since_known"])
        self.assertIsNotNone(health["first_recorded_failure_at"])
        self.assertTrue(str(health["last_success_at"]).startswith("2026-10-27"))
        meaning_search._memo.update(status=None, checked_pending=False)

    def test_outage_start_is_known_when_the_state_saw_the_service_answer_first(self):
        meaning_search._memo.update(status=None, checked_pending=False)
        meaning_search.record_success(session_factory=self.session, start_backfill=lambda: None)
        meaning_search.record_failure(QuotaError(QUOTA), session_factory=self.session)
        with self.Session() as db:
            first = db.execute(text("SELECT down_since FROM service_health_states")).scalar()
            health = meaning_search.health(db=db)
        self.assertTrue(health["down_since_known"])
        self.assertEqual(str(health["down_since"]).replace("T", " ")[:19], str(first).replace("T", " ")[:19])
        meaning_search._memo.update(status=None, checked_pending=False)

    def test_ai_settings_reports_search_embeddings_down(self):
        from routers import ai_settings

        class Connection:
            configured = True

        down = {"status": "down", "reason": QUOTA_REASON, "down_since": "2026-11-04T05:00:00+00:00"}
        with patch.object(ai_settings.credential_store, "get_connection", return_value=Connection()), patch.object(
                meaning_search, "health", return_value=down):
            services = ai_settings._supporting_services(None)
        embeddings = next(s for s in services if s["id"] == "embeddings")
        self.assertEqual(embeddings["status"], "down")
        self.assertEqual(embeddings["health"]["reason"], QUOTA_REASON)


    def _transcription(self, health, *, last_transcription=None):
        from routers import ai_settings

        class Connection:
            configured = True

        with patch.object(ai_settings.credential_store, "get_connection", return_value=Connection()), patch.object(
                meaning_search, "health", return_value=health), patch.object(
                ai_settings, "_last_transcription", return_value=last_transcription), patch.object(
                ai_settings, "EMBEDDING_PROVIDER", "openai"):
            services = ai_settings._supporting_services(None)
        return next(s for s in services if s["id"] == "transcription")

    def test_ai_settings_reports_transcription_down_when_the_openai_account_has_no_credits(self):
        """followups m11040644368621: on live the row said Ready while every OpenAI call was refused."""
        from datetime import datetime, timezone
        down = {"status": "down", "reason_code": "quota", "reason": QUOTA_REASON,
                "down_since": "2026-11-04T05:00:00+00:00", "last_failure_at": "2026-11-04T06:42:00+00:00"}
        row = self._transcription(down, last_transcription=datetime(2026, 9, 17, 15, 5, tzinfo=timezone.utc))
        self.assertEqual(row["status"], "down")
        self.assertIn("no credits left", row["health"]["reason"])
        self.assertIn("search embedding calls", row["health"]["reason"])
        self.assertEqual(row["health"]["last_success_at"], "2026-09-17T15:05:00+00:00")
        self.assertIn("cannot be transcribed", row["health"]["consequence"])
        self.assertNotIn("failures_since_down", row["health"])  # those were embedding calls, not transcriptions

    def test_transcription_outage_is_bounded_by_the_accounts_last_working_call(self):
        down = {"status": "down", "reason_code": "quota", "reason": QUOTA_REASON, "down_since": None,
                "down_since_known": False, "first_recorded_failure_at": "2026-11-04T06:42:00+00:00",
                "last_success_at": "2026-10-27T18:42:49+00:00"}
        row = self._transcription(down)
        self.assertIsNone(row["health"]["down_since"])
        self.assertFalse(row["health"]["down_since_known"])
        self.assertEqual(row["health"]["first_recorded_failure_at"], "2026-11-04T06:42:00+00:00")
        self.assertEqual(row["health"]["failing_after"], "2026-10-27T18:42:49+00:00")

    def test_transcription_stays_ready_when_the_outage_is_not_account_wide(self):
        for health in ({"status": "up"}, {"status": "down", "reason_code": "rate_limited", "reason": "429"},
                       {"status": "down", "reason_code": "error", "reason": "timeout"}):
            row = self._transcription(health)
            self.assertEqual(row["status"], "ready", health)
            self.assertNotIn("health", row)


class GapBackfillTests(Fixture):
    def _patches(self):
        import scripts.backfill_chunk_embeddings as backfill
        live_like = sessionmaker(bind=self.engine, future=True)  # expire_on_commit, as on live

        @contextmanager
        def background_session():  # postgres.session.get_background_session: commit on exit, then close
            db = live_like()
            try:
                yield db
                db.commit()
            finally:
                db.close()

        return (patch.object(backfill, "get_background_session", background_session),
                patch.object(backfill, "_find_graph_document", lambda f: {"id": str(f.id), "key": "",
                                                                          "name": f.original_filename,
                                                                          "case_id": str(f.case_id)}),
                patch.object(backfill, "_set_vector_db_id", lambda doc_id: None))

    def test_gap_documents_embedded_from_stored_text_one_at_a_time(self):
        from scripts.backfill_chunk_embeddings import backfill_chunk_embeddings

        class Store:
            def __init__(self):
                self.added = []

                class Collection:
                    def get(self, where, include):
                        return {"ids": []}
                self.chunk_collection = Collection()

            def add_chunk(self, chunk_id, text, embedding, metadata):
                self.added.append(metadata)

        class Embeddings:
            def generate_embedding(self, text):
                return [0.5]

        store = Store()
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            result = backfill_chunk_embeddings(case_id=str(self.case_id), evidence_file_ids=[str(self.receipt.id)],
                                               prefer_stored_text=True, stop_on_failure=True,
                                               embedder=Embeddings(), vector_store=store)
        self.assertEqual(result["stats"]["processed"], 1)
        self.assertEqual({m["evidence_file_id"] for m in store.added}, {str(self.receipt.id)})  # only the gap
        self.assertEqual(result["stats"]["file_not_found"], 0)  # stored text: no file read from disk

    def test_quota_stops_the_backfill_with_nothing_half_stored(self):
        from scripts.backfill_chunk_embeddings import backfill_chunk_embeddings

        class Store:
            added = []

            class chunk_collection:  # noqa: N801 - the attribute name the backfill reads
                @staticmethod
                def get(where, include):
                    return {"ids": []}

            def add_chunk(self, **kwargs):
                self.added.append(kwargs)

        QuotaEmbeddings.calls = 0
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            result = backfill_chunk_embeddings(case_id=str(self.case_id),
                                               evidence_file_ids=[str(self.tender.id), str(self.receipt.id)],
                                               prefer_stored_text=True, stop_on_failure=True,
                                               embedder=QuotaEmbeddings(), vector_store=Store())
        self.assertEqual(result["stopped"], QUOTA_REASON)
        self.assertEqual(QuotaEmbeddings.calls, 1)  # one failed call, not one per document
        self.assertEqual(Store.added, [])

    def test_staged_never_activated_chunks_are_activated_without_an_embedding_call(self):
        """Live 2026-11-04: 17 documents (8,399 chunks) held complete vectors staged as 'draft' by ingestions that
        stopped before activation, so meaning search never read them, and the gap backfill skipped them as
        'already has chunks'. Their staged revision equals the stored text hash, so they are activated as is."""
        from scripts.backfill_chunk_embeddings import backfill_chunk_embeddings

        def matches(meta, where):
            if "$and" in where:
                return all(matches(meta, w) for w in where["$and"])
            return all(meta.get(k) == v for k, v in where.items())

        class Collection:
            def __init__(self, rows):
                self.rows = rows

            def get(self, where=None, include=None, limit=None, offset=0):
                hit = [(cid, m) for cid, m in self.rows.items() if matches(m, where or {})]
                hit = hit[offset:offset + limit] if limit else hit[offset:]
                return {"ids": [c for c, _ in hit], "metadatas": [dict(m) for _, m in hit]}

            def update(self, ids, metadatas):
                for cid, meta in zip(ids, metadatas):
                    self.rows[cid] = meta

        case = str(self.case_id)
        tender, receipt = str(self.tender.id), str(self.receipt.id)
        rows = {
            "%s:%s:chunk:%d" % (tender, "b" * 64, i): {"case_id": case, "doc_id": tender, "evidence_file_id": tender,
                                                       "revision_id": "b" * 64, "ingestion_state": "draft"}
            for i in range(3)}
        rows["%s:old:chunk:0" % tender] = {"case_id": case, "doc_id": tender, "evidence_file_id": tender,
                                           "revision_id": "old", "ingestion_state": "active"}
        # a staged revision of other text (not what the case holds now) stays staged and gets embedded
        rows["%s:stale:chunk:0" % receipt] = {"case_id": case, "doc_id": receipt, "evidence_file_id": receipt,
                                              "revision_id": "c" * 64, "ingestion_state": "draft"}

        class Store:
            def __init__(self):
                self.added = []
                self.chunk_collection = Collection(rows)

            def add_chunk(self, chunk_id, text, embedding, metadata):
                self.added.append(metadata)

        QuotaEmbeddings.calls = 0
        store = Store()
        p1, p2, p3 = self._patches()
        with p1, p2, p3:
            result = backfill_chunk_embeddings(case_id=case, evidence_file_ids=[tender, receipt],
                                               prefer_stored_text=True, stop_on_failure=True,
                                               embedder=QuotaEmbeddings(), vector_store=store)
        states = {cid: m["ingestion_state"] for cid, m in rows.items()}
        self.assertEqual([states["%s:%s:chunk:%d" % (tender, "b" * 64, i)] for i in range(3)], ["active"] * 3)
        self.assertEqual(states["%s:old:chunk:0" % tender], "inactive")
        self.assertEqual(states["%s:stale:chunk:0" % receipt], "draft")
        self.assertEqual((result["stats"]["staged_activated"], result["stats"]["staged_chunks_activated"]), (1, 3))
        # the receipt's draft does not count as having chunks: it was sent to embedding (refused, nothing stored)
        self.assertEqual(result["stopped"], QUOTA_REASON)
        self.assertEqual(QuotaEmbeddings.calls, 1)
        self.assertEqual(store.added, [])

        meaning_search._gap_cache.clear()
        with self.Session() as db:
            gap = meaning_search.vector_gap(case, db=db, collection=store.chunk_collection, fresh=True)
        self.assertNotIn(tender, gap["missing_evidence_file_ids"])
        self.assertIn(receipt, gap["missing_evidence_file_ids"])

    def test_run_gap_backfill_keeps_pending_when_stopped_and_clears_it_when_done(self):
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO service_health_states (service, status, backfill_pending) "
                              "VALUES ('meaning_search', 'up', 1)"))
        gap = lambda case_id, fresh: {"missing_evidence_file_ids": ["f1"]}  # noqa: E731
        logged = []
        stopped = meaning_search.run_gap_backfill(
            case_ids=["c1", "c2"], gap=gap, session_factory=self.session, lock=False,
            log=lambda level, msg: logged.append(msg),
            backfill=lambda **kw: {"stopped": QUOTA_REASON, "stats": {}})
        self.assertEqual(stopped["stopped"], QUOTA_REASON)
        self.assertEqual(stopped["cases"], 1)  # stopped at the first case
        with self.Session() as db:
            self.assertTrue(db.execute(text("SELECT backfill_pending FROM service_health_states")).scalar())
        calls = []
        done = meaning_search.run_gap_backfill(
            case_ids=["c1", "c2"], gap=gap, session_factory=self.session, lock=False, log=lambda *a: None,
            backfill=lambda **kw: calls.append(kw) or {"stats": {"processed": 1, "total_chunks_created": 2}})
        self.assertEqual((done["documents_embedded"], done["chunks"], done["stopped"]), (2, 4, None))
        self.assertTrue(all(kw["prefer_stored_text"] and kw["stop_on_failure"] for kw in calls))
        with self.Session() as db:
            self.assertFalse(db.execute(text("SELECT backfill_pending FROM service_health_states")).scalar())


if __name__ == "__main__":
    unittest.main()
