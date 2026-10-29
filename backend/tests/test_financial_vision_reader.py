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

    def test_a_clabe_names_the_account_its_account_digits_hold(self):
        # Live: 06 ING. R2 MONEX MXN JUN 24, the images print CLABE 112180000030419770, the text the contract 3041977.
        self.assertTrue(vr.same_number('3041977', '112180000030419770'))
        self.assertFalse(vr.same_number('3041977', '112180000030419771'))  # check digit wrong: not a CLABE
        self.assertFalse(vr.same_number('3041978', '112180000030419770'))
        with mock.patch.object(vr, 'CLABE_ACCOUNT', False):
            self.assertFalse(vr.same_number('3041977', '112180000030419770'))

    def test_cost_per_page(self):
        self.assertAlmostEqual(vr.cost_usd('gpt-4o', dict(prompt_tokens=1_000_000, completion_tokens=0)), 2.5)
        self.assertAlmostEqual(vr.cost_usd('gpt-4o-2024-08-06', dict(prompt_tokens=0, completion_tokens=1_000_000)), 10.0)
        self.assertEqual(vr.price('unknown-model'), vr.FALLBACK_PRICE)


class ProofTest(unittest.TestCase):
    def test_a_section_heading_number_printed_beside_the_statement_clabe_is_its_account(self):
        # Live: 07 ARRENDO KAPITAL MXN JUL 26 and 8 other Kapital statements, the images give the heading's
        # '194-99292-001-6', the text reading the CLABE printed on the same line; every one matched no section.
        clabe = '128180000000109664'
        heading = dict(kind='header', fields={}, source_cells=[
            dict(expected_text='SERVICIO EMPRESARIAL FX KAPITAL 194-99292-001-6'), dict(expected_text='CLABE ' + clabe)])
        pages = _balanced_pages()
        pages[0][1]['sections'][0]['account_number'] = '194-99292-001-6'
        proposal = _proposal([heading], account_number=clabe)
        reading = _proved(proposal, _knowledge(account=clabe), pages)
        self.assertEqual((reading['account_number'], len(reading['rows'])), (clabe, 3))
        with mock.patch.object(vr, 'SECTION_NUMBER', False):
            with self.assertRaisesRegex(vr.NotProved, 'no account section matching'):
                _proved(proposal, _knowledge(account=clabe), pages)
        # A line printing another number as well names no one section number; a payment line is never a heading.
        for cells, kind in (([heading['source_cells'][0], dict(expected_text='CLABE %s 012790001102745939' % clabe)], 'header'),
                            (heading['source_cells'], 'transaction')):
            with self.assertRaisesRegex(vr.NotProved, 'no account section matching'):
                _proved(_proposal([dict(kind=kind, fields={}, source_cells=cells)], account_number=clabe),
                        _knowledge(account=clabe), pages)

    def test_the_images_reading_the_clabe_match_a_statement_read_by_its_printed_number(self):
        # The text reading names the account by the printed '194-99292-001-6' and keeps the CLABE beside it.
        clabe = '128180000000109664'
        heading = dict(kind='header', fields={}, source_cells=[
            dict(expected_text='SERVICIO EMPRESARIAL FX KAPITAL 194-99292-001-6'), dict(expected_text='CLABE ' + clabe)])
        proposal = _proposal([heading], account_number='194-99292-001-6', account_clabe=clabe)
        for printed in (clabe, '194-99292-001-6'):
            pages = _balanced_pages()
            pages[0][1]['sections'][0]['account_number'] = printed
            reading = _proved(proposal, _knowledge(account='194992920016'), pages)
            self.assertEqual(len(reading['rows']), 3)

    def test_a_section_printing_zero_counts_and_totals_proves_a_quiet_period(self):
        # Live: ECO Feb..Nov 2023 DOLARES and BBVA 23 USD, one page of a "PAGINA n/5" printing: 0 deposits,
        # 0 withdrawals, totals 0.00, 60.25 at both ends.
        from services.financial.statement_admission import source_proves_no_activity
        quiet = dict(HEADER, opening_balance='60.25', closing_balance='60.25', count_credits=0, count_debits=0,
                     total_credits='0.00', total_debits='0.00')
        pages = [(1, _page([_section([], **quiet)], 2, 5))]
        proposal = _proposal(account_number='0123456789', currency='MXN', period_start='2025-12-01', period_end='2025-12-31')
        section = vr.choose_section(vr.combine(pages), proposal)
        reading = vr.prove(proposal, section, _knowledge())
        self.assertEqual((reading['rows'], reading['opening'], reading['closing']), ([], 6025, 6025))
        request = vr.build_request(proposal, reading)
        controls = vr.printed_controls(proposal, section, reading, request)
        evidence = vr.image_evidence(proposal, controls)['no_activity_evidence']
        self.assertEqual(evidence['basis'], 'page_image_zero_counts')
        self.assertTrue(source_proves_no_activity(evidence, request))
        edited = dict(request, rows=[dict(r, balance_minor='6000') if r['id'] == evidence['closing_row_id'] else r
                                     for r in request['rows']])
        self.assertFalse(source_proves_no_activity(evidence, edited))
        # A count not printed as zero, a non-zero total or balances that differ prove nothing.
        for change in (dict(count_debits=1), dict(total_credits='0.01'), dict(closing_balance='60.00')):
            pages = [(1, _page([_section([], **dict(quiet, **change))], 2, 5))]
            with self.assertRaises(vr.NotProved):
                vr.prove(proposal, vr.choose_section(vr.combine(pages), proposal), _knowledge())
        with mock.patch.object(vr, 'QUIET_PRINTED', False):
            pages = [(1, _page([_section([], **quiet)], 2, 5))]
            with self.assertRaisesRegex(vr.NotProved, 'No payments were read'):
                vr.prove(proposal, vr.choose_section(vr.combine(pages), proposal), _knowledge())

    def test_an_opening_the_pages_do_not_print_is_the_closing_less_the_payments_when_a_neighbour_confirms_it(self):
        # fin-queue3 L8 (BNB2 ECO Ago 2023 MN): bank pages 2-16 of 20, the summary page with the opening balance is not
        # in the production; 180 payments, their printed counts and totals, and the closing are read.
        from dataclasses import replace
        pages = _balanced_pages()
        pages[0][1]['sections'][0].update(opening_balance=None, count_debits=2, total_debits='100.00')
        proposal = _proposal(account_number='0123456789', currency='MXN', period_start='2025-12-01', period_end='2025-12-31')

        def knowledge(*statements):
            known = _knowledge()
            known.accounts[0].statements[:] = list(statements)
            return known
        before = replace(_knowledge().accounts[0].statements[0], closing_minor=100000)
        after = replace(before, period_start='2026-01-01', period_end='2026-01-31', opening_minor=100000, closing_minor=None)
        for neighbours, confirmed in (((before,), 'the previous saved statement, to 2025-11-30'),
                                      ((after,), 'the next saved statement, from 2026-01-01')):
            reading = vr.prove(proposal, vr.choose_section(vr.combine(pages), proposal), knowledge(*neighbours))
            self.assertEqual((reading['opening'], reading['closing'], reading['opening_previous_end']),
                             (100000, 100000, confirmed))
            request = vr.build_request(proposal, reading)
            opening = next(r for r in request['rows'] if r['id'] == 'manual:opening-balance')
            self.assertEqual((opening['balance_minor'], opening['manual_page']), ('100000', 1))
            self.assertIn('Opening balance not printed in these pages', opening['reason'])
            self.assertIn(confirmed, opening['reason'])
        refused = dict(
            previous_differs=knowledge(replace(before, closing_minor=99900)),
            next_differs=knowledge(before, replace(after, opening_minor=99900)),
            no_neighbour=knowledge(replace(before, period_start='2025-10-01', period_end='2025-10-27')),
            no_balances=knowledge(replace(before, closing_minor=None)))
        for name, known in refused.items():
            with self.assertRaisesRegex(vr.NotProved, 'opening balance is not printed', msg=name):
                vr.prove(proposal, vr.choose_section(vr.combine(pages), proposal), known)
        # A printed count or total missing, or disagreeing with the payments read, fixes nothing.
        for change in (dict(count_credits=None), dict(total_debits='100.01'), dict(count_debits=3)):
            changed = _balanced_pages()
            changed[0][1]['sections'][0].update(dict(dict(opening_balance=None, count_debits=2, total_debits='100.00'),
                                                     **change))
            with self.assertRaises(vr.NotProved, msg=str(change)):
                vr.prove(proposal, vr.choose_section(vr.combine(changed), proposal), knowledge(before))
        with mock.patch.object(vr, 'OPENING_FROM_PREVIOUS', False):
            with self.assertRaisesRegex(vr.NotProved, 'opening or closing balance could not be read'):
                vr.prove(proposal, vr.choose_section(vr.combine(pages), proposal), knowledge(before))

    def test_a_proved_reading_s_printed_counts_reach_later_readings_and_settle_the_page_gap(self):
        # Live: ECO Jun 2023 MN, 15 of 20 printed pages; the text reading sees the gap and reads no totals, the images
        # print 3 deposits / 203 withdrawals and their totals, and the 206 payments read match all four.
        from services.financial import import_issues
        from services.financial.statement_import import StatementReviewDraft
        proposal = _proposal(account_number='0123456789', currency='MXN', period_start='2025-12-01', period_end='2025-12-31')
        pages = _balanced_pages()
        pages[0][1]['sections'][0].update(count_credits=1, count_debits=2, total_credits='100.00', total_debits='100.00')
        section = vr.choose_section(vr.combine(pages), proposal)
        reading = vr.prove(proposal, section, _knowledge())
        request = vr.build_request(proposal, reading)
        controls = vr.printed_controls(proposal, section, reading, request)
        self.assertEqual((controls['count_debits'], controls['total_debits_minor']), (2, 10000))
        file = SimpleNamespace(metadata_={vr.METADATA_KEY: {'b' * 64: dict(status='proved', revision='a' * 64,
                                                                          printed_controls=controls)}})
        stored = vr.stored_image_evidence(file, dict(proposal, statement_id='b' * 64))
        self.assertEqual(stored['image_printed_controls'], controls)
        self.assertEqual(vr.stored_image_evidence(file, dict(proposal, statement_id='b' * 64, revision='c' * 64)), {})
        draft = StatementReviewDraft.model_validate(dict(request, holder='ACME SA DE CV', account_number='0123456789',
                                                         institution='BBVA MEXICO'))
        gap = dict(printed_total=20, missing=[8, 9], held=18)
        held = lambda proposal, draft: [i['kind'] for i in import_issues.retained_issues(dict(proposal, printed_pages_missing=gap), draft)
                                        if i['kind'] == 'printed_pages_missing']
        self.assertEqual(held(dict(proposal, **stored), draft), [])
        self.assertEqual(held(proposal, draft), ['printed_pages_missing'])
        # A payment a person typed in is not one the images' counts were proved against.
        typed = draft.model_copy(update=dict(rows=[r.model_copy(update=dict(id='manual:typed')) if r.id.startswith('manual:vision-')
                                                   and r.direction == 'credit' else r for r in draft.rows]))
        self.assertEqual(held(dict(proposal, **stored), typed), ['printed_pages_missing'])

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
        with mock.patch.object(vr, 'PRINTED_ORDER', False):
            with self.assertRaisesRegex(vr.NotProved, 'skip'):
                vr.check_page_numbering(numbered((1, 2), (2, 1)), [1, 2, 3])
        # Printed 2, 1 is one complete run: read in printed order where the caller checks it (see PrintedOrderTest).
        self.assertTrue(vr.check_page_numbering(numbered((1, 2), (2, 1)), [1, 2, 3], printed_order=True))
        with self.assertRaisesRegex(vr.NotProved, 'skip'):
            vr.check_page_numbering(numbered((1, 2), (2, 1)), [1, 2, 3])
        with self.assertRaisesRegex(vr.NotProved, 'skip'):
            vr.check_page_numbering(numbered((1, 3), (2, 1)), [1, 2, 3], printed_order=True)
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
        with self.assertRaisesRegex(vr.NotProved, 'No statement of account 0123456789 is confirmed in this case yet'):
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


