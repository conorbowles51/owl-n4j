"""A statement too long for one answer is read in parts of its pages (fin-holders, 2026-10-31: a 20-page BBVA
statement, DeepSeek stopped at its 64,000-token output limit while still thinking, 39,247 tokens in, $0.0234).

document_request reads it again in two halves, each with the same instructions (one builder, page_instructions), joins
the halves into one reading (join_parts) and returns it to be proved as a whole. What two parts print differently for
one account is never chosen between. Every request is counted, the cut-off one included.
"""
import copy
import json
import re
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import requests

import importlib

llm_service = importlib.import_module("services.llm_service")
from services.financial import vision_reader as vr


def statement(pages=4):
    """A whole-statement reading: one account, opening on the first page, closing on the last, two rows a page."""
    rows = [dict(page=n, date='2023-06-%02d' % (n * 2 + k), description='LINE %d.%d' % (n, k), amount='10.00',
                 direction='debit', balance_after=None, unreadable=False, charge_kind='')
            for n in range(1, pages + 1) for k in range(2)]
    account = dict(section_name='MAESTRA PYME', institution='BANK', holder='ACME SA DE CV', account_number='0123456789',
                   full_account_number='', currency='MXN', currency_as_printed='M.N.', period_start='2023-06-01',
                   period_end='2023-06-30', opening_balance='1000.00', opening_balance_page=1,
                   closing_balance='%.2f' % (1000 - 10 * len(rows)), closing_balance_page=pages, days_in_period=30,
                   total_credits=None, total_debits='%.2f' % (10 * len(rows)), count_credits=None,
                   count_debits=len(rows), total_fees=None, total_interest=None, no_transactions_printed=False, rows=rows)
    return dict(pages=[dict(page=n, printed_page_number=n, printed_page_total=pages, is_statement_page=True)
                       for n in range(1, pages + 1)], accounts=[account])


def part_of(document, labels):
    """What a reader given only ``labels`` reads: those pages, their rows, and a balance or total printed on them."""
    part = copy.deepcopy(document)
    part['pages'] = [p for p in part['pages'] if p['page'] in labels]
    account = part['accounts'][0]
    account['rows'] = [r for r in account['rows'] if r['page'] in labels]
    for key in ('opening_balance', 'closing_balance'):
        if account[key + '_page'] not in labels:
            account[key], account[key + '_page'] = None, None
    if 1 not in labels:
        account.update(total_debits=None, count_debits=None, days_in_period=None)
    return part


class FakeContext:
    """LLMExecutionContext for one request: the whole statement is cut off at the output limit; a part is answered."""
    sent = []
    DEEPSEEK_READ_GAP_SECONDS = llm_service.LLMExecutionContext.DEEPSEEK_READ_GAP_SECONDS

    def __init__(self, provider, model_id, api_key=None):
        self.last_usage = None

    def call_vision_json(self, prompt, images, *, image_labels, schema, schema_name, timeout, max_output_tokens):
        labels = sorted({int(re.match(r'Page (\d+)', label).group(1)) for label in image_labels})
        FakeContext.sent.append(dict(prompt=prompt, labels=labels, timeout=timeout))
        whole = FakeContext.document
        if len(labels) > FakeContext.fits:
            self.last_usage = dict(prompt_tokens=1000 * len(labels), completion_tokens=64000)
            raise llm_service.IncompleteAnswer('The page-image reading was incomplete (length)', 'length')
        self.last_usage = dict(prompt_tokens=1000 * len(labels), completion_tokens=500 * len(labels))
        return json.dumps(FakeContext.answer(whole, labels))


def pages_of(count, strips=6):
    return [(n, [b'png'] * strips) for n in range(1, count + 1)]


