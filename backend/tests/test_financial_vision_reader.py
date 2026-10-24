"""Page-image fallback reader: proof rules, the review it records, and failing closed."""
import json
import unittest
from types import SimpleNamespace
from unittest import mock

from services.financial import vision_reader as vr
from services.financial.field_proposals import CaseKnowledge, KnownAccount, SavedStatement


def _page(sections, number=None, total=None):
    return dict(printed_page_number=number, printed_page_total=total, is_statement_page=True, sections=sections)


def _section(rows=(), **values):
    base = dict(institution='', holder='', account_number='', currency='', currency_as_printed='', period_start='',
                period_end='', opening_balance=None, closing_balance=None, total_credits=None, total_debits=None,
                count_credits=None, count_debits=None, rows=list(rows), no_transactions_printed=False)
    base.update(values)
    return base


def _row(day, amount, direction, balance=None, description='PAGO'):
    return dict(date=day, description=description, amount=amount, direction=direction, balance_after=balance,
                unreadable=False)


def _knowledge(currency='MXN', holder='ACME SA DE CV', institution='BBVA MEXICO', account='0123456789'):
    saved = SavedStatement(currency=currency, period_start='2025-11-01', period_end='2025-11-30',
                           institution=institution, holder=holder, account_number=account)
    known = KnownAccount(key='00000000-0000-0000-0000-0000000000a1', account=account, digits=account, masked=False, institution=institution,
                         currency=currency, statements=[saved])
    return CaseKnowledge(accounts=[known])


def _proposal(rows=(), **metadata):
    meta = dict(holder='', account_number='', institution='', period_start='', period_end='',
                balance_convention='asset_balance')
    meta.update(metadata)
    return dict(revision='a' * 64, statement_id='b' * 64, currency=meta.pop('currency', ''), metadata=meta,
                rows=list(rows), page_numbers=[1, 2], statement_page_numbers=[1, 2],
                sources=[dict(page_number=1, table_index=0), dict(page_number=2, table_index=0)])


HEADER = dict(institution='BBVA MEXICO', holder='ACME SA DE CV', account_number='0123456789', currency='MXN',
              period_start='2025-12-01', period_end='2025-12-31')


def _balanced_pages():
    return [(1, _page([_section([_row('2025-12-02', '100.00', 'credit', '1100.00'),
                                 _row('2025-12-05', '30.50', 'debit', '1069.50')],
                                opening_balance='1000.00', total_credits='100.00', count_credits=1, **HEADER)], 1, 2)),
            (2, _page([_section([_row('2025-12-20', '69.50', 'debit', '1000.00')],
                                closing_balance='1000.00', total_debits='100.00')], 2, 2))]


def _proved(proposal=None, knowledge=None, pages=None):
    proposal = proposal or _proposal()
    pages = pages or _balanced_pages()
    vr.check_page_numbering(pages, proposal['page_numbers'])
    section = vr.choose_section(vr.combine(pages), proposal)
    return vr.prove(proposal, section, knowledge or _knowledge())


class ValuesTest(unittest.TestCase):
    def test_minor_units_exact_and_fail_closed(self):
        self.assertEqual(vr.to_minor('1234.56', 2), 123456)
        self.assertEqual(vr.to_minor('7', 2), 700)
        self.assertEqual(vr.to_minor('-5.10', 2, signed=True), -510)
        self.assertEqual(vr.to_minor('1,234,567.89', 2), 123456789)
        self.assertEqual(vr.to_minor('0.00 USD', 2), 0)
        for bad in ('1.234,56', '36033,789.24', '12,34.00', '12.345', '-5.10', '', None, '1.2.3', 'abc'):
            self.assertIsNone(vr.to_minor(bad, 2), bad)

    def test_cost_per_page(self):
        self.assertAlmostEqual(vr.cost_usd('gpt-4o', dict(prompt_tokens=1_000_000, completion_tokens=0)), 2.5)
        self.assertAlmostEqual(vr.cost_usd('gpt-4o-2024-08-06', dict(prompt_tokens=0, completion_tokens=1_000_000)), 10.0)
        self.assertEqual(vr.price('unknown-model'), vr.FALLBACK_PRICE)


