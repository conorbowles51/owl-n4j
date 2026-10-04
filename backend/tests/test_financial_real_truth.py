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


class HarnessRealCorpusTests(unittest.TestCase):
    def entry(self, scored, can_import, expected='auto'):
        return dict(item_id='i', filename='x.pdf', statement_id=None, status='ready' if can_import else 'attention',
                    can_import=can_import, truth_id='x.pdf#1', family='f', expected=expected, defects=[],
                    added_in='real', reasons={}, problems=[], read={}, scored=scored)

    def test_only_scored_periods_count(self):
        m = harness.metrics(dict(periods=[self.entry(True, True), self.entry(False, True), self.entry(False, False)]))
        self.assertEqual((m['overall']['periods'], m['overall']['ready_without_edits']), (1, 1))
        self.assertEqual(m['unscored'], dict(periods=2, offered_for_import=1, by_status={'ready': 1, 'attention': 1}))

    def test_scored_truth_statuses(self):
        self.assertTrue(harness._scored(None))
        self.assertTrue(harness._scored(dict(id='synthetic')))
        self.assertTrue(harness._scored(dict(truth_status='verified')))
        self.assertFalse(harness._scored(dict(truth_status='ocr_reconciled')))
        self.assertFalse(harness._scored(dict(truth_status='unverified')))

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


if __name__ == '__main__':
    unittest.main()
