"""The graph's Query panel and the chat's generated Cypher read only inside one case, with stated limits.

Before: POST /api/query took no case. An administrator's ``MATCH (n) RETURN n`` read every case's nodes, a case
member could not use the panel at all (it posted to /api/graph/cypher, which does not exist), the answer was
never cut or timed, and the chat ran model-written Cypher unscoped in a WRITE transaction (and
/api/chat/extract-nodes let any signed-in person have the model write Cypher from text they supplied).

Now case mode needs case view, refuses any query not bound to $case_id by the case-scope grammar, supplies
$case_id itself, runs READ with a time limit, and states the row limit and whether the answer was cut.
"""

import types
import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from neo4j import READ_ACCESS
from neo4j.exceptions import ClientError

from postgres.models.user import GlobalRole
from postgres.session import get_db
from routers import auth, chat, query, users
from services.neo4j.driver import driver as neo4j_driver

CASE_A = "11111111-1111-1111-1111-111111111111"
CASE_B = "22222222-2222-2222-2222-222222222222"


class FakeNeo4j:
    """Two cases' nodes; a tx returns rows matching the case_id parameter when one is given."""

    def __init__(self, rows_per_case=2):
        self.nodes = [{"name": f"{case}-{i}", "case_id": case} for case in (CASE_A, CASE_B)
                      for i in range(rows_per_case)]
        self.calls = []
        self.modes = []
        self.error = None

    def session(self, default_access_mode=None, **kw):
        self.modes.append(default_access_mode)
        return FakeSession(self)


class FakeSession:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute_read(self, work):
        return work(FakeTx(self.db))

    def execute_write(self, work):  # pragma: no cover - a write transaction is never opened here
        raise AssertionError("write transaction opened")


class FakeTx:
    def __init__(self, db):
        self.db = db

    def run(self, cypher, params):
        self.db.calls.append((cypher, dict(params)))
        if self.db.error is not None:
            raise self.db.error
        case = params.get("case_id")
        return [{"name": n["name"]} for n in self.db.nodes if case is None or n["case_id"] == case]


def _client_error(code):
    error = ClientError("refused")
    error.code = code
    return error


class QueryCaseScopeTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeNeo4j()
        self._driver = neo4j_driver._driver
        neo4j_driver._driver = self.fake
        self._log = query.system_log_service.log
        query.system_log_service.log = lambda **kw: None
        self._authorize = query.authorize_case
        self.viewable = {CASE_A}

        def authorize(db, case_id, user, permission):
            self.assertEqual(permission, ("case", "view"))
            if str(case_id) not in self.viewable:
                raise HTTPException(status_code=403, detail="no access")
            return __import__("uuid").UUID(str(case_id))

        query.authorize_case = authorize
        app = FastAPI()
        app.include_router(query.router)
        app.dependency_overrides[get_db] = lambda: None
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        neo4j_driver._driver = self._driver
        query.system_log_service.log = self._log
        query.authorize_case = self._authorize

    def _sign_in(self, role):
        person = types.SimpleNamespace(email="person@example.com", global_role=role, is_active=True)
        self.app.dependency_overrides[auth.get_current_user] = lambda: {"username": person.email}
        self.app.dependency_overrides[users.get_current_db_user] = lambda: person

    def _post(self, **body):
        return self.client.post("/api/query", json=body)

    def test_case_member_reads_only_their_case(self):
        self._sign_in(GlobalRole.user)
        response = self._post(query="MATCH (n {case_id: $case_id}) RETURN n.name AS name", case_id=CASE_A)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["success"], body)
        self.assertEqual({r["name"] for r in body["results"]}, {f"{CASE_A}-0", f"{CASE_A}-1"})
        self.assertEqual(body["columns"], ["name"])
        self.assertEqual(self.fake.calls[-1][1]["case_id"], CASE_A)
        self.assertEqual(set(self.fake.modes), {READ_ACCESS})

    def test_another_case_is_refused(self):
        self._sign_in(GlobalRole.user)
        response = self._post(query="MATCH (n {case_id: $case_id}) RETURN n.name AS name", case_id=CASE_B)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.fake.calls, [])

    def test_unscoped_query_in_a_case_never_reaches_the_database(self):
        # Before, an administrator's MATCH (n) read every case; in case mode it is refused before running.
        self._sign_in(GlobalRole.admin)
        for cypher in ("MATCH (n) RETURN n.name AS name",
                       "MATCH (n {case_id: $case_id})-[r]-(m) RETURN m.name AS name",
                       "MATCH (n) WHERE n.case_id = $case_id OR true RETURN n.name AS name"):
            with self.subTest(cypher=cypher):
                body = self._post(query=cypher, case_id=CASE_A).json()
                self.assertFalse(body["success"])
                self.assertIn("case", body["error"])
        self.assertEqual(self.fake.calls, [])

    def test_client_cannot_supply_case_id(self):
        self._sign_in(GlobalRole.user)
        response = self._post(query="MATCH (n {case_id: $case_id}) RETURN n.name AS name",
                              case_id=CASE_A, params={"case_id": CASE_B})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.fake.calls, [])

    def test_writes_are_refused_before_or_by_the_database(self):
        self._sign_in(GlobalRole.user)
        # The grammar refuses anything but MATCH ... RETURN; a CALL that dodges every keyword never runs.
        body = self._post(query="CALL apoc.create.node(['X'], {case_id: $case_id}) YIELD node RETURN node",
                          case_id=CASE_A).json()
        self.assertFalse(body["success"])
        self.assertEqual(self.fake.calls, [])
        # And if the database is reached, it is a READ transaction: its refusal is reported as read only.
        self.fake.error = _client_error("Neo.ClientError.Statement.AccessMode")
        body = self._post(query="MATCH (n {case_id: $case_id}) RETURN n.name AS name", case_id=CASE_A).json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"], query.READ_ONLY_REFUSAL)

    def test_whole_case_needs_an_administrator(self):
        self._sign_in(GlobalRole.user)
        self.assertEqual(self._post(query="MATCH (n) RETURN n.name AS name").status_code, 403)
        self.assertEqual(self.fake.calls, [])

    def test_row_limit_is_stated_and_a_cut_is_reported(self):
        self.fake.nodes = [{"name": str(i), "case_id": CASE_A} for i in range(query.ROW_LIMIT + 50)]
        self._sign_in(GlobalRole.user)
        body = self._post(query="MATCH (n {case_id: $case_id}) RETURN n.name AS name", case_id=CASE_A).json()
        self.assertTrue(body["success"], body)
        self.assertEqual(body["count"], query.ROW_LIMIT)
        self.assertEqual(body["row_limit"], query.ROW_LIMIT)
        self.assertTrue(body["truncated"])
        self.assertIsNone(body["total"])
        # The server asks for one row past the limit so a cut is detected, not guessed.
        self.assertTrue(self.fake.calls[-1][0].rstrip().endswith(f"LIMIT {query.ROW_LIMIT + 1}"))

    def test_property_named_limit_is_not_the_limit_clause(self):
        self._sign_in(GlobalRole.user)
        body = self._post(query="MATCH (n {case_id: $case_id}) RETURN n.limit AS limit", case_id=CASE_A).json()
        self.assertTrue(body["success"], body)
        self.assertTrue(self.fake.calls[-1][0].rstrip().endswith(f"LIMIT {query.ROW_LIMIT + 1}"))

    def test_parameter_limit_within_the_cap_is_kept(self):
        self._sign_in(GlobalRole.user)
        body = self._post(query="MATCH (n {case_id: $case_id}) RETURN n.name AS name LIMIT $n",
                          case_id=CASE_A, params={"n": 1}).json()
        self.assertTrue(body["success"], body)
        self.assertTrue(self.fake.calls[-1][0].rstrip().endswith("LIMIT $n"))
        body = self._post(query="MATCH (n {case_id: $case_id}) RETURN n.name AS name LIMIT $n",
                          case_id=CASE_A, params={"n": 10_000}).json()
        self.assertTrue(self.fake.calls[-1][0].rstrip().endswith(f"LIMIT {query.ROW_LIMIT + 1}"))

    def test_whole_answer_reports_its_total(self):
        self._sign_in(GlobalRole.user)
        body = self._post(query="MATCH (n {case_id: $case_id}) RETURN n.name AS name", case_id=CASE_A).json()
        self.assertFalse(body["truncated"])
        self.assertEqual(body["total"], 2)

    def test_console_rows_are_limited_too(self):
        self.fake.nodes = [{"name": str(i), "case_id": CASE_A} for i in range(query.ROW_LIMIT + 1)]
        self._sign_in(GlobalRole.admin)
        body = self._post(query="MATCH (n) RETURN n.name AS name").json()
        self.assertEqual(body["count"], query.ROW_LIMIT)
        self.assertTrue(body["truncated"])

    def test_time_limit_is_reported(self):
        self._sign_in(GlobalRole.user)
        self.fake.error = _client_error("Neo.ClientError.Transaction.TransactionTimedOutClientConfiguration")
        body = self._post(query="MATCH (n {case_id: $case_id}) RETURN n.name AS name", case_id=CASE_A).json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"], query.TIMEOUT_REFUSAL)


class ChatCypherCaseScopeTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeNeo4j()
        self._driver = neo4j_driver._driver
        neo4j_driver._driver = self.fake
        from services.rag_service import RAGService

        self.rag = RAGService.__new__(RAGService)
        self.generated = None
        self.rag._build_schema_info = lambda summary: "schema"
        self.rag._get_llm = lambda: types.SimpleNamespace(generate_cypher=lambda q, s: self.generated)
        neo = types.SimpleNamespace(run_cypher=self._write_path)
        self.rag.neo4j = neo

    def tearDown(self):
        neo4j_driver._driver = self._driver

    def _write_path(self, *a, **kw):
        raise AssertionError("chat Cypher ran through the write path")

    def test_unscoped_generated_query_is_not_run(self):
        self.generated = "MATCH (n:Person) RETURN n.name AS name"
        log = {}
        self.assertIsNone(self.rag._try_cypher_query("who?", {}, log, case_id=CASE_A))
        self.assertIn("refused", log["cypher_answer_query"])
        self.assertEqual(self.fake.calls, [])

    def test_scoped_generated_query_reads_only_the_asking_case(self):
        self.generated = "MATCH (n:Person {case_id: $case_id}) RETURN n.name AS name"
        text = self.rag._try_cypher_query("who?", {}, None, case_id=CASE_A)
        self.assertIn(f"{CASE_A}-0", text)
        self.assertNotIn(CASE_B, text)
        self.assertEqual(self.fake.calls[-1][1]["case_id"], CASE_A)
        self.assertEqual(set(self.fake.modes), {READ_ACCESS})

    def test_a_case_id_written_by_the_model_is_overridden(self):
        self.generated = "MATCH (n:Person {case_id: $case_id}) RETURN n.name AS name"
        self.rag._try_cypher_query("who?", {}, None, case_id=CASE_A)
        self.assertEqual(self.fake.calls[-1][1], {"case_id": CASE_A})

    def test_no_case_no_query(self):
        self.generated = "MATCH (n:Person {case_id: $case_id}) RETURN n.name AS name"
        self.assertIsNone(self.rag._try_cypher_query("who?", {}, None, case_id=None))
        self.assertEqual(self.fake.calls, [])

    def test_more_rows_than_shown_is_said(self):
        self.fake.nodes = [{"name": str(i), "case_id": CASE_A} for i in range(30)]
        self.generated = "MATCH (n:Person {case_id: $case_id}) RETURN n.name AS name"
        text = self.rag._try_cypher_query("who?", {}, None, case_id=CASE_A)
        self.assertIn("only the first 20 rows are shown", text)

    def test_extract_nodes_endpoint_is_gone(self):
        paths = {getattr(route, "path", None) for route in chat.router.routes}
        self.assertNotIn("/api/chat/extract-nodes", paths)


if __name__ == "__main__":
    unittest.main()
