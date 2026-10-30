"""The whole printed description of payments read from page images (vision_descriptions).

The description lines are read in a request of their own, after the money reading: only a payment's description ever
changes. Real descriptions from the page images of a BBVA Mexico statement (December 2024, page 2 and 3) are used for
the answers; the page reader is a stub.
"""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import select

from postgres.models.financial import AdjudicationEvent, FinancialSourceDocument, FinancialTransaction
from services.financial import saved_reading_replacement as replacement
from services.financial import vision_descriptions as vd

FIRST = 'T17 SPEI ENVIADO SANTANDER'
FULL = ('T17 SPEI ENVIADO SANTANDER 0212248TJZA PENSION ALIMENTICIA 2A Q Ref. 0000259567 014 0001485460571777977 '
        '002601002412020000259567 JULLY LEONOR VAZQUEZ VAZQUEZ')
NEXT_FIRST = 'T17 SPEI ENVIADO BANORTE'
NEXT_FULL = ('T17 SPEI ENVIADO BANORTE 0412248PAGO REC A143 RENTA DIC24 Ref. 0000772484 072 00072180000130110734 '
             '002601002412040000772484 ROLANDO PELAEZ BENGOCHEA')
MISREAD = NEXT_FULL.replace('BENGOCHEA', 'BENGOECHEA')


def rows():
    return vd.listed([dict(id='a', page=2, date='2024-12-02', amount='2386.61', direction='debit', balance=None,
                           description=FIRST),
                      dict(id='b', page=2, date='2024-12-04', amount='163931.35', direction='debit', balance=None,
                           description=NEXT_FIRST)])


def answer(**texts):
    return {'rows': [{'id': key, 'description': value} for key, value in texts.items()]}


class CompletedTests(TestCase):
    def test_lines_starting_with_the_first_line_complete_it(self):
        found, kept = vd.completed(rows(), answer(a=FULL, b=NEXT_FIRST))
        self.assertEqual((found, kept), ({'a': FULL}, {}))

    def test_an_answer_not_starting_with_the_first_line_is_not_taken(self):
        found, kept = vd.completed(rows(), answer(a='SPEI ENVIADO SANTANDER JULLY LEONOR VAZQUEZ VAZQUEZ', b=NEXT_FULL))
        self.assertEqual((found, kept), ({'b': NEXT_FULL}, {'a': 'does_not_start_with_first_line'}))

    def test_a_shorter_answer_is_not_taken(self):
        found, kept = vd.completed(rows(), answer(a='T17 SPEI ENVIADO', b=NEXT_FIRST))
        self.assertEqual((found, kept), ({}, {'a': 'does_not_start_with_first_line'}))

    def test_lines_reaching_into_the_next_payment_are_not_taken(self):
        found, kept = vd.completed(rows(), answer(a=FULL + ' ' + NEXT_FIRST + ' 0412248PAGO REC', b=NEXT_FIRST))
        self.assertEqual((found, kept), ({}, {'a': 'reaches_another_payment'}))

    def test_an_answer_missing_or_adding_a_payment_takes_nothing(self):
        found, kept = vd.completed(rows(), answer(a=FULL))
        self.assertEqual(found, {})
        self.assertEqual(set(kept.values()), {'answer_ids_differ'})
        found, _ = vd.completed(rows(), answer(a=FULL, b=NEXT_FULL, c='T17 SPEI ENVIADO HSBC'))
        self.assertEqual(found, {})

    def test_a_run_on_answer_is_not_taken(self):
        found, kept = vd.completed(rows(), answer(a=FULL + ' X' * 400, b=NEXT_FIRST))
        self.assertEqual(kept, {'a': 'too_long'})