class ProofTest(unittest.TestCase):
    def test_balanced_reading_proves_with_pages_on_every_row(self):
        reading = _proved()
        self.assertEqual((reading['opening'], reading['closing']), (100000, 100000))
        self.assertEqual([r['page'] for r in reading['rows']], [1, 1, 2])
        self.assertEqual(reading['currency'], 'MXN')
        self.assertEqual((reading['opening_page'], reading['closing_page']), (1, 2))

    def test_not_balancing_states_the_difference(self):
        pages = _balanced_pages()
        pages[1][1]['sections'][0]['rows'][0].update(amount='69.00', balance_after=None)
        pages[1][1]['sections'][0]['total_debits'] = None
        with self.assertRaisesRegex(vr.NotProved, r'did not balance.*difference 0\.50'):
            _proved(pages=pages)

    def test_running_balance_must_agree(self):
        pages = _balanced_pages()
        pages[0][1]['sections'][0]['rows'][0]['balance_after'] = '1101.00'
        with self.assertRaisesRegex(vr.NotProved, 'running balance'):
            _proved(pages=pages)

    def test_printed_totals_and_counts_must_agree(self):
        pages = _balanced_pages()
        pages[0][1]['sections'][0]['count_credits'] = 2
        with self.assertRaisesRegex(vr.NotProved, 'printed count'):
            _proved(pages=pages)
        pages = _balanced_pages()
        pages[1][1]['sections'][0]['total_debits'] = '99.00'
        with self.assertRaisesRegex(vr.NotProved, 'printed total'):
            _proved(pages=pages)

    def test_unreadable_or_out_of_period_rows_hold(self):
        pages = _balanced_pages()
        pages[0][1]['sections'][0]['rows'][1]['unreadable'] = True
        with self.assertRaisesRegex(vr.NotProved, 'certainty'):
            _proved(pages=pages)
        pages = _balanced_pages()
        pages[0][1]['sections'][0]['rows'][1]['date'] = '2026-01-05'
        with self.assertRaisesRegex(vr.NotProved, 'outside the statement period'):
            _proved(pages=pages)

    def test_missing_pages_hold(self):
        pages = _balanced_pages()
        for _, page in pages:
            page['printed_page_total'] = 3
        with self.assertRaisesRegex(vr.NotProved, 'pages may be missing'):
            vr.check_page_numbering(pages, [1, 2])
        # A period using pages 1-2 of a 3-page file whose numbering counts the whole file is complete.
        vr.check_page_numbering(pages, [1, 2, 3])

    def test_a_gap_in_the_printed_page_numbers_holds(self):
        numbered = lambda *numbers: [(physical, _page([], number, 3)) for physical, number in numbers]
        with self.assertRaisesRegex(vr.NotProved, 'skip from page 1 to page 3'):
            vr.check_page_numbering(numbered((1, 1), (2, 3)), [1, 2, 3, 4, 5])
        # An unnumbered page of the period may stand in for the gap only where it sits.
        vr.check_page_numbering(numbered((1, 1), (2, None), (3, 3)), [1, 2, 3])
        with self.assertRaisesRegex(vr.NotProved, 'skip'):
            vr.check_page_numbering(numbered((1, 1), (2, 3), (3, None)), [1, 2, 3])
        with self.assertRaisesRegex(vr.NotProved, 'skip'):
            vr.check_page_numbering(numbered((1, 2), (2, 1)), [1, 2, 3])
        with self.assertRaisesRegex(vr.NotProved, 'same page number'):
            vr.check_page_numbering(numbered((1, 1), (2, 1)), [1, 2, 3])
        # Printed pages before or after the period must at least be pages of the file.
        later = [(5, _page([], 2, 3)), (6, _page([], 3, 3))]
        vr.check_page_numbering(later, [1, 2, 3, 4, 5, 6])
        with self.assertRaisesRegex(vr.NotProved, 'not in the file'):
            vr.check_page_numbering(later, [5, 6, 7])
        with self.assertRaisesRegex(vr.NotProved, 'not in the file'):
            vr.check_page_numbering([(2, _page([], 1, 3)), (3, _page([], 2, 3))], [1, 2, 3])

    def test_a_partial_account_number_needs_the_printed_holder(self):
        masked = _knowledge(account='****6789')
        masked.accounts[0].digits, masked.accounts[0].masked = '6789', True
        self.assertEqual(len(_proved(knowledge=masked)['rows']), 3)
        pages = _balanced_pages()
        pages[0][1]['sections'][0]['holder'] = ''
        with self.assertRaisesRegex(vr.NotProved, 'partial number'):
            _proved(knowledge=masked, pages=pages)
        # The number printed only on the page images (the text read none): the same.
        with self.assertRaisesRegex(vr.NotProved, 'partial number'):
            _proved(pages=pages)
        # Saved statements that record no holder or bank cannot confirm a partial number.
        for field in ('holder', 'institution'):
            unrecorded = _knowledge(account='****6789', **{field: ''})
            unrecorded.accounts[0].digits, unrecorded.accounts[0].masked = '6789', True
            unrecorded.accounts[0].institution = unrecorded.accounts[0].institution if field == 'holder' else ''
            with self.assertRaisesRegex(vr.NotProved, 'do not record the holder and bank'):
                _proved(knowledge=unrecorded)
        # A full number the text reading also read needs no printed holder (the saved one is used).
        self.assertEqual(len(_proved(_proposal(account_number='0123456789'), pages=pages)['rows']), 3)

    def test_header_must_agree_with_text_reading(self):
        with self.assertRaisesRegex(vr.NotProved, 'no account section matching'):
            _proved(_proposal(account_number='9999999999'))
        with self.assertRaisesRegex(vr.NotProved, 'period'):
            _proved(_proposal(period_end='2025-12-30'))
        with self.assertRaisesRegex(vr.NotProved, 'holder'):
            _proved(_proposal(holder='SOMEONE ELSE'))

    def test_header_must_agree_with_saved_statements(self):
        with self.assertRaisesRegex(vr.NotProved, 'no saved statement'):
            _proved(knowledge=_knowledge(account='5555555555'))
        with self.assertRaisesRegex(vr.NotProved, 'currency'):
            _proved(knowledge=_knowledge(currency='USD'))
        with self.assertRaises(vr.NotProved):
            _proved(knowledge=_knowledge(holder='OTHER PERSON'))

    def test_currency_sub_accounts_of_one_number(self):
        mxn, usd = _knowledge().accounts[0], _knowledge(currency='USD').accounts[0]
        usd.key = '00000000-0000-0000-0000-0000000000a2'
        both = CaseKnowledge(accounts=[mxn, usd])
        self.assertEqual(_proved(knowledge=both)['currency'], 'MXN')
        pages = _balanced_pages()
        pages[0][1]['sections'][0]['currency'] = ''
        with self.assertRaisesRegex(vr.NotProved, 'more than one'):
            _proved(knowledge=both, pages=pages)
        self.assertEqual(_proved(_proposal(currency='USD'), knowledge=both, pages=pages)['currency'], 'USD')

    def test_never_drops_a_payment_or_balance_the_text_read(self):
        text_payment = dict(id='t9', kind='transaction', excluded=False, issues=[], page_number=1,
                            fields=dict(amount_minor='4200', direction='debit', date='2025-12-03'))
        with self.assertRaisesRegex(vr.NotProved, '1 payment read from the text was not found'):
            _proved(_proposal([text_payment]))
        # A text payment the reader itself doubted (an issue) does not have to appear.
        _proved(_proposal([dict(text_payment, issues=['Amount unreadable'])]))
        opening = dict(id='b1', kind='balance', excluded=True, issues=[], page_number=1,
                       fields=dict(description='Opening Balance', balance='99999'))
        with self.assertRaisesRegex(vr.NotProved, 'opening balance'):
            _proved(_proposal([opening]))

    def test_two_sections_need_a_match(self):
        pages = _balanced_pages()
        other = _section([_row('2025-12-02', '5.00', 'credit')], opening_balance='0.00', closing_balance='5.00',
                         **dict(HEADER, account_number='0987654321'))
        pages[0][1]['sections'].insert(0, other)
        with self.assertRaisesRegex(vr.NotProved, 'account sections'):
            _proved(pages=pages)
        # The text reading's account picks the section.
        self.assertEqual(_proved(_proposal(account_number='0123456789'), pages=pages)['closing'], 100000)

    def test_sub_accounts_of_one_account_stay_apart(self):
        first = _section([_row('2025-12-02', '1.00', 'credit')], section_name='SAVINGS', opening_balance='10.00',
                         closing_balance='11.00', **dict(HEADER, account_number='XXXX6789'))
        second = _section([_row('2025-12-03', '2.00', 'debit')], section_name='CHECKING', opening_balance='50.00',
                          closing_balance='48.00', **dict(HEADER, account_number='XXXX6789'))
        tail = _section([_row('2025-12-09', '3.00', 'debit')], section_name='CHECKING')
        merged = vr.combine([(1, _page([first, second])), (2, _page([tail]))])
        self.assertEqual([(m['label'], len(m['rows'])) for m in merged], [('SAVINGS', 1), ('CHECKING', 2)])
        # An unnamed header section continues into the named movements of the next page.
        merged = vr.combine([(1, _page([_section(opening_balance='1.00', **HEADER)])),
                             (2, _page([_section([_row('2025-12-03', '1.00', 'credit')], section_name='MOVIMIENTOS',
                                                 account_number='0123456789')]))])
        self.assertEqual(len(merged), 1)

    def test_conflicting_printed_values_hold(self):
        pages = _balanced_pages()
        pages[1][1]['sections'][0]['opening_balance'] = '1.00'
        with self.assertRaisesRegex(vr.NotProved, 'two different values'):
            vr.combine(pages)

    def test_liability_convention(self):
        pages = [(1, _page([_section([_row('2025-12-02', '100.00', 'debit'), _row('2025-12-03', '40.00', 'credit')],
                                     opening_balance='10.00', closing_balance='70.00', **HEADER)]))]
        proposal = _proposal(balance_convention='liability_owed')
        self.assertEqual(_proved(proposal, pages=pages)['closing'], 7000)


