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

    def save_typed_mirror(self, change=None):
        """A person typed the whole statement in the other sign convention (a card typed as a deposit
        account): every payment's direction flipped and every printed balance negated."""
        def mirror(request):
            for row in request['rows']:
                if not row['excluded']:
                    row['direction'] = {'debit': 'credit', 'credit': 'debit'}[row['direction']]
                if row.get('balance_minor') not in (None, ''):
                    row['balance_minor'] = str(-int(row['balance_minor']))
            if change:
                change(request)
        request = self.f.request()
        mirror(request)
        return UUID(self.f.confirm_legacy(request)['source_document_id'])

    def test_a_typed_period_that_is_the_proving_reading_in_the_other_sign_is_replaced_and_restores(self):
        old_id = self.save_typed_mirror()
        rows = self.admitted_rows()
        verdict = self.assess(old_id)
        self.assertEqual((verdict['outcome'], verdict.get('basis')), ('replace', 'typed_mirror'), verdict)
        result = self.replace(old_id)
        self.assertTrue(result['applied'], result)
        new_id = UUID(result['receipt']['source_document_id'])
        self.assertEqual((self.admitted_rows(), self.document(old_id).status), (rows, 'superseded'))
        with self.f.SessionLocal() as db:
            directions = lambda doc: sorted((t.amount_minor, t.direction) for t in db.scalars(select(FinancialTransaction)
                                            .where(FinancialTransaction.source_document_id == doc)))
            flip = {'debit': 'credit', 'credit': 'debit'}
            self.assertEqual(directions(new_id), sorted((a, flip[d]) for a, d in directions(old_id)))
        self.assertEqual(self.assess(new_id)['outcome'], 'same')
        self.assertEqual(self.restore(new_id)['counting_source_document_id'], str(old_id))
        self.assertEqual((self.admitted_rows(), self.document(old_id).status), (rows, 'admitted'))

    def test_a_typed_period_that_is_not_an_exact_mirror_is_never_replaced(self):
        def one_more_cent(request):
            row = next(r for r in request['rows'] if not r['excluded'] and r['amount_minor'] not in ('', '0'))
            row['amount_minor'] = str(int(row['amount_minor']) + 1)
        self.assertEqual(self.assess(self.save_typed_mirror(one_more_cent))['code'], 'typed_payments')

    def test_the_typed_mirror_rule_switched_off_refuses_typed_periods(self):
        old_id = self.save_typed_mirror()
        with patch.object(replacement, 'TYPED_MIRROR', False):
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

    def test_the_same_money_read_into_its_contract_currency_account_is_refiled(self):
        # 2026-10-26 fin-queue3 L30c: Monex 2836625 periods saved in the contract's old single account while the
        # current reader files the same money in the contract's account of that currency.
        from postgres.models.financial import FinancialAccount, FinancialStatementPeriod
        from services.financial.accounts import TIER_CONTRACT_CURRENCY, TIER_INSTITUTION_ACCOUNT
        old_id = UUID(self.f.confirm()['source_document_id'])
        with self.f.SessionLocal() as db:
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == old_id))
            saved = db.get(FinancialAccount, period.account_id)
            contract = FinancialAccount(case_id=saved.case_id, identity_key=saved.identity_key + '\x1f' + period.currency,
                institution_name=saved.institution_name, identifier_as_printed=saved.identifier_as_printed,
                identifier_normalised=saved.identifier_normalised, holder_name=saved.holder_name, currency=period.currency,
                first_seen_run_id=saved.first_seen_run_id, metadata_=dict(identity_tier=TIER_CONTRACT_CURRENCY,
                                                                          account_reference_kind='multi_currency_contract'))
            db.add(contract)
            db.commit()
            contract_id = contract.id
        target = lambda session, *args, **kwargs: (None, session.get(FinancialAccount, contract_id))
        with patch.object(replacement, 'target_account', side_effect=target):
            verdict = self.assess(old_id)
            self.assertEqual((verdict['outcome'], verdict['differs'], verdict['account_moved']), ('replace', ['account'], True), verdict)
            self.assertEqual((verdict['missing_payments'], verdict['extra_payments']), (0, 0))
            self.assertEqual(verdict['request']['details_reason'], replacement.REFILED_REASON)
            with patch.object(replacement, 'REFILED_ACCOUNT', False):
                self.assertEqual(self.assess(old_id)['outcome'], 'same')
            with self.f.SessionLocal() as db:
                db.get(FinancialAccount, contract_id).metadata_ = dict(identity_tier=TIER_INSTITUTION_ACCOUNT)
                db.commit()
            self.assertEqual(self.assess(old_id)['outcome'], 'same', 'only the contract\'s currency account takes it')

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


