"""Real-document ground truth tooling (tier A): readers, reconciliation, harness scoring.

The end-to-end check runs the truth reader over the synthetic corpus, whose
correct values are known: whatever it marks ``verified`` must equal the
corpus manifest exactly, and a reading taken from an OCR layer is never
``verified``.
"""
import hashlib
import json
import os
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from benchmarks.statement_automation import harness, real_inventory, real_truth as rt

try:
    import pdfplumber  # noqa: F401
    import fitz  # noqa: F401
    READERS = True
except ImportError:  # pdfplumber is a private benchmark dependency, not a service one
    READERS = False

CORPUS = Path(harness.__file__).resolve().parent / 'corpus'


def word(text, x0, top=10.0, width=None):
    return dict(text=text, x0=x0, x1=x0 + (width if width is not None else 4.0 * len(text)), top=top, bottom=top + 8)


def page(number, lines):
    built = [rt.Line(10.0 * i, [word(w, 10.0 * j, 10.0 * i) for j, w in enumerate(line.split())])
             for i, line in enumerate(lines)]
    return rt.Page(number, 600.0, built, '\n'.join(l.text for l in built))


def period(**fields):
    base = dict(family='f', institution='i', currency='MXN', holder='H', account='1234',
                period_start='2024-01-01', period_end='2024-01-31', opening_minor=1000, closing_minor=1500)
    base.update(fields)
    return rt.Period(**base)


def row(amount, direction, balance=None, day=5):
    item = dict(date=f'2024-01-{day:02d}', description='x', amount_minor=amount, direction=direction)
    if balance is not None:
        item['balance_after'] = balance
    return item


class ValueReaderTests(unittest.TestCase):
    def test_money_formats(self):
        self.assertEqual(rt.money_minor('1,234.56'), 123456)
        self.assertEqual(rt.money_minor('-12.00'), -1200)
        self.assertEqual(rt.money_minor('(12.00)'), -1200)
        self.assertEqual(rt.money_minor('12.00-'), -1200)
        self.assertEqual(rt.money_minor('$1,000.00'), 100000)
        self.assertIsNone(rt.money_minor('12.0'))
        self.assertIsNone(rt.money_minor('0123456789'))
        self.assertIsNone(rt.money_minor('1,23.45'))

    def test_ocr_money_repairs_only_spacing_letters_and_decimal_comma(self):
        self.assertEqual(rt.ocr_money('1424. 63'), 142463)
        self.assertEqual(rt.ocr_money('107 . 75', negative=True), -10775)
        self.assertEqual(rt.ocr_money('2.ll'), 211)
        self.assertEqual(rt.ocr_money('o.oo'), 0)
        self.assertEqual(rt.ocr_money('240,88'), 24088)
        self.assertEqual(rt.ocr_money('1,240.88'), 124088)
        self.assertIsNone(rt.ocr_money('1269.3'))
        self.assertIsNone(rt.ocr_money('12,345'))

    def test_spaced_digits_merge_only_where_glyphs_touch(self):
        words = [word('SALDO', 0, width=30), word('2', 100, width=4), word(',', 104, width=4), word('5', 108, width=4),
                 word('0', 112, width=4), word('0', 116, width=4), word('.', 120, width=4), word('0', 124, width=4),
                 word('0', 128, width=4), word('7', 200, width=4)]
        merged = rt.merge_spaced_digits(words)
        self.assertEqual([w['text'] for w in merged], ['SALDO', '2,500.00', '7'])

    def test_undouble_only_on_pages_that_are_doubled(self):
        doubled = [word('CCRREEDDIITT', 0), word('BBAANNKK', 60), word('$$7755..0000', 120), word('1100', 200)]
        self.assertEqual([w['text'] for w in rt.undouble(doubled)], ['CREDIT', 'BANK', '$75.00', '10'])
        normal = [word('Balance', 0), word('1100', 60), word('2200', 100), word('Total', 150)]
        self.assertEqual([w['text'] for w in rt.undouble(normal)], ['Balance', '1100', '2200', 'Total'])


class ReconcileTests(unittest.TestCase):
    def test_verified_needs_every_control_to_agree(self):
        p = period(rows=[row(700, 'credit', 1700), row(200, 'debit', 1500, day=9)],
                   controls=dict(credits_total=700, debits_total=200, credits_count=1, debits_count=1))
        self.assertEqual(rt.reconcile(p), ('verified', []))

    def test_any_disagreement_is_unverified_with_reasons(self):
        p = period(rows=[row(700, 'credit', 1700), row(200, 'debit', 1500, day=9)], controls=dict(credits_total=701))
        status, reasons = rt.reconcile(p)
        self.assertEqual(status, 'unverified')
        self.assertIn('credit total differs from printed total', reasons)
        p = period(closing_minor=1501, rows=[row(500, 'credit')])
        self.assertIn('opening + transactions != closing', rt.reconcile(p)[1])
        p = period(rows=[row(700, 'credit', 1600), row(200, 'debit', 1500, day=9)])
        self.assertIn('running balance differs at row 1', rt.reconcile(p)[1])
        p = period(rows=[dict(row(500, 'credit'), date='2024-02-03')])
        self.assertIn('row date outside the printed period', rt.reconcile(p)[1])

    def test_card_balances_are_owed_so_purchases_raise_them(self):
        p = period(kind='card', opening_minor=1000, closing_minor=1300,
                   rows=[row(500, 'debit'), row(200, 'credit', day=9)])
        self.assertEqual(rt.reconcile(p)[0], 'verified')
        early = period(kind='card', opening_minor=1000, closing_minor=1500,
                       rows=[dict(row(500, 'debit'), date='2023-12-20')])
        self.assertEqual(rt.reconcile(early)[0], 'verified')

    def test_missing_printed_page_is_incomplete_and_held(self):
        p = period(rows=[row(500, 'credit')], page_total=3, page_sequence={1: 1, 3: 2})
        status, reasons = rt.reconcile(p)
        self.assertEqual(status, 'incomplete')
        self.assertEqual(rt.expected_outcome(p, status), 'hold')

    def test_unread_fields_never_verify(self):
        self.assertIn('account not read', rt.reconcile(period(account=None, closing_minor=1000))[1])
        self.assertEqual(rt.expected_outcome(period(holder=None), 'verified'), 'decision')


