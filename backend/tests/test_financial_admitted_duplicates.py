"""Statements already saved twice are set aside as linked duplicates.

Synthetic statements only. The legacy state (both productions of one card
statement saved to the ledger) is built the way it arose live: before
r1-reproduced a masked card reference never matched another production, so
both copies were imported. The patches below reproduce that older matching
only while the copies are saved.
"""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import select

from postgres.models.evidence import EvidenceFile, IngestionLog
from postgres.models.financial import AdjudicationEvent, FinancialSourceDocument, FinancialTransaction
from postgres.models.financial_import_batches import FinancialImportBatchItem as Item
from services.financial import admitted_statement_duplicates as admitted
from services.financial.duplicate_decisions import DuplicateDecisionError
from services.financial.statement_import import read_statement_import
from tests import test_financial_statement_overlap as overlap_fixture


def legacy_matching():
    """Pre-r1 matching: a masked reference is never the same printed period."""
    stack = ExitStack()
    for target in ('services.financial.statement_import_overlap.same_printed_period',
                   'services.financial.pending_statement_duplicates.same_printed_period'):
        stack.enter_context(patch(target, return_value=False))
    return stack


class AdmittedDuplicateTests(TestCase):
    def setUp(self):
        self.fixture = overlap_fixture.StatementOverlapTests('test_reason_bound_to_coverage_stays_valid_when_peer_imports')
        self.fixture.setUp()
        self.f = self.fixture.f
        self.b = self.fixture.b
        self.primary = self.f.file
        self.case_id = self.f.case.id

    def tearDown(self):
        self.fixture.tearDown()

    # Building the legacy state ------------------------------------------

    def mask_reference(self):
        import hashlib
        from postgres.models.evidence import EvidenceDocumentText
        text = self.f.db.get(EvidenceDocumentText, self.primary.id)
        text.content = text.content.replace('TEST123', '***123')
        text.content_sha256 = hashlib.sha256(text.content.encode()).hexdigest()
        self.f.db.commit()

    def masked_request(self):
        return {**self.f.request(), 'account_number': '***123'}

    def name_files(self, first_name, second_name, other, *, received_together=True):
        with self.f.SessionLocal() as db:
            first, second = db.get(EvidenceFile, self.primary.id), db.get(EvidenceFile, other.id)
            first.original_filename, second.original_filename = first_name, second_name
            if received_together:
                second.created_at = first.created_at = datetime(2026, 9, 16, 21, 9, tzinfo=timezone.utc)
            db.commit()

    def save_twice(self, *, revised=False, second_request=None, batch=True):
        """Both productions saved to the ledger; returns the second file and batch."""
        self.mask_reference()
        other = self.fixture.copy_file(revised=revised)
        batch_id = None
        with legacy_matching():
            self.f.file = self.primary
            self.f.confirm(self.masked_request())
            self.f.file = other
            request = self.masked_request()
            self.assertTrue(self.f.confirm(second_request(request) if second_request else request).get('created'))
            if batch:
                # A batch prepared over both saved files lists both periods as imported.
                batch_id = self.fixture.create(self.primary, other)
                self.assertEqual(self.b.status(batch_id)['counts']['imported'], 2)
        self.assertEqual(self.admitted_rows(), 24)
        return other, batch_id

    # Reading state ---------------------------------------------------------

    def admitted_rows(self):
        with self.f.SessionLocal() as db:
            return len(list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.ledger_status == 'admitted'))))

    def source_of(self, file):
        with self.f.SessionLocal() as db:
            return db.scalar(select(FinancialSourceDocument).where(FinancialSourceDocument.evidence_file_id == file.id))

    def plan(self):
        with self.f.SessionLocal() as db:
            return admitted.find_admitted_duplicates(db, self.case_id)

    def apply(self):
        with self.f.SessionLocal() as db:
            return admitted.set_aside_admitted_duplicates(db, self.case_id)

    def review(self, file):
        with self.f.SessionLocal() as db:
            return read_statement_import(db, case_id=self.case_id, evidence_file_id=file.id)

    def item(self, batch_id, file):
        with self.f.SessionLocal() as db:
            return db.scalar(select(Item).where(Item.batch_id == batch_id, Item.file_id == file.id))

    # Separately produced copy ----------------------------------------------

    def test_later_production_is_set_aside_linked_and_counts_once(self):
        other, batch_id = self.save_twice()
        # Received in one upload: file-name (Bates) order decides, not save order.
        self.name_files('000500-000699 Statements.pdf', '000100-000299 Statements.pdf', other)
        kept, copy = self.source_of(other), self.source_of(self.primary)
        with self.f.SessionLocal() as db:
            db.get(FinancialSourceDocument, copy.id).created_at = datetime(2026, 9, 24, 2, 49, tzinfo=timezone.utc)
            db.get(FinancialSourceDocument, kept.id).created_at = datetime(2026, 9, 24, 2, 51, tzinfo=timezone.utc)
            db.commit()
        plan = self.plan()
        self.assertEqual(len(plan['set_aside']), 1, plan)
        entry = plan['set_aside'][0]
        self.assertEqual(entry['document_id'], str(copy.id))
        self.assertEqual(entry['retained_document_id'], str(kept.id))
        self.assertFalse(entry['retained_saved_first'])
        self.assertEqual(entry['transactions'], 12)
        self.assertEqual((plan['held'], plan['kept'], plan['restored']), ([], [], []))
        self.assertEqual(self.admitted_rows(), 24, 'a plan writes nothing')

        result = self.apply()
        self.assertEqual(len(result['applied']), 1, result)
        self.assertEqual(self.admitted_rows(), 12)
        with self.f.SessionLocal() as db:
            source = db.get(FinancialSourceDocument, copy.id)
            self.assertEqual((source.status, source.superseded_by_id), ('superseded', kept.id))
            self.assertIsNotNone(db.get(EvidenceFile, self.primary.id))
            rows = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == copy.id)))
            self.assertEqual({row.ledger_status for row in rows}, {'superseded'})
            event = db.scalar(select(AdjudicationEvent).where(AdjudicationEvent.subject_id == copy.id))
            self.assertEqual((event.decision, event.actor_name), ('supersede_duplicate', 'system: duplicate set-aside'))
            self.assertEqual(event.after['basis'], admitted.SET_ASIDE_BASIS)
            log = db.scalar(select(IngestionLog).where(IngestionLog.evidence_file_id == self.primary.id,
                IngestionLog.extra['action'].as_string() == 'financial_duplicate_set_aside'))
            self.assertIsNotNone(log)

        # The set-aside copy says what it is a copy of; the retained copy lists it.
        review = self.review(self.primary)
        self.assertTrue(review['current_import']['excluded_as_duplicate'])
        disposition = review['duplicate_disposition']
        self.assertEqual((disposition['status'], disposition['label']), ('ignored', 'Duplicate - Ignored by system'))
        self.assertEqual(disposition['retained']['filename'], '000100-000299 Statements.pdf')
        self.assertIn('000100-000299 Statements.pdf, page 1', disposition['reason'])
        retained_review = self.review(other)
        self.assertEqual([c['source_document_id'] for c in retained_review['current_import']['duplicate_copies']], [str(copy.id)])

        item = self.item(batch_id, self.primary)
        self.assertEqual(item.status, 'duplicate_ignored')
        self.assertEqual(item.summary['readiness']['state'], 'duplicate_ignored')
        self.assertEqual(item.summary['duplicate_disposition']['label'], 'Duplicate - Ignored by system')
        self.assertEqual(item.summary['transaction_count'], 0)
        state = self.b.status(batch_id)
        self.assertEqual((state['counts']['imported'], state['counts']['duplicate_ignored']), (1, 1),
                         [(i['status'], i.get('problems')) for i in state['items']])

        from services.financial.import_batches import refresh_case_readiness
        with self.f.SessionLocal() as db:
            refresh_case_readiness(db, case_id=self.case_id)
        self.assertEqual(self.item(batch_id, self.primary).status, 'duplicate_ignored')
        # Idempotent: a second run changes nothing and reports the copy as set aside.
        again = self.apply()
        self.assertEqual((again['applied'], again['refused']), ([], []))
        self.assertEqual(len(again['plan']['already_set_aside']), 1)
        self.assertEqual(self.admitted_rows(), 12)

    def test_restore_counts_both_again_and_is_not_undone_by_the_next_run(self):
        other, batch_id = self.save_twice()
        self.name_files('000100-000299 Statements.pdf', '000500-000699 Statements.pdf', other)
        self.apply()
        copy = self.source_of(other)
        self.assertEqual(copy.status, 'superseded', 'saved second, received second')
        with self.f.SessionLocal() as db:
            admitted.restore_copy(db, case_id=self.case_id, document_id=copy.id)
        self.assertEqual(self.admitted_rows(), 24)
        item = self.item(batch_id, other)
        self.assertEqual((item.status, item.summary['transaction_count']), ('imported', 12))
        self.assertNotIn('duplicate_disposition', item.summary)
        self.assertFalse(self.review(other)['current_import'].get('excluded_as_duplicate'))
        plan = self.plan()
        self.assertEqual((plan['set_aside'], len(plan['restored'])), ([], 1))
        self.assertEqual(self.apply()['applied'], [])
        self.assertEqual(self.admitted_rows(), 24)
        with self.f.SessionLocal() as db:
            decisions = [e.decision for e in db.scalars(select(AdjudicationEvent).where(
                AdjudicationEvent.subject_id == copy.id).order_by(AdjudicationEvent.subject_sequence))]
        self.assertEqual(decisions, ['supersede_duplicate', 'restore_document'])

    def test_investigator_can_keep_the_other_copy_instead(self):
        other, batch_id = self.save_twice()
        self.name_files('000100-000299 Statements.pdf', '000500-000699 Statements.pdf', other)
        self.apply()
        first, second = self.source_of(self.primary), self.source_of(other)
        self.assertEqual(second.superseded_by_id, first.id)
        with self.f.SessionLocal() as db:
            result = admitted.keep_copy(db, case_id=self.case_id, document_id=second.id,
                actor=self.f.actor, reason='This production carries the cited Bates range.')
        self.assertEqual(result['set_aside'], [str(first.id)])
        self.assertEqual(self.admitted_rows(), 12)
        first, second = self.source_of(self.primary), self.source_of(other)
        self.assertEqual((first.status, first.superseded_by_id, second.status), ('superseded', second.id, 'admitted'))
        self.assertEqual(self.item(batch_id, self.primary).status, 'duplicate_ignored')
        self.assertEqual(self.item(batch_id, other).status, 'imported')
        self.assertEqual(self.review(self.primary)['duplicate_disposition']['label'], 'Duplicate - Excluded by investigator')
        # The investigator's choice stands on the next run.
        self.assertEqual(self.apply()['applied'], [])
        self.assertEqual(self.source_of(other).status, 'admitted')

    def test_third_production_links_to_the_same_retained_copy_and_swaps_together(self):
        other, _ = self.save_twice(batch=False)
        third = self.fixture.copy_file()
        with legacy_matching():
            self.f.file = third
            self.assertTrue(self.f.confirm(self.masked_request()).get('created'))
        with self.f.SessionLocal() as db:
            for file, name in ((self.primary, '000100.pdf'), (other, '000500.pdf'), (third, '000900.pdf')):
                db.get(EvidenceFile, file.id).original_filename = name
                db.get(EvidenceFile, file.id).created_at = datetime(2026, 9, 16, 21, 9, tzinfo=timezone.utc)
            db.commit()
        self.assertEqual(self.admitted_rows(), 36)
        self.assertEqual(len(self.apply()['applied']), 2)
        self.assertEqual(self.admitted_rows(), 12)
        first, second, last = (self.source_of(f) for f in (self.primary, other, third))
        self.assertEqual({second.superseded_by_id, last.superseded_by_id}, {first.id})
        with self.f.SessionLocal() as db:
            admitted.keep_copy(db, case_id=self.case_id, document_id=last.id, actor=self.f.actor, reason='Cited copy')
        first, second, last = (self.source_of(f) for f in (self.primary, other, third))
        self.assertEqual((last.status, first.superseded_by_id, second.superseded_by_id), ('admitted', last.id, last.id))
        self.assertEqual(self.admitted_rows(), 12)
        self.assertEqual(self.apply()['applied'], [])

    def test_copy_with_different_money_is_held_never_set_aside(self):
        other, _ = self.save_twice(revised=True)
        plan = self.plan()
        self.assertEqual(plan['set_aside'], [])
        self.assertEqual([entry['code'] for entry in plan['held']], ['money_differs'])
        self.assertEqual(self.apply()['applied'], [])
        self.assertEqual(self.admitted_rows(), 24)
        # The product decision refuses it as well, under its own locks.
        with self.f.SessionLocal() as db:
            with self.assertRaises(DuplicateDecisionError):
                admitted.set_aside_copy(db, case_id=self.case_id, document_id=self.source_of(other).id,
                    retained_id=self.source_of(self.primary).id)
        self.assertEqual(self.admitted_rows(), 24)

    def test_copy_carrying_investigator_edits_is_the_one_kept(self):
        def edited(request):
            request = deepcopy(request)
            request['rows'][1]['description'] = 'Investigator wording'
            return request
        other, _ = self.save_twice(batch=False, second_request=edited)
        plan = self.plan()
        self.assertEqual(len(plan['set_aside']), 1, plan)
        self.assertEqual(plan['set_aside'][0]['retained_document_id'], str(self.source_of(other).id))
        self.apply()
        self.assertEqual(self.source_of(self.primary).status, 'superseded')
        self.assertEqual(self.admitted_rows(), 12)

    def test_recorded_reason_for_both_copies_is_respected(self):
        def both_needed(request):
            return {**request, 'coverage_review_reason': 'Second production carries an annotation.'}
        self.save_twice(batch=False, second_request=both_needed)
        plan = self.plan()
        self.assertEqual((plan['set_aside'], [e['code'] for e in plan['kept']]), ([], ['investigator_kept_both']))
        self.assertEqual(self.apply()['applied'], [])
        self.assertEqual(self.admitted_rows(), 24)

    def test_other_cases_are_never_touched(self):
        from uuid import uuid4
        self.save_twice()
        with self.f.SessionLocal() as db:
            self.assertEqual(admitted.find_admitted_duplicates(db, uuid4())['set_aside'], [])
            with self.assertRaises(admitted.AdmittedDuplicateError):
                admitted.set_aside_copy(db, case_id=uuid4(), document_id=self.source_of(self.primary).id,
                    retained_id=self.source_of(self.primary).id)


