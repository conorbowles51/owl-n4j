import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from postgres.models.enums import GlobalRole
from postgres.models.runtime_state import AIModelPolicy, AIProviderCredential, SystemLog
from postgres.models.user import User
from postgres.session import get_db
from routers.ai_settings import router
from routers.users import get_current_db_user, require_super_admin


class AISettingsAPITests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        for table in (AIModelPolicy.__table__, AIProviderCredential.__table__, SystemLog.__table__):
            table.create(engine)
        self.Session = sessionmaker(bind=engine, future=True)
        self.db = self.Session()
        self.user = User(
            email="root@example.test",
            name="Root",
            password_hash="unused",
            global_role=GlobalRole.super_admin,
            is_active=True,
        )
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_db_user] = lambda: self.user
        app.dependency_overrides[require_super_admin] = lambda: self.user
        self.client = TestClient(app)

    def tearDown(self):
        self.db.close()

    def test_settings_never_expose_ollama_or_plaintext_credentials(self):
        response = self.client.get("/api/ai-settings")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([item["id"] for item in payload["providers"]], ["openai", "anthropic", "gemini"])
        self.assertNotIn("ollama", response.text.lower())
        self.assertNotIn("api_key", response.text)

    @patch("routers.ai_settings.validate_provider_credential")
    def test_super_admin_can_save_a_validated_masked_key(self, validate):
        validate.return_value = {"models": ["claude-sonnet-5"]}
        response = self.client.put(
            "/api/ai-settings/providers/anthropic/credential",
            json={"api_key": "sk-ant-secret-value", "expected_revision": 0},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["key_last_four"], "alue")
        self.assertNotIn("sk-ant-secret-value", response.text)


if __name__ == "__main__":
    unittest.main()