class MonexTruthTests(unittest.TestCase):
    LINES = ['CONTRATO: 7654321', 'PERIODO: 1 al 30 de ABRIL de 2019', 'HOJA 1 DE 1',
             'CUENTA VISTA YEN JAPONES al 30 de ABRIL de 2019 DEL PERIODO ACUMULADO',
             'SALDO INICIAL: 0.00 SALDO PROMEDIO (INTERESES): 0.00', '+ ABONOS: 5,000.00', '- CARGOS: 5,000.00',
             'SALDO FINAL: 0.00', 'Saldo Inicial: 0.00 0.00 0.00',
             '03/Abr Compra 45629016 5,000.00 0.00 0.00 0.00 5,000.00 5,000.00',
             '03/Abr Retiro 61585153 0.00 5,000.00 0.00 0.00 0.00 0.00', 'Saldo Final: 0.00 0.00 0.00']

    def test_a_yen_section_is_its_own_period_in_whole_yen(self):
        (found,) = rt.parse_monex([page(1, self.LINES)])
        self.assertEqual((found.currency, found.opening_minor, found.closing_minor), ('JPY', 0, 0))
        self.assertEqual([(r['amount_minor'], r['direction'], r['balance_after']) for r in found.rows],
                         [(5000, 'credit', 5000), (5000, 'debit', 0)])
        self.assertEqual((found.controls['credits_total'], found.controls['debits_total']), (5000, 5000))
        self.assertEqual(rt.reconcile(found)[0], 'verified')

    def test_the_holder_comes_from_the_cover_even_after_a_notice_page(self):
        notice = page(1, ['Estimado Cliente', 'una actualizacion de datos fiscales'])
        cover = page(2, ['ACME SA DE CV', 'CALLE UNO 1', 'C.P. 11000',
                         'TIPO DE CONTRATO: SERVICIOS BANCARIOS'])
        bank = page(4, ['Estimado cliente', 'BANCO EJEMPLO SA', 'C.P. 06600'])
        (found,) = rt.parse_monex([notice, cover, page(3, self.LINES), bank])
        self.assertEqual(found.holder, 'ACME SA DE CV')
        (first,) = rt.parse_monex([cover, page(3, self.LINES)])
        self.assertEqual(first.holder, 'ACME SA DE CV')
        (none,) = rt.parse_monex([notice, page(3, self.LINES), bank])  # no cover: page 1 only, as before
        self.assertIsNone(none.holder)

    @staticmethod
    def placed(number, rows):
        """A page from (top, [(x0, text), ...]) rows: words where the layout prints them."""
        built = [rt.Line(top, [word(text, x0, top) for x0, text in words]) for top, words in rows]
        return rt.Page(number, 792.0, built, '\n'.join(l.text for l in built))

    def test_the_holder_skips_a_notice_line_printed_beside_the_address(self):
        cover = self.placed(1, [
            (277.0, [(84, 'incrementan'), (160, 'a'), (170, 'HR')]),
            (289.0, [(486, 'ACME'), (510, 'SERV'), (535, 'SA'), (548, 'DE'), (560, 'CV')]),
            (291.0, [(84, 'corto'), (116, 'plazo')]),
            (300.0, [(486, 'CALLE'), (512, 'UNO'), (530, '14-BODEGA'), (575, 'COLONIA')]),
            (310.0, [(486, 'CIUDAD'), (514, 'DE'), (524, 'MEXICO')]),
            (322.0, [(486, 'C.P.'), (588, '02970')]),
            (402.0, [(486, 'TIPO'), (503, 'DE'), (514, 'CONTRATO:'), (588, 'SERVICIOS')])])
        (found,) = rt.parse_monex([cover, page(2, self.LINES)])
        self.assertEqual(found.holder, 'ACME SERV SA DE CV')

    def test_the_holder_is_never_the_banks_own_footer_address(self):
        cover = self.placed(1, [
            (128.7, [(10, 'ACME'), (34, 'TEXTILES'), (70, 'Y'), (80, 'COMERCIO'), (130, 'S.A.'), (160, 'DE'),
                     (186, 'C.V.'), (396, 'CLIENTE'), (432, 'No.'), (461, '1234567')]),
            (140.7, [(12, 'CARRETERA'), (63, 'FEDERAL'), (396, 'CONTRATO:'), (456, '7654321')]),
            (152.7, [(12, 'CIUDAD'), (46, 'DE'), (61, 'MEXICO'), (396, 'CTA.'), (418, 'CLABE:')]),
            (164.7, [(396, 'CTA.'), (418, 'SPID:')]),
            (170.7, [(17, 'C.P.:'), (38, '11560'), (101, 'C.R.:'), (131, '0'), (190, 'FOLIO:')]),
            (201.0, [(14, 'TIPO'), (33, 'DE'), (46, 'CONTRATO:'), (88, 'SERVICIOS')]),
            (717.8, [(174, 'Banco'), (197, 'Monex'), (225, 'S.A.'), (243, 'Institución'), (280, 'de'),
                     (290, 'Banca'), (315, 'Multiple,')]),
            (727.1, [(176, 'Monex'), (200, 'Grupo'), (223, 'Financiero')]),
            (736.4, [(174, 'Av.'), (186, 'Paseo'), (209, 'de'), (219, 'la'), (227, 'Reforma')]),
            (745.7, [(174, 'Ciudad'), (199, 'de'), (209, 'México'), (235, 'C.P.'), (251, '06600')])])
        (found,) = rt.parse_monex([cover, page(2, self.LINES)])
        # The whole printed name, though it runs past the address column's usual width.
        self.assertEqual(found.holder, 'ACME TEXTILES Y COMERCIO S.A. DE C.V.')
        bank_only = self.placed(1, [
            (717.8, [(174, 'Banco'), (197, 'Monex'), (243, 'Institución'), (280, 'de'), (290, 'Banca')]),
            (745.7, [(174, 'Ciudad'), (235, 'C.P.'), (251, '06600')]),
            (760.0, [(14, 'TIPO'), (33, 'DE'), (46, 'CONTRATO:')])])
        (none,) = rt.parse_monex([bank_only, page(2, self.LINES)])
        self.assertIsNone(none.holder)

    def test_a_printed_fraction_of_a_yen_is_never_rounded(self):
        lines = [l.replace('5,000.00', '5,000.50') for l in self.LINES]
        (found,) = rt.parse_monex([page(1, lines)])
        self.assertIn('fraction printed for a currency without minor units', found.problems)
        self.assertNotEqual(rt.reconcile(found)[0], 'verified')


class PageNumberingTests(unittest.TestCase):
    def test_an_unnumbered_insert_stands_for_its_printed_number(self):
        pages = [page(1, ['advert']), page(2, ['PAGINA 2 / 3']), page(3, ['PAGINA 3 / 3'])]
        sequence, total, fillers = rt.printed_sequence(pages, r'PAGINA\s+(\d+)\s*/\s*(\d+)')
        self.assertEqual((sequence, total, fillers), ({1: 1, 2: 2, 3: 3}, 3, [1]))

    def test_runs_restart_at_printed_page_one(self):
        pages = [page(1, ['Page 1 of 2']), page(2, ['terms']), page(3, ['Page 2 of 2']), page(4, ['Page 1 of 1'])]
        runs = rt.split_runs(pages, r'Page\s+(\d+)\s+of\s+(\d+)')
        self.assertEqual([[p.number for p in r['pages']] for r in runs], [[1, 2, 3], [4]])


class IssuerTests(unittest.TestCase):
    def test_a_bank_named_in_transactions_does_not_decide_the_issuer(self):
        body = ['row %d SPEI ENVIADO SANTANDER' % i for i in range(30)]
        pages = [page(n, ['Estado de Cuenta'] + [''] * 15 + body + [''] * 15 + ['BBVA MEXICO, S.A., INSTITUCION'])
                 for n in (1, 2, 3)]
        self.assertEqual(rt.detect_issuer(pages), 'bbva-mexico')

    def test_no_text_has_no_issuer(self):
        self.assertIsNone(rt.detect_issuer([rt.Page(1, 600.0, [], '')]))


class ManifestTests(unittest.TestCase):
    def test_manifest_period_carries_every_field_the_harness_reads(self):
        p = period(rows=[row(500, 'credit', 1500)])
        record = dict(p.__dict__, id='d000000000000#1', truth_status='verified', truth_reasons=[], expected='auto')
        out = rt.manifest_period(record)
        needed = {'id', 'family', 'institution', 'account', 'account_printed', 'holder', 'holder_printed', 'currency',
                  'period_start', 'period_end', 'start_printed', 'opening_minor', 'closing_minor', 'expected',
                  'defects', 'rows', 'share', 'truth_status', 'added_in'}
        self.assertLessEqual(needed, set(out))
        self.assertEqual(set(out['rows'][0]), {'date', 'description', 'amount_minor', 'direction', 'balance_after'})

    def test_the_same_printed_period_in_two_documents_is_a_duplicate(self):
        def result(doc):
            p = dict(period(rows=[row(500, 'credit')]).__dict__, id=doc + '#1', truth_status='verified', expected='auto')
            return dict(id=doc, periods=[p])
        results = [result('db'), result('da')]
        rt.mark_duplicates(results)
        self.assertEqual(results[0]['periods'][0]['expected'], 'duplicate')
        self.assertEqual(results[0]['periods'][0]['duplicate_of'], 'da#1')
        self.assertEqual(results[1]['periods'][0]['expected'], 'auto')

    def test_summary_is_counts_only(self):
        status = [dict(id='d1', status='verified', issuer='bbva-mexico', inventory_family='x', mode='digital', pages=3,
                       reason=None, period_status={'verified': 2}, period_reasons={})]
        text = json.dumps(rt.summarise(status))
        self.assertNotIn('d1', text)


