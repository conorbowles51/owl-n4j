"""fin-judgements: recording is idempotent, a recording failure never breaks the rule, and the saved statement's
own record yields the judgement calls its rules made (opening worked back, damaged cell, file-name currency)."""
import shutil
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole
from postgres.models.evidence import EvidenceFile
from postgres.models.financial import (AdjudicationEvent, FinancialAccount, FinancialSourceDocument,
                                       FinancialStatementPeriod, FinancialTransaction)
from postgres.models.financial_judgements import FinancialJudgement
from postgres.models.user import User
from services.financial import judgements
from services.financial.decisions import Actor


def _model_edit(at, before_account, after_account, before_details, after_details, *, model=True):
    origin = dict(kind='model', model='Claude', at=at, **{'for': dict(name='Neil Byrne', user_id=None)},
                  citation=dict(file='09 BBVA 23 USD.pdf', page=1), how='page 1 prints the addressee')
    entry = dict(at=at, actor_name='Claude (for Neil Byrne)' if model else 'Alex',
                 before=dict(account_id=before_account, details=before_details, currency='USD', balances={}),
                 after=dict(account_id=after_account, details=after_details, currency='USD', balances={}))
    if model:
        entry['origin'] = origin
    return entry


# The live shape (d5b330d1, Sept 2023): Claude corrected the holder, then the account number, which moved the
# statement onto another account.
_HOLDER = _model_edit('2026-10-31T07:41:24', 'acct-a', 'acct-a', dict(holder='ns BVA', account_number='119201424'),
                      dict(holder='CAAL ENERGY SYSTEMS SA DE CV', account_number='119201424'))
