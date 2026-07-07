import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import admin_update
from services.platform_update_service import PlatformUpdateError


class StubUpdateService:
    def __init__(self):
        self.deployed_by = None

    def get_status(self):
        return self._status()

    def refresh_status(self):
        return {**self._status(), "last_checked_at": "2026-07-07T12:00:00+00:00"}

    def trigger_deploy(self, *, requested_by):
        self.deployed_by = requested_by
        return {**self._status(), "deployment_status": "running", "deployment_running": True}

    @staticmethod
    def _status():
        return {
            "enabled": True,
            "configured": True,
            "config_error": None,
            "can_deploy": True,
            "repo_dir": "/opt/owl-n4j",
            "remote": "origin",
            "branch": "main",
            "service_name": "owl-self-update.service",
            "local_sha": "a" * 40,
            "local_short_sha": "aaaaaaaa",
            "remote_sha": "b" * 40,
            "remote_short_sha": "bbbbbbbb",
            "update_available": True,
            "last_checked_at": None,
            "last_check_error": None,
            "deployment_running": False,
            "deployment_status": "idle",
            "deployment_error": None,
            "deployment_started_at": None,
            "deployment_completed_at": None,
            "last_deploy_requested_by": None,
            "deploy_log_path": None,
            "deploy_log_tail": None,
        }


class UserStub:
    email = "admin@example.com"
    name = "Admin"
    id = "user-1"


class AdminUpdateRouterTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(admin_update.router)
        self.client = TestClient(self.app)
        self.service = StubUpdateService()
        self.original_service = admin_update.platform_update_service
        admin_update.platform_update_service = self.service

        self.app.dependency_overrides[admin_update.require_admin] = lambda: UserStub()

    def tearDown(self):
        admin_update.platform_update_service = self.original_service
        self.app.dependency_overrides.clear()

    def test_status_requires_admin(self):
        self.app.dependency_overrides[admin_update.require_admin] = lambda: (_ for _ in ()).throw(
            HTTPException(status_code=403, detail="Admin privileges required")
        )

        response = self.client.get("/api/admin/update/status")

        self.assertEqual(response.status_code, 403)

    def test_status_returns_update_state(self):
        response = self.client.get("/api/admin/update/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["update_available"])
        self.assertEqual(body["local_short_sha"], "aaaaaaaa")

    def test_check_refreshes_update_state(self):
        response = self.client.post("/api/admin/update/check")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["last_checked_at"], "2026-07-07T12:00:00+00:00")

    def test_deploy_uses_current_admin_identity(self):
        response = self.client.post("/api/admin/update/deploy")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.service.deployed_by, "admin@example.com")
        self.assertEqual(response.json()["deployment_status"], "running")

    def test_deploy_error_maps_to_http_response(self):
        class RejectingService(StubUpdateService):
            def trigger_deploy(self, *, requested_by):
                raise PlatformUpdateError("Update service is not configured", status_code=409)

        admin_update.platform_update_service = RejectingService()

        response = self.client.post("/api/admin/update/deploy")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "Update service is not configured")


if __name__ == "__main__":
    unittest.main()