class UnverifiedOutcomeTests(unittest.TestCase):
    """An unverified period's expected outcome follows the class of its reason (corpus convention)."""

    PAGE = 'printed page 1 of the statement is not in the file; every present page reconciles'
    OPENING = 'printed Saldo Inicial is the balance after the first listed movement; the opening before it is not printed'
    CONTRADICTS = ('the one printed payment (1.00) does not take the printed opening (1.00 owed) to the printed '
                   'closing (1.00 in favour); the summary has no second movement line')
    BLANK = 'closing balance (Saldo al Corte) printed blank on a zero-activity credit line'

    def test_each_reason_class(self):
        cases = [(self.PAGE, 'hold', ['printed_pages_missing']), (self.OPENING, 'decision', ['opening_unprinted']),
                 (self.CONTRADICTS, 'hold', ['printed_figures_disagree']), (self.BLANK, 'decision', ['closing_unprinted']),
                 ('printed page 1 absent; the rest reconciles', 'hold', ['printed_pages_missing'])]
        for reason, outcome, defects in cases:
            self.assertEqual(rt.unverified_expectation([reason]), (outcome, defects), reason)
            self.assertEqual(rt.expected_outcome(period(), 'unverified', [reason]), outcome, reason)

    def test_hold_wins_and_unknown_reasons_keep_the_identity_rule(self):
        self.assertEqual(rt.unverified_expectation([self.OPENING, self.PAGE]),
                         ('hold', ['opening_unprinted', 'printed_pages_missing']))
        self.assertEqual(rt.unverified_expectation(['ending balance differs']), (None, []))
        self.assertEqual(rt.expected_outcome(period(), 'unverified', ['ending balance differs']), 'auto')
        self.assertEqual(rt.expected_outcome(period(holder=None), 'unverified', ['ending balance differs']), 'decision')
        # Only an unverified period is classed by its reasons.
        self.assertEqual(rt.expected_outcome(period(), 'verified', [self.PAGE]), 'auto')
        self.assertEqual(rt.expected_outcome(period(), 'incomplete', [self.OPENING]), 'hold')

    def test_final_documents_without_a_scored_period_enter_the_manifest_unscored(self):
        def result(doc, status, truth_status, reasons):
            p = dict(period(rows=[row(500, 'credit')]).__dict__, id=doc + '#1', truth_status=truth_status,
                     truth_reasons=reasons)
            p['expected'] = rt.expected_outcome(rt.Period(**{k: p[k] for k in rt.Period.__dataclass_fields__}),
                                                truth_status, reasons)
            return dict(id=doc, sha256=doc * 4, pages=1, mode='digital', status=status, periods=[p],
                        period_status={truth_status: 1})
        results = [result('da', 'verified', 'verified', []),
                   result('db', 'unverified', 'unverified', [self.OPENING]),  # final: every page read by a person
                   result('dc', 'unverified', 'unverified', [self.PAGE]),
                   result('dd', 'partly_verified', 'unverified', [self.PAGE]),  # not final: still queued
                   dict(id='de', sha256='e', pages=1, mode='digital', status='not_statement', periods=[])]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'docs').mkdir()
            for r in results:
                (tmp / 'docs' / f"{r['id']}.pdf").write_bytes(b'%PDF')
            manifest, _ = rt.write_outputs(tmp / 'out', results, tmp / 'docs')
        files = {f['filename']: f for f in manifest['files']}
        self.assertEqual(sorted(files), ['da.pdf', 'db.pdf', 'dc.pdf'])
        self.assertTrue(files['da.pdf']['truth_complete'])
        for name, expected, defects in (('db.pdf', 'decision', ['opening_unprinted']),
                                        ('dc.pdf', 'hold', ['printed_pages_missing'])):
            entry = files[name]
            self.assertFalse(entry['truth_complete'])
            (only,) = entry['periods']
            self.assertEqual((only['truth_status'], only['expected'], only['defects']), ('unverified', expected, defects))
            self.assertFalse(harness._scored(only))  # the scored denominator does not move
        self.assertEqual(files['da.pdf']['periods'][0]['defects'], [])


