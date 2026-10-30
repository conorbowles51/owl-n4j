"""The Cypher console is read only because the database refuses writes, not because of a keyword list.

The console used to refuse queries containing DELETE/REMOVE/SET/CREATE/MERGE/DROP/DETACH anywhere (so a property
named 'offset' was refused) and then ran everything else in a WRITE transaction (so CALL apoc.create.node(...),
which avoids every listed word, wrote to the graph). It now runs in a READ session and READ transaction.

The fake driver below behaves like Neo4j 5 as measured on 5.26 with APOC: in READ access mode every write
(plain CREATE, CALL apoc.refactor.rename.label / apoc.create.node / apoc.cypher.doIt / apoc.periodic.iterate, CREATE INDEX) fails with
Neo.ClientError.Statement.AccessMode; in WRITE mode it lands. Set LOUPE_TEST_NEO4J_URI (and _USER/_PASSWORD) to
a scratch database to run the same checks against a real Neo4j; it deletes and creates nodes there.
"""

import os
import types
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from neo4j import READ_ACCESS
from neo4j.exceptions import ClientError

from postgres.models.user import GlobalRole
from routers import auth, query, users
from services.neo4j.driver import driver as neo4j_driver

WRITES = ("CREATE", "APOC.CREATE", "APOC.CYPHER.DOIT", "APOC.PERIODIC", "APOC.REFACTOR")


def _access_mode_error():
    error = ClientError("Writing in read access mode not allowed. Attempted write to neo4j")
    error.code = "Neo.ClientError.Statement.AccessMode"
    return error


class FakeNeo4j:
    def __init__(self):
        self.graph = [{"offset": 7, "name": "a"}]
        self.written = []
        self.modes = []

    def session(self, default_access_mode=None, **kw):
        self.modes.append(default_access_mode)
        return FakeSession(self, default_access_mode)


class FakeSession:
    def __init__(self, db, mode):
        self.db, self.mode, self.tx_kind = db, mode, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def _tx(self, work, kind):
        self.tx_kind = kind
        return work(FakeTx(self.db, read=(self.mode == READ_ACCESS or kind == "read")))

    def execute_read(self, work):
        return self._tx(work, "read")

    def execute_write(self, work):
        return self._tx(work, "write")


class FakeTx:
    def __init__(self, db, read):
        self.db, self.read = db, read

    def run(self, cypher, params):
        if any(word in cypher.upper() for word in WRITES):
            if self.read:
                raise _access_mode_error()
            self.db.written.append(cypher)
            return [{"x": 1}]
        return [dict(row) for row in self.db.graph]


class ConsoleReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeNeo4j()
        self._driver = neo4j_driver._driver
        neo4j_driver._driver = self.fake
        self._log = query.system_log_service.log
        self.logged = []
        query.system_log_service.log = lambda **kw: self.logged.append(kw)
        app = FastAPI()
        app.include_router(query.router)
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        neo4j_driver._driver = self._driver
        query.system_log_service.log = self._log

    def _sign_in(self, role):
        person = types.SimpleNamespace(email="admin@example.com", global_role=role, is_active=True)
        self.app.dependency_overrides[auth.get_current_user] = lambda: {"username": person.email}
        self.app.dependency_overrides[users.get_current_db_user] = lambda: person

    def _run(self, cypher):
        return self.client.post("/api/query", json={"query": cypher}).json()

    def test_write_that_avoids_the_keywords_is_refused_by_the_database(self):
        self._sign_in(GlobalRole.admin)
        for cypher in (
            # None of the old blocked words appear in this one; the old code ran it in a write transaction.
            "CALL apoc.refactor.rename.label('P', 'Q') YIELD committedOperations RETURN committedOperations",
            "CALL apoc.create.node(['X'], {}) YIELD node RETURN node",
            "CALL apoc.cypher.doIt('CREATE (:X) RETURN 1 AS x', {}) YIELD value RETURN value",
            "CALL apoc.periodic.iterate('RETURN 1 AS x', 'CREATE (:X)', {}) YIELD batches RETURN batches",
        ):
            with self.subTest(cypher=cypher):
                body = self._run(cypher)
                self.assertFalse(body["success"])
                self.assertEqual(body["error"], query.READ_ONLY_REFUSAL)
        self.assertEqual(self.fake.written, [])
        self.assertEqual(set(self.fake.modes), {READ_ACCESS})

    def test_read_with_set_inside_an_identifier_succeeds(self):
        self._sign_in(GlobalRole.admin)
        body = self._run("MATCH (n:P) RETURN n.offset AS offset, n.name AS name")
        self.assertTrue(body["success"], body)
        self.assertEqual(body["results"], [{"offset": 7, "name": "a"}])

    def test_file_and_network_reads_are_refused(self):
        self._sign_in(GlobalRole.admin)
        for cypher in ("LOAD CSV FROM 'http://169.254.169.254/' AS row RETURN row",
                       "CALL apoc.load.json('file:///etc/passwd') YIELD value RETURN value"):
            with self.subTest(cypher=cypher):
                self.assertFalse(self._run(cypher)["success"])
        self.assertEqual(self.fake.modes, [])

    def test_console_needs_an_administrator(self):
        self.assertEqual(self.client.post("/api/query", json={"query": "MATCH (n) RETURN n"}).status_code, 401)
        self._sign_in(GlobalRole.user)
        self.assertEqual(self.client.post("/api/query", json={"query": "MATCH (n) RETURN n"}).status_code, 403)
        self.assertEqual(self.fake.modes, [])


@unittest.skipUnless(os.environ.get("LOUPE_TEST_NEO4J_URI"), "needs a scratch Neo4j (LOUPE_TEST_NEO4J_URI)")
class RealNeo4jReadModeTests(unittest.TestCase):
    def test_real_database_refuses_writes_in_read_mode(self):
        from neo4j import GraphDatabase

        real = GraphDatabase.driver(os.environ["LOUPE_TEST_NEO4J_URI"], auth=(
            os.environ.get("LOUPE_TEST_NEO4J_USER", "neo4j"), os.environ["LOUPE_TEST_NEO4J_PASSWORD"]))
        saved = neo4j_driver._driver
        neo4j_driver._driver = real
        try:
            with real.session() as s:
                s.run("MATCH (n) DETACH DELETE n").consume()
                s.run("CREATE (:P {offset: 7})").consume()
            for cypher in ("CREATE (:X) RETURN 1",
                           "CALL apoc.refactor.rename.label('P', 'Q') YIELD committedOperations RETURN committedOperations",
                           "CALL apoc.create.node(['X'], {}) YIELD node RETURN node",
                           "CALL apoc.cypher.doIt('CREATE (:X) RETURN 1 AS x', {}) YIELD value RETURN value"):
                with self.subTest(cypher=cypher):
                    with self.assertRaises(ClientError) as caught:
                        neo4j_driver.run_cypher_read(cypher)
                    self.assertTrue(query._is_write_refusal(caught.exception))
            self.assertEqual(neo4j_driver.run_cypher_read("MATCH (n:P) RETURN n.offset AS offset"),
                             [{"offset": 7}])
            with real.session() as s:
                self.assertEqual(s.run("MATCH (n) WHERE NOT n:P RETURN count(n) AS c").single()["c"], 0)
                self.assertEqual(s.run("MATCH (n:P) RETURN count(n) AS c").single()["c"], 1)
        finally:
            neo4j_driver._driver = saved
            real.close()


if __name__ == "__main__":
    unittest.main()
