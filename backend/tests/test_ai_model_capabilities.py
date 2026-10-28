"""Page images only go to a model that takes images (services/ai_model_capabilities), in every image path."""
import json
import unittest
from unittest import mock

from services import ai_model_capabilities as cap
from services.ai_model_policy import DEFAULT_POLICY, validate_policy

# GET https://api.deepseek.com/models on Loupe's key, 2026-10-28 (the account's two models).
DEEPSEEK_LIST = {'deepseek-flash': {'text', 'image'}, 'deepseek-v4-pro': {'text'}}


def listed(_api_key):
    return {k: set(v) for k, v in DEEPSEEK_LIST.items()}


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        cap.clear_cache()
        self.addCleanup(cap.clear_cache)

    def test_text_only_deepseek_model_is_refused(self):
        ok, why = cap.accepts_images('deepseek', 'deepseek-v4-pro', api_key='k', fetch=listed)
        self.assertFalse(ok)
        self.assertIn('text', why)
        with self.assertLogs('services.ai_model_capabilities', 'WARNING') as logs, \
                self.assertRaisesRegex(cap.ModelCannotReadImages, cap.CANNOT_READ_IMAGES):
            cap.require_images('deepseek', 'deepseek-v4-pro', api_key='k', fetch=listed)
        self.assertIn(cap.CANNOT_READ_IMAGES, logs.output[0])

    def test_image_models_are_allowed(self):
        self.assertEqual(cap.accepts_images('deepseek', 'deepseek-flash', api_key='k', fetch=listed), (True, ''))
        self.assertEqual(cap.accepts_images('openai', 'gpt-5.6-terra'), (True, ''))
        self.assertEqual(cap.accepts_images('openai', 'gpt-4o'), (True, ''))

    def test_unknown_or_unlisted_models_are_refused(self):
        self.assertFalse(cap.accepts_images('openai', 'gpt-9-new')[0])
        self.assertFalse(cap.accepts_images('deepseek', 'deepseek-v9', api_key='k', fetch=listed)[0])
        self.assertFalse(cap.accepts_images('anthropic', 'claude-sonnet-5')[0])
        self.assertFalse(cap.accepts_images('', '')[0])

    def test_model_list_without_modalities_is_not_permission(self):
        ok, _ = cap.accepts_images('deepseek', 'deepseek-flash', api_key='k', fetch=lambda key: {'deepseek-flash': set()})
        self.assertFalse(ok)

    def test_unreachable_list_fails_closed_and_stale_list_expires(self):
        def down(_key):
            raise ConnectionError('no route')
        self.assertFalse(cap.accepts_images('deepseek', 'deepseek-flash', api_key='k', fetch=down, now=1000)[0])
        # A list fetched once is used for a day, then refreshed; if the refresh fails it is used up to two days.
        self.assertTrue(cap.accepts_images('deepseek', 'deepseek-flash', api_key='k', fetch=listed, now=1000)[0])
        calls = []
        self.assertTrue(cap.accepts_images('deepseek', 'deepseek-flash', api_key='k',
                                           fetch=lambda key: calls.append(1) or listed(key), now=1000 + 3600)[0])
        self.assertEqual(calls, [])
        with self.assertLogs('services.ai_model_capabilities', 'WARNING'):
            self.assertTrue(cap.accepts_images('deepseek', 'deepseek-flash', api_key='k', fetch=down,
                                               now=1000 + cap.REFRESH_SECONDS + 1)[0])
        with self.assertLogs('services.ai_model_capabilities', 'WARNING'):
            self.assertFalse(cap.accepts_images('deepseek', 'deepseek-flash', api_key='k', fetch=down,
                                                now=1000 + cap.STALE_SECONDS + 1)[0])

    def test_the_list_is_read_from_the_provider(self):
        response = mock.Mock()
        response.json.return_value = {'data': [{'id': 'deepseek-flash', 'input_modalities': ['text', 'image']},
                                               {'id': 'deepseek-v4-pro', 'input_modalities': ['text']},
                                               {'id': 'other'}]}
        with mock.patch('requests.get', return_value=response) as get:
            models = cap._fetch_deepseek('secret')
        self.assertEqual(get.call_args.args[0], cap.DEEPSEEK_MODELS_URL)
        self.assertEqual(get.call_args.kwargs['headers'], {'Authorization': 'Bearer secret'})
        self.assertEqual(models, {'deepseek-flash': {'text', 'image'}, 'deepseek-v4-pro': {'text'}, 'other': set()})