class ReadLinesTests(TestCase):
    pages = [(2, [b'p2']), (3, [b'p3'])]

    def test_reads_agreeing_complete_and_a_name_read_two_ways_stays_as_read(self):
        import threading
        answers, lock = [answer(a=FULL, b=NEXT_FULL)] * 3 + [answer(a=FULL, b=MISREAD)], threading.Lock()
        sent = []

        def read(shown, listed_rows):
            with lock:
                sent.append(([number for number, _ in shown], [row['id'] for row in listed_rows]))
                return answers.pop(), {'prompt_tokens': 10, 'completion_tokens': 5}
        record, found = vd.read_lines(read, self.pages, [dict(r, description=r['first_line']) for r in rows()])
        self.assertEqual(vd.READS, 4)
        self.assertEqual(found, {'a': FULL})
        self.assertEqual(record['kept'], {'b': 'reads_differ'})
        self.assertEqual(sorted(record['differ']['b']), sorted([NEXT_FULL] * 3 + [MISREAD]))
        self.assertEqual(sent, [([2, 3], ['a', 'b'])] * 4, 'its page and the next one, read four times')
        self.assertEqual(record['usage'], {'prompt_tokens': 40, 'completion_tokens': 20})
        self.assertEqual(record['first_lines'], {'a': FIRST})

    def test_a_failed_request_leaves_the_page_as_read(self):
        def read(shown, listed_rows):
            raise TimeoutError('slow')
        record, found = vd.read_lines(read, self.pages, [dict(r, description=r['first_line']) for r in rows()])
        self.assertEqual(found, {})
        self.assertEqual(set(record['kept'].values()), {'request_failed'})
        self.assertEqual(record['errors'][0]['page'], 2)


    def test_nothing_is_sent_that_could_end_after_the_deadline(self):
        import time

        def read(shown, listed_rows):
            raise AssertionError('sent')
        record, found = vd.read_lines(read, self.pages, [dict(r, description=r['first_line']) for r in rows()],
                                      deadline=time.monotonic() + vd.request_seconds() - 1)
        self.assertEqual((found, set(record['kept'].values())), ({}, {'deferred'}))