class PrintedOrderTest(unittest.TestCase):
    """Live: Andrews "statement 820433320 Pt 1" Dec 2020 is file pages 38,37,36,35,39,40 printing 1..6 (scanned out of
    order); both page-image readings read the numbering right and the file-order check refused them."""

    def _document(self, numbering):
        first, second, third = (numbering[printed] for printed in sorted(numbering))
        rows = [dict(_row('2025-12-02', '100.00', 'credit', '1100.00'), page=first),
                dict(_row('2025-12-05', '30.50', 'debit', '1069.50'), page=second),
                dict(_row('2025-12-20', '69.50', 'debit', '1000.00'), page=third)]
        account = dict(_section(**HEADER), opening_balance='1000.00', opening_balance_page=first,
                       closing_balance='1000.00', closing_balance_page=third, rows=rows)
        return dict(pages=[dict(page=physical, printed_page_number=printed, printed_page_total=3, is_statement_page=True)
                           for printed, physical in numbering.items()], accounts=[account])

    def _proposal(self, sent, text_pages=None):
        # The text reading: one (set aside) payment line per page, in the order the text reader keeps the pages.
        text = [dict(id='t%d' % page, kind='transaction', page_number=page, excluded=False, issues=[], fields={})
                for page in (text_pages or sent)]
        return dict(_proposal(text, currency='MXN'), page_numbers=sorted(sent), statement_page_numbers=list(sent))

    def _prove(self, document, sent, file_pages=None, text_pages=None):
        # As judge: the order check, then the pages as the text reading keeps them.
        proposal = self._proposal(sent, text_pages)
        pages = vr.document_pages(document, sent)
        if vr.check_page_numbering(pages, file_pages or sorted(sent), printed_order=True):
            vr.check_text_keeps_printed_order(document, proposal, sent)
        return vr.prove(proposal, vr.choose_section(vr.combine(pages), proposal), _knowledge())

    def _saved_order(self, document, sent):
        from services.financial.manual_row_placement import place_manual_rows
        proposal = self._proposal(sent)
        request = vr.build_request(proposal, self._prove(document, sent))
        effective = list(proposal['rows']) + [
            dict(id=r['id'], kind='manual_entry', excluded=False, issues=[], page_number=r['manual_page'],
                 fields=dict(r)) for r in request['rows'] if r['id'].startswith('manual:vision-')]
        placed = place_manual_rows(effective, {r['id']: r for r in proposal['rows']},
                                   statement_pages=proposal['statement_page_numbers'])
        return [(r['page_number'], r['fields']['balance_minor']) for r in placed if r['kind'] == 'manual_entry']

    def test_pages_scanned_in_reverse_are_read_in_printed_order(self):
        document = self._document({1: 7, 2: 6, 3: 5})
        reading = self._prove(document, [7, 6, 5])
        self.assertEqual([r['page'] for r in reading['rows']], [7, 6, 5])
        self.assertEqual(reading['closing'], 100000)
        # The saved review keeps the printed order, so its running balances chain as printed.
        self.assertEqual(self._saved_order(document, [7, 6, 5]), [(7, '110000'), (6, '106950'), (5, '100000')])
        self.assertEqual(vr.printed_order(document, [5, 6, 7]), [7, 6, 5])
        with mock.patch.object(vr, 'PRINTED_ORDER', False):
            with self.assertRaisesRegex(vr.NotProved, 'skip from page'):
                self._prove(document, [7, 6, 5])

    def test_the_text_reading_must_keep_the_printed_order_too(self):
        # The saved review places the image rows beside the text rows page by page: a text reading in file order
        # would save them out of printed order, so the statement holds.
        document = self._document({1: 7, 2: 6, 3: 5})
        with self.assertRaisesRegex(vr.NotProved, 'does not read them in the printed order'):
            self._prove(document, [5, 6, 7])
        with self.assertRaisesRegex(vr.NotProved, 'does not read them in the printed order'):
            self._prove(document, [7, 6, 5], text_pages=[5, 6, 7])
        # Pages in file order printing a rising run are not affected.
        rising = self._document({1: 5, 2: 6, 3: 7})
        self.assertEqual(self._prove(rising, [5, 6, 7], text_pages=[5, 6, 7])['closing'], 100000)

    def test_the_live_shape_pages_out_of_order_then_in_order(self):
        # File pages 38,37,36 print 1,2,3 then 39 prints 4 (the live period, shortened).
        document = self._document({1: 38, 2: 37, 3: 36})
        document['pages'].append(dict(page=39, printed_page_number=4, printed_page_total=4, is_statement_page=True))
        for entry in document['pages']:
            entry['printed_page_total'] = 4
        self.assertEqual(vr.printed_order(document, [36, 37, 38, 39]), [38, 37, 36, 39])
        self.assertEqual(self._prove(document, [38, 37, 36, 39], text_pages=[38, 37, 36])['closing'], 100000)

    def test_judge_applies_the_order_check_only_where_printed_order_let_the_pages_pass(self):
        document = self._document({1: 7, 2: 6, 3: 5})
        with mock.patch.object(vr, 'check_text_keeps_printed_order', side_effect=vr.NotProved('order')) as check, \
                mock.patch.object(vr, 'choose_section', side_effect=vr.NotProved('section')):
            with mock.patch.object(vr, 'PRINTED_COUNTS', False):
                with self.assertRaisesRegex(vr.NotProved, '^order$'):
                    vr.judge(None, 'c', self._proposal([5, 6, 7]), document, [5, 6, 7], _knowledge())
            # As before the rule, pages out of order are a page gap the printed counts may settle (judged on).
            with self.assertRaisesRegex(vr.NotProved, '^section$'):
                vr.judge(None, 'c', self._proposal([5, 6, 7]), document, [5, 6, 7], _knowledge())
            # Pages rising in file order, or a numbering refused outright (left to the page-gap path): not checked.
            with self.assertRaisesRegex(vr.NotProved, '^section$'):
                vr.judge(None, 'c', self._proposal([5, 6, 7]), self._document({1: 5, 2: 6, 3: 7}), [5, 6, 7], _knowledge())
            gap = self._document({1: 7, 2: 6, 3: 5})
            gap['pages'][2]['printed_page_number'] = 4
            with self.assertRaisesRegex(vr.NotProved, '^section$|skip'):
                vr.judge(None, 'c', self._proposal([5, 6, 7]), gap, [5, 6, 7], _knowledge())
            self.assertEqual(check.call_count, 2)

    def test_text_in_file_order_with_all_four_printed_counts_proves_in_file_order_as_before(self):
        # Review: images misreading 1,2,3 as 2,1,3 while the text keeps file order: the printed counts settle it,
        # read in file order (the order saved), as before the rule.
        document = self._document({1: 5, 2: 6, 3: 7})
        for entry in document['pages']:
            entry['printed_page_number'] = {5: 2, 6: 1, 7: 3}[entry['page']]
        document['accounts'][0].update(total_credits='100.00', total_debits='100.00', count_credits=1, count_debits=2)
        proposal = self._proposal([5, 6, 7])
        pages = vr.document_pages(document, [5, 6, 7])
        self.assertTrue(vr.check_page_numbering(pages, [5, 6, 7], printed_order=True))
        # Without the caller's order check (a page-image example has no text reading), the old rule stands.
        with self.assertRaisesRegex(vr.NotProved, 'skip'):
            vr.check_page_numbering(pages, [5, 6, 7])
        with self.assertRaisesRegex(vr.NotProved, 'does not read them in the printed order'):
            vr.check_text_keeps_printed_order(document, proposal, [5, 6, 7])
        section = vr.choose_section(vr.combine(pages), proposal)
        self.assertEqual([r['page'] for r in vr.prove(proposal, section, _knowledge())['rows']], [5, 6, 7])

    def test_a_gap_or_a_number_twice_still_holds_whatever_the_order(self):
        gap = self._document({1: 7, 2: 6, 3: 5})
        gap['pages'][2]['printed_page_number'] = 4  # printed 3 missing
        self.assertEqual(vr.printed_order(gap, [5, 6, 7]), [5, 6, 7])
        with self.assertRaisesRegex(vr.NotProved, 'skip|missing'):
            self._prove(gap, [7, 6, 5])
        twice = self._document({1: 7, 2: 6, 3: 5})
        twice['pages'][2]['printed_page_number'] = 2
        with self.assertRaisesRegex(vr.NotProved, 'same page number|skip'):
            self._prove(twice, [7, 6, 5])
        # Printed pages before the run must still be pages of the file outside the period.
        later = self._document({2: 7, 3: 6, 4: 5})
        for entry in later['pages']:
            entry['printed_page_total'] = 4
        with self.assertRaisesRegex(vr.NotProved, 'may be missing'):
            self._prove(later, [7, 6, 5], [5, 6, 7])
        # A page of the file after the period cannot stand for printed page 1 before it.
        with self.assertRaisesRegex(vr.NotProved, 'not in the file|skip'):
            self._prove(later, [7, 6, 5], [5, 6, 7, 8])
        self.assertEqual(self._prove(later, [7, 6, 5], [4, 5, 6, 7])['closing'], 100000)

    def test_rows_out_of_printed_order_still_fail_the_running_balance(self):
        # Numbers misread so the run is complete but the true order differs: the balances refuse it.
        document = self._document({1: 7, 2: 6, 3: 5})
        for entry in document['pages']:
            entry['printed_page_number'] = {7: 2, 6: 1, 5: 3}[entry['page']]
        with self.assertRaisesRegex(vr.NotProved, 'running balance|opening'):
            self._prove(document, [6, 7, 5])


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

    def test_a_text_total_the_scan_misread_takes_the_total_the_images_read_and_checked(self):
        # fin-queue3 L8 (BNB2 09 BBVA 23 MXN): the text reading's deposit total is 3,428,314.57, the images print
        # 3,129,314.57, the one deposit read; the text's total held the period the images prove.
        from services.financial.review_arithmetic import arithmetic_problems, check_proposed_rows
        misread = dict(id='s1', kind='statement_total', excluded=True, issues=[], page_number=1,
                       fields=dict(description='Total credit', balance='10100', total_direction='credit',
                                   printed_transaction_count='1'))
        proposal = _proposal([misread])
        reading = _proved(proposal)
        self.assertEqual(reading['printed_totals'], dict(credit=10000, debit=10000))
        request = vr.build_request(proposal, reading)
        total = next(r for r in request['rows'] if r['id'] == 's1')
        self.assertEqual((total['balance_minor'], total['excluded']), ('10000', True))
        self.assertEqual(total['reason'], vr.TOTAL_REASON.format(page=1))
        self.assertFalse(arithmetic_problems(check_proposed_rows(proposal, request['rows'])))
        with mock.patch.object(vr, 'IMAGE_TOTALS', False):
            request = vr.build_request(proposal, reading)
        self.assertEqual(next(r for r in request['rows'] if r['id'] == 's1')['balance_minor'], '10100')
        self.assertEqual([p['check'] for p in arithmetic_problems(check_proposed_rows(proposal, request['rows']))],
                         ['credit_total'])

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

    def test_only_approved_cases_are_read(self):
        approved_case, other_case = 'D5B330D1-0000-0000-0000-000000000001', '49494305-0000-0000-0000-000000000002'
        with mock.patch.object(vr, 'APPROVED_CASES', frozenset({approved_case.lower()})):
            self.assertTrue(vr.approved(approved_case))
            self.assertFalse(vr.approved(other_case))
        with mock.patch.object(vr, 'APPROVED_CASES', frozenset()):
            self.assertFalse(vr.approved(approved_case))  # unset: no case's images are sent

    def test_star_approves_every_case(self):
        with mock.patch.object(vr, 'APPROVED_CASES', frozenset({vr.EVERY_CASE})):
            self.assertTrue(vr.approved('D5B330D1-0000-0000-0000-000000000001'))
            self.assertTrue(vr.approved('49494305-0000-0000-0000-000000000002'))

    def test_pending_skips_cases_not_approved(self):
        class Db:
            def __init__(self):
                self.calls = 0

            def execute(self, statement):
                self.calls += 1
                return [('batch-1', 'other-case', [{vr.MARK: True, 'file_id': 'f1'}])]
        db = Db()
        with mock.patch.object(vr, 'APPROVED_CASES', frozenset({'bnb2'})):
            self.assertEqual(vr.pending(db), [])
        self.assertEqual(db.calls, 1)  # no item query: nothing of the unapproved case is looked at

    def test_read_item_refuses_a_case_not_approved_before_any_request(self):
        item = SimpleNamespace(batch_id='b', file_id='f', statement_key='k')
        batch = SimpleNamespace(case_id='other-case', status='review', files=[])

        class Db:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, model, key):
                return {'b': batch, 'f': object()}.get(key, item)
        reader = mock.Mock()
        with mock.patch.object(vr, 'APPROVED_CASES', frozenset({'bnb2'})):
            out = vr.read_item(lambda: Db(), 'item', None, page_reader=reader, knowledge_for=lambda *a: None)
        self.assertEqual(out['reason'], 'case_not_approved')
        reader.assert_not_called()

    def test_read_item_leaves_a_file_removed_from_financial_without_reading_it(self):
        # Live 10-26 10:18: the sweep read held items of removed files and logged a failure for each.
        item = SimpleNamespace(batch_id='b', file_id='f', statement_key='k')
        batch = SimpleNamespace(case_id='bnb2', status='review', files=[])
        removed = SimpleNamespace(metadata_={'financial_file_visibility': {'removed': True}})

        class Db:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, model, key):
                return {'b': batch, 'f': removed}.get(key, item)
        reader = mock.Mock()
        with mock.patch.object(vr, 'APPROVED_CASES', frozenset({'bnb2'})), \
                mock.patch('services.financial.statement_import.read_statement_import') as read:
            out = vr.read_item(lambda: Db(), 'item', None, page_reader=reader, knowledge_for=lambda *a: None)
        self.assertEqual(out['reason'], 'file_removed')
        read.assert_not_called()
        reader.assert_not_called()

    def test_provider_without_page_images_or_key_is_unavailable(self):
        db = object()
        with self.assertLogs(vr.log.name, 'WARNING'):
            self.assertIn('not available', vr.provider_page_reader(db, 'c', 'anthropic', 'claude-sonnet-5').unavailable)
        with mock.patch('services.ai_provider_credentials.get_provider_api_key', return_value=None), \
                mock.patch('services.ai_model_policy.deepseek_only', return_value=False), \
                self.assertLogs(vr.log.name, 'WARNING'):
            with self.assertRaisesRegex(RuntimeError, 'no OpenAI key'):
                vr.openai_page_reader(db, 'c', 'gpt-4o')
            self.assertEqual(vr.provider_page_reader(db, 'c', 'deepseek', 'deepseek-flash').unavailable,
                             'no DeepSeek key is connected')

    def test_deepseek_only_on_no_openai_reader_is_made_anywhere(self):
        # "DeepSeek only" ON: OpenAI alone, the learning loop's default reader and the chain never get an OpenAI
        # reader (its key is not even read).
        db = object()
        chain = [{'provider': 'deepseek', 'model_id': 'deepseek-flash'}, {'provider': 'openai', 'model_id': 'gpt-4o'}]
        key = mock.Mock(return_value=None)
        with mock.patch('services.ai_model_policy.deepseek_only', return_value=True), \
                mock.patch('services.ai_model_policy.get_workload_chain', return_value=chain), \
                mock.patch('services.ai_provider_credentials.get_provider_api_key', key), \
                self.assertLogs(vr.log.name, 'WARNING'):
            with self.assertRaisesRegex(RuntimeError, 'OpenAI failover is switched off'):
                vr.openai_page_reader(db, 'c', 'gpt-4o')
            with self.assertRaisesRegex(RuntimeError, 'no DeepSeek key is connected.*OpenAI failover is switched off'):
                vr.workload_page_reader(db, 'c')
        self.assertEqual([c.args[1] for c in key.call_args_list], ['deepseek'])
        self.assertEqual(vr.reserve_usd('deepseek-flash', [(1, [b'png'])]),
                         vr.reserve_usd('deepseek-flash', [(1, [b'png'])], vr.DEEPSEEK_RESERVE_OUTPUT_TOKENS))

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

    def test_workload_is_deepseek_first_with_the_openai_failsafe(self):
        from services.ai_model_policy import DEFAULT_POLICY, PROVIDER_DEFAULTS, WORKLOADS
        self.assertIn(vr.WORKLOAD, WORKLOADS)
        for profile in (DEFAULT_POLICY, *PROVIDER_DEFAULTS.values()):
            self.assertEqual(profile[vr.WORKLOAD]['chain'], [{'provider': 'deepseek', 'model_id': 'deepseek-flash'},
                                                            {'provider': 'openai', 'model_id': 'gpt-5.6-terra'}])
            self.assertEqual(profile[vr.WORKLOAD]['provider'], 'deepseek')

    def test_case_budget(self):
        with mock.patch.dict(vr._spend, {}, clear=True):
            vr._add_spend('case', 1.25)
            vr._add_spend('case', 0.25)
            self.assertAlmostEqual(vr.spent('case'), 1.5)
            self.assertEqual(vr.spent('other'), 0.0)