_NUMBER = _model_edit('2026-10-31T07:52:40', 'acct-a', 'acct-b',
                      dict(holder='CAAL ENERGY SYSTEMS SA DE CV', account_number='119201424'),
                      dict(holder='CAAL ENERGY SYSTEMS SA DE CV', account_number='0119201424'))


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='loupe-judgements-')
        self.engine = create_engine(f"sqlite+pysqlite:///{Path(self._dir) / 'j.db'}", future=True)
        Base.metadata.create_all(self.engine, tables=[
            User.__table__, Case.__table__, FinancialJudgement.__table__, AdjudicationEvent.__table__,
            EvidenceFile.__table__, FinancialSourceDocument.__table__, FinancialStatementPeriod.__table__,
            FinancialAccount.__table__, FinancialTransaction.__table__])
        self.db = sessionmaker(bind=self.engine, autoflush=False)()
        user = User(id=uuid.uuid4(), email='a@example.test', name='Alex', password_hash='x',
                    global_role=GlobalRole.user, is_active=True)
        self.case = Case(id=uuid.uuid4(), title='J', created_by_user_id=user.id, owner_user_id=user.id)
        self.db.add_all([user, self.case])
        self.db.commit()
        self.actor = Actor(name='Alex', email='a@example.test', user_id=user.id)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._dir, ignore_errors=True)

    def _record(self, reading='doc-1'):
        return judgements.record_judgement(
            self.db, case_id=self.case.id, subject_type='statement_period', subject_id=self.subject,
            rule_id='L8.unprinted_opening', summary='Opening 1.00 is the closing less the payments.',
            target_key='opening_balance', reading=reading)

    def test_the_same_reading_records_once(self):
        self.subject = uuid.uuid4()
        first, again = self._record(), self._record()
        self.db.commit()
        self.assertEqual(first.id, again.id)
        self.assertEqual(self.db.scalar(select(FinancialJudgement.id).where(FinancialJudgement.id == first.id)), first.id)
        self.assertEqual(len(self.db.scalars(select(FinancialJudgement)).all()), 1)
        self._record(reading='doc-2')  # a new reading of the statement is a new call
        self.assertEqual(len(self.db.scalars(select(FinancialJudgement)).all()), 2)
        self.assertEqual(first.strength, 'inferred')

    def test_a_recording_failure_never_reaches_the_rule(self):
        broken = SimpleNamespace(scalar=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('database gone')))
        self.assertIsNone(judgements.record_judgement(
            broken, case_id=self.case.id, subject_type='transaction', subject_id=uuid.uuid4(),
            rule_id='L1.glyph_cell', summary='x'))
        self.assertEqual(judgements.record_saved(broken, SimpleNamespace(id=uuid.uuid4(), metadata_=None)), [])

    def test_looks_right_and_correct_it(self):
        self.subject = uuid.uuid4()
        row = self._record()
        self.db.commit()
        done = judgements.confirm(self.db, case_id=self.case.id, judgement_id=row.id, actor=self.actor)
        self.assertEqual((done['status'], done['resolved_by']), ('confirmed', 'Alex'))
        with self.assertRaises(judgements.JudgementError):
            judgements.correct(self.db, case_id=self.case.id, judgement_id=row.id, actor=self.actor, reason=' ')
        decision = AdjudicationEvent(id=uuid.uuid4(), case_id=self.case.id, subject_type='statement_period',
                                     subject_id=self.subject, subject_sequence=1, decision='correct_transaction',
                                     reason='The page prints 2.00', before={'opening': 100}, after={'opening': 200},
                                     actor_name='Alex', actor_email='a@example.test')
        self.db.add(decision)
        self.db.commit()
        fixed = judgements.correct(self.db, case_id=self.case.id, judgement_id=row.id, actor=self.actor,
                                   reason='The July statement prints 2.00')
        self.assertEqual((fixed['status'], fixed['adjudication_id']), ('corrected', str(decision.id)))
        track = {r['rule_id']: r for r in judgements.track_record(self.db, self.case.id)}
        self.assertEqual(track['L8.unprinted_opening']['corrected'], 1)


    def test_search_filters_and_counts_like_the_queue(self):
        for rule, origin, summary in (('L1.glyph_cell', 'processor', 'Damaged cell read as 2,293.42.'),
                                      ('L8.unprinted_opening', 'processor', 'Opening worked back from the closing.'),
                                      ('agent.page_entry', 'agent', 'Its 156 payments were entered by hand.')):
            judgements.record_judgement(self.db, case_id=self.case.id, subject_type='statement_period',
                                        subject_id=uuid.uuid4(), rule_id=rule, summary=summary, origin=origin)
        self.db.commit()
        page = judgements.search(self.db, self.case.id)
        self.assertEqual([i['rule_id'] for i in page['items']],  # all "Check first": inferred, then hand entry
                         ['L8.unprinted_opening', 'agent.page_entry', 'L1.glyph_cell'])
        typed = judgements.search(self.db, self.case.id, categories=['damaged_scan'])
        self.assertEqual(typed['total'], 1)
        # Each facet counts under the other filters, never its own.
        self.assertEqual(typed['facets']['category'], {'all': 3, 'damaged_scan': 1, 'balance': 1, 'hand_entry': 1})
        self.assertEqual(typed['facets']['origin'], {'all': 1, 'processor': 1})
        self.assertEqual(judgements.search(self.db, self.case.id, q='HAND entered')['total'], 1)
        self.assertEqual(len(judgements.search(self.db, self.case.id, offset=1, limit=1)['items']), 1)

    def test_calls_come_focus_first_by_priority_and_amount(self):
        # Check soon: an inferred call and a proved one, recorded proved first, so only the strength orders them.
        calls = (('category.model', 'transaction', 900_00), ('L26.duplicate_set_aside', 'statement_period', None),
                 ('L1.glyph_cell', 'transaction', 5_00), ('L9.scan_amount_marks', 'transaction', 70_000_00),
                 ('L30c.contract_refile', 'statement_period', None))
        for rule, subject_type, amount in calls:
            judgements.record_judgement(self.db, case_id=self.case.id, subject_type=subject_type,
                                        subject_id=uuid.uuid4(), rule_id=rule, summary=f'{rule} call.',
                                        evidence={'amount_minor': amount} if amount is not None else None)
        self.db.commit()
        page = judgements.search(self.db, self.case.id)
        # Check first (larger amount first), then Check soon (inferred before checked), then When convenient.
        self.assertEqual([(i['priority'], i['rule_id']) for i in page['items']],
                         [(1, 'L9.scan_amount_marks'), (1, 'L1.glyph_cell'), (2, 'L30c.contract_refile'),
                          (2, 'L26.duplicate_set_aside'), (3, 'category.model')])
        self.assertEqual(page['items'][0]['priority_label'], 'Check first')
        self.assertEqual(page['facets']['priority'], {'all': 5, '1': 2, '2': 2, '3': 1})
        soon = judgements.search(self.db, self.case.id, priorities=['2'])
        self.assertEqual([i['rule_id'] for i in soon['items']], ['L30c.contract_refile', 'L26.duplicate_set_aside'])
        self.assertEqual(soon['facets']['priority'], {'all': 5, '1': 2, '2': 2, '3': 1})  # its own filter not applied
        # Paging keeps the order; the export carries the tier and every matching call, not one page.
        self.assertEqual([i['rule_id'] for i in judgements.search(self.db, self.case.id, offset=2, limit=2)['items']],
                         ['L30c.contract_refile', 'L26.duplicate_set_aside'])
        lines = judgements.export_csv(judgements.search(self.db, self.case.id, limit=1, everything=True)
                                      ).decode('utf-8-sig').splitlines()
        self.assertEqual(len(lines), 6)
        self.assertTrue(lines[0].startswith('Priority,Why this priority,Status'))
        self.assertTrue(lines[1].startswith('1 Check first,'))
        self.assertTrue(lines[5].startswith('3 When convenient,'))
        self.assertEqual(judgements.counts(self.db, self.case.id)['case']['priority_1'], 2)

    def test_a_model_edit_of_statement_details_is_an_open_call_until_a_person_settles_it(self):
        # The recording reads only the statement's id, case and stored history.
        document = SimpleNamespace(id=uuid.uuid4(), case_id=self.case.id,
                                   metadata_=dict(statement_details_history=[_HOLDER]))
        first = judgements.record_model_details(self.db, document)
        self.assertEqual((first.rule_id, first.status, first.origin), ('model.statement_account', 'open', 'agent'))
        # A further model edit before anyone settles the call updates the same call: one call, both edits.
        document.metadata_ = dict(statement_details_history=[_HOLDER, _NUMBER])
        again = judgements.record_model_details(self.db, document)
        self.db.commit()
        self.assertEqual(again.id, first.id)
        self.assertIn('moved the statement', again.summary)
        self.assertEqual(len(self.db.scalars(select(FinancialJudgement)).all()), 1)
        self.assertEqual(judgements.statement_model_work(self.db, self.case.id, document.id)['status'], 'not_confirmed')
        self.assertFalse(judgements.statement_model_work(self.db, self.case.id, document.id)['saved'])
        # A person confirms the statement: the call is theirs to settle, a model's confirm is refused.
        with self.assertRaises(Exception):
            judgements.confirm_statement(self.db, case_id=self.case.id, source_document_id=document.id,
                                         actor=Actor(name='Claude (for Neil Byrne)', email='n@x', user_id=None,
                                                     origin=dict(kind='model', model='Claude')))
        self.db.rollback()
        judgements.confirm_statement(self.db, case_id=self.case.id, source_document_id=document.id, actor=self.actor)
        self.assertIsNone(judgements.record_model_details(self.db, document))  # settled edits record nothing more
        later = _model_edit('2026-11-01T09:00:00', 'acct-b', 'acct-b', _NUMBER['after']['details'],
                            dict(_NUMBER['after']['details'], institution='BBVA'))
        document.metadata_ = dict(statement_details_history=[_HOLDER, _NUMBER, later])
        newer = judgements.record_model_details(self.db, document)
        self.assertNotEqual(newer.id, first.id)
        self.assertEqual((newer.rule_id, newer.status), ('model.statement_details', 'open'))
        self.assertEqual(newer.evidence['edits'], ['2026-11-01T09:00:00'])