class NeighbourTest(unittest.TestCase):
    def _check(self, *rows):
        from datetime import date
        db = mock.Mock()
        db.execute.return_value.all.return_value = [tuple(date.fromisoformat(v) if isinstance(v, str) else v for v in row)
                                                    for row in rows]
        vr.check_neighbours(db, 'case', _proved())

    def test_adjacent_saved_balances_must_continue(self):
        self._check(('2025-11-01', '2025-11-30', 90000, 100000), ('2026-01-01', '2026-01-31', 100000, 5))
        with self.assertRaisesRegex(vr.NotProved, 'previous saved statement'):
            self._check(('2025-11-01', '2025-11-30', 90000, 99999))
        with self.assertRaisesRegex(vr.NotProved, 'next saved statement'):
            self._check(('2026-01-01', '2026-01-31', 1, 5))
        # Not adjacent, or no recorded balance: no comparison.
        self._check(('2025-10-01', '2025-10-31', 1, 2), ('2025-11-01', '2025-11-30', None, None))

    def test_overlapping_saved_period_holds(self):
        with self.assertRaisesRegex(vr.NotProved, 'already covers'):
            self._check(('2025-12-15', '2026-01-14', 1, 2))


class DocumentTest(unittest.TestCase):
    def test_document_reading_becomes_one_section_per_account(self):
        account = dict(_section(**HEADER), opening_balance='1000.00', opening_balance_page=1, closing_balance='1000.00',
                       closing_balance_page=2, total_credits='100.00', count_credits=1, total_debits='100.00',
                       rows=[dict(_row('2025-12-02', '100.00', 'credit', '1100.00'), page=1),
                             dict(_row('2025-12-05', '30.50', 'debit', '1069.50'), page=1),
                             dict(_row('2025-12-20', '69.50', 'debit', '1000.00'), page=2)])
        other = dict(_section(section_name='USD', **dict(HEADER, currency='USD')), opening_balance='5.00',
                     opening_balance_page=1, closing_balance='5.00', closing_balance_page=1, rows=[])
        document = dict(pages=[dict(page=1, printed_page_number=1, printed_page_total=2, is_statement_page=True),
                               dict(page=2, printed_page_number=2, printed_page_total=2, is_statement_page=True)],
                        accounts=[account, other])
        pages = vr.document_pages(document, [1, 2])
        merged = vr.combine(pages)
        self.assertEqual(len(merged), 2)
        self.assertEqual([r['page'] for r in merged[0]['rows']], [1, 1, 2])
        self.assertEqual(merged[0]['balance_pages'], dict(opening_balance=1, closing_balance=2, total_credits=1,
                                                          total_debits=1, count_credits=1))
        vr.check_page_numbering(pages, [1, 2])
        reading = vr.prove(_proposal(currency='MXN'), vr.choose_section(merged, _proposal(currency='MXN')), _knowledge())
        self.assertEqual(reading['closing'], 100000)

    def test_a_row_citing_a_page_not_read_holds(self):
        account = dict(_section(**HEADER), opening_balance_page=None, closing_balance_page=None,
                       rows=[dict(_row('2025-12-02', '1.00', 'credit'), page=7)])
        with self.assertRaisesRegex(vr.NotProved, 'not read'):
            vr.document_pages(dict(pages=[dict(page=1), dict(page=2)], accounts=[account]), [1, 2])
        # Every page read must be described, or its printed numbering could not be checked.
        with self.assertRaisesRegex(vr.NotProved, 'every page'):
            vr.document_pages(dict(pages=[dict(page=1)], accounts=[]), [1, 2])