class FirstStatementTest(unittest.TestCase):
    """Rule 1 (Neil, 2026-10-27): the first statement of an account, no saved statement to confirm it."""
    TEXT = dict(account_number='0123456789', holder='ACME SA DE CV', institution='BBVA MEXICO', currency='MXN',
                period_start='2025-12-01', period_end='2025-12-31')

    def _first(self, pages=None, knowledge=None, **text):
        return _proved(_proposal(**dict(self.TEXT, **text)), knowledge=knowledge or CaseKnowledge(accounts=[]), pages=pages)

    def _pages(self, **header):
        pages = _balanced_pages()
        pages[0][1]['sections'][0].update(header)
        return pages

    def test_full_number_holder_and_bank_agreeing_with_the_text_prove_it(self):
        reading = self._first()
        self.assertEqual(reading['account_basis'], 'page_image_header_matches_text')
        self.assertEqual(reading['account_keys'], [])
        self.assertEqual((reading['opening'], reading['closing'], len(reading['rows'])), (100000, 100000, 3))
        # The bank spelled differently but naming the same bank is the same bank.
        self.assertEqual(self._first(institution='BBVA')['account_basis'], 'page_image_header_matches_text')

    def test_a_masked_or_partial_number_holds(self):
        # Not a card statement: rule 1 needs the full number, and LAST4 is for cards only.
        masked = r'The bank prints only the last 4 digits of this account \(ending 6789\) and no statement of it is ' \
                 r'confirmed in this case yet\. Confirm one statement of this account and the rest can follow\.'
        with self.assertRaisesRegex(vr.NotProved, masked + ' .*not a card statement'):
            self._first(account_number='******6789')
        with self.assertRaisesRegex(vr.NotProved, masked + ' .*not a card statement'):
            self._first(pages=self._pages(account_number='XXXX6789'), account_number='XXXX6789')
        with self.assertRaisesRegex(vr.NotProved, masked + ' .*not a card statement'):
            self._first(pages=self._pages(account_number='6789'), account_number='6789')

    def test_every_header_value_must_be_read_by_both(self):
        for field, words in (('holder', 'the account holder'), ('institution', 'the bank')):
            why = 'not accepted as its first because %s is not read from both the page images and the text' % words
            with self.subTest(images_without=field), self.assertRaisesRegex(vr.NotProved, why):
                self._first(pages=self._pages(**{field: ''}))
            with self.subTest(text_without=field), self.assertRaisesRegex(vr.NotProved, why):
                self._first(**{field: ''})
        with self.assertRaisesRegex(vr.NotProved, 'because the full number is not read from both'):
            self._first(account_number='')  # only the images print the number

    def test_disagreeing_values_hold(self):
        with self.assertRaisesRegex(vr.NotProved, 'holder'):
            self._first(holder='SOMEONE ELSE')
        with self.assertRaisesRegex(vr.NotProved, 'bank'):
            self._first(institution='SANTANDER')

    def test_the_currency_must_be_printed(self):
        with self.assertRaisesRegex(vr.NotProved, 'currency is not printed'):
            self._first(pages=self._pages(currency=''), currency='')

    def test_a_saved_account_with_the_number_at_another_bank_holds(self):
        other = _knowledge(institution='SANTANDER')
        with self.assertRaisesRegex(vr.NotProved, 'An account with the same number is saved in this case: 0123456789 at '
                                                  'SANTANDER. This statement .* prints BBVA MEXICO. Confirm which account'):
            self._first(knowledge=other)

    def test_every_other_proof_is_unchanged(self):
        pages = _balanced_pages()
        pages[1][1]['sections'][0]['closing_balance'] = '1000.01'
        with self.assertRaisesRegex(vr.NotProved, 'did not balance'):
            self._first(pages=pages)
        with self.assertRaisesRegex(vr.NotProved, 'period'):
            self._first(period_end='2025-12-30')

    def test_switch_off_holds_and_the_proof_version_counts_it(self):
        with mock.patch.object(vr, 'FIRST_STATEMENT', False), self.assertRaisesRegex(vr.NotProved, 'switched off'):
            self._first()
        self.assertTrue(vr.FIRST_STATEMENT)
        # 13 before rule 1, 14 before row dates, 15 before printed order, 16 before LAST4: stored not-proved readings
        # are judged again once
        self.assertEqual(vr.PROOF_VERSION, 22)

    def test_a_known_account_is_judged_as_before(self):
        self.assertNotIn('account_basis', _proved(_proposal(**self.TEXT)))