class TypedMirrorTests(TestCase):
    def money(self, rows, opening, closing):
        from collections import Counter
        return dict(rows=Counter(rows), opening=opening, closing=closing)

    def test_mirrored_needs_every_payment_flipped_and_both_balances_negated(self):
        fresh = self.money([(500, 'debit', '2024-03-02'), (900, 'credit', '2024-03-05')], -1000, -1400)
        self.assertTrue(replacement.mirrored(
            self.money([(500, 'credit', '2024-03-02'), (900, 'debit', '2024-03-05')], 1000, 1400), fresh))
        for saved in (self.money([(500, 'credit', '2024-03-02')], 1000, 1400),
                      self.money([(500, 'credit', '2024-03-02'), (900, 'debit', '2024-03-06')], 1000, 1400),
                      self.money([(500, 'debit', '2024-03-02'), (900, 'credit', '2024-03-05')], 1000, 1400),
                      self.money([(500, 'credit', '2024-03-02'), (900, 'debit', '2024-03-05')], 1000, None),
                      self.money([], 0, 0)):
            self.assertFalse(replacement.mirrored(saved, fresh), saved)
        self.assertFalse(replacement.mirrored(self.money([], 0, 0), self.money([], 0, 0)))


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


class ImageReplacementTests(TestCase):
    """An incomplete saved period its text reading does not prove is replaced by its stored page reading (L22)."""

    def setUp(self):
        self.t = SavedReadingReplacementTests('test_a_reading_that_does_not_prove_is_left_and_nothing_is_written')
        self.t.setUp()
        self.f = self.t.f
        self.truth = self.t.review()

    def tearDown(self):
        self.t.tearDown()

    def _reading(self):
        """The page reading: every printed payment and both balances of the period, as the true statement prints them."""
        from services.financial.review_arithmetic import integer
        rows, balances = [], {}
        for row in self.truth['rows']:
            fields = row['fields']
            if row['kind'] == 'balance':
                balances[(fields.get('description') or '').strip().lower()] = (integer(fields.get('balance')), row['page_number'])
            elif row['kind'] == 'transaction' and not row['excluded']:
                rows.append(dict(index=len(rows), date=fields['date'], description=fields.get('description') or 'PAYMENT',
                                 amount_minor=int(fields['amount_minor']), direction=fields['direction'],
                                 balance_minor=integer(fields.get('balance')), page=row['page_number']))
        meta = self.truth['metadata']
        return dict(currency='EUR', holder='Test Company', account_number='TEST123', institution=meta['institution'],
                    period_start=meta['period_start'], period_end=meta['period_end'], rows=rows,
                    opening=balances['opening balance'][0], closing=balances['closing balance'][0],
                    opening_page=balances['opening balance'][1], closing_page=balances['closing balance'][1],
                    charge_totals={})

    def _save(self):
        """Saved from the statement it was read from (its statement key), as every batch save is."""
        return self.t.save_earlier_reading(lambda request: request.update(statement_id=self.truth['statement_id']))

    def _broken_text(self):
        payload = deepcopy(self.t.full)
        for value in payload[0]['table']['values']:
            if value['text'] == '€47,450':
                value['text'] = '€47,451'  # the current text reading no longer reconciles
        self.t.set_payload(payload)

    def _incomplete(self, document_id):
        from postgres.models.financial import FinancialStatementPeriod
        with self.f.SessionLocal() as db:
            period = db.scalar(select(FinancialStatementPeriod).where(FinancialStatementPeriod.source_document_id == document_id))
            # As Merrick was saved from a damaged reading: no closing balance.
            period.closing_balance_minor = None
            period.closing_balance_source = 'absent'
            db.commit()

    def _image(self):
        reading = self._reading()

        def stored(db, document, statement_id, proposal):
            from services.financial import vision_reader
            return (vision_reader.build_request(proposal, reading), dict(proposal), reading), None
        return patch('services.financial.vision_reader.saved_image_request', side_effect=stored)

    def test_an_incomplete_period_is_replaced_by_its_page_reading_and_restores(self):
        old_id = self._save()
        self._incomplete(old_id)
        self._broken_text()
        rows = self.t.admitted_rows()
        with patch.object(replacement, 'FROM_IMAGES', False):
            self.assertEqual(self.t.assess(old_id)['code'], 'not_proved')
        with self._image():
            verdict = self.t.assess(old_id)
            self.assertEqual((verdict['outcome'], verdict.get('basis')), ('replace', replacement.IMAGE_BASIS), verdict)
            self.assertIn('payments', verdict['differs'])
            result = self.t.replace(old_id)
        self.assertTrue(result['applied'], result)
        new_id = UUID(result['receipt']['source_document_id'])
        self.assertEqual(self.t.admitted_rows(), rows + 1, 'the period counts once, from the page reading')
        with self.f.SessionLocal() as db:
            new = db.get(FinancialSourceDocument, new_id)
            self.assertEqual(new.metadata_['statement_import_request']['details_reason'], replacement.IMAGE_REASON)
            self.assertTrue(all(r['id'].startswith('manual:vision-') for r in new.metadata_['statement_import_request']['rows']
                                if not r['excluded']))
        self.assertEqual(self.t.document(old_id).status, 'superseded')
        self.t.restore(new_id)
        self.assertEqual(self.t.admitted_rows(), rows, 'restore is the exact reversal')
        self.assertEqual(self.t.document(old_id).status, 'admitted')

    def test_a_page_reading_stored_as_not_proved_is_judged_again_before_the_writer_reads_it(self):
        from services.financial import vision_reader
        old_id = self._save()
        self._incomplete(old_id)
        self._broken_text()

        def target(db, document):
            # This fixture's file holds one statement (key ''); a Merrick file's statements each have a key.
            file = db.get(EvidenceFile, document.evidence_file_id)
            return document.case_id, file, '', 'EUR', read_statement_import(db, case_id=document.case_id,
                                                                            evidence_file_id=file.id, currency='EUR')
        with self.f.SessionLocal() as db:
            _, file, key, _, proposal = target(db, db.get(FinancialSourceDocument, old_id))
            metadata = deepcopy(file.metadata_ or {})
            # Read before the current rules: stored as not proved, without the proved printed totals.
            metadata.setdefault(vision_reader.SAVED_KEY, {})[key] = dict(
                version=vision_reader.VERSION, proof=vision_reader.PROOF_VERSION - 1, status='not_proved',
                revision=proposal['revision'], model='m', pages=vision_reader.statement_pages(proposal), raw={'stored': 1})
            file.metadata_ = metadata
            db.commit()
        reading = self._reading()
        reading['charge_totals'] = dict(fee=0)

        def judge(db, case_id, proposal, raw, pages, knowledge, saved=False, by=None):
            self.assertEqual(raw, {'stored': 1}, 'the stored reading is judged again')
            return reading, None, None, dict(proposal)
        with self._image(), patch.object(vision_reader, '_saved_target', side_effect=target), \
                patch.object(vision_reader, 'judge', side_effect=judge), \
                patch.object(vision_reader, 'openai_page_reader', side_effect=AssertionError('no request is sent')):
            result = self.t.replace(old_id)
        self.assertTrue(result['applied'], result)
        with self.f.SessionLocal() as db:
            record = db.get(EvidenceFile, self.f.file.id).metadata_[vision_reader.SAVED_KEY][key]
        self.assertEqual((record['status'], record['proof'], record['charge_totals']),
                         ('proved', vision_reader.PROOF_VERSION, dict(fee=0)))
        self.assertEqual(record['raw'], {'stored': 1})

    def test_a_complete_period_is_not_replaced_from_images(self):
        old_id = self._save()
        self._broken_text()
        with self._image():
            self.assertEqual(self.t.assess(old_id)['code'], 'not_proved')

    def test_without_a_stored_page_reading_the_text_verdict_stands(self):
        old_id = self._save()
        self._incomplete(old_id)
        self._broken_text()
        self.assertEqual(self.t.assess(old_id)['code'], 'not_proved')

    def test_the_writer_refuses_when_the_page_reading_is_gone(self):
        old_id = self._save()
        self._incomplete(old_id)
        self._broken_text()
        with self._image():
            verdict = self.t.assess(old_id)
        self.assertEqual(verdict['outcome'], 'replace')
        with self.assertRaises(PdfMappingError):
            confirm_statement_import(session_factory=self.f.SessionLocal, case_id=self.f.case.id,
                                     evidence_file_id=self.f.file.id, request=StatementImportRequest.model_validate(verdict['request']),
                                     actor=replacement.ACTOR, resolve_path=Path)
        self.assertEqual(self.t.document(old_id).status, 'admitted')


