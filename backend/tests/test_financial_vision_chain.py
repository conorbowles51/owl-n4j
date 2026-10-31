"""The page-image reader chain: DeepSeek first, OpenAI the failsafe, the same instructions to both (Neil, 2026-10-28).

Each test reads one held statement of the batch fixture (test_financial_reader_release) through a chain of readers
and checks what is accepted, what is recorded and what is sent. A reading is never accepted unproved and readings
are never combined; when no reader proves, the statement stays held with every reason.
"""
import ast
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import requests

from services import ai_model_capabilities as cap
from services.financial import import_batches as batches
from services.financial import vision_reader as vr
from tests import test_financial_reader_release as release

USAGE = dict(prompt_tokens=10000, completion_tokens=2000)


def reader(provider, model, read=None, unavailable=''):
    return vr.PageReader(provider=provider, model=model, read=read, unavailable=unavailable, strips=1,
                         max_output_tokens=1000)


class ChainTests(TestCase):
    def setUp(self):
        self.r = release.ReaderReleaseTests('test_no_mark_with_the_page_image_reader_off')
        self.r.setUp()
        self.addCleanup(self.r.tearDown)
        self.f = self.r.f
        spend = patch.dict(vr._spend, {}, clear=True)
        spend.start()
        self.addCleanup(spend.stop)
        # The chain with OpenAI failover on (the "DeepSeek only" switch OFF) unless a test switches it on.
        self.only = patch('services.ai_model_policy.deepseek_only', return_value=False)
        self.only.start()
        self.addCleanup(self.only.stop)

    def held(self):
        with patch.object(vr, 'ENABLED', True):
            batch = self.r.prepare_with_old_reader()
        held = self.r.item(batch)
        self.assertEqual(held.status, 'attention')
        return batch, held

    def read(self, batch, held, page_reader, knowledge, neighbours=lambda *a: None):
        rendered = []

        def render(path, pages, width=None, strips=None, sha256=None):
            rendered.append(strips)
            return [(p, [b'png'] * (strips or 1)) for p in pages]
        with patch.object(vr, 'render_pages', render), \
                patch.object(batches, 'read_statement_import', release.old_reader), \
                patch('services.financial.statement_import.read_statement_import', release.old_reader), \
                patch.object(vr, 'check_neighbours', neighbours), \
                patch('services.financial.field_proposals.MIN_MASKED_DIGITS', 3):
            outcome = vr.read_item(self.f.SessionLocal, held.id, Path, page_reader=page_reader,
                                   knowledge_for=lambda db, case_id: knowledge)
        return outcome, rendered

    def stored(self, held):
        from postgres.models.evidence import EvidenceFile
        with self.f.SessionLocal() as db:
            return db.get(EvidenceFile, held.file_id).metadata_[vr.METADATA_KEY][held.statement_key or '']

    # -- which reading is accepted ---------------------------------------------------------------------------------

    def test_deepseek_proves_first_and_openai_is_never_asked(self):
        batch, held = self.held()
        document, knowledge = self.r._image_reading(held)
        openai = Mock(side_effect=AssertionError('the failsafe is not asked when DeepSeek proves'))
        chain = [reader('deepseek', 'deepseek-flash', lambda images: (document, USAGE)),
                 reader('openai', 'gpt-5.6-terra', openai)]
        outcome, _ = self.read(batch, held, lambda db, case_id: chain, knowledge)
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        self.assertEqual(outcome['message'], 'Read from the page images by DeepSeek; the period reconciles exactly.')
        stored = self.stored(held)
        self.assertEqual((stored['provider'], stored['model'], stored['prompt_version']),
                         ('deepseek', 'deepseek-flash', vr.PROMPT_VERSION))
        self.assertEqual([a['status'] for a in stored['attempts']], ['proved'])
        self.assertNotIn('failover', stored)
        self.assertEqual(stored['cost_usd'], vr.cost_usd('deepseek-flash', USAGE))
        rows = [r for r in self.r.item(batch).review_request['rows'] if r['id'].startswith('manual:vision-')]
        self.assertTrue(rows and all(r['reason'].endswith(', by DeepSeek.') for r in rows))

    def test_an_unproved_deepseek_reading_goes_to_openai_and_the_reason_is_recorded(self):
        batch, held = self.held()
        wrong, knowledge = self.r._image_reading(held, nudge=1)  # closing balance a cent out: does not prove
        right, _ = self.r._image_reading(held)
        chain = [reader('deepseek', 'deepseek-flash', lambda images: (wrong, USAGE)),
                 reader('openai', 'gpt-5.6-terra', lambda images: (right, USAGE))]
        outcome, _ = self.read(batch, held, lambda db, case_id: chain, knowledge)
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        self.assertTrue(outcome['message'].startswith('Read from the page images by OpenAI (DeepSeek could not prove it: '),
                        outcome['message'])
        stored = self.stored(held)
        self.assertEqual(stored['provider'], 'openai')
        self.assertEqual([(a['provider'], a['status']) for a in stored['attempts']],
                         [('deepseek', 'not_proved'), ('openai', 'proved')])
        self.assertEqual([(f['provider'], f['status']) for f in stored['failover']], [('deepseek', 'not_proved')])
        # Both calls are paid for and counted, each at its provider's price; the accepted reading is OpenAI's alone.
        both = vr.cost_usd('deepseek-flash', USAGE) + vr.cost_usd('gpt-5.6-terra', USAGE)
        self.assertAlmostEqual(stored['cost_usd'], both, places=5)
        self.assertAlmostEqual(vr._spend[str(self.f.case.id)] if str(self.f.case.id) in vr._spend
                               else sum(vr._spend.values()), both, places=5)
        self.assertEqual(stored['raw'], right)
        rows = [r for r in self.r.item(batch).review_request['rows'] if r['id'].startswith('manual:vision-')]
        self.assertTrue(rows and all(r['reason'].endswith(', by OpenAI.') for r in rows))

    def test_neither_proves_the_statement_stays_held_with_both_reasons(self):
        batch, held = self.held()
        wrong, knowledge = self.r._image_reading(held, nudge=1)
        chain = [reader('deepseek', 'deepseek-flash', lambda images: (wrong, USAGE)),
                 reader('openai', 'gpt-5.6-terra', lambda images: (wrong, USAGE))]
        outcome, _ = self.read(batch, held, lambda db, case_id: chain, knowledge)
        self.assertEqual(outcome['status'], 'not_proved')
        self.assertIn('DeepSeek could not prove it: ', outcome['message'])
        self.assertIn('OpenAI could not prove it: ', outcome['message'])
        after = self.r.item(batch)
        self.assertEqual(after.status, 'attention')
        self.assertFalse(any(r['id'].startswith('manual:vision-') for r in (after.review_request or {}).get('rows') or []))
        self.assertIn('OpenAI could not prove it', after.summary['vision_reading']['line'])

    def test_errors_and_unreadable_answers_go_to_openai(self):
        for error, words in ((vr.UnreadableAnswer('the answer was not valid JSON'), 'the answer was not valid JSON'),
                             (requests.exceptions.ReadTimeout('read timed out'), 'it did not answer in time'),
                             (requests.exceptions.ConnectionError('reset by peer'), 'the connection to it failed')):
            with self.subTest(words=words):
                batch, held = self.held()
                right, knowledge = self.r._image_reading(held)

                def fail(images, error=error):
                    raise error
                chain = [reader('deepseek', 'deepseek-flash', fail),
                         reader('openai', 'gpt-5.6-terra', lambda images: (right, USAGE))]
                with self.assertLogs(vr.log.name, 'WARNING'):
                    outcome, _ = self.read(batch, held, lambda db, case_id: chain, knowledge)
                self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
                self.assertIn(f'(DeepSeek could not read it: {words})', outcome['message'])
                self.assertEqual(self.stored(held)['failover'][0]['status'], 'failed')
                self.r.tearDown()
                self.setUp()

    def test_both_fail_the_statement_stays_held_and_is_tried_again(self):
        batch, held = self.held()
        _, knowledge = self.r._image_reading(held)

        def fail(images):
            raise requests.exceptions.ConnectionError('reset')
        chain = [reader('deepseek', 'deepseek-flash', fail), reader('openai', 'gpt-5.6-terra', fail)]
        with self.assertLogs(vr.log.name, 'WARNING'):
            outcome, _ = self.read(batch, held, lambda db, case_id: chain, knowledge)
        self.assertEqual((outcome['status'], outcome['failures']), ('failed', 1))
        self.assertIn('DeepSeek could not read it', outcome['message'])
        self.assertIn('OpenAI could not read it', outcome['message'])
        self.assertEqual(self.r.item(batch).status, 'attention')

    def test_no_deepseek_key_starts_the_chain_at_openai_with_a_warning(self):
        batch, held = self.held()
        right, knowledge = self.r._image_reading(held)
        keys = {'deepseek': None, 'openai': 'k'}
        chain = [{'provider': 'deepseek', 'model_id': 'deepseek-flash'}, {'provider': 'openai', 'model_id': 'gpt-5.6-terra'}]
        with patch('services.ai_model_policy.get_workload_chain', return_value=chain), \
                patch('services.ai_provider_credentials.get_provider_api_key', side_effect=lambda db, p: keys[p]), \
                patch.object(vr, 'document_request', lambda model, key, provider: lambda images: (right, USAGE)), \
                self.assertLogs(vr.log.name, 'WARNING') as logs:
            outcome, rendered = self.read(batch, held, vr.chain_page_reader, knowledge)
        self.assertTrue(any('no DeepSeek key is connected' in line for line in logs.output))
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        self.assertIn('by OpenAI (DeepSeek was not used: no DeepSeek key is connected)', outcome['message'])
        self.assertEqual(rendered, [vr.READER_SETTINGS['openai']['strips']], 'only OpenAI is rendered for')

    # -- the "DeepSeek only" switch (Neil, 2026-10-28) ------------------------------------------------------------

    def switched(self, on):
        self.only.stop()
        self.only = patch('services.ai_model_policy.deepseek_only', return_value=on)
        self.only.start()
        cap.clear_cache()
        self.addCleanup(cap.clear_cache)
        listed = patch.object(cap, '_fetch_deepseek', return_value={'deepseek-flash': {'text', 'image'}})
        listed.start()
        self.addCleanup(listed.stop)

    def test_deepseek_only_on_never_sends_anything_to_openai(self):
        chain = [{'provider': 'deepseek', 'model_id': 'deepseek-flash'}, {'provider': 'openai', 'model_id': 'gpt-5.6-terra'}]
        self.switched(True)
        for case in ('not_proved', 'error', 'timeout', 'no_key'):
            with self.subTest(case=case):
                batch, held = self.held()
                right, knowledge = self.r._image_reading(held)
                wrong, _ = self.r._image_reading(held, nudge=1)
                sent = []

                def request(model, key, provider):
                    def read(images):
                        sent.append(provider)
                        if provider == 'openai':
                            raise AssertionError('nothing is sent to OpenAI while DeepSeek only is ON')
                        if case == 'error':
                            raise requests.exceptions.ConnectionError('reset by peer')
                        if case == 'timeout':
                            raise requests.exceptions.ReadTimeout('read timed out')
                        return wrong, USAGE
                    return read
                keys = {'deepseek': None if case == 'no_key' else 'k', 'openai': 'k'}
                api_key = Mock(side_effect=lambda db, p: keys[p])
                with patch('services.ai_model_policy.get_workload_chain', return_value=chain), \
                        patch('services.ai_provider_credentials.get_provider_api_key', api_key), \
                        patch.object(vr, 'RETRY_PAUSE_SECONDS', 0), \
                        patch.object(vr, 'document_request', request):
                    outcome, _ = self.read(batch, held, vr.chain_page_reader, knowledge)
                self.assertNotIn('openai', sent)
                self.assertNotIn('openai', [c.args[1] for c in api_key.call_args_list], 'OpenAI\'s key is not even read')
                self.assertNotEqual(outcome['status'], 'proved')
                self.assertIn('OpenAI failover is switched off', outcome['message'])
                self.assertEqual(self.r.item(batch).status, 'attention')
                if case != 'no_key':
                    self.assertIn('DeepSeek could not', outcome['message'])

    def test_deepseek_only_on_accepts_a_proved_deepseek_reading(self):
        self.switched(True)
        batch, held = self.held()
        right, knowledge = self.r._image_reading(held)
        chain = [{'provider': 'deepseek', 'model_id': 'deepseek-flash'}, {'provider': 'openai', 'model_id': 'gpt-5.6-terra'}]
        with patch('services.ai_model_policy.get_workload_chain', return_value=chain), \
                patch('services.ai_provider_credentials.get_provider_api_key', return_value='k'), \
                patch.object(vr, 'document_request', lambda model, key, provider: lambda images: (right, USAGE)):
            outcome, _ = self.read(batch, held, vr.chain_page_reader, knowledge)
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        self.assertEqual(outcome['message'], 'Read from the page images by DeepSeek; the period reconciles exactly.')
        # Switching failover back on is a different chain: held statements are read again with the failsafe.
        self.assertEqual(self.stored(held)['reader'], f'deepseek/deepseek-flash ({vr.PROMPT_VERSION})')

    def test_deepseek_only_off_fails_over_to_openai(self):
        self.switched(False)
        batch, held = self.held()
        right, knowledge = self.r._image_reading(held)
        wrong, _ = self.r._image_reading(held, nudge=1)
        chain = [{'provider': 'deepseek', 'model_id': 'deepseek-flash'}, {'provider': 'openai', 'model_id': 'gpt-5.6-terra'}]
        with patch('services.ai_model_policy.get_workload_chain', return_value=chain), \
                patch('services.ai_provider_credentials.get_provider_api_key', return_value='k'), \
                patch.object(vr, 'document_request',
                             lambda model, key, provider: lambda images: ((wrong if provider == 'deepseek' else right), USAGE)):
            outcome, _ = self.read(batch, held, vr.chain_page_reader, knowledge)
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        self.assertTrue(outcome['message'].startswith('Read from the page images by OpenAI (DeepSeek could not prove it'))
        self.assertEqual(self.stored(held)['reader'],
                         f'deepseek/deepseek-flash > openai/gpt-5.6-terra ({vr.PROMPT_VERSION})')

    def test_deepseek_only_on_never_accepts_a_stored_openai_reading(self):
        # Review #1: an OpenAI reading stored while failover was on (not proved then) is not judged again once
        # DeepSeek only is ON, even if it would prove now.
        batch, held = self.held()
        right, knowledge = self.r._image_reading(held)

        def broken(images):
            raise requests.exceptions.ConnectionError('reset by peer')

        def no_neighbour(*a):
            raise vr.NotProved('This account has no saved statement in the case to confirm the page-image reading against.')
        chain = [reader('deepseek', 'deepseek-flash', broken), reader('openai', 'gpt-5.6-terra', lambda images: (right, USAGE))]
        with self.assertLogs(vr.log.name, 'WARNING'):
            first, _ = self.read(batch, held, lambda db, case_id: chain, knowledge, neighbours=no_neighbour)
        self.assertEqual(first['status'], 'failed', first.get('message'))
        self.assertTrue(any(a.get('raw') for a in self.stored(held)['attempts'] if a['provider'] == 'openai')
                        or self.stored(held).get('raw'))
        off = vr.PageReader(provider='openai', model='gpt-5.6-terra', read=None, switched_off=True, strips=None,
                            unavailable='OpenAI failover is switched off', max_output_tokens=1000)
        chain = [reader('deepseek', 'deepseek-flash', broken), off]
        with self.assertLogs(vr.log.name, 'WARNING'):
            second, _ = self.read(batch, held, lambda db, case_id: chain, knowledge)
        self.assertNotEqual(second['status'], 'proved', second.get('message'))
        self.assertIn('OpenAI failover is switched off', second['message'])
        self.assertEqual(self.r.item(batch).status, 'attention')

    def test_a_reader_that_could_outlast_the_claim_is_not_started(self):
        batch, held = self.held()
        right, knowledge = self.r._image_reading(held)
        deepseek = Mock(side_effect=AssertionError('not started: it could outlast the claim'))
        chain = [vr.PageReader(provider='deepseek', model='deepseek-flash', read=deepseek, unavailable='', strips=1,
                               max_output_tokens=1000),
                 vr.PageReader(provider='openai', model='gpt-5.6-terra', read=lambda images: (right, USAGE),
                               unavailable='', strips=1, max_output_tokens=1000)]
        self.assertLess(vr.CHAIN_SECONDS, vr.CLAIM_SECONDS)
        # The default chain at its slowest fits inside the chain's time.
        self.assertLess(sum(vr.reader_worst_seconds(r) for r in chain), vr.CHAIN_SECONDS)
        with patch.object(vr, 'CHAIN_SECONDS', vr.reader_worst_seconds(chain[1]) + 60):
            outcome, _ = self.read(batch, held, lambda db, case_id: chain, knowledge)
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        self.assertIn('DeepSeek was not used: not enough time was left to read it in this round', outcome['message'])

    def test_a_reader_skipped_for_time_leaves_the_statement_to_be_read_again(self):
        # Review #2: DeepSeek does not prove it and OpenAI is not started for lack of time: not a final outcome.
        batch, held = self.held()
        wrong, knowledge = self.r._image_reading(held, nudge=1)
        openai = Mock(side_effect=AssertionError('not started'))
        chain = [reader('deepseek', 'deepseek-flash', lambda images: (wrong, USAGE)),
                 vr.PageReader(provider='openai', model='gpt-5.6-terra', read=openai, unavailable='', strips=1,
                               max_output_tokens=1000)]
        worst = lambda r: 10 if r.provider == 'deepseek' else vr.CHAIN_SECONDS + 1  # noqa: E731
        with patch.object(vr, 'reader_worst_seconds', worst):
            outcome, _ = self.read(batch, held, lambda db, case_id: chain, knowledge)
        self.assertEqual(outcome['status'], 'unavailable', outcome.get('message'))
        self.assertNotIn(outcome['status'], vr.FINAL)
        self.assertIn('DeepSeek could not prove it', outcome['message'])
        self.assertIn('OpenAI was not used: not enough time', outcome['message'])
        self.assertEqual(self.r.item(batch).status, 'attention')

    def test_worst_case_chain_fits_inside_the_claim(self):
        deepseek = vr.PageReader(provider='deepseek', model='deepseek-flash')
        openai = vr.PageReader(provider='openai', model='gpt-5.6-terra')
        self.assertLess(vr.reader_worst_seconds(deepseek) + vr.reader_worst_seconds(openai), vr.CHAIN_SECONDS)
        self.assertLess(vr.CHAIN_SECONDS, vr.CLAIM_SECONDS)

    def test_deepseek_only_on_a_stored_openai_reading_never_replaces_a_saved_statement(self):
        from services.financial import saved_reading_replacement  # noqa: F401 - the caller of saved_image_request
        stored = {'raw': {'accounts': []}, 'version': vr.VERSION, 'revision': 'r1', 'pages': [1]}
        file = SimpleNamespace(metadata_={vr.SAVED_KEY: {'s': stored}})
        db = Mock()
        db.get.return_value = file
        document = SimpleNamespace(evidence_file_id='f', case_id='c')
        proposal = {'revision': 'r1'}
        judge = Mock(side_effect=AssertionError('a reading by OpenAI is not judged while DeepSeek only is ON'))
        self.switched(True)
        for provider in (None, 'openai'):  # a reading stored before the chain was OpenAI's
            stored['provider'] = provider
            with patch.object(vr, 'SAVED_READING', True), patch.object(vr, 'statement_pages', lambda p: [1]), \
                    patch.object(vr, 'judge', judge):
                self.assertEqual(vr.saved_image_request(db, document, 's', proposal), (None, 'image_reader_switched_off'))
        stored['provider'] = 'deepseek'
        with patch.object(vr, 'SAVED_READING', True), patch.object(vr, 'statement_pages', lambda p: [1]), \
                patch.object(vr, 'judge', return_value=('reading', 'request', None, 'judged')), \
                patch('services.financial.field_proposals.case_knowledge', return_value=None):
            self.assertEqual(vr.saved_image_request(db, document, 's', proposal), (('request', 'judged', 'reading'), None))

    def test_a_failed_answer_that_was_billed_is_counted(self):
        batch, held = self.held()
        right, knowledge = self.r._image_reading(held)

        def cut_short(images):
            error = ValueError('The page-image reading was incomplete (length)')
            error.usage = dict(prompt_tokens=10000, completion_tokens=64000)
            raise error
        chain = [reader('deepseek', 'deepseek-flash', cut_short), reader('openai', 'gpt-5.6-terra', lambda images: (right, USAGE))]
        with self.assertLogs(vr.log.name, 'WARNING'):
            outcome, _ = self.read(batch, held, lambda db, case_id: chain, knowledge)
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        stored = self.stored(held)
        billed = vr.cost_usd('deepseek-flash', dict(prompt_tokens=10000, completion_tokens=64000))
        self.assertAlmostEqual(stored['attempts'][0]['cost_usd'], billed, places=5)
        self.assertAlmostEqual(stored['cost_usd'], billed + vr.cost_usd('gpt-5.6-terra', USAGE), places=5)

    def test_a_failed_reading_in_parts_counts_all_it_cost_against_the_case_budget(self):
        """A long statement read in parts makes several requests; when it fails, what they cost beyond the one
        request reserved is counted against the case's budget too (review, 2026-10-31)."""
        batch, held = self.held()
        right, knowledge = self.r._image_reading(held)
        usage = dict(prompt_tokens=30000, completion_tokens=3 * 64000, requests=3)

        def parts_fail(images):
            error = vr.UnreadableAnswer('the parts of the reading print two different holder for one account')
            error.usage = usage
            raise error
        chain = [reader('deepseek', 'deepseek-flash', parts_fail), reader('openai', 'gpt-5.6-terra', lambda images: (right, USAGE))]
        with self.assertLogs(vr.log.name, 'WARNING'):
            outcome, _ = self.read(batch, held, lambda db, case_id: chain, knowledge)
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        billed = vr.cost_usd('deepseek-flash', usage) + vr.cost_usd('gpt-5.6-terra', USAGE)
        self.assertAlmostEqual(sum(vr._spend.values()), billed, places=5)

    def test_a_text_only_model_in_the_chain_is_never_sent_the_pages(self):
        batch, held = self.held()
        right, knowledge = self.r._image_reading(held)
        chain = [{'provider': 'deepseek', 'model_id': 'deepseek-v4-pro'}, {'provider': 'openai', 'model_id': 'gpt-5.6-terra'}]
        sent = []
        cap.clear_cache()
        self.addCleanup(cap.clear_cache)
        listed = {'deepseek-flash': {'text', 'image'}, 'deepseek-v4-pro': {'text'}}
        with patch('services.ai_model_policy.get_workload_chain', return_value=chain), \
                patch.object(cap, '_fetch_deepseek', return_value=listed), \
                patch('services.ai_provider_credentials.get_provider_api_key', return_value='k'), \
                patch.object(vr, 'document_request',
                             lambda model, key, provider: lambda images: sent.append(model) or (right, USAGE)), \
                self.assertLogs(vr.log.name, 'WARNING'):
            outcome, _ = self.read(batch, held, vr.chain_page_reader, knowledge)
        self.assertEqual(sent, ['gpt-5.6-terra'])
        self.assertIn(cap.CANNOT_READ_IMAGES, outcome['message'])

    def test_no_reader_usable_nothing_is_sent_and_both_reasons_show(self):
        batch, held = self.held()
        _, knowledge = self.r._image_reading(held)
        chain = [reader('deepseek', 'deepseek-flash', unavailable='no DeepSeek key is connected'),
                 reader('openai', 'gpt-5.6-terra', unavailable=cap.CANNOT_READ_IMAGES)]
        outcome, rendered = self.read(batch, held, lambda db, case_id: chain, knowledge)
        self.assertEqual(outcome['status'], 'unavailable')
        self.assertIn('no DeepSeek key is connected', outcome['message'])
        self.assertIn(cap.CANNOT_READ_IMAGES, outcome['message'])
        self.assertEqual(rendered, [])

    # -- one set of instructions for every provider ----------------------------------------------------------------

    def test_deepseek_and_openai_are_sent_the_same_instructions_including_on_failover(self):
        """Neil, 2026-10-28: the OpenAI failsafe gets the same advanced instructions DeepSeek gets. The requests that
        leave for each provider (DeepSeek dropping its connection three times, OpenAI taking over) are captured."""
        batch, held = self.held()
        right, knowledge = self.r._image_reading(held)
        deepseek_sent, openai_sent = [], []

        def deepseek_post(url, headers=None, json=None, timeout=None, stream=None):
            deepseek_sent.append(json)
            raise requests.exceptions.ConnectionError('Connection reset by peer')

        def answer(**kwargs):
            openai_sent.append(kwargs)
            message = SimpleNamespace(content=json.dumps(right), refusal=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason='stop')],
                                   usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=100, total_tokens=1100),
                                   model='gpt-5.6-terra', id='r1')
        fake_openai = Mock()
        fake_openai.chat.completions.create.side_effect = answer
        chain = [{'provider': 'deepseek', 'model_id': 'deepseek-flash'}, {'provider': 'openai', 'model_id': 'gpt-5.6-terra'}]
        cap.clear_cache()
        self.addCleanup(cap.clear_cache)
        with patch('services.ai_model_policy.get_workload_chain', return_value=chain), \
                patch.object(cap, '_fetch_deepseek', return_value={'deepseek-flash': {'text', 'image'}}), \
                patch('services.ai_provider_credentials.get_provider_api_key', return_value='k'), \
                patch('services.llm_service.requests.post', side_effect=deepseek_post), \
                patch('services.llm_service.OpenAI', return_value=fake_openai), \
                patch.object(vr, 'RETRY_PAUSE_SECONDS', 0), \
                self.assertLogs(vr.log.name, 'WARNING'):
            outcome, rendered = self.read(batch, held, vr.chain_page_reader, knowledge)
        self.assertEqual(outcome['status'], 'proved', outcome.get('message'))
        self.assertEqual(len(deepseek_sent), 1 + vr.READER_SETTINGS['deepseek']['retries'])
        self.assertEqual(len(openai_sent), 1)
        pages = len(right['pages'])
        deepseek_text = deepseek_sent[0]['messages'][0]['content'][0]['text']
        openai_text = openai_sent[0]['messages'][0]['content'][0]['text']
        ds_instructions, ds_version = vr.page_instructions(pages, vr.READER_SETTINGS['deepseek']['strips'])
        oa_instructions, oa_version = vr.page_instructions(pages, vr.READER_SETTINGS['openai']['strips'])
        # OpenAI: the instructions exactly, its schema enforced as the response format.
        self.assertEqual(openai_text, oa_instructions)
        self.assertEqual(openai_sent[0]['response_format']['json_schema']['schema'], vr.DOCUMENT_SCHEMA)
        # DeepSeek: the same instructions, then (transport only) the schema it does not enforce.
        self.assertTrue(deepseek_text.startswith(ds_instructions))
        self.assertEqual(json.loads(deepseek_text[len(ds_instructions):].split('\n', 3)[-1]), vr.DOCUMENT_SCHEMA)
        # The only difference between the two instruction texts is the strip count.
        strip_free = lambda text: re.sub(r'given as \d+ overlapping strip', 'given as N overlapping strip', text)
        self.assertEqual(strip_free(ds_instructions), strip_free(oa_instructions))
        self.assertTrue(openai_text.startswith(vr.PROMPT) and deepseek_text.startswith(vr.PROMPT))
        self.assertEqual(ds_version, oa_version)
        stored = self.stored(held)
        self.assertEqual([(a['provider'], a['prompt_version']) for a in stored['attempts']],
                         [('deepseek', vr.PROMPT_VERSION), ('openai', vr.PROMPT_VERSION)])
        self.assertEqual(stored['prompt_version'], vr.PROMPT_VERSION)
        self.assertEqual(rendered, [vr.READER_SETTINGS['deepseek']['strips'], vr.READER_SETTINGS['openai']['strips']])

    def test_no_other_page_image_instructions_exist(self):
        """The page-image instruction text is built in one place (vision_reader.page_instructions). The one other
        page-image request, the payments' description lines (vision_descriptions, read after the money reading), has
        its own single builder (vision_descriptions.instructions), sent the same to every provider."""
        backend = Path(__file__).resolve().parents[1]
        callers = []
        for path in list((backend / 'services').rglob('*.py')) + list((backend / 'routers').rglob('*.py')):
            text = path.read_text(encoding='utf-8')
            if 'call_vision_json(' in text and path.name != 'llm_service.py':
                callers.append(path.relative_to(backend).as_posix())
        self.assertEqual(sorted(callers), ['services/financial/vision_descriptions.py',
                                           'services/financial/vision_reader.py'])
        lines = (backend / 'services/financial/vision_descriptions.py').read_text(encoding='utf-8')
        self.assertEqual(lines.count('call_vision_json('), 1)
        self.assertEqual(lines.count('instructions('), 2, 'defined once, used once (description_request)')
        source = (backend / 'services/financial/vision_reader.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        constants = [t.id for node in ast.walk(tree) if isinstance(node, ast.Assign) for t in node.targets
                     if isinstance(t, ast.Name) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
                     and len(node.value.value) > 200]
        # PROMPT, and the note that takes PAGES_NOTE's place for a part of a long statement (both used only by
        # page_instructions, sent the same to every provider).
        self.assertEqual(constants, ['PROMPT', 'PART_NOTE'], 'one long instruction constant and its part note')
        self.assertEqual(source.count('PART_NOTE.format('), 1)
        self.assertNotIn('STRIPS_NOTE', source)
        users = [line.strip() for line in source.splitlines() if re.search(r'\bPROMPT\b(?!_VERSION)', line)
                 and not line.lstrip().startswith(('#', 'PROMPT ='))]
        self.assertEqual([u for u in users if 'PROMPT +' in u or 'PROMPT,' in u and 'return' in u],
                         ['return PROMPT + note, PROMPT_VERSION'])
        self.assertEqual(source.count('call_vision_json('), 1)
        self.assertEqual(source.count('page_instructions('), 2, 'defined once, used once (document_request)')

    def test_the_whole_chain_fits_inside_one_claim(self):
        """A statement being read stays claimed (CLAIM_SECONDS) for the longest the chain can take, so no second
        worker reads it at the same time."""
        longest = sum((s['retries'] + 1) * (s['timeout'] + 10) + sum(vr.RETRY_PAUSE_SECONDS * (k + 1)
                      for k in range(s['retries'])) for s in vr.READER_SETTINGS.values())
        self.assertLess(longest, vr.CLAIM_SECONDS)


class WordingTests(TestCase):
    def test_names_keep_their_capitals_in_a_reason(self):
        self.assertEqual(vr._clause('DeepSeek returned an empty response.'), 'DeepSeek returned an empty response')
        self.assertEqual(vr._clause('OpenAI failover is switched off'), 'OpenAI failover is switched off')
        self.assertEqual(vr._clause('The answer was cut short'), 'the answer was cut short')