if __name__ == '__main__':
    unittest.main()


class SectionByTextTest(unittest.TestCase):
    """Andrews: one member number over several share sections, no currency printed (L17, Erica Jun 2020)."""

    def _andrews(self):
        rows = [dict(kind='balance', fields=dict(description='Opening Balance', balance='72486')),
                dict(kind='balance', fields=dict(description='Closing Balance', balance='70161')),
                dict(kind='transaction', fields=dict(amount_minor='2325', direction='debit', date='2020-06-01'))]
        proposal = _proposal(rows, currency='USD', account_number='820433320 / Share 0040',
                             institution='Andrews Federal Credit Union', holder='ERICA MCCAULEY / LASHIKA HOPPER',
                             period_start='2020-06-01', period_end='2020-06-30')
        header = dict(institution='Andrews', holder='ERICA MCCAULEY LASHIKA HOPPER', account_number='820433320',
                      period_start='2020-06-01', period_end='2020-06-30')
        pages = [(1, _page([_section([], section_name='BASE SHARE SAVINGS', opening_balance='0.00', closing_balance='0.00', **header),
                            _section([_row('2020-06-01', '23.25', 'debit', '701.61')], section_name='FREE CHECKING',
                                     opening_balance='724.86', closing_balance='701.61', **header)], 1, 1))]
        return proposal, pages

    def test_the_section_the_text_reading_identifies(self):
        proposal, pages = self._andrews()
        section = vr.choose_section(vr.combine(pages), proposal)
        self.assertEqual(section['values']['opening_balance'], '724.86')

    def test_off_matches_no_section(self):
        proposal, pages = self._andrews()
        with mock.patch.object(vr, 'SECTION_BY_TEXT', False):
            with self.assertRaises(vr.NotProved):
                vr.choose_section(vr.combine(pages), proposal)

    def test_two_sections_agreeing_stay_unmatched(self):
        proposal, pages = self._andrews()
        pages[0][1]['sections'][0].update(opening_balance='724.86', closing_balance='701.61',
                                          rows=[_row('2020-06-01', '23.25', 'debit', '701.61')])
        with self.assertRaises(vr.NotProved):
            vr.choose_section(vr.combine(pages), proposal)

    def test_text_payment_missing_from_section_is_not_identified(self):
        proposal, pages = self._andrews()
        proposal['rows'].append(dict(kind='transaction', fields=dict(amount_minor='999', direction='debit')))
        with self.assertRaises(vr.NotProved):
            vr.choose_section(vr.combine(pages), proposal)

    def _records(self, second_holders):
        def known(key, institution, holders):
            statements = [SavedStatement(currency='USD', period_start='2021-0%d-01' % (i + 1), period_end='2021-0%d-28' % (i + 1),
                                         institution=institution, holder=h, account_number='8204333200040')
                          for i, h in enumerate(holders)]
            return KnownAccount(key=key, account='8204333200040', digits='8204333200040', masked=False,
                                institution=institution, currency='USD', statements=statements)
        return [known('a1', 'Andrews Federal Credit Union', ['ERICA HOPPER / LASHIKA HOPPER', 'ERICA MCCAULEY / LASHIKA HOPPER']),
                known('a2', 'Andrews', second_holders)]

    def test_spelled_apart_with_a_changed_holder_name_is_one_account(self):
        candidates = self._records(['ERICA MCCAULEY\nLASHIKA HOPPER'])
        found, matched = vr.one_account_spelled_apart(candidates, '820433320 / Share 0040', 'Andrews Federal Credit Union',
                                                      'ERICA HOPPER / LASHIKA HOPPER')
        self.assertEqual(len(found), 2)
        with mock.patch.object(vr, 'SECTION_BY_TEXT', False):
            self.assertEqual(vr.one_account_spelled_apart(candidates, '820433320 / Share 0040', 'Andrews Federal Credit Union',
                                                           'ERICA HOPPER / LASHIKA HOPPER')[1], {'ambiguous'})

    def test_spelled_apart_with_an_unrelated_holder_stays_ambiguous(self):
        candidates = self._records(['JORDAN H HOPPER'])
        self.assertEqual(vr.one_account_spelled_apart(candidates, '820433320 / Share 0040', 'Andrews Federal Credit Union',
                                                      'ERICA HOPPER / LASHIKA HOPPER')[1], {'ambiguous'})