class UndatedPeriodTests(TestCase):
    """A period saved with no dates is the statement it was saved from (L22, 41 Erica Merrick periods)."""

    def test_only_the_statement_it_was_saved_from_is_an_undated_period(self):
        from types import SimpleNamespace
        period = SimpleNamespace(currency='USD', period_end=None, period_start=None)
        raw = dict(currency='USD', period_start='2022-03-26', period_end='2022-04-25', account_number='4120 6180 6507 0753')
        saved = dict(account_number='4120618065070753')
        self.assertTrue(replacement._same_period(raw, period, saved, same_key=True))
        self.assertFalse(replacement._same_period(raw, period, saved, same_key=False))
        self.assertFalse(replacement._same_period(dict(raw, account_number='999'), period, saved, same_key=True))
        with patch.object(replacement, 'UNDATED', False):
            self.assertFalse(replacement._same_period(raw, period, saved, same_key=True))

    def test_incomplete_means_no_dates_or_a_balance_missing(self):
        from types import SimpleNamespace
        whole = dict(period_end=1, period_start=1, opening_balance_minor=0, closing_balance_minor=5)
        self.assertFalse(replacement.incomplete(SimpleNamespace(**whole)))
        for key in whole:
            self.assertTrue(replacement.incomplete(SimpleNamespace(**dict(whole, **{key: None}))))
