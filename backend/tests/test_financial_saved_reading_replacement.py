"""A saved statement period the current reader proves wrong is replaced, linked and reversible.

Synthetic statements only. The "earlier reader" is the same file saved while
one stored payment row was missing from its table geometry (as an older reader
missed it); putting the row back is the current reader reading it again.
"""
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import func, select

from postgres.models.evidence import EvidenceFile, EvidenceTableGeometry, IngestionLog
from postgres.models.financial import AdjudicationEvent, FinancialSourceDocument, FinancialTransaction
from services.financial import saved_reading_replacement as replacement
from services.financial.duplicate_decisions import DuplicateDecisionError, decide_duplicate, duplicate_revision
from services.financial.pdf_candidates import PdfMappingError
from services.financial.statement_import import (StatementImportRequest, confirm_statement_import,
                                                 forget_shared_readings, read_statement_import)
from tests import test_financial_statement_import as statement_import_fixture


def _logs(fixture):
    from postgres.base import Base
    Base.metadata.create_all(fixture.db.connection(), tables=[IngestionLog.__table__])
    fixture.db.commit()


class SavedReadingReplacementTests(TestCase):
    def setUp(self):
        self.f = statement_import_fixture.StatementImportTests('test_file_reading_is_shared_across_requests_and_follows_stored_edits')
        self.f.setUp()
        _logs(self.f)
        self.case_id = self.f.case.id
        geometry = self.f.db.get(EvidenceTableGeometry, (self.f.file.id, 1))
        self.full = deepcopy(geometry.payload)

    def tearDown(self):
        self.f.tearDown()

    # Building state ---------------------------------------------------------

    def set_payload(self, payload):
        geometry = self.f.db.get(EvidenceTableGeometry, (self.f.file.id, 1))
        geometry.payload = deepcopy(payload)
        self.f.db.commit()
        forget_shared_readings()

    def without_payment_row(self):
        """The table as an earlier reader saw it: one payment line missing."""
        payload = deepcopy(self.full)
        values = payload[0]['table']['values']
        rows = sorted({v['row'] for v in values})
        payment_row = rows[3]
        payload[0]['table']['values'] = [v for v in values if v['row'] != payment_row]
        return payload

    def save_earlier_reading(self, edit=None):
        """Saved on the earlier reading (it did not reconcile then; saved before today's admission)."""
        self.set_payload(self.without_payment_row())
        request = self.f.request()
        if edit:
            edit(request)
        receipt = self.f.confirm_legacy(request)
        self.set_payload(self.full)  # the current reader reads the whole table again
        return UUID(receipt['source_document_id'])

    def admitted_rows(self):
        with self.f.SessionLocal() as db:
            return db.scalar(select(func.count()).select_from(FinancialTransaction).where(
                FinancialTransaction.ledger_status == 'admitted'))

    def document(self, document_id):
        with self.f.SessionLocal() as db:
            return db.get(FinancialSourceDocument, document_id)

    def assess(self, document_id):
        with self.f.SessionLocal() as db:
            return replacement.assess_document(db, db.get(FinancialSourceDocument, document_id))

    def replace(self, document_id):
        return replacement.replace_document(session_factory=self.f.SessionLocal, case_id=self.case_id,
                                            document_id=document_id, resolve_path=Path)

    def restore(self, document_id):
        return replacement.restore_replacement(session_factory=self.f.SessionLocal, case_id=self.case_id,
                                               document_id=document_id)

    def review(self):
        with self.f.SessionLocal() as db:
            return read_statement_import(db, case_id=self.case_id, evidence_file_id=self.f.file.id)

    # Replace and restore ------------------------------------------------------

    def test_proved_reading_replaces_the_saved_period_linked_counted_once_and_restores_exactly(self):
        old_id = self.save_earlier_reading()
        saved_rows = self.admitted_rows()
        verdict = self.assess(old_id)
        self.assertEqual(verdict['outcome'], 'replace', verdict)
        self.assertEqual((verdict['missing_payments'], verdict['extra_payments']), (1, 0))
        self.assertEqual(verdict['saved_payments'] + 1, verdict['fresh_payments'])
        self.assertEqual(self.admitted_rows(), saved_rows, 'assessing writes nothing')

        result = self.replace(old_id)
        self.assertTrue(result['applied'], result)
        new_id = UUID(result['receipt']['source_document_id'])
        self.assertEqual(self.admitted_rows(), saved_rows + 1, 'the period counts once, from the new reading')
        with self.f.SessionLocal() as db:
            old, new = db.get(FinancialSourceDocument, old_id), db.get(FinancialSourceDocument, new_id)
            self.assertEqual((old.status, old.superseded_by_id, new.status), ('superseded', new_id, 'admitted'))
            self.assertEqual(new.metadata_['reader_replacement']['replaced_source_document_id'], str(old_id))
            self.assertEqual(new.metadata_['statement_import_request']['replaces_source_document_id'], str(old_id))
            old_rows = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == old_id)))
            self.assertEqual(len(old_rows), saved_rows)
            self.assertEqual({row.ledger_status for row in old_rows}, {'superseded'}, 'old rows kept, not counted')
            event = db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.subject_id == old_id)
                              .order_by(AdjudicationEvent.subject_sequence.desc()).limit(1))
            self.assertEqual((event.decision, event.actor_name, event.after['basis']),
                             ('supersede_duplicate', 'system: reader replacement', replacement.BASIS))
            self.assertEqual(set(event.after['rows']), {str(row.id) for row in old_rows})
            self.assertIsNotNone(db.scalar(select(IngestionLog).where(
                IngestionLog.extra['action'].as_string() == 'financial_reader_replacement')))
        review = self.review()['current_import']
        self.assertEqual(review['source_document_id'], str(new_id))
        self.assertFalse(review['excluded_as_duplicate'])
        self.assertEqual(review['duplicate_copies'], [], 'a replaced reading is not listed as a copy')
        self.assertEqual(review['reader_replacement']['status'], 'replaced')
        self.assertEqual(review['reader_replacement']['replaced_source_document_id'], str(old_id))

        # Repeat: nothing more to do; the replaced copy no longer counts.
        self.assertEqual(self.assess(new_id)['outcome'], 'same')
        self.assertEqual(self.assess(old_id)['code'], 'not_admitted')

        # Restoring one reading alone would count the period twice: the generic restore refuses it.
        with self.f.SessionLocal() as db:
            old = db.get(FinancialSourceDocument, old_id)
            with self.assertRaises(DuplicateDecisionError):
                decide_duplicate(db, case_id=self.case_id, document_id=old_id, action='restore',
                                 expected_revision=duplicate_revision(db, old), actor=self.f.actor, reason='test')
        self.assertEqual(self.admitted_rows(), saved_rows + 1)

        restored = self.restore(new_id)
        self.assertEqual(restored['counting_source_document_id'], str(old_id))
        self.assertEqual(self.admitted_rows(), saved_rows, 'restore is the exact reversal')
        self.assertEqual((self.document(old_id).status, self.document(new_id).status), ('admitted', 'superseded'))
        self.assertEqual(self.document(new_id).superseded_by_id, old_id)
        review = self.review()['current_import']
        self.assertEqual(review['source_document_id'], str(old_id))
        self.assertFalse(review['excluded_as_duplicate'], 'a restored replacement is not a duplicate exclusion')
        self.assertEqual(review['reader_replacement']['status'], 'restored')
        # Never replaced again automatically once restored.
        self.assertEqual(self.assess(old_id)['code'], 'restored_by_request')
        # A repeated (or stale) restore of the same page changes nothing.
        again = self.restore(new_id)
        self.assertFalse(again['applied'])
        self.assertEqual(self.admitted_rows(), saved_rows)
        self.assertEqual((self.document(old_id).status, self.document(new_id).status), ('admitted', 'superseded'))

        # And back again on request (the notice's second button): still one count at a time.
        self.restore(old_id)
        self.assertEqual(self.admitted_rows(), saved_rows + 1)
        self.assertEqual((self.document(old_id).status, self.document(new_id).status), ('superseded', 'admitted'))

    def test_investigator_details_are_kept_and_the_notice_says_so(self):
        old_id = self.save_earlier_reading()
        with self.f.SessionLocal() as db:
            old = db.get(FinancialSourceDocument, old_id)
            old.metadata_ = {**old.metadata_, 'statement_details_history': [dict(before={}, after={'holder': 'x'})]}
            db.commit()
        verdict = self.assess(old_id)
        self.assertEqual(verdict['outcome'], 'replace', verdict)
        self.assertTrue(verdict['investigator_work'])
        self.replace(old_id)
        notice = self.review()['current_import']['reader_replacement']
        self.assertEqual(notice['message'], replacement.NOTICE)
        self.assertTrue(notice['investigator_work'])
        self.assertIn('statement_details_history', self.document(old_id).metadata_, 'her version stays on the old copy')

    # Refusals ---------------------------------------------------------------

    def test_a_reading_that_does_not_prove_is_left_and_nothing_is_written(self):
        old_id = self.save_earlier_reading()
        payload = deepcopy(self.full)
        for value in payload[0]['table']['values']:
            if value['text'] == '€47,450':
                value['text'] = '€47,451'  # the current reading no longer reconciles
        self.set_payload(payload)
        rows = self.admitted_rows()
        verdict = self.assess(old_id)
        self.assertEqual((verdict['outcome'], verdict['code']), ('refused', 'not_proved'), verdict)
        self.assertEqual(self.replace(old_id)['code'], 'not_proved')
        self.assertEqual((self.admitted_rows(), self.document(old_id).status), (rows, 'admitted'))

    def test_payments_a_person_typed_are_never_replaced(self):
        def typed(request):
            row = next(r for r in request['rows'] if not r['excluded'] and r['amount_minor'] not in ('', '0'))
            row['amount_minor'] = str(int(row['amount_minor']) + 1)
        old_id = self.save_earlier_reading(typed)
        self.assertEqual(self.assess(old_id)['code'], 'typed_payments')

    def test_a_description_or_counterparty_a_person_changed_is_never_replaced(self):
        def described(request):
            row = next(r for r in request['rows'] if not r['excluded'] and r['amount_minor'] not in ('', '0'))
            row['description'] = (row.get('description') or '') + ' (checked)'
        self.assertEqual(self.assess(self.save_earlier_reading(described))['code'], 'typed_payments')

    def test_a_line_a_person_moved_into_or_out_of_the_payments_is_never_replaced(self):
        def moved(request):
            row = next(r for r in request['rows'] if not r['excluded'] and r['amount_minor'] not in ('', '0'))
            row['excluded'] = True
        self.assertEqual(self.assess(self.save_earlier_reading(moved))['code'], 'typed_payments')

    def test_a_signed_in_account_named_like_the_system_is_not_the_reader_replacement(self):
        from services.financial.decisions import Actor
        self.assertTrue(replacement.is_replacement(replacement.ACTOR))
        self.assertFalse(replacement.is_replacement(Actor(name=replacement.ACTOR.name, email=replacement.ACTOR.email,
                                                          user_id=UUID(int=7))))

    def test_restore_refuses_to_set_aside_payments_corrected_since(self):
        old_id = self.save_earlier_reading()
        new_id = UUID(self.replace(old_id)['receipt']['source_document_id'])
        with self.f.SessionLocal() as db:
            row = db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == new_id)).first()
            row.ledger_status, row.quarantine_reason = 'quarantined', 'adjudicated'  # a person's decision on a payment in use
            db.commit()
        with self.assertRaises(replacement.ReplacementError):
            self.restore(new_id)
        self.assertEqual((self.document(old_id).status, self.document(new_id).status), ('superseded', 'admitted'))

    def test_a_saved_period_equal_to_the_current_reading_is_left(self):
        receipt = self.f.confirm()
        self.assertEqual(self.assess(UUID(receipt['source_document_id']))['outcome'], 'same')

    def test_switch_off_replaces_nothing_and_the_writer_refuses(self):
        old_id = self.save_earlier_reading()
        with self.f.SessionLocal() as db:
            request = replacement.assess_document(db, db.get(FinancialSourceDocument, old_id))['request']
        with patch.object(replacement, 'ENABLED', False):
            self.assertEqual(self.replace(old_id)['code'], 'disabled')
            with self.assertRaises(PdfMappingError):
                confirm_statement_import(session_factory=self.f.SessionLocal, case_id=self.case_id,
                    evidence_file_id=self.f.file.id, request=StatementImportRequest.model_validate(request),
                    actor=replacement.ACTOR, resolve_path=Path)
        self.assertEqual(self.document(old_id).status, 'admitted')

    def test_the_writer_proves_again_on_its_own_reading_and_refuses_a_changed_request(self):
        old_id = self.save_earlier_reading()
        with self.f.SessionLocal() as db:
            request = deepcopy(replacement.assess_document(db, db.get(FinancialSourceDocument, old_id))['request'])
        row = next(r for r in request['rows'] if not r['excluded'] and r['amount_minor'] not in ('', '0'))
        row['description'] = row['description'] + ' (changed)'
        rows = self.admitted_rows()
        with self.assertRaises(PdfMappingError):
            confirm_statement_import(session_factory=self.f.SessionLocal, case_id=self.case_id,
                evidence_file_id=self.f.file.id, request=StatementImportRequest.model_validate(request),
                actor=replacement.ACTOR, resolve_path=Path)
        self.assertEqual((self.admitted_rows(), self.document(old_id).status), (rows, 'admitted'))

    def test_the_reader_replacement_actor_never_imports_a_new_statement(self):
        request = self.f.request()
        with self.assertRaises(PdfMappingError):
            confirm_statement_import(session_factory=self.f.SessionLocal, case_id=self.case_id,
                evidence_file_id=self.f.file.id, request=StatementImportRequest.model_validate(request),
                actor=replacement.ACTOR, resolve_path=Path)
        self.assertEqual(self.admitted_rows(), 0)


