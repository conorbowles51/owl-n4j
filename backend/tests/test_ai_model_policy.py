import unittest

from models.llm_models import AVAILABLE_MODELS, LLMProvider, get_default_model, get_model_by_id
from services.ai_model_policy import DEFAULT_POLICY, PROVIDER_DEFAULTS, validate_policy


class AIModelPolicyTests(unittest.TestCase):
    def test_current_openai_models_are_available(self):
        self.assertIsNotNone(get_model_by_id("gpt-5.6-sol"))
        self.assertIsNotNone(get_model_by_id("gpt-5.6-terra"))
        self.assertIsNotNone(get_model_by_id("gpt-5.6-luna"))
        self.assertEqual(get_default_model(LLMProvider.OPENAI).id, "gpt-5.6-terra")

    def test_default_policy_uses_quality_model_for_document_synthesis(self):
        self.assertEqual(
            DEFAULT_POLICY["ingestion_document_summary"]["model_id"],
            "gpt-5.6-sol",
        )
        self.assertEqual(DEFAULT_POLICY["chat"]["model_id"], "gpt-5.6-terra")

    def test_policy_rejects_provider_model_mismatch(self):
        configuration = {key: dict(value) for key, value in DEFAULT_POLICY.items()}
        configuration["chat"] = {
            "provider": "anthropic",
            "model_id": "gpt-5.6-terra",
        }
        with self.assertRaisesRegex(ValueError, "does not belong"):
            validate_policy(configuration)

    def test_ollama_is_not_a_selectable_generative_provider(self):
        self.assertNotIn("ollama", {provider.value for provider in LLMProvider})
        self.assertNotIn("ollama", {model.provider.value for model in AVAILABLE_MODELS})

    def test_each_cloud_provider_has_a_complete_recommended_profile(self):
        self.assertEqual(set(PROVIDER_DEFAULTS), {"openai", "anthropic", "gemini"})
        for configuration in PROVIDER_DEFAULTS.values():
            self.assertEqual(set(configuration), set(DEFAULT_POLICY))
            validate_policy(configuration, require_configured_provider=False)


if __name__ == "__main__":
    unittest.main()