class HarnessRealCorpusTests(unittest.TestCase):
    def entry(self, scored, can_import, expected='auto'):
        return dict(item_id='i', filename='x.pdf', statement_id=None, status='ready' if can_import else 'attention',
                    can_import=can_import, truth_id='x.pdf#1', family='f', expected=expected, defects=[],
                    added_in='real', reasons={}, problems=[], read={}, scored=scored)

    def test_only_scored_periods_count(self):
        m = harness.metrics(dict(periods=[self.entry(True, True), self.entry(False, True), self.entry(False, False)]))
        self.assertEqual((m['overall']['periods'], m['overall']['ready_without_edits']), (1, 1))
        self.assertEqual(m['unscored'], dict(periods=2, offered_for_import=1, by_status={'ready': 1, 'attention': 1},
                                             by_expected={'auto': 2}, wrongly_ready=[], ready_where_decision=[]))

    def test_an_unscored_period_offered_where_the_truth_expects_a_hold_fails_the_run(self):
        held = dict(self.entry(False, True, expected='hold'), truth_id='h.pdf#1')
        decided = dict(self.entry(False, True, expected='decision'), truth_id='d.pdf#1')
        saved = dict(self.entry(False, False, expected='hold'), truth_id='s.pdf#1', final_status='imported')
        kept = dict(self.entry(False, False, expected='hold'), truth_id='k.pdf#1')
        m = harness.metrics(dict(periods=[self.entry(True, True), held, decided, saved, kept]))
        # The scored denominator does not move; the unscored block names the failures.
        self.assertEqual((m['overall']['periods'], m['overall']['hold_periods']), (1, 0))
        self.assertEqual(m['unscored']['wrongly_ready'], ['h.pdf#1', 's.pdf#1'])
        self.assertEqual(m['unscored']['ready_where_decision'], ['d.pdf#1'])
        result = dict(metrics=m, ledger=dict(wrongly_admitted=[], duplicate_contributions=0))
        failures = harness.safety_failures(result)
        self.assertEqual(len(failures), 1)
        self.assertIn('2 unscored period(s)', failures[0])
        m = harness.metrics(dict(periods=[self.entry(True, True), decided, kept]))
        self.assertEqual(harness.safety_failures(dict(metrics=m, ledger=dict(wrongly_admitted=[]))), [])

    def test_scored_truth_statuses(self):
        self.assertTrue(harness._scored(None))
        self.assertTrue(harness._scored(dict(id='synthetic')))
        self.assertTrue(harness._scored(dict(truth_status='verified')))
        self.assertFalse(harness._scored(dict(truth_status='ocr_reconciled')))
        self.assertFalse(harness._scored(dict(truth_status='unverified')))
        self.assertTrue(harness._scored(dict(truth_status='incomplete')))  # must be held: admitting it is wrong

    def test_unmatched_admission_in_a_document_with_incomplete_truth_is_not_judged(self):
        class Query:
            def where(self, *_):
                return self

        class Column:
            def __eq__(self, other):
                return True

        class Transaction:
            source_document_id = Column()

        class Session:
            def scalars(self, *_):
                return []
        item = dict(item_id='i1', filename='d1.pdf', truth_id=None, status='ready', can_import=True)
        final = {'i1': dict(status='imported', source_document_id='00000000-0000-0000-0000-000000000001')}
        judged = harness.verify_ledger(Session(), [dict(item)], final, {}, Transaction, None, lambda _: Query())
        self.assertEqual(len(judged['wrongly_admitted']), 1)
        unjudged = harness.verify_ledger(Session(), [dict(item)], final, {}, Transaction, None, lambda _: Query(),
                                         incomplete_files={'d1.pdf'})
        self.assertEqual((unjudged['wrongly_admitted'], unjudged['admitted_unscored']), ([], 1))

    def test_real_matching_uses_the_account(self):
        cheque = dict(id='d#1', period_end='2025-03-31', account='65500012340', added_in='real', rows=[])
        savings = dict(id='d#2', period_end='2025-03-31', account='66500012340', added_in='real', rows=[])
        proposal = dict(rows=[], metadata={})
        item = dict(period_end='2025-03-31', account='66-50001234-0')
        self.assertGreater(harness._score(proposal, savings, item), harness._score(proposal, cheque, item))

    def test_rescore_rematch_pairs_items_by_date_account_and_share(self):
        truths = {t['id']: dict(t, filename='d.pdf', added_in='real') for t in (
            dict(id='d#1', period_end='2021-12-31', account='123456789', share='0000'),
            dict(id='d#2', period_end='2021-12-31', account='123456789', share='0040'))}
        periods = [dict(item_id='a', filename='d.pdf', truth_id='d#1', read=dict(period_end='2021-12-31',
                                                                                   account='123456789 / Share 0040')),
                   dict(item_id='b', filename='d.pdf', truth_id='d#2', read=dict(period_end='2021-12-31',
                                                                                   account='123456789 / Share 0000'))]
        self.assertEqual(harness._rematch(periods, truths), 2)
        self.assertEqual([p['truth_id'] for p in periods], ['d#2', 'd#1'])

    def test_rescore_rematch_pairs_currency_sections_by_currency(self):
        truths = {t['id']: dict(t, filename='m.pdf', added_in='real') for t in (
            dict(id='m#1', period_end='2022-11-30', account='1977', currency='MXN'),
            dict(id='m#2', period_end='2022-11-30', account='1977', currency='USD'),
            dict(id='m#3', period_end='2022-11-30', account='1977', currency='EUR'))}
        def item(name, truth_id, currency):
            return dict(item_id=name, filename='m.pdf', truth_id=truth_id,
                        read=dict(period_end='2022-11-30', account='CONTRATO 3041977', currency=currency))
        # Batch items need not arrive in section order; date and account alone tie on every section.
        periods = [item('b', 'm#2', 'usd'), item('a', 'm#1', 'MXN'), item('c', 'm#3', 'EUR')]
        self.assertEqual(harness._rematch(periods, truths), 0)  # the run's own pairing is kept
        self.assertEqual([p['truth_id'] for p in periods], ['m#2', 'm#1', 'm#3'])
        swapped = [item('c', 'm#1', 'EUR'), item('a', 'm#2', 'MXN'), item('b', 'm#3', 'USD')]
        self.assertEqual(harness._rematch(swapped, truths), 3)
        self.assertEqual([p['truth_id'] for p in swapped], ['m#3', 'm#1', 'm#2'])

    def test_run_pairs_shares_by_the_share_printed_with_the_account(self):
        def t(i, share):
            return dict(id=f'd#{i}', period_end='2021-12-31', account='123456789', share=share, added_in='real',
                        currency='USD', rows=[])
        truths = [t(1, '0000'), t(2, '0040')]
        proposal = dict(metadata=dict(holder_reference='>2000000000<', account_number='123456789'), rows=[],
                        currency='USD')  # '0000' appears in the metadata, not as the share
        summary = dict(period_end='2021-12-31', account='123456789 / Share 0040', currency='USD')
        self.assertEqual(harness.pair_truth(proposal, truths, summary)['id'], 'd#2')
        self.assertEqual(harness.pair_truth(proposal, truths, dict(summary, account='123456789 / Share 0000'))['id'],
                         'd#1')

    def test_closing_date_outranks_many_repeated_amounts(self):
        def row(amount):
            return dict(amount_minor=amount, direction='debit', date=None, description='x')
        short = dict(id='d#1', period_end='2021-02-28', account='1', share=None, added_in='real', currency='USD',
                     rows=[row(1059), row(500)])
        long = dict(id='d#2', period_end='2022-07-31', account='1', share=None, added_in='real', currency='USD',
                    rows=[row(1059)] * 12 + [row(777)])
        proposal = dict(metadata={}, currency='USD', rows=[
            dict(id=str(i), kind='transaction', excluded=False, fields=dict(amount_minor=a))
            for i, a in enumerate(['1059', '500'])])
        summary = dict(period_end='2021-02-28', account='1', currency='USD')
        self.assertEqual(harness.pair_truth(proposal, [long, short], summary)['id'], 'd#1')
        # Without a matching closing date, payments in common decide, each counted once.
        self.assertEqual(harness.pair_truth(proposal, [long, short], dict(summary, period_end='2021-03-31'))['id'],
                         'd#1')

    def test_rescore_refreshes_not_detected_entries_for_the_current_truth(self):
        def t(i):
            return dict(id=f'd#{i}', filename='d.pdf', family='f', expected='auto', defects=[], truth_status='verified')
        truths = {x['id']: x for x in (t(1), t(2), t(3))}
        periods = [dict(item_id='a', filename='d.pdf', truth_id='d#1'),
                   dict(item_id=None, filename='d.pdf', truth_id='d#1', status='not_detected'),  # now paired
                   dict(item_id=None, filename='d.pdf', truth_id='d#2', status='not_detected'),  # still missing
                   dict(item_id=None, filename='d.pdf', truth_id='d#9', status='not_detected')]  # gone
        kept, added = harness._refresh_not_detected(periods, truths)
        self.assertEqual(added, 1)
        self.assertEqual([(p['item_id'], p['truth_id']) for p in kept],
                         [('a', 'd#1'), (None, 'd#2'), (None, 'd#3')])
        self.assertTrue(kept[-1]['scored'])

    def test_rows_pair_by_value_before_description(self):
        truth = [dict(description='SPEI ENVIADO A', amount_minor=100, direction='debit', date='2024-01-02'),
                 dict(description='SPEI ENVIADO B', amount_minor=200, direction='debit', date='2024-01-03')]
        proposal = [dict(id='r1', fields=dict(description='SPEI ENVIADO', amount_minor='200', direction='debit',
                                              date='2024-01-03'), source_cells=[])]
        self.assertEqual(harness._match_rows(proposal, truth, by_value=True)[0], {'r1': 1})
        self.assertEqual(harness._match_rows(proposal, truth)[0], {'r1': 0})


class VisualQueueTests(unittest.TestCase):
    def test_shards_by_family_with_document_and_page_limits(self):
        def result(doc, status, family, pages, periods=()):
            return dict(id=doc, status=status, issuer=family, inventory_family=family, mode='digital', pages=pages,
                        reason=None, periods=[dict(id=f'{doc}#1', family=family, truth_status=s, truth_reasons=[])
                                              for s in periods])
        results = [result(f'a{i:02d}', 'needs_visual', 'big', 5) for i in range(45)]
        results += [result('b1', 'ocr_reconciled', 'small', 300, ['ocr_reconciled']),
                    result('b2', 'partly_verified', 'other', 200, ['verified', 'unverified']),
                    result('c1', 'verified', 'big', 5, ['verified']), result('c2', 'not_statement', 'big', 1)]
        queue = rt.visual_queue(results)
        self.assertEqual(queue['documents'], 47)
        self.assertEqual([(s['families'], s['count']) for s in queue['shards']],
                         [(['big'], 40), (['big'], 5), (['other'], 1), (['small'], 1)])
        confirm = next(d for s in queue['shards'] for d in s['documents'] if d['id'] == 'b1')
        self.assertEqual(confirm['work'], ['confirm'])
        partly = next(d for s in queue['shards'] for d in s['documents'] if d['id'] == 'b2')
        self.assertEqual([p['status'] for p in partly['periods']], ['unverified'])