class SummaryPageRowsTest(unittest.TestCase):
    """A summary page is read for the balances and header only: no payment is read from it (SUMMARY_PAGES)."""

    def test_a_row_cited_on_a_summary_page_holds_the_statement(self):
        proposal = dict(_proposal(), statement_page_numbers=[2], summary_page_numbers=[1])
        with self.assertRaisesRegex(vr.NotProved, 'read from page 1, the summary page of this period'):
            _proved(proposal)
        self.assertEqual(len(_proved()['rows']), 3)


class SignedDebitsTest(unittest.TestCase):
    """The images give a withdrawal as printed, '-15.89' (L20, Erica Andrews Dec 2020)."""

    def test_minus_on_a_debit_is_its_amount(self):
        self.assertEqual(vr.row_amount(dict(amount='-15.89', direction='debit'), 2), 1589)
        self.assertEqual(vr.row_amount(dict(amount='15.89', direction='debit'), 2), 1589)

    def test_minus_on_a_credit_is_refused(self):
        self.assertIsNone(vr.row_amount(dict(amount='-15.89', direction='credit'), 2))

    def test_minus_on_a_card_payment_is_its_amount(self):
        # Capital One prints a payment to the card '- $246.92' (fdaf956c): on a liability, the minus is the credit's.
        self.assertEqual(vr.row_amount(dict(amount='-246.92', direction='credit'), 2, liability=True), 24692)
        self.assertIsNone(vr.row_amount(dict(amount='-246.92', direction='credit'), 2, liability=False))
        with mock.patch.object(vr, 'SIGNED_CARD_CREDITS', False):
            self.assertIsNone(vr.row_amount(dict(amount='-246.92', direction='credit'), 2, liability=True))

    def test_off_refuses_the_minus(self):
        with mock.patch.object(vr, 'SIGNED_DEBITS', False):
            self.assertIsNone(vr.row_amount(dict(amount='-15.89', direction='debit'), 2))

    def test_a_signed_withdrawal_reading_proves(self):
        pages = _balanced_pages()
        pages[0][1]['sections'][0]['rows'][1]['amount'] = '-30.50'
        self.assertEqual(_proved()['closing'], 100000)
        self.assertEqual(len(_proved(pages=pages)['rows']), 3)


