"""fin-alexjudge: a judgement call marked Looks right on the statement screen before import is kept with the review
and recorded at import as the same confirmation the saved-statement marker writes, under the person who clicked it
and at that time, once; the browser can never name who checked."""
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select

from postgres.base import Base
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_judgements import FinancialJudgement
from postgres.models.manual_change import ManualChange
from services.financial import judgements
from services.financial.decisions import Actor
from services.financial.statement_import import JudgementCheck, StatementImportRequest, StatementReviewDraft
from tests import test_financial_statement_import as base_import  # module, so its tests are not collected here

DATE_REASON = 'Date read from page image, page 1: the text layer could not read it.'


def _request(**extra):
    return StatementReviewDraft.model_validate(dict(
        expected_revision='a' * 64, currency='EUR', account_number='1', holder='H',
        rows=[dict(id='r1', excluded=False, amount_minor='100', direction='credit', date='2023-01-02',
                   description='x')], **extra))


class StampTests(unittest.TestCase):
    def setUp(self):
        self.alex = Actor('Alex', 'alex@example.test', uuid4())
        self.sam = Actor('Sam', 'sam@example.test', uuid4())

    def test_a_review_without_checks_serialises_as_before(self):
        self.assertNotIn('judgement_checks', _request().model_dump(mode='json'))

    def test_a_new_check_is_the_sending_person_and_a_browser_name_is_never_believed(self):
        at = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        request = _request(judgement_checks=[dict(rule_id='image.date', row_id='r1', target_key='date', checked_at=at,
                                                  checked_by=dict(name='Neil Byrne', email='n@example.test'))])
        stamped = judgements.stamp_checks(request, None, self.alex)
        check = stamped.judgement_checks[0]
        self.assertEqual((check.checked_by['name'], check.checked_by['email']), ('Alex', 'alex@example.test'))
        self.assertEqual(datetime.fromisoformat(check.checked_at), datetime.fromisoformat(at))

    def test_a_saved_check_keeps_who_made_it_and_a_future_time_is_now(self):
        future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
        first = judgements.stamp_checks(_request(judgement_checks=[
            dict(rule_id='image.date', row_id='r1', target_key='date', checked_at=future)]), None, self.alex)
        self.assertLessEqual(datetime.fromisoformat(first.judgement_checks[0].checked_at), datetime.now(timezone.utc))
        again = _request(judgement_checks=[dict(rule_id='image.date', row_id='r1', target_key='date',
                                                checked_by=dict(name='Sam'))] * 2)
        kept = judgements.stamp_checks(again, first.model_dump(mode='json'), self.sam)
        self.assertEqual(len(kept.judgement_checks), 1)
        self.assertEqual(kept.judgement_checks[0].checked_by['name'], 'Alex')
        self.assertEqual(kept.judgement_checks[0].checked_at, first.judgement_checks[0].checked_at)

    def test_a_model_or_the_automatic_step_checks_nothing(self):
        model = Actor('Claude (for Neil Byrne)', 'n@example.test', uuid4(),
                      origin=dict(kind='model', model='Claude', **{'for': dict(name='Neil Byrne')}))
        request = _request(judgement_checks=[dict(rule_id='image.date', row_id='r1', target_key='date')])
        self.assertEqual(judgements.stamp_checks(request, None, model).judgement_checks, [])
        self.assertEqual(judgements.stamp_checks(request, None, Actor('System', 'system@loupe.invalid')).judgement_checks, [])
        self.assertEqual(judgements.stamp_checks(request, None, None).judgement_checks, [])