class UnprintedDateAndAuditTests(unittest.TestCase):
    def test_a_row_without_a_printed_date_accepts_any_recorded_date(self):
        self.assertTrue(harness._same_date(None, '2024-01-31'))
        self.assertTrue(harness._same_date(None, None))
        self.assertFalse(harness._same_date('2024-01-30', '2024-01-31'))
        p = dict(period(kind='card', rows=[dict(row(500, 'debit'), date_unprinted=True, date='2024-01-31')]).__dict__,
                 id='d#1', truth_status='verified', truth_reasons=[], expected='auto')
        self.assertIsNone(rt.manifest_period(p)['rows'][0]['date'])

    def test_audit_tells_conventions_from_disagreement(self):
        from benchmarks.statement_automation import real_ledger_audit as audit
        truth = dict(opening_minor=1000, closing_minor=1300, account='1234',
                     rows=[dict(amount_minor=500, direction='debit', date='2024-01-05'),
                           dict(amount_minor=200, direction='credit', date='2024-01-09'),
                           dict(amount_minor=7, direction='debit', date='2024-01-31', date_unprinted=True)])
        live = dict(opening_minor=1000, closing_minor=1300, account='999991234',
                    rows=[(500, 'debit', '2024-01-05'), (200, 'credit', '2024-01-09'), (7, 'debit', None)])
        self.assertEqual(audit.compare(live, truth)['outcome'], 'agrees')
        flipped = dict(live, opening_minor=-1000, closing_minor=-1300)
        self.assertEqual(audit.compare(flipped, truth)['outcome'], 'convention_only')
        wrong = dict(live, rows=[(800, 'debit', '2024-01-05'), (200, 'credit', '2024-01-09'), (7, 'debit', None)])
        result = audit.compare(wrong, truth)
        self.assertEqual((result['outcome'], result['missing_rows'], result['extra_rows']), ('disagrees', 1, 1))
        held = dict(truth, id='d#2', family='f', truth_status='verified', expected='hold')
        self.assertEqual(audit.judge(live, held)['outcome'], 'must_be_held')  # rows agree, but it must not be there
        self.assertEqual(audit.judge(live, dict(held, truth_status='incomplete', expected='auto'))['outcome'],
                         'must_be_held')
        self.assertEqual(audit.judge(live, dict(held, expected='auto'))['outcome'], 'agrees')

    def test_audit_pairs_a_share_printed_as_account_digits_with_a_named_section(self):
        from benchmarks.statement_automation import real_ledger_audit as audit
        def truth(share, opening, closing, rows):
            return dict(share=share, account='1111', period_end='2024-02-16', currency='USD', opening_minor=opening,
                        closing_minor=closing, rows=[dict(amount_minor=a, direction=d) for a, d in rows])
        checking = truth('EveryDay Checking', 10000, 12000, [(5000, 'credit'), (3000, 'debit')])
        credit_line = truth('Checking Line of Credit', 0, 0, [])
        savings = dict(truth('Membership Savings', 500, 500, []), account='2222')
        live = dict(share='1111', account='1111', period_end='2024-02-16', currency='USD', opening_minor=10000,
                    closing_minor=12000, rows=[(5000, 'credit', '2024-01-20'), (3000, 'debit', '2024-01-25')])
        candidates = [checking, credit_line, savings]
        self.assertIs(audit.best_truth(live, candidates), checking)
        quiet = dict(live, opening_minor=0, closing_minor=0, rows=[])
        self.assertIs(audit.best_truth(quiet, candidates), credit_line)  # same digits: told apart by balances
        self.assertIs(audit.best_truth(dict(quiet, share='2222', account='2222', opening_minor=500,
                                            closing_minor=500), candidates), savings)
        self.assertIsNone(audit.best_truth(dict(live, share='3333'), candidates))  # other digits: no pairing
        # Four-digit truth shares (Andrews) still never pair across shares.
        andrews = dict(checking, share='0040')
        self.assertIsNone(audit.best_truth(dict(live, share='0000'), [andrews]))
        self.assertIs(audit.best_truth(dict(live, share='0040'), [andrews]), andrews)

    def test_audit_compares_the_admitted_holder_with_the_printed_one(self):
        from benchmarks.statement_automation import real_ledger_audit as audit
        truth = dict(holder='EJEMPLO SERVICIOS SA DE CV')
        cases = ((dict(holder='EJEMPLO SERVICIOS SA DE CV'), 'agrees', 'statement'),
                 (dict(holder='EJEMPLO SERVICIOS S.A. DE C.V.'), 'same_entity', 'statement'),
                 (dict(holder='EJEMPLO SERVICIOS'), 'same_entity', 'statement'),
                 (dict(holder='AVENIDA EJEMPLO 12, CENTRO', account_holder='EJEMPLO SERVICIOS SA DE CV'), 'differs',
                  'statement'),
                 (dict(holder='', account_holder='OTRA EMPRESA SA DE CV'), 'differs', 'account'),
                 (dict(), 'not_recorded', 'account'))
        for live, outcome, source in cases:
            self.assertEqual(audit.holder_outcome(live, truth), dict(holder=outcome, holder_source=source), live)
        self.assertEqual(audit.holder_outcome(dict(holder='X Y'), dict(holder=''))['holder'], 'not_printed')

    def test_audit_tells_an_overlap_trim_from_missing_rows(self):
        """A movement query whose first days a saved period of the same account counts: counted once, not missing."""
        from benchmarks.statement_automation import real_ledger_audit as audit
        truth = dict(period_start='2024-05-31', opening_minor=1000, closing_minor=1150, account='1234',
                     rows=[dict(amount_minor=100, direction='credit', date='2024-06-03', balance_after=1100),
                           dict(amount_minor=50, direction='debit', date='2024-06-07', balance_after=1050),
                           dict(amount_minor=100, direction='credit', date='2024-06-19', balance_after=1150)])
        live = dict(period_id='p2', period_start='2024-06-11', period_end='2024-07-08', opening_minor=1050,
                    closing_minor=1150, account='1234', rows=[(100, 'credit', '2024-06-19')])
        cover = dict(period_id='p1', period_start='2024-03-27', period_end='2024-06-10', closing_minor=1050,
                     rows=[(7, 'debit', '2024-04-01'), (100, 'credit', '2024-06-03'), (50, 'debit', '2024-06-07')])
        entry = audit.compare(live, truth)
        self.assertEqual((entry['outcome'], entry['missing_rows'], entry['balances']), ('disagrees', 2, ['opening']))
        self.assertEqual(audit.overlap_trimmed(live, truth, entry, [live, cover]), 'p1')
        # Fails closed: no covering period, a cover missing a row, a cover ending another day, a wrong opening.
        self.assertIsNone(audit.overlap_trimmed(live, truth, entry, [live]))
        self.assertIsNone(audit.overlap_trimmed(live, truth, entry, [live, dict(cover, rows=cover['rows'][:2])]))
        self.assertIsNone(audit.overlap_trimmed(live, truth, entry, [live, dict(cover, period_end='2024-06-09')]))
        other = dict(live, opening_minor=1100)
        self.assertIsNone(audit.overlap_trimmed(other, truth, audit.compare(other, truth), [other, cover]))
        unclosed = dict(live, closing_minor=None)
        self.assertIsNone(audit.overlap_trimmed(unclosed, truth, audit.compare(unclosed, truth), [unclosed, cover]))
        # A kept day's row missing as well is a disagreement, whatever covers the earlier days.
        short = dict(live, rows=[])
        self.assertIsNone(audit.overlap_trimmed(short, truth, audit.compare(short, truth), [short, cover]))


    def test_audit_counts_a_copy_saved_through_a_file_the_inventory_does_not_list(self):
        """r11-copy-audit: an upload of the same bytes after the inventory, saved to another ledger account."""
        from unittest import mock
        from benchmarks.statement_automation import real_ledger_audit as audit
        rows = [dict(amount_minor=500, direction='debit', date='2024-01-05')]
        def truth_period(pid, duplicate_of=None):
            return dict(id=pid, family='f', truth_status='verified', expected='duplicate' if duplicate_of else 'auto',
                        duplicate_of=duplicate_of, period_start='2024-01-01', period_end='2024-01-31', currency='MXN',
                        account='1234', share=None, opening_minor=1000, closing_minor=500, rows=rows)
        inventory = dict(documents=[dict(id='dorig', sha256='a' * 64, evidence_files=[]),
                                    dict(id='dcopy', sha256='b' * 64, evidence_files=[dict(evidence_file_id='f-copy')])])
        def live(file_id, account):
            return dict(period_id='p-' + file_id, evidence_file_id=file_id, source_document_id='s-' + file_id,
                        period_start='2024-01-01', period_end='2024-01-31', currency='MXN', opening_minor=1000,
                        closing_minor=500, account='991234', case_id='c' * 8 + '-case', share=None,
                        account_id=account, rows=[(500, 'debit', '2024-01-05')])
        session = mock.Mock()
        session.execute.return_value.all.return_value = [('f-orig', 'a' * 64)]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'periods').mkdir()
            for doc, period in (('dorig', truth_period('dorig#1')), ('dcopy', truth_period('dcopy#1', 'dorig#1'))):
                (Path(tmp) / 'periods' / (doc + '.json')).write_text(json.dumps(dict(id=doc, status='verified', periods=[period])))
            seen = []
            def periods(_session, files):
                seen.append(sorted(files))
                return [live(f, 'acct-' + f) for f in sorted(files)]
            with mock.patch.object(audit, 'live_periods', periods):
                summary, detail = audit.audit(Path(tmp), inventory, session)
        self.assertEqual(seen, [['f-copy', 'f-orig']])
        self.assertEqual(summary['live_files_on_truth_documents'], dict(inventory=1, same_bytes=1))
        duplicates = summary['duplicates']
        self.assertEqual(duplicates['same_printed_period_admitted_more_than_once_in_a_case'], 1)
        self.assertEqual(duplicates['same_printed_period_in_more_than_one_ledger_account'], 1)
        self.assertEqual(duplicates['same_printed_period_admitted_more_than_once_examples'], ['cccccccc dorig#1'])
        self.assertEqual({e['outcome'] for e in detail}, {'agrees'})
        # By page identity: a file with other bytes whose pages render identically to the copy.
        session.execute.return_value.all.return_value = []
        mapping, how = audit.live_files_of(session, inventory, {'f-copy': 'x', 'f-other': 'x', 'f-alone': 'y'})
        self.assertEqual((mapping.get('f-other'), 'f-alone' in mapping, how['same_pages']), ('dcopy', False, 1))