class DatesFromImageTest(unittest.TestCase):
    """A text reading held only for a row date takes it from the page image (L21, Erica Andrews Dec 2020)."""

    def _proposal(self, date_issue=True, day_issue='Check the full date in the PDF. It could not be read within this statement period.'):
        def payment(id_, day, amount, balance, issues=()):
            fields = dict(amount_minor=amount, direction='debit', balance=balance)
            if day:
                fields['date'] = day
            return dict(id=id_, kind='transaction', excluded=False, page_number=35, issues=list(issues), fields=fields)
        issues = [day_issue] if date_issue else \
            ['Check the transaction amount in the PDF. Its digits, sign or decimal point could not be read.']
        rows = [payment('a', '2020-12-17', '477', '83481'), payment('b', None, '5771', '77710', issues),
                payment('c', '2020-12-18', '1175', '76535')]
        return _proposal(rows, currency='USD', period_start='2020-12-01', period_end='2020-12-31')

    def _readings(self, day='2020-12-18', balance='777.10'):
        return [(35, dict(sections=[dict(rows=[_row('2020-12-17', '-4.77', 'debit', '834.81'),
                                               _row(day, '-57.71', 'debit', balance),
                                               _row('2020-12-18', '-11.75', 'debit', '765.35')])]))]

    def _run(self, proposal, readings, state='ready'):
        request = dict(rows=[dict(id=r['id'], date=r['fields'].get('date', ''), reason='') for r in proposal['rows']])
        with mock.patch('services.financial.import_batches.initial_request', return_value=request), \
                mock.patch('services.financial.import_batches.assess', return_value=(state, {})) as assess:
            result = vr.dates_request(proposal, readings)
        return result, assess

    def test_the_one_matching_image_row_gives_the_date(self):
        result, assess = self._run(self._proposal(), self._readings())
        row = next(r for r in result['rows'] if r['id'] == 'b')
        self.assertEqual(row['date'], '2020-12-18')
        self.assertIn('page 35', row['reason'])
        assess.assert_called_once()

    def test_a_kapital_line_whose_day_the_scan_lost_takes_the_image_date(self):
        # 10 ARRENDO INTERCAM OCT 2022 Hoja 1: '320637478 CARGO A CUENTA DE CHEQUES 462,300.00' read with no DIA cell
        # (between days 5 and 10); the page image reads 05/10 with the same amount and running balance.
        proposal = self._proposal(day_issue='Check the printed day against this statement period.')
        result, _ = self._run(proposal, self._readings())
        self.assertEqual(next(r for r in result['rows'] if r['id'] == 'b')['date'], '2020-12-18')

    def test_a_date_outside_the_payment_order_is_refused(self):
        with self.assertRaises(vr.NotProved):
            self._run(self._proposal(), self._readings(day='2020-12-19'))

    def test_a_row_held_for_its_money_is_refused(self):
        with self.assertRaises(vr.NotProved):
            self._run(self._proposal(date_issue=False), self._readings())

    def test_no_image_row_with_the_same_balance_is_refused(self):
        with self.assertRaises(vr.NotProved):
            self._run(self._proposal(), self._readings(balance='777.11'))

    def test_a_statement_still_held_after_the_dates_is_refused(self):
        with self.assertRaises(vr.NotProved):
            self._run(self._proposal(), self._readings(), state='attention')


