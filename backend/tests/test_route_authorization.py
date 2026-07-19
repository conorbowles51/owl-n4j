import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from postgres.session import get_db
from routers import evidence, filesystem, financial, graph, users as users_router
from routers.users import get_current_db_user


class _QueryResult:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class _CaseAccessDb:
    def __init__(self, *, membership=None, records=None):
        self.case = SimpleNamespace(id=uuid4())
        self.membership = membership
        self.records = records or {}

    def query(self, model):
        if model.__name__ == "Case":
            return _QueryResult(self.case)
        if model.__name__ == "CaseMembership":
            return _QueryResult(self.membership)
        raise AssertionError(f"Unexpected model query: {model}")

    def get(self, model, record_id):
        return self.records.get(record_id)


class GraphLocationAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(graph.router)
        self.client = TestClient(self.app)

    def test_locations_rejects_an_unauthenticated_request(self):
        with patch.object(
            graph.neo4j_service,
            "get_entities_with_locations",
            return_value=[],
        ):
            response = self.client.get(
                "/api/graph/locations",
                params={"case_id": "8c2d0ed8-4d19-4c45-b58b-bf0ec2de76e0"},
            )

        self.assertEqual(response.status_code, 401)

    def test_graph_router_rejects_unauthenticated_case_reads_by_default(self):
        with patch.object(
            graph.neo4j_service,
            "get_graph_summary",
            return_value={},
        ):
            response = self.client.get(
                "/api/graph/summary",
                params={"case_id": "8c2d0ed8-4d19-4c45-b58b-bf0ec2de76e0"},
            )

        self.assertEqual(response.status_code, 401)

    def test_graph_case_read_rejects_an_authenticated_non_member(self):
        current_user = SimpleNamespace(
            id=uuid4(),
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb()
        self.app.dependency_overrides[graph.get_current_db_user] = lambda: current_user
        self.app.dependency_overrides[graph.get_db] = lambda: db

        with patch.object(
            graph.neo4j_service,
            "get_graph_summary",
            return_value={"entities": 99},
        ) as get_summary:
            response = self.client.get(
                "/api/graph/summary",
                params={"case_id": str(db.case.id)},
            )

        self.assertEqual(response.status_code, 403)
        get_summary.assert_not_called()

    def test_locations_preserves_the_complete_payload_for_a_permitted_member(self):
        membership = SimpleNamespace(
            permissions={"case": {"view": True, "edit": False}}
        )
        current_user = SimpleNamespace(
            id=uuid4(),
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb(membership=membership)
        self.app.dependency_overrides[graph.get_current_db_user] = lambda: current_user
        self.app.dependency_overrides[graph.get_db] = lambda: db
        payload = [
            {
                "id": "location-1",
                "key": "location-1",
                "name": "Example Place",
                "type": "Location",
                "latitude": 53.3498,
                "longitude": -6.2603,
                "connections": [{"key": "person-1", "relationship": "VISITED"}],
            }
        ]

        with patch.object(
            graph.neo4j_service,
            "get_entities_with_locations",
            return_value=payload,
        ) as get_locations:
            response = self.client.get(
                "/api/graph/locations",
                params={"case_id": str(db.case.id)},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        get_locations.assert_called_once_with(None, case_id=str(db.case.id))

    def test_locations_needing_review_uses_case_read_authorization(self):
        membership = SimpleNamespace(
            permissions={"case": {"view": True, "edit": False}}
        )
        current_user = SimpleNamespace(
            id=uuid4(),
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb(membership=membership)
        self.app.dependency_overrides[graph.get_current_db_user] = lambda: current_user
        self.app.dependency_overrides[graph.get_db] = lambda: db
        payload = [
            {
                "key": "loc-1",
                "name": "Unknown warehouse",
                "type": "Location",
                "location_raw": "warehouse",
                "geocoding_status": "ambiguous",
                "geocoding_confidence": None,
                "manual_fields": [],
            }
        ]

        with patch.object(
            graph.neo4j_service,
            "get_locations_needing_review",
            return_value=payload,
        ) as get_locations:
            response = self.client.get(
                "/api/graph/locations/needs-review",
                params={"case_id": str(db.case.id)},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)
        get_locations.assert_called_once_with(case_id=str(db.case.id))

    def test_graph_mutation_rejects_a_view_only_member(self):
        membership = SimpleNamespace(
            permissions={"case": {"view": True, "edit": False}}
        )
        current_user = SimpleNamespace(
            id=uuid4(),
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb(membership=membership)
        self.app.dependency_overrides[graph.get_current_db_user] = lambda: current_user
        self.app.dependency_overrides[graph.get_db] = lambda: db

        with patch.object(graph.neo4j_service, "update_location") as update_location:
            response = self.client.put(
                "/api/graph/node/location-1/location",
                json={
                    "case_id": str(db.case.id),
                    "location_name": "Changed Place",
                    "latitude": 51.0,
                    "longitude": -6.0,
                },
            )

        self.assertEqual(response.status_code, 403)
        update_location.assert_not_called()

    def test_unsafe_legacy_graph_routes_are_not_registered(self):
        registered_paths = {route.path for route in graph.router.routes}

        self.assertTrue(
            {
                "/api/graph/load-case",
                "/api/graph/execute-single-query",
                "/api/graph/execute-batch-queries",
                "/api/graph/clear-graph",
                "/api/graph/last-graph",
            }.isdisjoint(registered_paths)
        )

    def test_relationship_analysis_is_registered_only_on_the_case_scoped_client_path(self):
        registered_paths = {route.path for route in graph.router.routes}

        self.assertIn(
            "/api/graph/node/{node_key}/analyze-relationships",
            registered_paths,
        )
        self.assertNotIn(
            "/api/graph/analyze-relationships/{node_key}",
            registered_paths,
        )


class FinancialAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(financial.router)
        self.client = TestClient(self.app)

    def test_financial_router_rejects_unauthenticated_reads(self):
        with patch.object(
            financial.neo4j_service,
            "get_financial_summary",
            return_value={},
        ):
            response = self.client.get(
                "/api/financial/summary",
                params={"case_id": "8c2d0ed8-4d19-4c45-b58b-bf0ec2de76e0"},
            )

        self.assertEqual(response.status_code, 401)

    def test_financial_read_rejects_an_authenticated_non_member(self):
        current_user = SimpleNamespace(
            id=uuid4(),
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb()
        self.app.dependency_overrides[get_current_db_user] = lambda: current_user
        self.app.dependency_overrides[get_db] = lambda: db

        with patch.object(
            financial.neo4j_service,
            "get_financial_summary",
            return_value={"total": 100},
        ) as get_summary:
            response = self.client.get(
                "/api/financial/summary",
                params={"case_id": str(db.case.id)},
            )

        self.assertEqual(response.status_code, 403)
        get_summary.assert_not_called()


class FilesystemAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(filesystem.router)
        self.client = TestClient(self.app)

    def test_filesystem_rejects_an_authenticated_non_member(self):
        current_user = SimpleNamespace(
            id=uuid4(),
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb()
        self.app.dependency_overrides[filesystem.get_current_user] = lambda: {
            "username": "nonmember@example.test"
        }
        self.app.dependency_overrides[get_current_db_user] = lambda: current_user
        self.app.dependency_overrides[get_db] = lambda: db

        with TemporaryDirectory() as root, patch.object(
            filesystem,
            "FILESYSTEM_ROOT",
            Path(root),
        ):
            response = self.client.get(
                "/api/filesystem/list",
                params={"case_id": str(db.case.id)},
            )

        self.assertEqual(response.status_code, 403)


class EvidenceAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(evidence.router)
        self.client = TestClient(self.app)

    def test_evidence_list_rejects_an_authenticated_non_member(self):
        current_user = SimpleNamespace(
            id=uuid4(),
            global_role="user",
            is_active=True,
        )
        db = _CaseAccessDb()
        self.app.dependency_overrides[evidence.get_current_user] = lambda: {
            "username": "nonmember@example.test"
        }
        self.app.dependency_overrides[get_current_db_user] = lambda: current_user
        self.app.dependency_overrides[get_db] = lambda: db

        with patch.object(
            evidence.EvidenceDBStorage,
            "list_files",
            return_value=[],
        ) as list_files:
            response = self.client.get(
                "/api/evidence",
                params={"case_id": str(db.case.id)},
            )

        self.assertEqual(response.status_code, 403)
        list_files.assert_not_called()

    def test_evidence_object_read_uses_the_records_actual_case(self):
        evidence_id = uuid4()
        current_user = SimpleNamespace(
            id=uuid4(),
            global_role="user",
            is_active=True,
        )
        record = SimpleNamespace(
            id=evidence_id,
            case_id=uuid4(),
            original_filename="secret.pdf",
        )
        db = _CaseAccessDb(records={evidence_id: record})
        self.app.dependency_overrides[get_current_db_user] = lambda: current_user
        self.app.dependency_overrides[get_db] = lambda: db

        with patch.object(evidence.neo4j_service, "run_cypher") as run_cypher:
            response = self.client.get(f"/api/evidence/{evidence_id}/entities")

        self.assertEqual(response.status_code, 403)
        run_cypher.assert_not_called()


class UserDirectoryAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(users_router.router)
        self.client = TestClient(self.app)

    def test_user_directory_rejects_unauthenticated_requests(self):
        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = []
        db = MagicMock()
        db.query.return_value = query
        self.app.dependency_overrides[get_db] = lambda: db

        response = self.client.get("/api/users")

        self.assertEqual(response.status_code, 401)
        db.query.assert_not_called()

    def test_user_directory_rejects_an_authenticated_non_admin(self):
        current_user = SimpleNamespace(
            id=uuid4(),
            global_role="user",
            is_active=True,
        )
        self.app.dependency_overrides[get_current_db_user] = lambda: current_user

        response = self.client.get("/api/users")

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
