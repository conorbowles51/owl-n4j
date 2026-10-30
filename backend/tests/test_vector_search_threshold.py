"""A change to the vector-search confidence threshold reaches the next search, in every API process.

The setter used to change the config attribute and os.environ of the one process that took the request, while
rag_service had copied the start-up value by name at import: no search used the new value until a restart, and a
restart dropped it. The live API runs two worker processes. The value is now saved in the database and read
when a search runs.
"""

import types
import unittest
from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import config
import postgres.session as pg_session
from postgres.models.runtime_state import AIModelPolicy
from postgres.models.user import GlobalRole
from postgres.session import get_db
from routers import auth, llm_config, users
from services import rag_service as rag_module
from services import vector_search_settings


class FakeEmbeddings:
    def generate_embedding(self, text):
        return [0.0]


class FakeVectors:
    def count_chunks(self):
        return 2

    def search_chunks(self, query_embedding, top_k, filter_metadata):
        return [{"id": "near", "text": "near", "metadata": {}, "distance": 0.5},
                {"id": "far", "text": "far", "metadata": {}, "distance": 1.5}]


class ThresholdReachesNextSearchTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        AIModelPolicy.__table__.create(engine)
        self.Session = sessionmaker(bind=engine)

        @contextmanager
        def other_process_session():
            # A separate session, as another worker process would open: it sees only what was saved.
            db = self.Session()
            try:
                yield db
                db.commit()
            finally:
                db.close()

        self._saved = {
            (pg_session, "get_background_session"): pg_session.get_background_session,
            (rag_module, "VECTOR_DB_AVAILABLE"): rag_module.VECTOR_DB_AVAILABLE,
            (rag_module, "CHUNK_SEARCH_ENABLED"): rag_module.CHUNK_SEARCH_ENABLED,
            (rag_module, "embedding_service"): rag_module.embedding_service,
            (rag_module, "vector_db_service"): rag_module.vector_db_service,
            (config, "VECTOR_SEARCH_CONFIDENCE_THRESHOLD"): config.VECTOR_SEARCH_CONFIDENCE_THRESHOLD,
        }
        pg_session.get_background_session = other_process_session
        rag_module.VECTOR_DB_AVAILABLE = True
        rag_module.CHUNK_SEARCH_ENABLED = True
        rag_module.embedding_service = FakeEmbeddings()
        rag_module.vector_db_service = FakeVectors()
        config.VECTOR_SEARCH_CONFIDENCE_THRESHOLD = 2.0

        app = FastAPI()
        app.include_router(llm_config.router)

        def request_db():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = request_db
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        for (module, name), value in self._saved.items():
            setattr(module, name, value)

    def _sign_in(self, role):
        person = types.SimpleNamespace(email="admin@example.com", global_role=role, is_active=True)
        self.app.dependency_overrides[auth.get_current_user] = lambda: {"username": person.email}
        self.app.dependency_overrides[users.get_current_db_user] = lambda: person

    def _search_ids(self):
        debug = {}
        found = rag_module.rag_service._retrieve_chunks("q", case_id="case-1", debug_log=debug)
        return [r["id"] for r in found], debug["chunk_search"]["confidence_threshold"]

    def test_change_reaches_the_next_search_without_restart(self):
        self.assertEqual(self._search_ids(), (["near", "far"], 2.0))

        self._sign_in(GlobalRole.admin)
        response = self.client.post("/api/llm-config/confidence-threshold", json={"threshold": 1.0})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["threshold"], 1.0)

        self.assertEqual(self._search_ids(), (["near"], 1.0))
        self.assertEqual(self.client.get("/api/llm-config/confidence-threshold").json()["threshold"], 1.0)
        # Saved, not held in this process: the start-up value is untouched.
        self.assertEqual(config.VECTOR_SEARCH_CONFIDENCE_THRESHOLD, 2.0)
        with self.Session() as db:
            self.assertEqual(db.get(AIModelPolicy, "vector_search").configuration, {"confidence_threshold": 1.0})

        self.client.post("/api/llm-config/confidence-threshold", json={"threshold": 0.4})
        self.assertEqual(self._search_ids(), ([], 0.4))

    def test_out_of_range_is_refused_and_nothing_changes(self):
        self._sign_in(GlobalRole.admin)
        self.assertEqual(self.client.post("/api/llm-config/confidence-threshold",
                                          json={"threshold": 9}).status_code, 400)
        self.assertEqual(self._search_ids(), (["near", "far"], 2.0))

    def test_changing_it_needs_an_administrator(self):
        self._sign_in(GlobalRole.user)
        self.assertEqual(self.client.post("/api/llm-config/confidence-threshold",
                                          json={"threshold": 1.0}).status_code, 403)
        self.assertEqual(self._search_ids(), (["near", "far"], 2.0))

    def test_unreadable_setting_falls_back_to_the_start_up_value(self):
        @contextmanager
        def broken():
            raise RuntimeError("database unavailable")
            yield

        pg_session.get_background_session = broken
        self.assertEqual(vector_search_settings.get_confidence_threshold(), 2.0)


if __name__ == "__main__":
    unittest.main()
