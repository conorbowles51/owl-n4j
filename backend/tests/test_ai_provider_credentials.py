import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.runtime_state import AIProviderCredential
from services.ai_provider_credentials import (
    AIProviderCredentialStore,
    CredentialRevisionConflict,
)


class AIProviderCredentialStoreTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        AIProviderCredential.__table__.create(engine)
        self.Session = sessionmaker(bind=engine, future=True)
        self.store = AIProviderCredentialStore(
            encryption_key="unit-test-only-master-key",
            environment_keys={"openai": "sk-environment"},
        )

    def test_saved_key_is_encrypted_and_can_be_resolved(self):
        with self.Session() as db:
            connection = self.store.save(
                db,
                provider="anthropic",
                api_key="sk-ant-secret-value",
                expected_revision=0,
                updated_by="admin@example.test",
            )
            record = db.get(AIProviderCredential, "anthropic")

            self.assertEqual(connection.status, "connected")
            self.assertEqual(connection.key_last_four, "alue")
            self.assertNotIn("sk-ant-secret-value", record.encrypted_api_key)
            self.assertEqual(
                self.store.get_api_key(db, "anthropic"),
                "sk-ant-secret-value",
            )

    def test_explicit_disconnect_prevents_environment_key_from_returning(self):
        with self.Session() as db:
            self.assertEqual(self.store.get_api_key(db, "openai"), "sk-environment")
            self.store.disconnect(
                db,
                provider="openai",
                expected_revision=0,
                updated_by="admin@example.test",
            )
            self.assertIsNone(self.store.get_api_key(db, "openai"))
            self.assertEqual(self.store.get_connection(db, "openai").status, "disconnected")

    def test_stale_revision_does_not_replace_a_working_key(self):
        with self.Session() as db:
            self.store.save(
                db,
                provider="gemini",
                api_key="first-secret",
                expected_revision=0,
                updated_by="admin@example.test",
            )
            with self.assertRaises(CredentialRevisionConflict):
                self.store.save(
                    db,
                    provider="gemini",
                    api_key="second-secret",
                    expected_revision=0,
                    updated_by="other@example.test",
                )
            self.assertEqual(self.store.get_api_key(db, "gemini"), "first-secret")


if __name__ == "__main__":
    unittest.main()