class ImportTests(base_import.StatementImportTests):
    """Through the real writer, on the statement import fixture (its own tests are not run again here)."""

    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.db.connection(), tables=[FinancialJudgement.__table__, ManualChange.__table__])
        self.db.commit()

    def _request(self, checks=()):
        request = super().request()
        payment = next(r for r in request['rows'] if not r['excluded'])
        payment['reason'] = DATE_REASON
        if checks:
            request['judgement_checks'] = [dict(rule_id='image.date', row_id=payment['id'], target_key='date',
                                                checked_at=at, **({'checked_by': by} if by else {}))
                                           for at, by in checks]
        return request, payment['id']

    def _calls(self):
        with self.SessionLocal() as db:
            rows = db.scalars(select(FinancialJudgement)).all()
            by_txn = {t.id: ((t.provenance or {}).get('statement_import_original') or {}).get('id')
                      for t in db.scalars(select(FinancialTransaction))}
            return [(r, by_txn.get(r.subject_id)) for r in rows], db.scalars(select(ManualChange)).all()

    def test_the_preview_names_the_row_the_screen_checks(self):
        request, row_id = self._request()
        p = self.preview()
        found = judgements.preview(p['rows'], request['rows'], currency='EUR')
        self.assertIn(('image.date', row_id, 'date'), [(f['rule_id'], f['row_id'], f['target_key']) for f in found])

    def test_looks_right_before_import_is_recorded_once_under_the_clicker(self):
        at = (datetime.now(timezone.utc) - timedelta(minutes=7)).replace(microsecond=0)
        request, row_id = self._request(checks=[(at.isoformat(), dict(name='Neil Byrne'))])
        receipt = self.confirm(request)
        self.assertTrue(receipt.get('created') or receipt.get('applied'), receipt)
        calls, changes = self._calls()
        dated = [r for r, reading_row in calls if r.rule_id == 'image.date' and reading_row == row_id]
        self.assertEqual(len(dated), 1)
        call = dated[0]
        self.assertEqual((call.status, call.resolved_by, call.resolved_by_email),
                         ('confirmed', self.actor.name, self.actor.email))
        self.assertEqual(call.resolved_at.replace(tzinfo=timezone.utc) if call.resolved_at.tzinfo is None
                         else call.resolved_at, at)
        self.assertEqual(call.resolution_reason, judgements.PRIOR_CHECK_REASON)
        # Every other call stays open for the saved-statement marker.
        self.assertTrue(all(r.status == 'open' for r, _ in calls if r.id != call.id))
        fed = [c for c in changes if c.kind == 'judgement_confirm']
        self.assertEqual([(c.subject_id, c.change_type, c.actor_name) for c in fed],
                         [(str(call.id), 'confirm', self.actor.name)])
        # Asked once: the saved call is settled, so the marker offers no Looks right; a second confirm is refused
        # only for a correction, a repeat confirm changes nothing.
        with self.SessionLocal() as db:
            self.assertEqual(db.get(FinancialJudgement, call.id).status, 'confirmed')

    def test_without_a_check_the_call_stays_open_as_before(self):
        request, row_id = self._request()
        self.confirm(request)
        calls, changes = self._calls()
        dated = [r for r, reading_row in calls if r.rule_id == 'image.date' and reading_row == row_id]
        self.assertEqual([r.status for r in dated], ['open'])
        self.assertEqual([c for c in changes if c.kind == 'judgement_confirm'], [])

    def test_a_check_saved_with_the_review_keeps_its_person_when_another_imports(self):
        from services.financial.statement_progress import save_progress
        at = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0)
        request, row_id = self._request(checks=[(at.isoformat(), None)])
        checker = Actor('Sam Reviewer', 'sam@example.test', uuid4())
        with self.SessionLocal() as db:
            saved = save_progress(db, case_id=self.case.id, evidence_file_id=self.file.id,
                                  request=StatementReviewDraft.model_validate(request),
                                  expected_review_revision='initial', actor=checker)
        stored = saved['request']['judgement_checks'][0]
        self.assertEqual((stored['checked_by']['name'], stored['checked_at']), ('Sam Reviewer', at.isoformat()))
        # The browser sends the saved review back naming someone else; the importer is a third person.
        request['judgement_checks'][0]['checked_by'] = dict(name='Neil Byrne')
        self.confirm(request)
        calls, changes = self._calls()
        call = next(r for r, reading_row in calls if r.rule_id == 'image.date' and reading_row == row_id)
        self.assertEqual((call.status, call.resolved_by, call.resolved_by_email),
                         ('confirmed', 'Sam Reviewer', 'sam@example.test'))
        self.assertEqual([c.actor_name for c in changes if c.kind == 'judgement_confirm'], ['Sam Reviewer'])

    def test_the_request_contract_takes_checks(self):
        request, _ = self._request(checks=[('', None)])
        parsed = StatementImportRequest.model_validate(request)
        self.assertIsInstance(parsed.judgement_checks[0], JudgementCheck)


for _name in [n for n in dir(base_import.StatementImportTests) if n.startswith('test')]:
    if _name not in ImportTests.__dict__:
        setattr(ImportTests, _name, None)  # not callable: the loader does not collect the base tests again


if __name__ == '__main__':
    unittest.main()