class InventoryTests(unittest.TestCase):
    def test_family_guess_and_opaque_id(self):
        self.assertEqual(real_inventory.guess_family('BBVA MEXICO, S.A.'), 'bbva-mexico')
        self.assertEqual(real_inventory.guess_family('', 'Merrick Bank'), 'merrick-card?')
        self.assertEqual(real_inventory.guess_family('nothing'), 'unknown')
        self.assertEqual(real_inventory.opaque_id('ab' * 32), 'd' + 'ab' * 6)

    def test_build_copies_verified_originals_and_flags_changed_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            good, changed = tmp / 'a.pdf', tmp / 'b.pdf'
            good.write_bytes(b'one')
            changed.write_bytes(b'two')
            files = [dict(evidence_file_id='e1', case_id='c1', sha256=hashlib.sha256(b'one').hexdigest(),
                          stored_path=str(good), filename='a.pdf', batch_items=[dict(id='i1', status='imported',
                          institution=None)], source_documents=[]),
                     dict(evidence_file_id='e2', case_id='c1', sha256=hashlib.sha256(b'other').hexdigest(),
                          stored_path=str(changed), filename='b.pdf', batch_items=[], source_documents=[])]
            inventory = real_inventory.build(tmp / 'out', files, lambda value: Path(value),
                                             analyse_fn=lambda path: dict(pages=1, page_kinds={'digital': 1},
                                                                          mode='digital', first_text=''))
            states = {d['evidence_files'][0]['filename']: d['hash'] for d in inventory['documents']}
            self.assertEqual(states, {'a.pdf': 'verified', 'b.pdf': 'original_changed'})
            copied = tmp / 'out' / 'docs' / (real_inventory.opaque_id(files[0]['sha256']) + '.pdf')
            self.assertEqual(copied.read_bytes(), b'one')
            self.assertEqual(good.read_bytes(), b'one')
            self.assertEqual(oct(os.stat(tmp / 'out').st_mode & 0o777), '0o700')
            self.assertNotIn('a.pdf', json.dumps(real_inventory.counts(inventory)))


def placed(number, lines):
    """A page from lines of ``(text, x0)`` words (layouts where columns share a printed line)."""
    built = [rt.Line(10.0 * i, [word(text, x0, 10.0 * i) for text, x0 in line]) for i, line in enumerate(lines)]
    return rt.Page(number, 500.0, built, '\n'.join(l.text for l in built))


def at(x0, text):
    return [(w, x0 + 30.0 * i) for i, w in enumerate(text.split())]


class SynchronyTruthTests(unittest.TestCase):
    """Synchrony card: summary from the left box only, sections, wrapped descriptions, page continuation."""
    TABLE = at(10, 'Tran Date Post Date Reference') + at(230, 'Description') + at(420, 'Amount')

    def row(self, tran, post, reference, description, amount):
        return at(10, tran) + at(70, post) + (at(130, reference) if reference else []) + at(230, description) \
            + at(420, amount)

    def pages(self, fee='$12.00', late_fee=True):
        first = placed(1, [
            at(10, 'EXAMPLE/SYNCHRONY BANK') + at(260, 'JANE Q SAMPLE'),
            at(260, 'Account Number : 1111 2222 3333 4444'),
            at(260, 'Statement Closing Date: 03/12/2024'),
            at(10, 'Summary of Account Activity') + at(260, 'Payment Information'),
            at(10, 'Previous Balance') + at(200, '$1,000.00') + at(260, 'New Balance') + at(440, '$1,315.00'),
            at(10, '+ New Purchases') + at(200, '$300.00') + at(260, 'Total Minimum Payment Due $40.00'),
            at(10, '- Payments') + at(200, '$100.00'),
            at(10, '+/- Credits, Fees & Adjustments (net)') + at(200, '$105.00'),
            at(10, '+/- Interest Charge (net)') + at(200, '$10.00'),
            at(10, 'New Balance') + at(200, '$1,315.00') + at(260, 'reverse side.'),
            at(10, 'Transaction Summary'), self.TABLE,
            self.row('02/20/2024', '02/21/2024', 'REF001', 'PAYMENT - THANK YOU', '($100.00)'),
            self.row('02/25/2024', '02/25/2024', 'REF002', 'EXAMPLE CLINIC', '$300.00'),
            at(230, 'SOMEWHERE DC'),
            self.row('03/01/2024', '03/01/2024', 'REF003', 'MERCHANT CREDIT', '($7.00)'),
            at(10, 'Continued on next page'),
            at(10, 'PAGE 1 of 2')])
        terms = placed(2, [])  # the printed reverse side: an image, no text layer
        fees = [self.row('03/12/2024', '03/12/2024', None, 'PAPER STATEMENT FEE', fee)]
        if late_fee:
            fees.append(self.row('03/04/2024', '03/04/2024', None, 'LATE FEE', '$100.00'))
        second = placed(3, [
            at(10, 'Transaction Summary (Continued)'), self.TABLE, at(230, 'FEES')] + fees + [
            at(230, 'TOTAL FEES FOR THIS PERIOD') + at(420, '$112.00'),
            at(230, 'INTEREST CHARGED'),
            self.row('03/12/2024', '03/12/2024', None, 'INTEREST CHARGE ON PURCHASES', '$10.00'),
            self.row('03/12/2024', '03/12/2024', None, 'INTEREST CHARGE ON CASH ADVANCES', '$0.00'),
            at(230, 'TOTAL INTEREST FOR THIS PERIOD') + at(420, '$10.00'),
            at(100, '2024 Totals Year-to-Date'),
            at(100, 'Total Fees Charged in 2024') + at(300, '$112.00'),
            at(10, 'PAGE 2 of 2')])
        return [first, terms, second]

    def test_a_reconciled_statement_is_verified(self):
        (found,) = rt.parse_synchrony(self.pages())
        self.assertEqual((found.family, found.kind, found.currency, found.account, found.holder),
                         ('synchrony-card', 'card', 'USD', '4444', 'JANE Q SAMPLE'))
        self.assertEqual((found.period_start, found.period_end, found.opening_minor, found.closing_minor),
                         (None, '2024-03-12', 100000, 131500))
        self.assertIn(rt.START_UNPRINTED, found.notes)
        self.assertEqual([(r['date'], r['amount_minor'], r['direction']) for r in found.rows], [
            ('2024-02-20', 10000, 'credit'), ('2024-02-25', 30000, 'debit'), ('2024-03-01', 700, 'credit'),
            ('2024-03-12', 1200, 'debit'), ('2024-03-04', 10000, 'debit'), ('2024-03-12', 1000, 'debit')])
        self.assertEqual(found.rows[1]['description'], 'EXAMPLE CLINIC SOMEWHERE DC')  # wrapped, reference apart
        self.assertEqual(found.rows[1]['reference'], 'REF002')
        self.assertEqual(found.page_sequence, {1: 1, 2: 3})
        self.assertEqual(rt.reconcile(found), ('verified', []))

    def test_a_row_the_reader_missed_is_not_verified(self):
        (found,) = rt.parse_synchrony(self.pages(late_fee=False))
        status, reasons = rt.reconcile(found)
        self.assertEqual(status, 'unverified')
        self.assertIn('fee rows differ from the printed fee total', reasons)

    def test_a_misread_section_total_is_not_verified(self):
        # A fee read one dollar high: the printed fee total and the summary both disagree.
        (found,) = rt.parse_synchrony(self.pages(fee='$13.00'))
        self.assertEqual(rt.reconcile(found)[0], 'unverified')

    def test_the_card_named_in_a_bank_statement_does_not_decide_the_issuer(self):
        body = ['row %d SYNCHRONY BANK PAYMENT' % i for i in range(3)]
        pages = [page(n, ['Wells Fargo Everyday Checking'] + body) for n in (1, 2, 3)]
        self.assertEqual(rt.detect_issuer(pages), 'wells-fargo')
        self.assertEqual(rt.detect_issuer([placed(1, [at(10, 'EXAMPLE/SYNCHRONY BANK JANE Q SAMPLE')])]),
                         'synchrony-card')