class RequestTest(unittest.TestCase):
    def test_review_sets_text_rows_aside_and_cites_pages(self):
        from services.financial.statement_import import StatementReviewDraft
        text_payment = dict(id='t1', kind='transaction', excluded=False, issues=['Amount unreadable'], page_number=1,
                            fields=dict(amount_minor='', direction='debit', date='2025-12-05', description='X'))
        opening = dict(id='b1', kind='balance', excluded=True, issues=[], page_number=1,
                       fields=dict(description='Opening Balance', balance=None))
        proposal = _proposal([text_payment, opening])
        reading = _proved(proposal)
        request = vr.build_request(proposal, reading)
        StatementReviewDraft.model_validate(request)
        rows = {r['id']: r for r in request['rows']}
        self.assertTrue(rows['t1']['excluded'])
        self.assertEqual(rows['t1']['reason'], vr.REPLACED_REASON)
        self.assertEqual(rows['b1']['balance_minor'], '100000')
        self.assertEqual(rows['manual:closing-balance']['manual_page'], 2)
        self.assertTrue(rows['manual:closing-balance']['excluded'])
        added = [r for r in request['rows'] if r['id'].startswith('manual:vision-')]
        self.assertEqual([r['manual_page'] for r in added], [1, 1, 2])
        self.assertTrue(all(r['reason'] == f'Read from page image, page {r["manual_page"]}.' for r in added))
        self.assertEqual(added[0]['source_order_anchor'], dict(relation='after', row_id='t1'))
        self.assertEqual((request['holder'], request['currency'], request['period_end']), ('ACME SA DE CV', 'MXN', '2025-12-31'))

    def test_review_arithmetic_reconciles(self):
        from services.financial.review_arithmetic import check_proposed_rows
        proposal = _proposal()
        request = vr.build_request(proposal, _proved(proposal))
        checks = {c['kind']: c for c in check_proposed_rows(proposal, request['rows'])['checks']}
        self.assertEqual(checks['closing_balance']['status'], 'matches')