class DetectionTests(unittest.TestCase):
    def test_every_rule_has_a_priority(self):
        import re
        self.assertEqual(set(judgements.RULES) - set(judgements.RULE_PRIORITY), set())
        self.assertEqual(set(judgements.RULE_PRIORITY) - set(judgements.RULES), set())
        self.assertTrue(all(tier in judgements.PRIORITIES and why for tier, why in judgements.RULE_PRIORITY.values()))
        # Every rule id a module records by name is in the table too.
        root = Path(judgements.__file__).resolve().parent
        named = set()
        for path in root.glob('*.py'):
            text = path.read_text()
            named |= set(re.findall(r"rule_id=['\"]([A-Za-z0-9_.]+)['\"]", text))
            named |= set(re.findall(r"record_on_document\([^'\"]*?['\"]([A-Za-z0-9_]+\.[A-Za-z0-9_.]+)['\"]", text))
        named |= set(judgements.FIELD_BASIS.values()) | set(judgements.GLYPH_BASIS.values())
        self.assertEqual(named - set(judgements.RULE_PRIORITY), set())

    def test_a_reading_previews_its_calls_before_it_is_saved(self):
        reading = [dict(id='4:1:7', kind='transaction', page_number=4, excluded=False,
                        fields=dict(amount_minor='229342', date='2023-08-03', credit_column='2'),
                        source_cells=[dict(column_index=2, expected_text='2,293.42', locator=dict(page=4))],
                        value_repairs=[dict(page_number=4, held_text='~293.42', text='2293.42',
                                            basis='one_unread_glyph_fixed_by_printed_balances')])]
        review = [dict(id='manual:opening-balance', excluded=True, manual_page=2, balance_minor='1234000',
                       reason='Opening balance not printed in these pages: the closing less the payments.')]
        found = {f['rule_id']: f for f in judgements.preview(reading, review, currency='MXN')}
        self.assertEqual(found['L16.one_glyph']['row_id'], '4:1:7')
        self.assertIn('2,293.42', found['L16.one_glyph']['summary'])
        self.assertEqual(found['L8.unprinted_opening']['category'], 'balance')

    def test_a_hand_entry_is_said_plainly(self):
        period = SimpleNamespace(currency='MXN', opening_balance_minor=151477851, closing_balance_minor=976103067,
                                 credit_total_minor=1057821188, debit_total_minor=233195972,
                                 reconciliation_status='balanced', opening_balance_source='printed',
                                 closing_balance_source='printed')
        line = ('- ca490c7f | ECO Oct 2023 MN (0118467374; PDF pages 1-12 = bank PAGINA 2/17-13/17; reader read '
                'nothing; right edge of scan cut) | 156 movements from page images, every printed daily saldo (14) '
                'agrees; 145 cargos 2,331,959.72 / 11 abonos 10,578,211.88 = printed totals (13/17) | SAVED.')
        text = judgements.agent_entry_summary(rows=156, period=period, line=judgements.statement_log_line(
            line, ['ca490c7f']), previous_closing=151477851)
        self.assertEqual(text, "Loupe could not read this scan (the right edge of the pages is cut off), so its 156 "
                               "payments were entered by hand from the page images. Checked: all 14 printed daily "
                               "balances agree; the printed totals agree (money in 10,578,211.88, money out "
                               "2,331,959.72); the opening is the previous statement's closing.")
        for internal in ('PAGINA', 'saldo', 'cargos', 'ca490c7f', '...'):
            self.assertNotIn(internal, text)


    def test_the_saved_record_shows_each_rule_that_decided(self):
        period = SimpleNamespace(id=uuid.uuid4(), currency='MXN', opening_balance_minor=1234000,
                                 closing_balance_minor=1500000, period_start=date(2023, 8, 1),
                                 period_start_source='printed')
        document = SimpleNamespace(id=uuid.uuid4(), case_id=uuid.uuid4(), evidence_file_id=uuid.uuid4(), metadata_=dict(
            statement_import_statement_id='k1',
            statement_import_request=dict(currency='MXN', rows=[
                dict(id='manual:opening-balance', excluded=True, manual_page=2, balance_minor='1234000',
                     reason='Opening balance not printed in these pages: the closing balance read less the payments '
                            'read, which agree with the printed counts and totals; confirmed by the previous saved '
                            'statement, to 2023-07-31.'),
                dict(id='manual:vision-p2-0', excluded=False, reason='Read from page image, page 2.')]),
            statement_import_original=dict(rows=[])))
        glyph = SimpleNamespace(id=uuid.uuid4(), amount_minor=229342, transaction_date=date(2023, 8, 3), provenance=dict(
            confirmed_by=dict(name='System'),
            statement_import_original=dict(page_number=4, fields=dict(date_column='0', credit_column='2'), source_cells=[
                dict(column_index=0, expected_text='O3/AGO', locator=dict(page=4)),
                dict(column_index=2, expected_text='2,293.42?', locator=dict(page=4))], value_repairs=[dict(
                page_number=4, held_text='~293.42', text='2293.42', basis='one_unread_glyph_fixed_by_printed_balances')]),
            statement_import_review=dict(reason='')))
        file = SimpleNamespace(metadata_=dict(financial_account_detail_history=[dict(
            statement_id='k1', actor=dict(name='System'),
            basis='Currency MXN: the file name says MXN and MXN is the only currency the pages print')]))
        found = {(f['rule_id'], f['target_key']): f for f in judgements.detect(document, period, [glyph], file=file)}
        self.assertIn(('L8.unprinted_opening', 'opening_balance'), found)
        self.assertIn('12,340.00', found[('L8.unprinted_opening', 'opening_balance')]['summary'])
        self.assertIn(('image.page_reading', 'payments'), found)
        self.assertEqual(found[('L16.one_glyph', 'amount')]['subject_id'], glyph.id)
        self.assertIn(('L4.currency_from_name', 'currency'), found)
        self.assertIn(('L9.scan_amount_marks', 'amount'), found)
        self.assertIn(('L31.scan_day_letter', 'date'), found)
        self.assertNotIn('L8', ' '.join(f['summary'] for f in found.values()))

    def test_model_details_calls_say_what_claude_changed_and_where_it_read_it(self):
        subject = ('statement_period', 'p1')
        [call] = judgements.model_details_calls(dict(statement_details_history=[_HOLDER, _NUMBER]), subject, 'USD')
        self.assertEqual((call['rule_id'], call['strength'], call['origin']), ('model.statement_account', 'inferred',
                                                                                'agent'))
        self.assertEqual(judgements.priority(call['rule_id']), 2)
        for words in ("holder 'ns BVA' to 'CAAL ENERGY SYSTEMS SA DE CV'", "'119201424' to '0119201424'",
                      'moved the statement', "page 1 of '09 BBVA 23 USD.pdf'", 'No person has confirmed it'):
            self.assertIn(words, call['summary'])
        self.assertEqual(call['evidence']['page'], 1)
        # Read from another statement's page: said so, and the link opens this statement's own first page.
        [other] = judgements.model_details_calls(dict(statement_details_history=[_HOLDER, _NUMBER]), subject, 'USD',
                                                 own_file='08 BBVA 23 USD.pdf')
        self.assertIn("another statement in the case, not this statement's own pages", other['summary'])
        self.assertEqual((other['evidence']['page'], other['evidence']['first_page']), (None, 1))
        self.assertEqual((call['evidence']['before']['account_id'], call['evidence']['chosen']['account_id']),
                         ('acct-a', 'acct-b'))
        # A person's edit after the model's settles the model's changes before it.
        person = _model_edit('2026-10-31T09:00:00', 'acct-b', 'acct-b', {}, {}, model=False)
        self.assertEqual(judgements.model_details_calls(dict(statement_details_history=[_HOLDER, _NUMBER, person]),
                                                        subject), [])
        self.assertEqual(judgements.model_details_calls(dict(statement_details_history=[person]), subject), [])


if __name__ == '__main__':
    unittest.main()