def right(x1, text):
    """One word whose right edge is at ``x1`` (amounts are right aligned)."""
    return [(text, x1 - 4.0 * len(text))]


class NavyFederalTruthTests(unittest.TestCase):
    """Navy Federal 'Statement of Account': one period per account section, controls from the summary page."""
    HEADER = at(10, 'Date') + at(40, 'Transaction Detail') + right(466, 'Amount($)') + right(600, 'Balance($)')
    LOC_HEADER = at(10, 'Date') + at(40, 'Transaction Detail') + right(250, 'Amount($)') + right(330, 'Fee(s)') \
        + right(345, '($)') + right(400, 'Interest($)') + right(470, 'Principal') + right(490, '($)') \
        + right(585, 'Balance') + right(600, '($)')

    def furniture(self, number, total=2):
        return [right(560, f'Page {number} of {total}'), at(10, 'Statement of Account'),
                at(400, 'Statement Period'), at(400, '01/17/24 - 02/16/24')]

    def pages(self, redacted=False, loc_rows=False, deposits='$50.00'):
        first = placed(1, self.furniture(1) + [
            at(10, 'Summary of your deposit accounts'),
            right(176, 'Previous') + right(284, 'Deposits/') + right(392, 'Withdrawals/') + right(496, 'Ending'),
            right(176, 'Balance') + right(284, 'Credits') + right(392, 'Debits') + right(496, 'Balance'),
            at(30, 'Day Checking'),
            at(40, '1111') + right(176, '$100.00') + right(284, deposits) + right(392, '$30.00') + right(496, '$120.00'),
            at(10, 'Totals') + right(176, '$100.00') + right(284, deposits) + right(392, '$30.00') + right(496, '$120.00'),
            at(10, 'Navy Federal Credit Union Page 1 of 9')])
        rows = [at(10, '01-20') + at(40, 'Deposit') + right(466, '50.00') + right(600, '150.00'),
                at(10, '01-25') + at(40, 'POS Debit - Debit Card 9999 Transaction 01-24-24 EXAMPLE STORE'),
                at(40, 'Somewhere MD') + right(466, '25.00-') + right(600, '125.00'),
                at(10, '02-01') + at(40, 'Check 101') + right(462, '5.00') + [('-', 463.0)] + right(600, '120.00')]
        if redacted:
            rows = [at(10, '01-20'), at(10, '01-25')] + rows[3:]
        loc = [at(10, 'Checking Line of Credit - 1111'),
               at(10, 'Total Outstanding Balance') + right(172, '$40.00' if loc_rows else '$0.00'), self.LOC_HEADER,
               at(10, '01-17') + at(40, 'Beginning Balance') + right(600, '0.00')]
        if loc_rows:
            loc += [at(10, '01-30') + at(40, 'Advance') + right(250, '40.00') + right(470, '40.00') + right(600, '40.00'),
                    at(10, '02-16') + at(40, 'Ending Balance') + right(600, '40.00')]
        else:
            loc += [at(200, 'No Transactions This Period'), at(10, '02-16') + at(40, 'Ending Balance') + right(600, '0.00')]
        second = placed(2, self.furniture(2) + [at(10, 'For JANE Q SAMPLE'), at(10, 'Checking'),
                                                 at(10, 'EveryDay Checking - 1111'),
                                                 at(10, 'Joint Owner(s): JOHN Q SAMPLE'), self.HEADER,
                                                 at(10, '01-17') + at(40, 'Beginning Balance') + right(600, '100.00')]
                        + rows + [at(10, '02-16') + at(40, 'Ending Balance') + right(600, '120.00'),
                                  at(10, 'Your account earned $0.00 for the dividend period from 01-01-2024 through '
                                         '01-31-2024')] + loc + [at(10, 'Navy Federal Credit Union Page 2 of 9')])
        # page 2's statement-of-account heading and holder sit on two lines
        lines = second.lines
        index = next(i for i, l in enumerate(lines) if l.text == 'Statement of Account')
        lines.insert(index + 1, lines.pop(next(i for i, l in enumerate(lines) if l.text.startswith('For '))))
        return [placed(1, [at(10, 'Navy Federal Credit Union cover letter')]), first, second]

    def test_each_account_section_is_its_own_verified_period(self):
        checking, loc = rt.parse_navy_federal(self.pages())
        self.assertEqual((checking.family, checking.currency, checking.account, checking.share, checking.holder),
                         ('navy-federal', 'USD', '1111', 'EveryDay Checking', 'JANE Q SAMPLE'))
        self.assertEqual((checking.period_start, checking.period_end, checking.opening_minor, checking.closing_minor),
                         ('2024-01-17', '2024-02-16', 10000, 12000))
        self.assertEqual([(r['date'], r['amount_minor'], r['direction'], r['balance_after']) for r in checking.rows], [
            ('2024-01-20', 5000, 'credit', 15000), ('2024-01-25', 2500, 'debit', 12500),
            ('2024-02-01', 500, 'debit', 12000)])
        self.assertTrue(checking.rows[1]['description'].endswith('Somewhere MD'))  # a two-line entry
        self.assertEqual(rt.reconcile(checking), ('verified', []))
        self.assertEqual((loc.kind, loc.share, loc.rows, rt.reconcile(loc)),
                         ('card', 'Checking Line of Credit', [], ('verified', [])))

    def test_a_summary_total_that_disagrees_is_not_verified(self):
        checking, _ = rt.parse_navy_federal(self.pages(deposits='$51.00'))
        self.assertIn('credit total differs from printed total', rt.reconcile(checking)[1])

    def test_redacted_rows_are_never_verified(self):
        checking, _ = rt.parse_navy_federal(self.pages(redacted=True))
        status, reasons = rt.reconcile(checking)
        self.assertEqual(status, 'unverified')
        self.assertIn('row redacted in the production', reasons)

    def test_a_line_of_credit_with_movements_is_not_verified(self):
        _, loc = rt.parse_navy_federal(self.pages(loc_rows=True))
        self.assertEqual(rt.reconcile(loc)[0], 'unverified')
        self.assertIn(rt.NFCU_LOC_OPENING, rt.reconcile(loc)[1])

    def test_the_issuer_comes_from_the_page_footer(self):
        self.assertEqual(rt.detect_issuer(self.pages()), 'navy-federal')
        self.assertIsNone(rt.detect_issuer([page(n, ['01-05 Transfer to Navy Federal Credit Union', 'x'])
                                            for n in (1, 2, 3)]))

