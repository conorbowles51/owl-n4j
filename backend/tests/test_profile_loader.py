import unittest

import profile_loader


class ProfileLoaderTests(unittest.TestCase):
    def test_load_profile_uses_plain_postgres_snapshot(self):
        original = profile_loader._load_postgres_profile
        profile_loader._load_postgres_profile = lambda name: {
            "name": name,
            "description": "Runtime profile",
            "context_instructions": "Extract carefully.",
            "mandatory_instructions": ["Preserve dates"],
            "special_entity_types": [{"name": "Vessel"}],
            "chat_config": {
                "system_context": "Answer as an investigator.",
                "analysis_guidance": "Cite sources.",
            },
            "llm_config": {"model": "gpt-5-mini"},
            "folder_processing": {"mode": "deep"},
        }
        try:
            profile = profile_loader.load_profile("runtime")
        finally:
            profile_loader._load_postgres_profile = original

        self.assertEqual(profile["name"], "runtime")
        self.assertEqual(profile["description"], "Runtime profile")
        self.assertEqual(profile["ingestion"]["system_context"], "Extract carefully.")
        self.assertEqual(profile["ingestion"]["mandatory_instructions"], ["Preserve dates"])
        self.assertEqual(profile["ingestion"]["special_entity_types"], [{"name": "Vessel"}])
        self.assertEqual(profile["chat"]["system_context"], "Answer as an investigator.")
        self.assertEqual(profile["chat"]["analysis_guidance"], "Cite sources.")
        self.assertEqual(profile["llm_config"], {"model": "gpt-5-mini"})
        self.assertEqual(profile["folder_processing"], {"mode": "deep"})


if __name__ == "__main__":
    unittest.main()