class ImagePathTests(unittest.TestCase):
    """Both image-sending places refuse before anything is sent."""

    def setUp(self):
        cap.clear_cache()
        self.addCleanup(cap.clear_cache)
        patcher = mock.patch.object(cap, '_fetch_deepseek', side_effect=listed)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_vision_call_never_sends_to_a_text_only_model(self):
        from services.llm_service import LLMExecutionContext
        context = LLMExecutionContext('deepseek', 'deepseek-v4-pro', api_key='k')
        with mock.patch('requests.post') as post, self.assertLogs('services.ai_model_capabilities', 'WARNING'), \
                self.assertRaisesRegex(cap.ModelCannotReadImages, cap.CANNOT_READ_IMAGES):
            context.call_vision_json('p', [b'png'], schema={'type': 'object'}, schema_name='s')
        post.assert_not_called()
        with mock.patch.object(context, '_client') as client, self.assertLogs('services.ai_model_capabilities', 'WARNING'), \
                self.assertRaises(cap.ModelCannotReadImages):
            LLMExecutionContext('openai', 'gpt-9-new', api_key='k').call_vision_json('p', [b'png'], schema={}, schema_name='s')
        client.chat.completions.create.assert_not_called()

    def test_vision_call_to_deepseek_image_model_states_the_schema_and_uses_max_thinking(self):
        from services.llm_service import LLMExecutionContext
        answer = {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok": true}'}}],
                  'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}
        response = mock.Mock()
        # Streamed in pieces, with a keep-alive blank line first (read against a deadline).
        response.iter_content.side_effect = lambda chunk_size: iter([b'\n', json.dumps(answer).encode()])
        context = LLMExecutionContext('deepseek', 'deepseek-flash', api_key='k')
        with mock.patch('requests.post', return_value=response) as post:
            self.assertEqual(json.loads(context.call_vision_json('p', [b'png'], schema={'type': 'object'},
                                                                 schema_name='s')), {'ok': True})
        sent = post.call_args.kwargs['json']
        self.assertEqual(sent['model'], 'deepseek-flash')
        self.assertEqual(sent['thinking'], {'type': 'enabled'})
        self.assertEqual(sent['reasoning_effort'], 'max')
        self.assertEqual(sent['response_format'], {'type': 'json_object'})
        self.assertIn('{"type":"object"}', sent['messages'][0]['content'][0]['text'])
        self.assertEqual(sent['messages'][0]['content'][1]['type'], 'image_url')
        self.assertNotIn('png', json.dumps(context.last_request_arguments))
        self.assertTrue(post.call_args.kwargs['stream'])
        answer['choices'][0]['finish_reason'] = 'length'
        context.last_usage = None
        with mock.patch('requests.post', return_value=response), self.assertRaisesRegex(ValueError, 'incomplete'):
            context.call_vision_json('p', [b'png'], schema={}, schema_name='s')
        # An answer cut short is billed: its usage is kept for the caller to record.
        self.assertEqual(context.last_usage['completion_tokens'], 5)

    def test_deepseek_answer_is_bounded_by_the_clock_not_by_keep_alive_lines(self):
        from services.llm_service import LLMExecutionContext
        import services.llm_service as llm
        response = mock.Mock()
        response.iter_content.side_effect = lambda chunk_size: iter([b'\n'] * 5)
        clock = iter([0, 1, 2, 50, 100, 200, 300])
        context = LLMExecutionContext('deepseek', 'deepseek-flash', api_key='k')
        with mock.patch('requests.post', return_value=response), \
                mock.patch.object(llm.time, 'monotonic', lambda: next(clock)), \
                self.assertRaises(llm.requests.exceptions.ReadTimeout):
            context._call_deepseek_vision('p', [b'png'], schema={}, timeout=60, max_output_tokens=10)
        response.close.assert_called()

    def test_page_reader_holds_the_statement_when_the_setting_is_text_only(self):
        from services.financial import vision_reader as vr
        chain = [{'provider': 'deepseek', 'model_id': 'deepseek-v4-pro'}]
        with mock.patch('services.ai_model_policy.get_workload_chain', return_value=chain), \
                mock.patch('services.ai_model_policy.deepseek_only', return_value=False), \
                mock.patch('services.ai_provider_credentials.get_provider_api_key', return_value='k'), \
                mock.patch.object(vr, 'render_pages') as render, \
                self.assertLogs('services.ai_model_capabilities', 'WARNING'):
            readers = vr.chain_page_reader(object(), 'case')
            with self.assertRaisesRegex(RuntimeError, cap.CANNOT_READ_IMAGES):
                vr.deepseek_page_reader(object(), 'case')
        self.assertIsNone(readers[0].read)
        self.assertIn(cap.CANNOT_READ_IMAGES, readers[0].unavailable)
        render.assert_not_called()
        chain = [{'provider': 'deepseek', 'model_id': 'deepseek-flash'}, {'provider': 'openai', 'model_id': 'gpt-5.6-terra'}]
        with mock.patch('services.ai_model_policy.get_workload_chain', return_value=chain), \
                mock.patch('services.ai_model_policy.deepseek_only', return_value=False), \
                mock.patch('services.ai_provider_credentials.get_provider_api_key', return_value='k'):
            readers = vr.chain_page_reader(object(), 'case')
            model_id, read = vr.deepseek_page_reader(object(), 'case')
        self.assertEqual([(r.provider, r.model, r.unavailable) for r in readers],
                         [('deepseek', 'deepseek-flash', ''), ('openai', 'gpt-5.6-terra', '')])
        self.assertEqual(model_id, 'deepseek-flash')
        self.assertTrue(callable(read) and all(callable(r.read) for r in readers))

    def test_unknown_model_is_refused_in_the_chain(self):
        from services.financial import vision_reader as vr
        chain = [{'provider': 'openai', 'model_id': 'gpt-9-new'}]
        with mock.patch('services.ai_model_policy.get_workload_chain', return_value=chain), \
                mock.patch('services.ai_model_policy.deepseek_only', return_value=False), \
                mock.patch('services.ai_provider_credentials.get_provider_api_key', return_value='k'), \
                self.assertLogs('services.ai_model_capabilities', 'WARNING'):
            readers = vr.chain_page_reader(object(), 'case')
        self.assertIn(cap.CANNOT_READ_IMAGES, readers[0].unavailable)

    def test_held_statement_records_the_reason(self):
        """vision_reader turns a page reader that raises into 'unavailable' with the error as the message."""
        from services.financial import vision_reader as vr
        from pathlib import Path
        source = Path(vr.__file__).read_text()
        self.assertIn("return dict(record, status='unavailable', reason='unavailable', message=str(error)[:300])", source)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        cap.clear_cache()
        self.addCleanup(cap.clear_cache)
        patcher = mock.patch.object(cap, '_fetch_deepseek', side_effect=listed)
        patcher.start()
        self.addCleanup(patcher.stop)

    def policy(self, provider, model_id):
        configuration = {key: dict(value) for key, value in DEFAULT_POLICY.items()}
        configuration['financial_vision'] = {'provider': provider, 'model_id': model_id}
        return configuration

    def test_text_only_model_cannot_be_set_for_page_images(self):
        with mock.patch('services.ai_model_policy.DEEPSEEK_API_KEY', 'k'), \
                self.assertRaisesRegex(ValueError, 'cannot read page images'):
            validate_policy(self.policy('deepseek', 'deepseek-v4-pro'), require_configured_provider=False)

    def test_default_chain_saves_when_deepseeks_list_is_down_but_a_text_only_model_never_does(self):
        cap.clear_cache()
        configuration = {key: dict(value) for key, value in DEFAULT_POLICY.items()}
        with mock.patch.object(cap, '_fetch_deepseek', return_value=None), \
                mock.patch('services.ai_model_policy.DEEPSEEK_API_KEY', 'k'), \
                self.assertLogs('services.ai_model_policy', 'WARNING'):
            validated = validate_policy(configuration, require_configured_provider=False)
        self.assertEqual(validated['financial_vision']['chain'][0]['model_id'], 'deepseek-flash')
        cap.clear_cache()
        with mock.patch('services.ai_model_policy.DEEPSEEK_API_KEY', 'k'), \
                self.assertRaisesRegex(ValueError, 'cannot read page images'):
            validate_policy(self.chain(('deepseek', 'deepseek-flash'), ('deepseek', 'deepseek-v4-pro')),
                            require_configured_provider=False)

    def test_deepseek_only_needs_a_deepseek_model_in_the_chain(self):
        configuration = self.chain(('openai', 'gpt-5.6-terra'))
        with self.assertRaisesRegex(ValueError, 'DeepSeek only is on'):
            validate_policy(configuration, require_configured_provider=False)
        configuration['financial_vision']['deepseek_only'] = False
        validate_policy(configuration, require_configured_provider=False)

    def test_text_only_model_stays_allowed_for_text_workloads(self):
        configuration = {key: dict(value) for key, value in DEFAULT_POLICY.items()}
        configuration['chat'] = {'provider': 'deepseek', 'model_id': 'deepseek-v4-pro'}
        with mock.patch('services.ai_model_policy.DEEPSEEK_API_KEY', 'k'):
            validate_policy(configuration, require_configured_provider=False)

    def test_image_models_can_be_set(self):
        with mock.patch('services.ai_model_policy.DEEPSEEK_API_KEY', 'k'):
            validated = validate_policy(self.policy('deepseek', 'deepseek-flash'), require_configured_provider=False)
        self.assertEqual(validated['financial_vision'], {'provider': 'deepseek', 'model_id': 'deepseek-flash',
                                                         'chain': [{'provider': 'deepseek', 'model_id': 'deepseek-flash'}],
                                                         'deepseek_only': True})
        validate_policy(self.policy('openai', 'gpt-5.6-terra'), require_configured_provider=False)

    def chain(self, *entries):
        configuration = {key: dict(value) for key, value in DEFAULT_POLICY.items()}
        chain = [{'provider': p, 'model_id': m} for p, m in entries]
        configuration['financial_vision'] = dict(chain[0], chain=chain)
        return configuration

    def test_text_only_model_cannot_be_anywhere_in_the_chain(self):
        with mock.patch('services.ai_model_policy.DEEPSEEK_API_KEY', 'k'), \
                self.assertRaisesRegex(ValueError, 'cannot read page images'):
            validate_policy(self.chain(('openai', 'gpt-5.6-terra'), ('deepseek', 'deepseek-v4-pro')),
                            require_configured_provider=False)
        with mock.patch('services.ai_model_policy.DEEPSEEK_API_KEY', 'k'):
            validated = validate_policy(self.chain(('deepseek', 'deepseek-flash'), ('openai', 'gpt-5.6-terra')),
                                        require_configured_provider=False)
        self.assertEqual([e['provider'] for e in validated['financial_vision']['chain']], ['deepseek', 'openai'])
        self.assertEqual(validated['financial_vision']['provider'], 'deepseek')

    def test_unknown_or_unmeasured_model_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'Unknown model'):
            validate_policy(self.policy('openai', 'gpt-9-new'), require_configured_provider=False)
        with self.assertRaisesRegex(ValueError, 'cannot read page images'):
            validate_policy(self.policy('openai', 'gpt-5.6-luna'), require_configured_provider=False)

    def test_no_deepseek_key_means_refused(self):
        with mock.patch('services.ai_model_policy.DEEPSEEK_API_KEY', ''), \
                self.assertRaisesRegex(ValueError, 'cannot read page images'):
            validate_policy(self.policy('deepseek', 'deepseek-flash'), require_configured_provider=False)


if __name__ == '__main__':
    unittest.main()