class RerunTests(unittest.TestCase):
    """``--only`` reuses other documents' cached results, but never one that was waiting for a parser."""

    def test_a_document_waiting_for_a_parser_is_read_again(self):
        waiting = dict(id='a', status='needs_parser', reason='no tier-A parser for issuer unknown')
        self.assertFalse(rt.reuse_cached(waiting, 'a', {'c'}))
        self.assertTrue(rt.reuse_cached(dict(waiting, status='verified'), 'a', {'c'}))
        self.assertTrue(rt.reuse_cached(dict(waiting, status='not_statement'), 'a', {'c'}))
        self.assertFalse(rt.reuse_cached(dict(waiting, status='verified'), 'a', {'a'}))  # named: always read
        self.assertFalse(rt.reuse_cached(None, 'a', {'c'}))  # nothing cached
        self.assertFalse(rt.reuse_cached(dict(waiting, status='verified'), 'a', None))  # whole run

    def test_main_reads_the_waiting_document_and_reuses_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            docs = [dict(id=name, sha256=name * 4, hash='verified', mode='image_only', pages=1, family='?')
                    for name in ('a', 'b', 'c')]
            (tmp / 'inventory.json').write_text(json.dumps(dict(documents=docs)))
            (tmp / 'out' / 'periods').mkdir(parents=True)
            cached = dict(sha256='', mode='image_only', pages=1, periods=[], period_status={})
            (tmp / 'out' / 'periods' / 'a.json').write_text(json.dumps(dict(cached, id='a', status='needs_parser')))
            (tmp / 'out' / 'periods' / 'b.json').write_text(json.dumps(dict(cached, id='b', status='not_statement')))
            with open(os.devnull, 'w') as sink, unittest.mock.patch('sys.stdout', sink):
                rt.main(['--inventory', str(tmp / 'inventory.json'), '--out', str(tmp / 'out'), '--only', 'c',
                         '--jobs', '1'])
            status = {r['id']: r['status'] for r in json.loads((tmp / 'out' / 'status.json').read_text())}
        # a: read again (an image-only document now goes to the visual queue); b: cached result kept; c: read
        self.assertEqual(status, dict(a='needs_visual', b='not_statement', c='needs_visual'))


@unittest.skipUnless(READERS, 'pdfplumber and PyMuPDF are needed for the end-to-end reading check')
class SyntheticCorpusTruthTests(unittest.TestCase):
    """Whatever the independent reader verifies on the synthetic corpus equals the known truth."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((CORPUS / 'manifest.json').read_text())
        cls.results = []
        for record in cls.manifest['files']:
            info = real_inventory.analyse(CORPUS / record['filename'])
            doc = dict(id=record['filename'][:-4], sha256=record['sha256'], hash='verified', mode=info['mode'],
                       pages=info['pages'], page_kinds=info['page_kinds'], family='?')
            cls.results.append((record, rt.document_truth(doc, str(CORPUS))))

    @staticmethod
    def signature(rows):
        return sorted((r['amount_minor'], r['direction'], r['date']) for r in rows)

    def test_every_verified_period_equals_the_known_truth(self):
        verified = 0
        for record, result in self.results:
            for p in result.get('periods', []):
                if p['truth_status'] != 'verified':
                    continue
                verified += 1
                match = [t for t in record['periods'] if t['opening_minor'] == p['opening_minor']
                         and t['closing_minor'] == p['closing_minor'] and t['period_end'] == p['period_end']
                         and self.signature(t['rows']) == self.signature(p['rows'])]
                self.assertTrue(match, f"{p['id']} verified but differs from the corpus truth")
        self.assertGreaterEqual(verified, 3, 'the check would be vacuous')

    def test_an_ocr_layer_reading_is_never_verified(self):
        for record, result in self.results:
            if record['mode'] != 'scan_text_layer':
                continue
            for p in result.get('periods', []):
                self.assertNotEqual(p['truth_status'], 'verified', p['id'])

    def test_image_only_documents_need_visual_truth(self):
        for record, result in self.results:
            if record['mode'] == 'image_only':
                self.assertEqual(result['status'], 'needs_visual', record['filename'])


class TruistTruthTests(unittest.TestCase):
    """Truist consolidated statement (synthetic text): one period per account, from the dated balances."""

    def pages(self, checks_total='= $ 30.00'):
        return [page(1, [
            '111-22-33-44 55555 0 C 001 07 S 66 002', 'JANE Q EXAMPLE', '100 MAIN ST', 'SPRING MD 2 0 9 9 9',
            'Your consolidated statement Contact us', 'For 02/12/2024 Truist.com',
            'TRUIST STUDENT CHECKING 9990001112223',
            'Your previous balance as of 01/12/2024 $100.00', 'Checks - 30.00',
            'Other withdrawals, debits and service charges - 20.00', 'Deposits, credits and interest + 5.00',
            'Your new balance as of 02/12/2024 = $-45.00',
            'Checks', 'DATE CHECK # AMOUNT($)', '01/20 1001 10.00 01/22 * 1003 20.00',
            'Total checks ' + checks_total,
            'Other withdrawals, debits and service charges', 'DATE DESCRIPTION AMOUNT($)',
            '01/13 OVERDRAFT FEE NOT CHARGED 36 0.00', '02/01 DEBIT CARD PURCHASE STORE 20.00', 'continued',
            '00-0000000_Truist_0000_000001 03/17/2025']),
            page(2, ['TRUIST STUDENT CHECKING 9990001112223 (continued)',
                     'Total other withdrawals, debits and service charges = $20.00',
                     'Deposits, credits and interest', 'DATE DESCRIPTION AMOUNT($)', '12/31 NOT IN PERIOD 1.00',
                     'Total deposits, credits and interest = $5.00',
                     'TRUIST ONLINE SAVINGS 9990004445556',
                     'Your previous balance as of 01/12/2024 $2.50 Interest paid this statement period $0.00',
                     'Other withdrawals, debits and service charges - 0.00 2024 interest paid year-to-date $0.00',
                     'Deposits, credits and interest + 0.00 Interest rate 0.01%',
                     'Your new balance as of 02/12/2024 = $2.50',
                     '00-0000000_Truist_0000_000002 03/17/2025'])]

    def test_issuer_and_periods(self):
        pages = self.pages()
        self.assertEqual(rt.detect_issuer(pages), 'truist')
        checking, savings = rt.parse_truist(pages)
        # 'Your previous balance as of 01/12/2024' is the previous statement's last day: the period starts the day after.
        self.assertEqual((checking.account, checking.period_start, checking.period_end), ('9990001112223', '2024-01-13', '2024-02-12'))
        self.assertEqual((checking.opening_minor, checking.closing_minor), (10000, -4500))
        self.assertEqual(checking.holder, 'JANE Q EXAMPLE')
        # Two checks printed side by side on one line; the 0.00 line is not a movement.
        self.assertEqual([r['amount_minor'] for r in checking.rows if r['table'] == 'Checks'], [1000, 2000])
        self.assertEqual(checking.controls['debits_total'], 5000)
        self.assertEqual((savings.opening_minor, savings.closing_minor, savings.rows), (250, 250, []))
        self.assertEqual(rt.reconcile(savings), ('verified', []))

    def test_misread_lines_do_not_verify(self):
        checking = rt.parse_truist(self.pages())[0]
        # The deposit dated 12/31 falls outside the printed period: the reading is not verified.
        self.assertEqual(rt.reconcile(checking)[0], 'unverified')
        checking = rt.parse_truist(self.pages(checks_total='= $ 31.00'))[0]
        self.assertIn('checks lines differ from their printed total', rt.reconcile(checking)[1])


if __name__ == '__main__':
    unittest.main()
