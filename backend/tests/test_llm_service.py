import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from services.llm_service import LLMExecutionContext


class LLMExecutionContextTests(unittest.TestCase):
    def test_gpt5_uses_responses_api_when_chat_opts_in(self):
        responses = Mock()
        responses.create.return_value = SimpleNamespace(
            output_text="GPT-5 answer",
            usage=SimpleNamespace(
                input_tokens=11,
                output_tokens=7,
                total_tokens=18,
            ),
        )
        fake_client = SimpleNamespace(
            responses=responses,
            chat=SimpleNamespace(completions=SimpleNamespace(create=Mock())),
        )
        context = LLMExecutionContext(
            provider="openai",
            model_id="gpt-5-mini",
            use_responses_api_for_gpt5=True,
        )

        with patch("services.llm_service.client", fake_client):
            answer = context.call("Return JSON", json_mode=True)

        self.assertEqual(answer, "GPT-5 answer")
        responses.create.assert_called_once()
        kwargs = responses.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-5-mini")
        self.assertEqual(kwargs["input"], "Return JSON")
        self.assertEqual(kwargs["instructions"], context.system_context)
        self.assertEqual(kwargs["text"], {"format": {"type": "json_object"}})
        self.assertFalse(kwargs["store"])
        self.assertNotIn("temperature", kwargs)
        fake_client.chat.completions.create.assert_not_called()
        self.assertEqual(
            context.last_usage,
            {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "total_tokens": 18,
            },
        )

    def test_gpt5_defaults_to_existing_chat_completions_path(self):
        chat_create = Mock(
            return_value=SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="Legacy answer"))
                ],
                usage=SimpleNamespace(
                    prompt_tokens=2,
                    completion_tokens=3,
                    total_tokens=5,
                ),
            )
        )
        fake_client = SimpleNamespace(
            responses=SimpleNamespace(create=Mock()),
            chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
        )
        context = LLMExecutionContext(provider="openai", model_id="gpt-5-mini")

        with patch("services.llm_service.client", fake_client):
            answer = context.call("Question", temperature=0.2)

        self.assertEqual(answer, "Legacy answer")
        chat_create.assert_called_once()
        kwargs = chat_create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-5-mini")
        self.assertNotIn("temperature", kwargs)
        fake_client.responses.create.assert_not_called()

    def test_non_gpt5_openai_models_keep_chat_completions(self):
        chat_create = Mock(
            return_value=SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content="GPT-4o answer"))
                ],
                usage=SimpleNamespace(
                    prompt_tokens=5,
                    completion_tokens=6,
                    total_tokens=11,
                ),
            )
        )
        fake_client = SimpleNamespace(
            responses=SimpleNamespace(create=Mock()),
            chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
        )
        context = LLMExecutionContext(provider="openai", model_id="gpt-4o")

        with patch("services.llm_service.client", fake_client):
            answer = context.call("Question", temperature=0.2)

        self.assertEqual(answer, "GPT-4o answer")
        chat_create.assert_called_once()
        kwargs = chat_create.call_args.kwargs
        self.assertEqual(kwargs["model"], "gpt-4o")
        self.assertEqual(kwargs["temperature"], 0.2)
        fake_client.responses.create.assert_not_called()
        self.assertEqual(
            context.last_usage,
            {
                "prompt_tokens": 5,
                "completion_tokens": 6,
                "total_tokens": 11,
            },
        )


if __name__ == "__main__":
    unittest.main()