class AdmittedReprintTests(TestCase):
    """A statement printed twice in one PDF and saved once per printing."""

    def setUp(self):
        from tests.test_financial_statement_reprints import StatementReprintTests
        self.fixture = StatementReprintTests('test_an_identical_reprint_is_set_aside_and_the_period_imports_once')
        self.fixture.setUp()
        IngestionLog.__table__.create(self.fixture.db.get_bind(), checkfirst=True)

    def tearDown(self):
        self.fixture.tearDown()

    def test_second_printing_is_set_aside_for_the_first(self):
        from tests.test_financial_statement_reprints import transactions
        from services.financial.import_batches import initial_request
        fixture = self.fixture
        fixture.install(transactions(), transactions())
        first, second = fixture.printings()

        def legacy_disposition(session, *, case_id, file, proposal, request=None, actor=None, sources=None):
            return dict(status='not_duplicate')
        with legacy_matching(), patch('services.financial.pending_statement_duplicates.apply_duplicate_disposition',
                                      legacy_disposition):
            fixture.confirm(initial_request(second))
            fixture.confirm(initial_request(first))
        with fixture.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction)))), 6)
            sources = {s.metadata_.get('statement_import_statement_id'): s.id for s in db.scalars(select(FinancialSourceDocument))}
            self.assertLessEqual({first['statement_id'], second['statement_id']}, set(sources), sources)
            plan = admitted.find_admitted_duplicates(db, fixture.case.id)
        self.assertEqual(len(plan['set_aside']), 1, plan)
        self.assertEqual(plan['set_aside'][0]['document_id'], str(sources[second['statement_id']]))
        self.assertEqual(plan['set_aside'][0]['retained_document_id'], str(sources[first['statement_id']]))
        with fixture.SessionLocal() as db:
            result = admitted.set_aside_admitted_duplicates(db, fixture.case.id)
            self.assertEqual(len(result['applied']), 1, result['refused'])
            rows = list(db.scalars(select(FinancialTransaction).where(FinancialTransaction.ledger_status == 'admitted')))
            self.assertEqual(len(rows), 3)
            self.assertEqual({row.source_document_id for row in rows}, {sources[first['statement_id']]})
        reprint = fixture.read(second['statement_id'])
        self.assertEqual(reprint['duplicate_disposition']['label'], 'Duplicate - Ignored by system')
        self.assertEqual(reprint['duplicate_disposition']['retained']['source_document_id'], str(sources[first['statement_id']]))
        with fixture.SessionLocal() as db:
            admitted.restore_copy(db, case_id=fixture.case.id, document_id=sources[second['statement_id']])
            self.assertEqual(len(list(db.scalars(select(FinancialTransaction).where(
                FinancialTransaction.ledger_status == 'admitted')))), 6)


class ComparableReadingTests(TestCase):
    def reading(self, *kinds):
        rows = [dict(id=str(index), kind=kind, excluded=False, fields=dict(amount_minor='100', direction='debit', balance='5'))
                for index, kind in enumerate(kinds)]
        return dict(rows=rows, metadata={})

    def test_an_unread_row_counts_only_once_the_saved_review_excluded_it(self):
        reading = self.reading('balance', 'transaction', 'unresolved')
        self.assertFalse(admitted._comparable(reading, dict(rows=[dict(id='2', excluded=False)])))
        self.assertTrue(admitted._comparable(reading, dict(rows=[dict(id='2', excluded=True, reason='Not a payment')])))
        self.assertTrue(admitted._comparable(self.reading('balance', 'transaction'), dict(rows=[])))
        # Nothing left to compare is never comparable.
        self.assertFalse(admitted._comparable(self.reading('unresolved'), dict(rows=[dict(id='0', excluded=True)])))