class PartialFileTests(TestCase):
    """Per period, never per file: only the saved period whose reading changed is replaced."""

    def setUp(self):
        self.f = statement_import_fixture.StatementImportTests('test_two_printed_periods_in_one_pdf_import_separately_without_duplicates')
        self.f.setUp()
        _logs(self.f)
        self.case_id = self.f.case.id

    def tearDown(self):
        self.f.tearDown()

    def test_only_the_period_read_differently_is_replaced(self):
        choices = self.f.install_two_card_periods()
        first = UUID(self.f.confirm_legacy(self.f.card_period_request(choices[0])[1])['source_document_id'])
        # The second period saved by an earlier reader that missed one payment line of page 2.
        geometry = self.f.db.get(EvidenceTableGeometry, (self.f.file.id, 2))
        full = deepcopy(geometry.payload)
        proposal, request = self.f.card_period_request(choices[1])
        payment = next(r for r in proposal['rows'] if not r['excluded'] and r['kind'] == 'transaction')
        texts = sorted(c['expected_text'] for c in payment['source_cells'] if c.get('expected_text'))
        by_row = {}
        for value in full[0]['table']['values']:
            by_row.setdefault(value['row'], []).append(value['text'])
        missing_row = next(row for row, values in by_row.items() if sorted(t for t in values if t) == texts)
        partial = deepcopy(full)
        partial[0]['table']['values'] = [v for v in partial[0]['table']['values'] if v['row'] != missing_row]
        geometry.payload = partial
        self.f.db.commit()
        forget_shared_readings()
        second_choice = next(c for c in self.f.preview()['statement_choices'] if c['period_end'] == choices[1]['period_end'])
        second = UUID(self.f.confirm_legacy(self.f.card_period_request(second_choice)[1])['source_document_id'])
        geometry = self.f.db.get(EvidenceTableGeometry, (self.f.file.id, 2))
        geometry.payload = full
        self.f.db.commit()
        forget_shared_readings()

        with self.f.SessionLocal() as db:
            plan = {UUID(entry['document_id']): entry for entry in replacement.plan(db, case_ids=[self.case_id])}
        self.assertEqual(plan[first]['outcome'], 'same', plan[first])
        # The card fixture's periods carry no printed closing, so they would not reconcile today; the proof
        # and admission are covered above. Here only the targeting is under test.
        with patch.object(replacement, 'prove', return_value=None):
            with self.f.SessionLocal() as db:
                verdict = replacement.assess_document(db, db.get(FinancialSourceDocument, second))
            self.assertEqual(verdict['outcome'], 'replace', verdict)
            self.assertEqual(verdict['missing_payments'], 1)
            with self.f.SessionLocal() as db:
                first_rows = sorted(str(r.id) for r in db.scalars(select(FinancialTransaction).where(
                    FinancialTransaction.source_document_id == first)))
            from services.financial.statement_admission import assess_admission
            with patch('services.financial.statement_admission.require_admission', side_effect=assess_admission):
                result = replacement.replace_document(session_factory=self.f.SessionLocal, case_id=self.case_id,
                                                      document_id=second, resolve_path=Path)
        self.assertTrue(result.get('applied'), result)
        with self.f.SessionLocal() as db:
            self.assertEqual(db.get(FinancialSourceDocument, first).status, 'admitted', 'the other period is untouched')
            self.assertEqual(sorted(str(r.id) for r in db.scalars(select(FinancialTransaction).where(
                FinancialTransaction.source_document_id == first, FinancialTransaction.ledger_status == 'admitted'))),
                first_rows)
            self.assertEqual(db.get(FinancialSourceDocument, second).status, 'superseded')
            self.assertIsNone(db.scalar(select(AdjudicationEvent.id).where(AdjudicationEvent.subject_id == first)))
