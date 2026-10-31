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
FULL = ('T17 SPEI ENVIADO SANTANDER 0212248TJZA PENSIONA ALIMENTICIA 2A Q Ref. 0000259567 014 0001485460571777977 '
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


    def test_lines_reaching_into_a_payment_printing_the_same_first_line_are_not_taken(self):
        same = vd.listed([dict(id=k, page=2, date='2024-12-04', amount='1.00', direction='debit', balance=None,
                               description=FIRST) for k in ('a', 'b')])
        found, kept = vd.completed(same, answer(a=FULL + ' ' + FIRST + ' 0412248PAGO', b=FIRST))
        self.assertEqual((found, kept), ({}, {'a': 'reaches_another_payment'}))

    def test_the_first_line_keeps_its_saved_text(self):
        found, _ = vd.completed(rows(), answer(a=FULL.replace('T17 SPEI ENVIADO SANTANDER', 't17 spei enviado santander'),
                                               b=NEXT_FIRST))
        self.assertEqual(found, {'a': FULL})


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

    def test_lines_reaching_into_the_next_pages_first_payment_are_not_taken(self):
        listed = [dict(id='a', page=2, date='2024-12-02', amount='2386.61', direction='debit', balance=None,
                       description=FIRST),
                  dict(id='b', page=3, date='2024-12-04', amount='163931.35', direction='debit', balance=None,
                       description=NEXT_FIRST)]

        def read(shown, listed_rows):
            return answer(**{row['id']: (FULL + ' ' + NEXT_FIRST + ' 0412248PAGO REC' if row['id'] == 'a'
                                         else row['first_line']) for row in listed_rows}), {}
        record, found = vd.read_lines(read, self.pages + [(4, [b'p4'])], listed)
        self.assertEqual(found, {})
        self.assertEqual(record['kept'], {'a': 'reaches_another_payment'})

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

    def test_a_new_reading_is_asked_for_its_lines_only_as_before(self):
        asked = []

        def description_request(model, key, provider, first_lines=True):
            asked.append(first_lines)

            def read(shown, listed_rows):
                return answer(**{row['id']: row['first_line'] for row in listed_rows}), {}
            return read
        with patch.object(vd, '_reader', return_value=('deepseek', 'deepseek-flash', 'key')), \
                patch.object(vd, 'description_request', side_effect=description_request), \
                patch('services.financial.vision_reader.render_pages',
                      side_effect=lambda path, pages, strips=None: [(p, [b'png']) for p in pages]), \
                patch('services.financial.vision_reader._reserve', return_value=True), \
                patch('services.financial.vision_reader._add_spend'):
            record = vd.complete_request(self._session(), 'case', self.path, self.request())
        self.assertEqual((asked, record['prompt_version']), ([False], vd.LINES_PROMPT_VERSION))
        self.assertNotIn('printed_first_line', vd.instructions([], first_lines=False))
        self.assertNotIn('printed_first_line', str(vd.LINES_SCHEMA))

    @staticmethod
    def _session():
        class Session:
            def rollback(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False
        return Session

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


def printed(**texts):
    """An answer giving each payment's first line as printed (its description being that line)."""
    return {'rows': [{'id': key, 'description': value, 'printed_first_line': value} for key, value in texts.items()]}


class PrintedFirstLineTests(TestCase):
    """A misread first line (fin-parties 2026-10-30: printed RECIBIDOBANORTE saved as RECIDOBANORTE) is proposed for
    correction only when the printed line is the same line with a few characters misread."""

    def listed(self, first=FIRST, other=NEXT_FIRST):
        return vd.listed([dict(id='a', page=2, date='2024-12-02', amount='1.00', direction='debit', balance=None,
                               description=first),
                          dict(id='b', page=2, date='2024-12-04', amount='2.00', direction='debit', balance=None,
                               description=other)])

    def test_the_five_measured_misreads_are_proposed(self):
        for saved, page in (('T20 SPEI RECIDOBANORTE', 'T20 SPEI RECIBIDOBANORTE'),
                            ('SUNOCC 0831782800', 'SUNOCO 0831782800'),
                            ('CAPITAL ONE MOBILE PMT AuthDate', 'CAPITAL ONE MOBILE PYMTAuthDate'),
                            ('Withdrawal Online Banking Transfer To HOPPER, SKYLAR G XXXXXXXX Share 0040',
                             'Withdrawal Online Banking Transfer To HOPPER,SKYLAR G XXXXXXXXXX Share 0040')):
            self.assertEqual(vd.printed_first_lines(self.listed(saved), printed(a=page, b=NEXT_FIRST)), {'a': page})

    def test_the_same_line_or_a_case_difference_is_no_correction(self):
        self.assertEqual(vd.printed_first_lines(self.listed(), printed(a=FIRST, b=NEXT_FIRST)), {})
        self.assertEqual(vd.printed_first_lines(self.listed(), printed(a=FIRST.lower(), b=NEXT_FIRST)), {})

    def test_another_payments_line_or_a_different_line_is_never_a_correction(self):
        self.assertEqual(vd.printed_first_lines(self.listed(), printed(a=NEXT_FIRST, b=NEXT_FIRST)), {},
                         'the next entry, 0.84 alike')
        self.assertEqual(vd.printed_first_lines(self.listed('T17 SPEI ENVIADO SANTANDER', 'X'),
                                                printed(a='T17 SPEI ENVIADO BANORTE', b='X')), {},
                         'not listed, but 7 characters changed')

    def test_an_answer_missing_a_payment_gives_nothing(self):
        self.assertEqual(vd.printed_first_lines(self.listed('SUNOCC 0831782800'), printed(a='SUNOCO 0831782800')), {})

    def test_four_agreeing_reads_propose_and_reads_that_differ_do_not(self):
        import threading
        listed = self.listed('SUNOCC 0831782800')
        answers, lock = ([printed(a='SUNOCO 0831782800', b='T17 SPEI ENVIADO BANORTF')] * 3
                         + [printed(a='SUNOCO 0831782800', b=NEXT_FIRST)]), threading.Lock()

        def read(shown, listed_rows):
            with lock:
                return answers.pop(), {}
        record, found = vd.read_lines(read, [(2, [b'p2'])], [dict(r, description=r['first_line']) for r in listed])
        self.assertEqual(record['first_line_fixes'], {'a': 'SUNOCO 0831782800'})
        self.assertEqual(sorted(record['first_line_differ']['b'], key=str),
                         sorted(['T17 SPEI ENVIADO BANORTF'] * 3 + [None], key=str))
        self.assertEqual(record['first_lines'], {'a': 'SUNOCC 0831782800'})
        self.assertEqual(record['looked'], ['a', 'b'])

    def test_the_request_asks_for_the_printed_first_line(self):
        self.assertIn('printed_first_line', vd.SCHEMA['properties']['rows']['items']['required'])
        self.assertIn('never copy first_line', vd.PROMPT)


class SavedFirstLineTests(SavedImageDescriptionTests):
    """A proposed first-line correction is applied through the correction chain as the reading model's work for a
    person, never as theirs; the earlier row and its text stay."""
    WHO = dict(for_name='Neil Byrne', for_email='neil@owlconsultancygroup.com')

    def store_fix(self, key, text, first='Incoming'):
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, self.document_id)
            metadata = dict(document.metadata_ or {})
            stored = dict(metadata.get(vd.METADATA_KEY) or dict(provider='deepseek', model='deepseek-flash', lines={},
                                                                 kept={}, first_lines={}))
            stored['first_lines'] = {**stored.get('first_lines', {}), key: first}
            stored['first_line_fixes'] = {key: dict(text=text, provider='deepseek', model='deepseek-flash',
                                                    at='2026-10-30T22:00:00+00:00', prompt_version=vd.PROMPT_VERSION)}
            metadata[vd.METADATA_KEY] = stored
            document.metadata_ = metadata
            db.commit()

    def first_lines(self):
        with self.f.SessionLocal() as db:
            return replacement.assess_first_line_fixes(db, db.get(FinancialSourceDocument, self.document_id))

    def correct(self):
        return replacement.correct_first_lines(session_factory=self.f.SessionLocal, case_id=self.d.t.case_id,
                                               document_id=self.document_id, **self.WHO)

    def test_a_read_payment_gets_its_printed_first_line_as_the_models_reading(self):
        self.store_fix(str(self.labelled), 'lncoming')
        saved_rows = self.d.t.admitted_rows()
        verdict = self.first_lines()
        self.assertEqual([(c['first_line_before'], c['first_line_after'], c['after']) for c in verdict['changes']],
                         [('Incoming', 'lncoming', 'lncoming')])
        result = self.correct()
        self.assertTrue(result['applied'], result)
        self.assertEqual(self.d.t.admitted_rows(), saved_rows, 'the same payments count, once')
        with self.f.SessionLocal() as db:
            old = db.get(FinancialTransaction, self.labelled)
            new = db.get(FinancialTransaction, old.superseded_by_id)
            self.assertEqual((old.ledger_status, old.description, new.description), ('superseded', 'Incoming', 'lncoming'))
            self.assertEqual((new.amount_minor, new.direction, new.transaction_date, new.running_balance_minor),
                             (old.amount_minor, old.direction, old.transaction_date, old.running_balance_minor))
            provenance = new.provenance['reader_descriptions']
            self.assertEqual((provenance['basis'], provenance['first_line'], provenance['read_by']['model']),
                             (replacement.FIRST_LINE_BASIS, {'before': 'Incoming', 'after': 'lncoming'},
                              'deepseek-flash'))
            event = db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.subject_id == old.id,
                                                              AdjudicationEvent.decision == 'correct_transaction'))
            self.assertEqual(event.reason, replacement.FIRST_LINE_REASON)
            self.assertNotEqual(event.actor_name, 'Neil Byrne', 'never as the person')
            self.assertEqual((event.actor_origin['kind'], event.actor_origin['model'],
                              event.actor_origin['model_id'], event.actor_origin['for']['name']),
                             ('model', 'DeepSeek', 'deepseek-flash', 'Neil Byrne'))
            self.assertEqual(event.actor_origin['citation']['page'], 1)
        self.assertEqual(self.first_lines()['outcome'], 'same', 'done once')
        from services.financial.transaction_query import to_view
        with self.f.SessionLocal() as db:
            old = db.get(FinancialTransaction, self.labelled)
            shown = to_view(db.get(FinancialTransaction, old.superseded_by_id)).to_json()['description_correction']
            self.assertEqual({k: shown[k] for k in ('before', 'after', 'previous_description', 'model', 'model_id',
                                                     'for_name', 'confirmed', 'page')},
                             dict(before='Incoming', after='lncoming', previous_description='Incoming', model='DeepSeek',
                                  model_id='deepseek-flash', for_name='Neil Byrne', confirmed=False, page=1))
            self.assertNotIn('description_correction', to_view(old).to_json(), 'only on the corrected payment')

    def test_a_completed_payment_keeps_its_added_lines(self):
        self.store_lines('Incoming transfer from EXAMPLE SUPPLIER SA')
        replacement.refresh_descriptions(session_factory=self.f.SessionLocal, case_id=self.d.t.case_id,
                                         document_id=self.document_id, from_images=True)
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, self.document_id)
            pairs = vd.first_line_rows(db, document)
            completed = db.get(FinancialTransaction, self.labelled).superseded_by_id
            self.assertEqual([(row.id, first) for row, first in pairs], [(completed, 'Incoming')],
                             'read again for its first line, as read from the page image')
        self.store_fix(str(completed), 'lncoming')
        self.assertTrue(self.correct()['applied'])
        with self.f.SessionLocal() as db:
            new = db.get(FinancialTransaction, db.get(FinancialTransaction, completed).superseded_by_id)
            self.assertEqual(new.description, 'lncoming transfer from EXAMPLE SUPPLIER SA')
            self.assertEqual(vd.first_line_rows(db, db.get(FinancialSourceDocument, self.document_id)), [],
                             'a corrected first line is not read again')

    def test_only_the_named_payments_are_corrected(self):
        self.store_fix(str(self.labelled), 'lncoming')
        with self.f.SessionLocal() as db:
            document = db.get(FinancialSourceDocument, self.document_id)
            self.assertEqual(replacement.assess_first_line_fixes(db, document, only={'other'})['outcome'], 'same')
        result = replacement.correct_first_lines(session_factory=self.f.SessionLocal, case_id=self.d.t.case_id,
                                                 document_id=self.document_id, only={'other'}, **self.WHO)
        self.assertNotIn('applied', result)
        self.assertEqual(self.first_lines()['outcome'], 'describe', 'still proposed')

    def test_description_lines_waiting_are_added_first(self):
        self.store_lines('Incoming transfer from EXAMPLE SUPPLIER SA')
        self.store_fix(str(self.labelled), 'lncoming')
        verdict = self.first_lines()
        self.assertEqual((verdict['outcome'], [k['code'] for k in verdict['kept']]),
                         ('same', ['description_lines_pending']))

    def test_a_payment_whose_earlier_row_was_read_is_not_read_again(self):
        self.store_lines('Incoming transfer from EXAMPLE SUPPLIER SA')
        replacement.refresh_descriptions(session_factory=self.f.SessionLocal, case_id=self.d.t.case_id,
                                         document_id=self.document_id, from_images=True)
        with self.f.SessionLocal() as db:
            pairs = vd.first_line_rows(db, db.get(FinancialSourceDocument, self.document_id))
            self.assertEqual(len(vd.not_looked({'looked': [str(self.labelled)]}, pairs)), 0)
            self.assertEqual(len(vd.not_looked({}, pairs)), 1)

    def test_a_first_line_changed_since_stays(self):
        self.store_fix(str(self.labelled), 'lncoming', first='Incoming wire')
        verdict = self.first_lines()
        self.assertEqual((verdict['outcome'], [k['code'] for k in verdict['kept']]), ('same', ['first_line_changed']))

    def test_no_fix_stored_changes_nothing(self):
        self.store_lines('Incoming transfer from EXAMPLE SUPPLIER SA')
        self.assertEqual(self.first_lines()['code'], 'no_first_line_fixes')