class ClosingDaysTest(unittest.TestCase):
    """A card statement printing only its statement date and the days in its billing cycle (L22, Erica Merrick)."""

    CARD = dict(institution='Merrick Bank', holder='LASHIKA M HOPPER', account_number='4120 6180 6507 0753',
                currency='', period_start='', period_end='2022-04-25')

    def _pages(self, interest='39.59', total_interest='39.59', total_fees='0.00', days=31, extra=()):
        rows = [dict(_row('2022-03-31', '250.00', 'credit', description='MOBILE PAYMENT-THANK YOU'), charge_kind=''),
                dict(_row('2022-04-25', interest, 'debit', description='Interest Charge on Purchases'), charge_kind='interest'),
                *extra]
        section = _section(rows, opening_balance='2023.52', closing_balance='1813.11', **self.CARD)
        section.update(days_in_period=days, total_fees=total_fees, total_interest=total_interest)
        return [(19, _page([section], 1, 1))]

    def _proposal(self, rows=()):
        proposal = _proposal(rows, currency='USD', balance_convention='liability_owed', account_number='4120 6180 6507 0753',
                             period_end='2022-04-25')
        proposal.update(page_numbers=[19], statement_page_numbers=[19], sources=[dict(page_number=19, table_index=0)])
        return proposal

    def _knowledge(self):
        return _knowledge(currency='USD', holder='LASHIKA M HOPPER', institution='Merrick Bank', account='4120618065070753')

    def _prove(self, pages=None, proposal=None):
        pages = pages or self._pages()
        proposal = proposal or self._proposal()
        return vr.prove(proposal, vr.choose_section(vr.combine(pages), proposal), self._knowledge())

    def test_the_start_is_the_closing_date_less_the_printed_days(self):
        reading = self._prove()
        self.assertEqual((reading['period_start'], reading['period_end']), ('2022-03-26', '2022-04-25'))
        self.assertEqual((reading['opening'], reading['closing']), (202352, 181311))
        self.assertEqual(reading['charge_totals'], dict(fee=0, interest=3959))

    def test_off_the_period_is_not_read(self):
        with mock.patch.object(vr, 'CLOSING_DAYS', False):
            with self.assertRaisesRegex(vr.NotProved, 'period could not be read'):
                self._prove()

    def test_no_printed_days_reads_no_period(self):
        with self.assertRaisesRegex(vr.NotProved, 'period could not be read'):
            self._prove(self._pages(days=None))
        with self.assertRaisesRegex(vr.NotProved, 'period could not be read'):
            self._prove(self._pages(days=400))

    def test_a_start_the_text_read_differently_holds(self):
        proposal = self._proposal()
        proposal['metadata']['period_start'] = '2022-03-27'
        with self.assertRaisesRegex(vr.NotProved, 'differs from the one read from the text'):
            self._prove(proposal=proposal)

    def test_a_printed_interest_total_must_equal_its_lines(self):
        with self.assertRaisesRegex(vr.NotProved, 'interest charges read do not add up'):
            self._prove(self._pages(total_interest='39.60'))

    def test_a_text_total_read_differently_holds(self):
        control = dict(id='t9', kind='statement_total', excluded=True, issues=[], page_number=19,
                       fields=dict(total_scope='interest', balance='3960', description='TOTAL INTEREST'))
        with self.assertRaisesRegex(vr.NotProved, 'interest total read from the page images differs'):
            self._prove(proposal=self._proposal([control]))

    def test_a_charge_line_printed_as_zero_is_not_a_payment(self):
        zero = dict(_row('2022-04-25', '0.00', 'debit', description='Interest Charge on Cash Advances'), charge_kind='interest')
        reading = self._prove(self._pages(extra=[zero]))
        self.assertEqual(len(reading['rows']), 2)

    def test_the_document_reading_carries_the_days_and_charge_totals(self):
        account = dict(_section(**self.CARD), opening_balance='2023.52', opening_balance_page=19, closing_balance='1813.11',
                       closing_balance_page=19, days_in_period=31, total_fees='0.00', total_interest='39.59',
                       rows=[dict(_row('2022-03-31', '250.00', 'credit'), page=19, charge_kind=''),
                             dict(_row('2022-04-25', '39.59', 'debit'), page=19, charge_kind='interest')])
        document = dict(pages=[dict(page=19, printed_page_number=1, printed_page_total=1, is_statement_page=True)],
                        accounts=[account])
        section = vr.combine(vr.document_pages(document, [19]))[0]
        self.assertEqual(vr.closing_days(section), 31)
        self.assertEqual((section['values']['total_fees'], section['values']['total_interest']), ('0.00', '39.59'))
        self.assertIn('days_in_period', vr.DOCUMENT_SCHEMA['properties']['accounts']['items']['required'])

    def test_admission_takes_the_proved_total_only_for_rows_read_from_the_images(self):
        from services.financial.statement_admission import image_charge_total
        proposal = dict(image_charge_totals=dict(interest=3959))
        image = SimpleNamespace(rows=[SimpleNamespace(id='manual:vision-p19-0', excluded=False)])
        text = SimpleNamespace(rows=[SimpleNamespace(id='t1', excluded=False)])
        self.assertTrue(image_charge_total(proposal, image, 'interest'))
        self.assertFalse(image_charge_total(proposal, image, 'fee'))
        self.assertFalse(image_charge_total(proposal, text, 'interest'))
        self.assertFalse(image_charge_total({}, image, 'interest'))

    def test_stored_evidence_of_a_saved_statement_reading(self):
        file = SimpleNamespace(metadata_={vr.SAVED_KEY: {'k': dict(status='proved', revision='r', charge_totals=dict(fee=0))}})
        self.assertEqual(vr.stored_image_evidence(file, dict(statement_id='k', revision='r')),
                         dict(image_charge_totals=dict(fee=0)))
        self.assertEqual(vr.stored_image_evidence(file, dict(statement_id='k', revision='other')), {})