class PartsTests(TestCase):
    def setUp(self):
        FakeContext.sent = []
        FakeContext.document = statement(4)
        FakeContext.fits = 2
        FakeContext.answer = staticmethod(part_of)
        context = patch.object(llm_service, 'LLMExecutionContext', FakeContext)
        context.start()
        self.addCleanup(context.stop)

    def read(self, pages=4, provider='deepseek'):
        return vr.document_request('deepseek-flash', 'k', provider)(pages_of(pages))

    def test_a_cut_off_statement_is_read_in_two_halves_and_joined_into_the_whole_reading(self):
        with self.assertLogs(vr.log.name, 'WARNING'):
            document, usage = self.read()
        self.assertEqual([s['labels'] for s in FakeContext.sent], [[1, 2, 3, 4], [1, 2], [3, 4]])
        # The joined reading is the reading one request would have given: proved as a whole, like any other.
        self.assertEqual(document, FakeContext.document)
        self.assertEqual(usage['parts'], 2)
        self.assertEqual(usage['requests'], 3)
        # Every request is counted, the cut-off one included (it is billed).
        self.assertEqual(usage['prompt_tokens'], 4000 + 2000 + 2000)
        self.assertEqual(usage['completion_tokens'], 64000 + 1000 + 1000)

    def test_a_half_cut_off_again_is_halved_again(self):
        FakeContext.document = statement(8)
        FakeContext.fits = 2
        with self.assertLogs(vr.log.name, 'WARNING'):
            document, usage = self.read(8)
        self.assertEqual([s['labels'] for s in FakeContext.sent],
                         [list(range(1, 9)), [1, 2, 3, 4], [1, 2], [3, 4], [5, 6, 7, 8], [5, 6], [7, 8]])
        self.assertEqual(document, FakeContext.document)
        self.assertEqual(usage['parts'], 4)

    def test_a_statement_that_fits_is_one_request_as_before(self):
        FakeContext.fits = 4
        document, usage = self.read()
        self.assertEqual(len(FakeContext.sent), 1)
        self.assertNotIn('parts', usage)
        self.assertEqual(FakeContext.sent[0]['prompt'], vr.page_instructions(4, 6)[0])

    def test_every_part_gets_the_same_instructions_from_the_one_builder(self):
        with self.assertLogs(vr.log.name, 'WARNING'):
            self.read()
        first, second = FakeContext.sent[1]['prompt'], FakeContext.sent[2]['prompt']
        self.assertTrue(first.startswith(vr.PROMPT) and second.startswith(vr.PROMPT))
        self.assertEqual(first, vr.page_instructions(2, 6, part=([1, 2], 4))[0])
        self.assertEqual(second, vr.page_instructions(2, 6, part=([3, 4], 4))[0])
        self.assertIn('This statement has 4 pages. These images are 2 of them (labels 3, 4)', second)
        self.assertEqual(vr.page_instructions(2, 6, part=([1, 2], 4))[1], vr.PROMPT_VERSION)

    def test_a_single_page_cut_off_fails_as_before(self):
        FakeContext.document = statement(1)
        FakeContext.fits = 0
        with self.assertRaises(llm_service.IncompleteAnswer) as caught:
            self.read(1)
        self.assertEqual(caught.exception.usage['completion_tokens'], 64000)
        self.assertEqual(vr.failure_words(caught.exception), 'The page-image reading was incomplete (length)')

    def test_two_parts_printing_different_values_for_one_account_are_never_chosen_between(self):
        for key, value, words in (('holder', 'JOHN SMITH', 'two different holder'),
                                  ('institution', 'SANTANDER', 'two different institution'),
                                  ('period_end', '2023-07-31', 'two different period end'),
                                  ('opening_balance', '999.00', 'two different values for the opening balance')):
            with self.subTest(key=key):
                FakeContext.sent = []

                def answer(whole, labels, key=key, value=value):
                    part = part_of(whole, labels)
                    if 3 in labels:
                        part['accounts'][0][key] = value
                        if key == 'opening_balance':
                            part['accounts'][0]['opening_balance_page'] = 3
                    return part
                FakeContext.answer = staticmethod(answer)
                with self.assertLogs(vr.log.name, 'WARNING'), self.assertRaises(vr.UnreadableAnswer) as caught:
                    self.read()
                self.assertIn(words, str(caught.exception))
                self.assertEqual(caught.exception.usage['completion_tokens'], 64000 + 1000 + 1000)

    def test_a_part_that_fails_fails_the_reader_with_everything_counted(self):
        def answer(whole, labels):
            if 3 in labels:
                raise requests.exceptions.ReadTimeout('read timed out')
            return part_of(whole, labels)
        FakeContext.answer = staticmethod(answer)
        with self.assertLogs(vr.log.name, 'WARNING'), self.assertRaises(requests.exceptions.ReadTimeout) as caught:
            self.read()
        self.assertEqual(caught.exception.usage['requests'], 3)
        self.assertEqual(vr.failure_words(caught.exception), 'it did not answer in time')

    def test_a_part_citing_a_page_it_was_not_given_is_refused(self):
        whole = statement(4)
        first, second = part_of(whole, [1, 2]), part_of(whole, [3, 4])
        first['accounts'][0]['rows'][0]['page'] = 3
        with self.assertRaises(vr.UnreadableAnswer) as caught:
            vr.join_parts([([1, 2], first), ([3, 4], second)])
        self.assertIn('cites a page it was not given', str(caught.exception))

    def test_the_parts_stay_within_the_readers_allowance(self):
        """The halves share what is left of the reader's worst case (reader_worst_seconds, which the claim covers):
        a part never starts with less than PART_MIN_SECONDS."""
        clock = iter([0.0])  # the reader starts at 0; by the first part its allowance is spent
        with patch.object(vr.time, 'monotonic', lambda: next(clock, 10_000.0)), \
                self.assertLogs(vr.log.name, 'WARNING'), self.assertRaises(requests.exceptions.ReadTimeout) as caught:
            self.read()
        self.assertEqual(len(FakeContext.sent), 1)
        self.assertEqual(vr.failure_words(caught.exception),
                         'not enough of its time was left to read the rest of the statement')

    def test_join_matches_a_masked_number_and_keeps_the_first_parts_heading(self):
        whole = statement(4)
        first, second = part_of(whole, [1, 2]), part_of(whole, [3, 4])
        second['accounts'][0]['account_number'] = '****6789'
        joined = vr.join_parts([([1, 2], first), ([3, 4], second)])
        self.assertEqual(len(joined['accounts']), 1)
        self.assertEqual(joined['accounts'][0]['account_number'], '0123456789')
        self.assertEqual(len(joined['accounts'][0]['rows']), 8)

    def test_join_takes_the_banks_name_in_a_longer_form_as_the_same_bank(self):
        """Measured on the 20-page statement: the halves printed the bank's name in two forms. The same by the rule the
        proof compares names with (field_proposals.same_institution / same_holder); the first part's form is kept."""
        whole = statement(4)
        first, second = part_of(whole, [1, 2]), part_of(whole, [3, 4])
        first['accounts'][0]['institution'] = 'BBVA MEXICO'
        second['accounts'][0]['institution'] = 'BBVA MEXICO, S.A., INSTITUCION DE BANCA MULTIPLE'
        first['accounts'][0]['holder'] = 'COMERCIALIZADORA ACME'
        second['accounts'][0]['holder'] = 'COMERCIALIZADORA ACME DEL NORTE'
        joined = vr.join_parts([([1, 2], first), ([3, 4], second)])
        self.assertEqual(joined['accounts'][0]['institution'], 'BBVA MEXICO')
        self.assertEqual(joined['accounts'][0]['holder'], 'COMERCIALIZADORA ACME')
        self.assertEqual(joined['accounts'][0]['forms_in_parts'], {
            'institution': ['BBVA MEXICO', 'BBVA MEXICO, S.A., INSTITUCION DE BANCA MULTIPLE'],
            'holder': ['COMERCIALIZADORA ACME', 'COMERCIALIZADORA ACME DEL NORTE']})

    def test_join_keeps_a_different_account_apart(self):
        whole = statement(4)
        first, second = part_of(whole, [1, 2]), part_of(whole, [3, 4])
        other = copy.deepcopy(second['accounts'][0])
        other.update(account_number='9999999999', section_name='DOLARES')
        second['accounts'].append(other)
        joined = vr.join_parts([([1, 2], first), ([3, 4], second)])
        self.assertEqual([a['account_number'] for a in joined['accounts']], ['0123456789', '9999999999'])


class OutcomeProviderTests(TestCase):
    def test_a_failed_outcome_is_the_reader_that_read_not_the_switched_off_one(self):
        """fin-holders 2026-10-31: DeepSeek's cut-off reading was recorded as gpt-5.6-terra's while OpenAI failover was
        switched off and OpenAI was sent nothing."""
        attempts = [dict(provider='deepseek', model='deepseek-flash', prompt_version=vr.PROMPT_VERSION, status='failed',
                         error='IncompleteAnswer', message='The page-image reading was incomplete (length)'),
                    dict(provider='openai', model='gpt-5.6-terra', prompt_version=vr.PROMPT_VERSION,
                         status='switched_off', message='OpenAI failover is switched off')]
        record = vr._outcome(dict(status='pending'), attempts, None, 0.02, 248.0, {}, False)
        self.assertEqual((record['provider'], record['model']), ('deepseek', 'deepseek-flash'))
        self.assertEqual(record['status'], 'failed')
        self.assertIn('OpenAI failover is switched off', record['message'])
