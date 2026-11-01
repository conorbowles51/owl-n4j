"""The manual-change feed: one inbox line per person's change, written only after the save commits."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from postgres.base import Base
from postgres.models.manual_change import ManualChange
from services import manual_changes as mc
from services.financial import judgement_inbox

CASE = '11111111-2222-3333-4444-555555555555'
PERSON = dict(name='Alex Reviewer', email='alex@example.com', user_id='u1')


class FeedTestBase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.inbox = self.dir / 'MANUAL-CHANGES.jsonl'
        self.judgements = self.dir / 'JUDGEMENT-CORRECTIONS.md'
        for target, name, value in ((mc, 'INBOX', self.inbox), (judgement_inbox, 'INBOX', self.judgements)):
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.engine = create_engine(f"sqlite+pysqlite:///{self.dir / 'm.db'}", future=True)
        # pysqlite opens its transaction lazily, so a SAVEPOINT at the start of one commits on release: the
        # SQLAlchemy recipe makes SQLite begin explicitly, as PostgreSQL does.
        event.listen(self.engine, 'connect', lambda conn, _rec: setattr(conn, 'isolation_level', None))
        event.listen(self.engine, 'begin', lambda conn: conn.exec_driver_sql('BEGIN'))
        Base.metadata.create_all(self.engine, tables=[ManualChange.__table__])
        mc._READY.clear()
        self.addCleanup(mc._READY.clear)

    def lines(self):
        if not self.inbox.exists():
            return []
        return [json.loads(raw) for raw in self.inbox.read_text().splitlines() if raw.strip()]

    def change(self, session, **kw):
        args = dict(kind='transaction_correction', case_id=CASE, subject=('transaction', 't1'),
                    before={'amount': '10.00'}, after={'amount': '100.00'}, actor=PERSON, reason='printed 100.00',
                    link='/cases/x', field='amount', producer='santander@3', layout='fp1')
        args.update(kw)
        return mc.record_change(session, args.pop('kind'), args.pop('case_id'), args.pop('subject'),
                                args.pop('before'), args.pop('after'), args.pop('actor'), args.pop('reason'),
                                args.pop('link'), **args)


class RecordAfterCommitTests(FeedTestBase):
    def test_a_save_that_commits_writes_exactly_one_line(self):
        with Session(self.engine) as session:
            self.change(session)
            self.assertEqual(self.lines(), [], 'nothing is written before the save commits')
            session.commit()
            session.commit()  # a later commit on the same session writes nothing more
        lines = self.lines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['kind'], 'transaction_correction')
        self.assertEqual(lines[0]['pattern_key'], 'transaction_correction|amount|santander@3|fp1')
        self.assertFalse(lines[0]['test'])
        self.assertEqual(lines[0]['actor'], 'person')

    def test_a_save_that_rolls_back_writes_nothing(self):
        with Session(self.engine) as session:
            self.change(session)
            session.rollback()
            session.commit()
        self.assertEqual(self.lines(), [])
        with Session(self.engine) as session:
            self.assertEqual(session.scalars(select(ManualChange)).all(), [])

    def test_committed_mode_records_and_writes_at_once(self):
        with Session(self.engine) as session:
            ident = self.change(session, committed=True)
        self.assertEqual([line['id'] for line in self.lines()], [str(ident)])

    def test_a_failed_append_is_added_once_by_the_sync(self):
        with Session(self.engine) as session:
            with mock.patch.object(mc, 'append', side_effect=OSError('disk full')):
                self.change(session)
                session.commit()  # the save stands
            self.assertEqual(self.lines(), [])
            self.assertEqual(len(mc.missing(session)), 1)
            out = mc.check(session)
            self.assertEqual((out['appended'], out['missing'], out['error']), (1, [], ''))
            self.assertEqual(mc.check(session)['appended'], 0)
        self.assertEqual(len(self.lines()), 1)

    def test_a_record_that_cannot_be_made_never_fails_the_save(self):
        with Session(self.engine) as session:
            with mock.patch.object(mc, '_ready', return_value=False):
                self.assertIsNone(self.change(session))
            session.commit()
        self.assertEqual(self.lines(), [])

    def test_jobs_login_and_verification_case_test_changes_are_marked_test(self):
        with Session(self.engine) as session:
            self.change(session, actor=dict(name='Jobs', email='jobs-verify@loupe.invalid'))
            self.change(session, case_id=mc.VERIFICATION_CASE, reason='test change for the feed')
            self.change(session, case_id=mc.VERIFICATION_CASE, reason='real fix')
            session.commit()
        self.assertEqual([line['test'] for line in self.lines()], [True, True, False])
        self.assertEqual(self.lines()[0]['actor'], 'jobs')

    def test_phone_lines_carry_no_values_names_or_text(self):
        with Session(self.engine) as session:
            self.change(session, source='phone', before={'name': 'Jane'}, after={'name': 'John'},
                        reason='message text')
            session.commit()
        line = self.lines()[0]
        for key in ('before', 'after', 'reason'):
            self.assertNotIn(key, line)
        self.assertNotIn('Alex', json.dumps(line))

    def test_a_confirmation_is_recorded_with_its_type(self):
        with Session(self.engine) as session:
            mc.record_confirmation(session, 'payment_label_confirm', CASE, ('transaction', 't1'), {'name': 'X'},
                                   PERSON, committed=True)
        self.assertEqual(self.lines()[0]['type'], 'confirm')


class JudgementLineTests(FeedTestBase):
    item = dict(id='00000001-0000-0000-0000-000000000000', status='corrected', case_id='c' * 36,
                rule_id='L1.glyph_cell', target_key='amount', source_document_id='d' * 36,
                evidence={'before': '1,000.00', 'correction': {'after': '7,000.00'}},
                resolution_reason='wrong | digit', resolved_at='2026-10-30T10:00:00+00:00', resolved_by='Alex')

    def test_the_judgement_line_is_byte_identical_through_the_new_call(self):
        old = self.dir / 'old.md'
        with mock.patch.object(judgement_inbox, 'INBOX', old):
            judgement_inbox.append_correction(None, dict(self.item), statement='statement.pdf')
        with Session(self.engine) as session:
            mc.record_judgement_correction(session, dict(self.item), 'statement.pdf', committed=False)
            self.assertFalse(self.judgements.exists(), 'the judgement line waits for the commit')
            session.commit()
        self.assertEqual(self.judgements.read_bytes(), old.read_bytes())
        line = self.lines()[0]
        self.assertEqual((line['kind'], line['delivered_by']), ('judgement_correct', 'judgement-lessons'))

    def test_the_judgement_line_is_written_even_when_the_record_cannot_be_made(self):
        with Session(self.engine) as session:
            with mock.patch.object(mc, '_ready', return_value=False):
                mc.record_judgement_correction(session, dict(self.item), 'statement.pdf', committed=True)
        self.assertIn(f"judgement {self.item['id']}", self.judgements.read_text())

    def test_a_rolled_back_judgement_correction_writes_neither_line(self):
        with Session(self.engine) as session:
            mc.record_judgement_correction(session, dict(self.item), 'statement.pdf', committed=False)
            session.rollback()
        self.assertFalse(self.judgements.exists())
        self.assertEqual(self.lines(), [])


if __name__ == '__main__':
    unittest.main()
