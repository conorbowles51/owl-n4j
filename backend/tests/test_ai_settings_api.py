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
from routers.ai_settings import router, validate_provider_credential
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
        self.assertEqual(
            [item["id"] for item in payload["providers"]],
            ["openai", "anthropic", "gemini", "deepseek"],
        )
        self.assertNotIn("ollama", response.text.lower())
        self.assertNotIn("api_key", response.text)

    def test_page_image_chain_and_which_models_read_images(self):
        from services import ai_model_capabilities as cap
        cap.clear_cache()
        self.addCleanup(cap.clear_cache)
        listed = {"deepseek-flash": {"text", "image"}, "deepseek-v4-pro": {"text"}}
        from dataclasses import replace
        from services.ai_provider_credentials import credential_store as store
        real = store.list_connections

        def connected(db):  # OpenAI and DeepSeek connected
            return [replace(c, configured=c.provider in ("openai", "deepseek")) for c in real(db)]
        with patch.object(cap, "_fetch_deepseek", return_value=listed), \
                patch("services.ai_provider_credentials.get_provider_api_key", return_value="k"), \
                patch("routers.ai_settings.credential_store.list_connections", side_effect=connected):
            payload = self.client.get("/api/ai-settings").json()
        reads = {m["id"]: m["reads_images"] for m in payload["models"]}
        self.assertTrue(reads["deepseek-flash"])
        self.assertFalse(reads["deepseek-v4-pro"])
        self.assertTrue(reads["gpt-5.6-terra"])
        self.assertFalse(any(reads[m["id"]] for m in payload["models"] if m["provider"] in ("anthropic", "gemini")))
        chain = payload["routing"]["financial_vision"]["chain"]
        self.assertEqual([e["provider"] for e in chain], ["deepseek", "openai"])
        # The chain workload does not turn a one-provider profile into a mix.
        self.assertEqual(payload["default_provider"], "openai")

    def test_deepseek_only_switch_is_on_by_default_and_switching_it_is_recorded(self):
        from services import ai_model_capabilities as cap
        cap.clear_cache()
        self.addCleanup(cap.clear_cache)
        listed = {"deepseek-flash": {"text", "image"}, "deepseek-v4-pro": {"text"}}
        with patch.object(cap, "_fetch_deepseek", return_value=listed), \
                patch("services.ai_provider_credentials.get_provider_api_key", return_value="k"), \
                patch("services.ai_model_policy.provider_is_configured", return_value=True):
            payload = self.client.get("/api/ai-settings").json()
            vision = payload["routing"]["financial_vision"]
            self.assertIs(vision["deepseek_only"], True)
            configuration = {k: {"provider": v["provider"], "model_id": v["model_id"]} for k, v in payload["routing"].items()}
            configuration["financial_vision"] = {**configuration["financial_vision"], "chain": vision["chain"],
                                                 "deepseek_only": False}
            response = self.client.put("/api/ai-settings/policy",
                                       json={"revision": payload["policy_revision"], "configuration": configuration})
            self.assertEqual(response.status_code, 200, response.text)
            switched = response.json()["routing"]["financial_vision"]
            self.assertIs(switched["deepseek_only"], False)
            self.assertEqual(switched["deepseek_only_changed_by"], "root@example.test")
            self.assertTrue(switched["deepseek_only_changed_at"])
            # A later save that does not name the switch keeps it, and who switched it.
            configuration["financial_vision"].pop("deepseek_only")
            response = self.client.put("/api/ai-settings/policy",
                                       json={"revision": response.json()["policy_revision"], "configuration": configuration})
            kept = response.json()["routing"]["financial_vision"]
            self.assertIs(kept["deepseek_only"], False)
            self.assertEqual(kept["deepseek_only_changed_at"], switched["deepseek_only_changed_at"])
        logged = [row.action for row in self.db.query(SystemLog).all()]
        self.assertEqual([a for a in logged if "DeepSeek only" in a], ["Statement page images: DeepSeek only switched OFF"])

    @patch("routers.ai_settings.requests.get")
    def test_deepseek_key_validation_uses_official_model_catalog(self, get):
        response = get.return_value
        response.status_code = 200
        response.json.return_value = {
            "data": [{"id": "deepseek-v4-flash"}, {"id": "deepseek-v4-pro"}]
        }

        result = validate_provider_credential("deepseek", "sk-test")

        self.assertEqual(
            result["models"],
            ["deepseek-v4-flash", "deepseek-v4-pro"],
        )
        self.assertEqual(get.call_args.args[0], "https://api.deepseek.com/models")
        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"],
            "Bearer sk-test",
        )

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
