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
from postgres.models.financial import AdjudicationEvent
from postgres.models.financial_judgements import FinancialJudgement
from postgres.models.user import User
from services.financial import judgements
from services.financial.decisions import Actor


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp(prefix='loupe-judgements-')
        self.engine = create_engine(f"sqlite+pysqlite:///{Path(self._dir) / 'j.db'}", future=True)
        Base.metadata.create_all(self.engine, tables=[User.__table__, Case.__table__, FinancialJudgement.__table__,
                                                      AdjudicationEvent.__table__])
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


class DetectionTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