class EligibilityTest(unittest.TestCase):
    def _item(self, **values):
        return SimpleNamespace(**dict(dict(status='attention', review_request=None, statement_key='s1', summary={}), **values))

    def test_only_untouched_held_statements(self):
        file = SimpleNamespace(metadata_={})
        self.assertIsNone(vr.eligible(self._item(), file, _proposal()))
        self.assertEqual(vr.eligible(self._item(status='ready'), file, _proposal()), 'not_held')
        self.assertEqual(vr.eligible(self._item(review_request={'rows': []}), file, _proposal()), 'investigator_work')
        saved = SimpleNamespace(metadata_={'financial_review_progress': {'s1': {'request': {}}}})
        self.assertEqual(vr.eligible(self._item(), saved, _proposal()), 'investigator_work')
        self.assertEqual(vr.eligible(self._item(), file, dict(_proposal(), current_import={'x': 1})), 'saved')
        self.assertEqual(vr.eligible(self._item(), file, dict(_proposal(), not_payment_statement={'k': 1})), 'not_payment')
        self.assertEqual(vr.eligible(self._item(summary={'duplicate_disposition': {'status': 'ignored'}}), file,
                                     _proposal()), 'duplicate')


class FailClosedTest(unittest.TestCase):
    def test_switch_off_reads_nothing(self):
        with mock.patch.object(vr, 'ENABLED', False):
            self.assertEqual(vr.sweep(None, None)['read'], 0)

    def test_provider_without_page_images_or_key_is_unavailable(self):
        db = object()
        with mock.patch('services.ai_model_policy.get_workload_model', return_value=('anthropic', 'claude-sonnet-5')):
            with self.assertRaisesRegex(RuntimeError, 'not available'):
                vr.openai_page_reader(db, 'c')
        with mock.patch('services.ai_model_policy.get_workload_model', return_value=('openai', 'gpt-4o')), \
                mock.patch('services.ai_provider_credentials.get_provider_api_key', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'No OpenAI key'):
                vr.openai_page_reader(db, 'c')

    def test_vision_call_is_schema_enforced_and_raises_on_incomplete_or_refused(self):
        from services.llm_service import LLMExecutionContext
        context = LLMExecutionContext('openai', 'gpt-4o', api_key='test')
        calls = []

        def answer(finish='stop', refusal=None, content='{"ok": true}'):
            message = SimpleNamespace(content=content, refusal=refusal)
            return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish)],
                                   usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                                   model='gpt-4o', id='r1')
        fake = mock.Mock()
        fake.chat.completions.create.side_effect = lambda **kw: calls.append(kw) or answer()
        context._client = fake
        self.assertEqual(json.loads(context.call_vision_json('p', [b'png'], schema={'type': 'object'}, schema_name='s')), {'ok': True})
        sent = calls[0]
        self.assertEqual(sent['response_format']['json_schema']['strict'], True)
        self.assertEqual(sent['messages'][0]['content'][1]['image_url']['detail'], 'high')
        self.assertNotIn('png', json.dumps(context.last_request_arguments))
        self.assertEqual(context.last_usage['prompt_tokens'], 10)
        fake.chat.completions.create.side_effect = lambda **kw: answer(finish='length')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            context.call_vision_json('p', [b'png'], schema={}, schema_name='s')
        fake.chat.completions.create.side_effect = lambda **kw: answer(refusal='no')
        with self.assertRaisesRegex(ValueError, 'declined'):
            context.call_vision_json('p', [b'png'], schema={}, schema_name='s')
        with self.assertRaisesRegex(ValueError, 'not available'):
            LLMExecutionContext('gemini', 'gemini-3.6-flash', api_key='x').call_vision_json('p', [], schema={}, schema_name='s')

    def test_workload_registered_and_kept_on_openai(self):
        from services.ai_model_policy import DEFAULT_POLICY, PROVIDER_DEFAULTS, WORKLOADS
        self.assertIn(vr.WORKLOAD, WORKLOADS)
        self.assertEqual(DEFAULT_POLICY[vr.WORKLOAD]['provider'], 'openai')
        for profile in PROVIDER_DEFAULTS.values():
            self.assertEqual(profile[vr.WORKLOAD]['provider'], 'openai')

    def test_case_budget(self):
        with mock.patch.dict(vr._spend, {}, clear=True):
            vr._add_spend('case', 1.25)
            vr._add_spend('case', 0.25)
            self.assertAlmostEqual(vr.spent('case'), 1.5)
            self.assertEqual(vr.spent('other'), 0.0)


if __name__ == '__main__':
    unittest.main()