class TextMisreadsTest(ClosingDaysTest):
    """A damaged text layer's clean-looking misreadings, and card postings dated before the cycle (L24, Merrick)."""

    def _text_row(self, amount, direction, day):
        return dict(id='t' + amount, kind='transaction', excluded=False, issues=[], page_number=19,
                    fields=dict(amount_minor=amount, direction=direction, date=day, description='X'))

    def test_a_payment_whose_minus_the_text_lost_is_found(self):
        self.assertEqual(len(self._prove(proposal=self._proposal([self._text_row('25000', 'debit', '2022-03-31')]))['rows']), 2)

    def test_one_misread_digit_is_found(self):
        self.assertEqual(len(self._prove(proposal=self._proposal([self._text_row('3999', 'debit', '2022-04-25')]))['rows']), 2)

    def test_another_date_or_two_digits_is_missing(self):
        for row in (self._text_row('3999', 'debit', '2022-04-24'), self._text_row('3888', 'debit', '2022-04-25'),
                    self._text_row('399', 'debit', '2022-04-25')):
            with self.subTest(row=row['fields']):
                with self.assertRaisesRegex(vr.NotProved, 'not found in the page-image reading'):
                    self._prove(proposal=self._proposal([row]))

    def test_one_image_row_answers_one_text_payment(self):
        rows = [self._text_row('25000', 'debit', '2022-03-31'), self._text_row('25000', 'credit', '2022-03-31')]
        with self.assertRaisesRegex(vr.NotProved, 'not found'):
            self._prove(proposal=self._proposal(rows))

    def test_off_a_misreading_is_missing(self):
        with mock.patch.object(vr, 'TEXT_MISREADS', False):
            with self.assertRaisesRegex(vr.NotProved, 'not found'):
                self._prove(proposal=self._proposal([self._text_row('25000', 'debit', '2022-03-31')]))

    def test_a_card_posting_dated_days_before_the_cycle_is_this_cycles(self):
        early = dict(_row('2022-03-22', '10.00', 'debit', description='SBARRO'), charge_kind='')
        pages = self._pages(extra=[early])
        pages[0][1]['sections'][0]['closing_balance'] = '1823.11'
        self.assertEqual(len(self._prove(pages)['rows']), 3)
        too_early = dict(early, date='2022-03-20')
        pages = self._pages(extra=[too_early])
        pages[0][1]['sections'][0]['closing_balance'] = '1823.11'
        with self.assertRaisesRegex(vr.NotProved, 'outside the statement period'):
            self._prove(pages)


class RowDatesTest(unittest.TestCase):
    """Row dates the arithmetic cannot check (coordinator 2026-10-28, Andrews 820516588: OpenAI took a neighbour's date)."""

    def _text_row(self, amount, direction, day, **extra):
        return dict(dict(id='t' + amount + day, kind='transaction', excluded=False, issues=[], page_number=1,
                         fields=dict(amount_minor=amount, direction=direction, date=day, description='X')), **extra)

    def _pages(self, *rows, **values):
        values = dict(dict(opening_balance='1000.00', closing_balance='1000.00', **HEADER), **values)
        return [(1, _page([_section(rows, **values)], 1, 1))]

    def _prove(self, pages, text_rows=()):
        proposal = _proposal(text_rows)
        proposal['page_numbers'] = proposal['statement_page_numbers'] = [1]
        return _proved(proposal, pages=pages)

    def test_a_neighbours_date_disagreeing_with_the_text_is_held(self):
        # Printed "11/03 Withdrawal ... -20.00": the page images read the 11/02 of the line above.
        pages = self._pages(_row('2025-12-02', '0.10', 'debit', '999.90'), _row('2025-12-02', '20.00', 'debit', '979.90'),
                            _row('2025-12-05', '20.10', 'credit', '1000.00'))
        text = [self._text_row('10', 'debit', '2025-12-02'), self._text_row('2000', 'debit', '2025-12-03'),
                self._text_row('2010', 'credit', '2025-12-05')]
        with self.assertRaisesRegex(vr.NotProved, 'dated differently'):
            self._prove(pages, text)
        right = self._pages(_row('2025-12-02', '0.10', 'debit', '999.90'), _row('2025-12-03', '20.00', 'debit', '979.90'),
                            _row('2025-12-05', '20.10', 'credit', '1000.00'))
        self.assertEqual(len(self._prove(right, text)['rows']), 3)
        with mock.patch.object(vr, 'ROW_DATES', False):
            self.assertEqual(len(self._prove(pages, text)['rows']), 3)

    def test_same_amounts_on_other_days_are_counted_one_by_one(self):
        pages = self._pages(_row('2025-12-02', '20.00', 'debit', '980.00'), _row('2025-12-02', '20.00', 'debit', '960.00'),
                            _row('2025-12-09', '40.00', 'credit', '1000.00'))
        text = [self._text_row('2000', 'debit', '2025-12-02'), self._text_row('2000', 'debit', '2025-12-03'),
                self._text_row('4000', 'credit', '2025-12-09')]
        with self.assertRaisesRegex(vr.NotProved, 'dated differently'):
            self._prove(pages, text)

    def test_a_text_row_the_reader_doubted_or_without_date_does_not_count(self):
        pages = self._pages(_row('2025-12-02', '20.00', 'debit', '980.00'), _row('2025-12-09', '20.00', 'credit', '1000.00'))
        self._prove(pages, [self._text_row('2000', 'debit', '2025-12-04', issues=['Check the full date in the PDF.'])])
        self._prove(pages, [dict(self._text_row('2000', 'debit', ''))])
        # Held only for the second date printed beside it, its own date still counts.
        beside = self._text_row('2000', 'debit', '2025-12-04', issues=['Check the additional date printed beside this payment. It is unreadable, later than the row date.'])
        with self.assertRaisesRegex(vr.NotProved, 'dated differently'):
            self._prove(pages, [beside])

    def test_out_of_printed_order_is_held(self):
        pages = self._pages(_row('2025-12-02', '9.00', 'debit', '991.00'), _row('2025-12-01', '4.00', 'credit', '995.00'),
                            _row('2025-12-09', '5.00', 'debit', '990.00'), _row('2025-12-10', '10.00', 'credit', '1000.00'))
        with self.assertRaisesRegex(vr.NotProved, 'out of printed order on page 1'):
            self._prove(pages)

    def test_reverse_printed_and_grouped_by_direction_are_in_order(self):
        newest_first = self._pages(_row('2025-12-09', '13.00', 'credit', '1000.00'), _row('2025-12-05', '4.00', 'debit', '987.00'),
                                   _row('2025-12-02', '9.00', 'debit', '991.00'))
        self.assertEqual(len(self._prove(newest_first)['rows']), 3)
        grouped = self._pages(_row('2025-12-03', '5.00', 'credit'), _row('2025-12-20', '8.00', 'credit'),
                              _row('2025-12-01', '9.00', 'debit'), _row('2025-12-15', '4.00', 'debit'))
        self.assertEqual(len(self._prove(grouped)['rows']), 4)
        # Grouped, but a block out of order.
        broken = self._pages(_row('2025-12-03', '5.00', 'credit'), _row('2025-12-20', '8.00', 'credit'),
                             _row('2025-12-15', '9.00', 'debit'), _row('2025-12-01', '4.00', 'debit'))
        with self.assertRaisesRegex(vr.NotProved, 'out of printed order'):
            self._prove(broken)

    def test_a_two_cent_amount_slip_fails_the_printed_running_balance(self):
        # Printed "03/05 Withdrawal Debit Card -11.82  17.80": read as 11.80, a 2.00 read as 2.02 hiding the
        # difference in the closing balance. The running balance after it is checked row by row.
        pages = self._pages(_row('2025-12-02', '115.00', 'debit', '29.62'), _row('2025-12-05', '11.80', 'debit', '17.80'),
                            _row('2025-12-09', '2.02', 'debit', '15.80'), opening_balance='144.62', closing_balance='15.80')
        with self.assertRaisesRegex(vr.NotProved, 'running balance'):
            self._prove(pages)