class CompleteRequestTests(TestCase):
    """A new page-image reading: only its payment rows' descriptions and reasons change, before it is saved."""

    def setUp(self):
        import fitz
        import tempfile
        directory = tempfile.mkdtemp()
        self.path = f'{directory}/statement.pdf'
        with fitz.open() as pdf:
            for _ in range(3):
                pdf.new_page()
            pdf.save(self.path)

    def request(self):
        return dict(currency='MXN', rows=[
            dict(id='manual:opening-balance', excluded=True, manual_page=2, description='Opening Balance',
                 amount_minor='0', direction=None, balance_minor='100', reason='Read from page image, page 2.'),
            dict(id='manual:vision-p2-0', excluded=False, manual_page=2, date='2024-12-02', description=FIRST,
                 amount_minor='238661', direction='debit', balance_minor=None, reason='Read from page image, page 2.'),
            dict(id='2:0:5', excluded=True, description='T17 SPEI ENVIADO', amount_minor='238661', direction='debit')])

    def complete(self, request, texts):
        class Session:
            def rollback(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def request_for(model, key, provider):
            def read(shown, listed_rows):
                self.assertEqual([number for number, _ in shown], [2, 3])
                return answer(**{row['id']: texts.get(row['id'], row['first_line']) for row in listed_rows}), {}
            return read
        with patch.object(vd, '_reader', return_value=('deepseek', 'deepseek-flash', 'key')), \
                patch('services.financial.vision_reader.render_pages',
                      side_effect=lambda path, pages, strips=None: [(p, [b'png']) for p in pages]), \
                patch('services.financial.vision_reader._reserve', return_value=True), \
                patch('services.financial.vision_reader._add_spend'):
            return vd.complete_request(Session, 'case', self.path, request, request_for=request_for)

    def test_only_the_payment_rows_description_and_reason_change(self):
        request = self.request()
        before = deepcopy(request)
        record = self.complete(request, {'manual:vision-p2-0': FULL})
        self.assertEqual((record['status'], record['completed'], record['provider']), ('read', 1, 'deepseek'))
        self.assertEqual(request['rows'][1]['description'], FULL)
        self.assertEqual(request['rows'][1]['reason'], 'Read from page image, page 2. ' + vd.REASON.format(
            page=2, by='DeepSeek'))
        for key in ('id', 'amount_minor', 'direction', 'date', 'balance_minor', 'manual_page', 'excluded'):
            self.assertEqual(request['rows'][1][key], before['rows'][1][key], key)
        self.assertEqual((request['rows'][0], request['rows'][2]), (before['rows'][0], before['rows'][2]))

    def test_switched_off_nothing_is_sent(self):
        request = self.request()
        with patch.object(vd, 'LINES', False):
            self.assertIsNone(self.complete(request, {'manual:vision-p2-0': FULL}))
        self.assertEqual(request['rows'][1]['description'], FIRST)


class SavedImageDescriptionTests(TestCase):
    """A saved statement's payment read from a page image gains its description lines through the correction chain;
    its names stay on it and its money is untouched."""

    def setUp(self):
        from tests.test_financial_saved_reading_replacement import DescriptionRefreshTests
        self.d = DescriptionRefreshTests('test_the_same_description_is_same')
        self.d.setUp()
        self.f = self.d.f
        self.document_id = self.d.save(now='Incoming')
        self.labelled = self.d.label(self.document_id, 'EXAMPLE SUPPLIER SA')
        with self.f.SessionLocal() as db:
            row = db.get(FinancialTransaction, self.labelled)
            provenance = deepcopy(row.provenance or {})
            provenance['statement_import_review'] = dict(provenance.get('statement_import_review') or {},
                                                         id='manual:vision-p1-0', manual_page=1,
                                                         reason='Read from page image, page 1.',
                                                         description=row.description)
            row.provenance = provenance
            db.commit()

    def tearDown(self):
        self.d.tearDown()

    def store_lines(self, text, first='Incoming'):
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, self.document_id)
            metadata = dict(document.metadata_ or {})
            metadata[vd.METADATA_KEY] = dict(provider='deepseek', model='deepseek-flash', at='2026-10-30T05:00:00+00:00',
                                             prompt_version=vd.PROMPT_VERSION, lines={str(self.labelled): text},
                                             first_lines={str(self.labelled): first}, kept={})
            document.metadata_ = metadata
            db.commit()

    def assess(self):
        with self.f.SessionLocal() as db:
            return replacement.assess_image_descriptions(db, db.get(FinancialSourceDocument, self.document_id))

    def test_the_lines_complete_the_payment_keeping_its_name_and_money(self):
        self.store_lines('Incoming transfer from EXAMPLE SUPPLIER SA')
        saved_rows = self.d.t.admitted_rows()
        verdict = self.assess()
        self.assertEqual((verdict['outcome'], verdict['basis']), ('describe', replacement.IMAGE_DESCRIPTION_BASIS))
        self.assertEqual([(c['transaction_id'], c['after']) for c in verdict['changes']],
                         [(str(self.labelled), 'Incoming transfer from EXAMPLE SUPPLIER SA')])
        result = replacement.refresh_descriptions(session_factory=self.f.SessionLocal, case_id=self.d.t.case_id,
                                                  document_id=self.document_id, from_images=True)
        self.assertTrue(result['applied'], result)
        self.assertEqual(self.d.t.admitted_rows(), saved_rows, 'the same payments count, once')
        from services.financial.payment_labels import payment_label_view
        with self.f.SessionLocal() as db:
            old = db.get(FinancialTransaction, self.labelled)
            new = db.get(FinancialTransaction, old.superseded_by_id)
            self.assertEqual((old.ledger_status, new.description),
                             ('superseded', 'Incoming transfer from EXAMPLE SUPPLIER SA'))
            self.assertEqual((new.amount_minor, new.direction, new.transaction_date, new.running_balance_minor),
                             (old.amount_minor, old.direction, old.transaction_date, old.running_balance_minor))
            lines = new.provenance['reader_descriptions']
            self.assertEqual((lines['previous_description'], lines['basis'], lines['page'], lines['read_by']['model']),
                             ('Incoming', replacement.IMAGE_DESCRIPTION_BASIS, 1, 'deepseek-flash'))
            view = payment_label_view(new, new.account)
            self.assertEqual((view['from_name'], view['label_sources']['from_name']['source']),
                             ('EXAMPLE SUPPLIER SA', 'investigator'))
            event = db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.subject_id == old.id,
                                                              AdjudicationEvent.decision == 'correct_transaction'))
            self.assertEqual((event.reason, event.after['basis']),
                             (replacement.IMAGE_DESCRIPTION_REASON, replacement.IMAGE_DESCRIPTION_BASIS))
        self.assertEqual(self.assess()['outcome'], 'same', 'done once')

    def test_a_description_changed_since_the_lines_were_read_stays(self):
        self.store_lines('Incoming transfer from EXAMPLE SUPPLIER SA', first='Incoming wire')
        verdict = self.assess()
        self.assertEqual(verdict['outcome'], 'same')
        self.assertEqual([k['code'] for k in verdict['kept']], ['description_changed'])

    def test_lines_dropping_a_word_stay(self):
        self.store_lines('Wire from EXAMPLE SUPPLIER SA')
        self.assertEqual([k['code'] for k in self.assess()['kept']], ['description_loses_text'])

    def test_a_payment_not_read_from_a_page_image_is_never_touched(self):
        with self.f.SessionLocal() as db:
            row = db.get(FinancialTransaction, self.labelled)
            provenance = deepcopy(row.provenance)
            provenance['statement_import_review']['id'] = '1:0:3'
            row.provenance = provenance
            db.commit()
        self.store_lines('Incoming transfer from EXAMPLE SUPPLIER SA')
        self.assertEqual(self.assess()['outcome'], 'same')

    def test_switched_off_nothing_changes(self):
        self.store_lines('Incoming transfer from EXAMPLE SUPPLIER SA')
        with patch.object(vd, 'LINES', False):
            self.assertEqual(self.assess()['code'], 'disabled')
