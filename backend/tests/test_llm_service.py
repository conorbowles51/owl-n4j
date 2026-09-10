import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from services.llm_service import LLMExecutionContext


class LLMExecutionContextTests(unittest.TestCase):
    def test_transport_record_retains_provider_json_instruction_without_credentials(self):
        response = Mock()
        response.json.return_value = {'model':'reported-revision', 'id':'synthetic-response',
            'content':[{'type':'text','text':'{}'}], 'usage':{}}
        context = LLMExecutionContext(provider='anthropic', model_id='synthetic-model', api_key='private-test-key')
        with patch('services.llm_service.requests.post', return_value=response) as post:
            context.call('Original source', json_mode=True)
        sent = post.call_args.kwargs['json']
        self.assertEqual(context.last_request_arguments, sent)
        self.assertIn('Return only one valid JSON object', context.last_request_arguments['messages'][0]['content'])
        self.assertNotIn('private-test-key', str(context.last_request_arguments))
        self.assertEqual(context.last_response_metadata, {'reported_model':'reported-revision','response_id':'synthetic-response'})
        sent['messages'][0]['content'] = 'Changed after request'
        self.assertNotEqual(context.last_request_arguments['messages'][0]['content'], sent['messages'][0]['content'])
        context.provider = 'invalid'
        with self.assertRaises(ValueError): context.call('Next call')
        self.assertIsNone(context.last_request_arguments)
        self.assertEqual(context.last_response_metadata, {})

    def test_sdk_reported_model_is_recorded_separately_from_requested_model(self):
        response = SimpleNamespace(model='provider-reported-revision', id='synthetic-response',
            choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))], usage=None)
        create = Mock(return_value=response)
        context = LLMExecutionContext(provider='openai', model_id='requested-model')
        with patch('services.llm_service.client', SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))):
            context.call('Synthetic prompt', json_mode=True)
        self.assertEqual(context.last_request_arguments, create.call_args.kwargs)
        self.assertEqual(context.last_request_arguments['model'], 'requested-model')
        self.assertEqual(context.last_response_metadata['reported_model'], 'provider-reported-revision')

    def test_request_context_uses_runtime_credential_instead_of_startup_environment(self):
        fake_client = SimpleNamespace(
            responses=SimpleNamespace(
                create=Mock(
                    return_value=SimpleNamespace(output_text="Runtime answer", usage=None)
                )
            ),
            chat=SimpleNamespace(completions=SimpleNamespace(create=Mock())),
        )
        with patch("services.llm_service.OpenAI", return_value=fake_client) as factory:
            context = LLMExecutionContext(
                provider="openai",
                model_id="gpt-5.6-terra",
                api_key="database-key",
                use_responses_api_for_gpt5=True,
            )
            answer = context.call("Question")

        self.assertEqual(answer, "Runtime answer")
        factory.assert_called_once_with(api_key="database-key")

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

    def test_anthropic_messages_adapter_normalizes_content_and_usage(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "content": [{"type": "text", "text": '{"ok":true}'}],
            "usage": {"input_tokens": 12, "output_tokens": 4},
        }
        context = LLMExecutionContext(
            provider="anthropic",
            model_id="claude-sonnet-5",
        )

        with (
            patch("services.llm_service.ANTHROPIC_API_KEY", "test-key"),
            patch("services.llm_service.requests.post", return_value=response) as post,
        ):
            answer = context.call("Return JSON", json_mode=True, temperature=0.2)

        self.assertEqual(answer, '{"ok":true}')
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "claude-sonnet-5")
        self.assertNotIn("temperature", payload)
        self.assertIn("Return only one valid JSON object", payload["messages"][0]["content"])
        self.assertEqual(
            context.last_usage,
            {"prompt_tokens": 12, "completion_tokens": 4, "total_tokens": 16},
        )

    def test_gemini_adapter_uses_json_mime_type_without_unsupported_temperature(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}],
            "usageMetadata": {
                "promptTokenCount": 9,
                "candidatesTokenCount": 3,
                "totalTokenCount": 12,
            },
        }
        context = LLMExecutionContext(
            provider="gemini",
            model_id="gemini-3.5-flash",
        )

        with (
            patch("services.llm_service.GEMINI_API_KEY", "test-key"),
            patch("services.llm_service.requests.post", return_value=response) as post,
        ):
            answer = context.call("Return JSON", json_mode=True, temperature=0.2)

        self.assertEqual(answer, '{"ok":true}')
        payload = post.call_args.kwargs["json"]
        self.assertEqual(
            payload["generationConfig"],
            {"responseMimeType": "application/json"},
        )
        self.assertEqual(
            context.last_usage,
            {"prompt_tokens": 9, "completion_tokens": 3, "total_tokens": 12},
        )

    def test_deepseek_adapter_uses_current_endpoint_and_json_mode(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [{"message": {"content": '{"ok":true}'}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "total_tokens": 12,
            },
        }
        context = LLMExecutionContext(
            provider="deepseek",
            model_id="deepseek-v4-flash",
        )

        with (
            patch("services.llm_service.DEEPSEEK_API_KEY", "test-key"),
            patch("services.llm_service.requests.post", return_value=response) as post,
        ):
            answer = context.call("Return JSON", json_mode=True, temperature=0.2)

        self.assertEqual(answer, '{"ok":true}')
        self.assertEqual(post.call_args.args[0], "https://api.deepseek.com/chat/completions")
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "deepseek-v4-flash")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(
            context.last_usage,
            {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
        )


if __name__ == "__main__":
    unittest.main()
