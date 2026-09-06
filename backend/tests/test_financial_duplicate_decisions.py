"""Duplicate decisions preserve corrections, audit history and case isolation."""
import uuid
from unittest.mock import patch
from sqlalchemy import select
from postgres.models.financial import AdjudicationEvent, FinancialTransaction, FinancialSourceDocument
from services.financial.duplicate_decisions import DuplicateDecisionError, decide_duplicate, duplicate_revision
from services.financial.quarantine_row import release_case_row
from tests.test_financial_duplicates import DuplicateTestCase


class DuplicateDecisionTests(DuplicateTestCase):
    def pair(self):
        return self.make_copy(), self.make_copy()

    def decide(self, document, primary=None, **overrides):
        args = dict(case_id=self.case.id, document_id=document.id,
                    action="exclude" if primary else "restore",
                    expected_revision=duplicate_revision(self.db, document),
                    actor=self.actor, reason="Reviewed against the retained copy.",
                    primary_id=primary.id if primary else None,
                    expected_primary_revision=duplicate_revision(self.db, primary) if primary else None)
        args.update(overrides)
        return decide_duplicate(self.db, **args)

    def rows(self, document):
        return list(self.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == document.id)))

    def test_round_trip_records_exact_rows_actor_and_reason(self):
        copy, primary = self.pair()
        reviewed = duplicate_revision(self.db, copy)
        retained = duplicate_revision(self.db, primary)
        result = self.decide(copy, primary)
        self.assertEqual(result["changed_rows"], 2)
        self.assertEqual(self.reload(copy).status, "superseded")
        self.assertTrue(all(r.ledger_status == "admitted" for r in self.rows(primary)))
        event = self.db.get(AdjudicationEvent, uuid.UUID(result["adjudication_id"]))
        self.assertEqual(event.after["reviewed_revision"], reviewed)
        self.assertEqual(event.after["retained_revision"], retained)
        self.assertEqual(event.actor_user_id, self.user.id)
        self.assertEqual(event.reason, "Reviewed against the retained copy.")
        self.assertEqual(set(event.after["rows"]), {str(r.id) for r in self.rows(copy)})
        self.decide(copy)
        self.assertEqual(self.reload(copy).status, "admitted")
        self.assertTrue(all(r.ledger_status == "admitted" for r in self.rows(copy)))
        self.assertEqual(len(list(self.db.scalars(select(AdjudicationEvent)))), 2)

    def test_restore_leaves_preexisting_superseded_rows_untouched(self):
        copy, primary = self.pair()
        old = self.rows(copy)[0]
        old.ledger_status = "superseded"
        replacement_id = self.rows(copy)[1].id
        old.superseded_by_id = replacement_id
        self.db.commit()
        self.decide(copy, primary)
        self.decide(copy)
        self.db.refresh(old)
        self.assertEqual(old.ledger_status, "superseded")
        self.assertEqual(old.superseded_by_id, replacement_id)

    def test_quarantine_cannot_be_released_while_document_excluded(self):
        copy, primary = self.pair()
        held = self.rows(copy)[0]
        held.ledger_status, held.quarantine_reason = "quarantined", "unreadable_row"
        self.db.commit()
        self.decide(copy, primary)
        answer = release_case_row(self.db, case_id=self.case.id, transaction_id=held.id,
                                  actor=self.user, reason="Attempted while excluded")
        self.assertFalse(answer.applied)
        self.decide(copy)
        self.db.refresh(held)
        self.assertEqual(held.ledger_status, "quarantined")

    def test_stale_repeated_request_appends_nothing(self):
        copy, primary = self.pair()
        revision = duplicate_revision(self.db, copy)
        self.decide(copy, primary)
        with self.assertRaises(DuplicateDecisionError):
            self.decide(copy, primary, expected_revision=revision)
        self.assertEqual(len(list(self.db.scalars(select(AdjudicationEvent)))), 1)

    def test_changed_primary_revision_is_refused(self):
        copy, primary = self.pair()
        with self.assertRaises(DuplicateDecisionError):
            self.decide(copy, primary, expected_primary_revision="0" * 64)
        self.assertEqual(self.reload(copy).status, "admitted")

    def test_differing_readings_are_refused_even_with_same_bytes(self):
        for same_bytes in (False, True):
            with self.subTest(same_bytes=same_bytes):
                copy = self.make_copy(sha256="a" * 64)
                primary = self.make_copy(rows=((400_00, "aa"),), sha256=("a" if same_bytes else "b") * 64)
                with self.assertRaises(DuplicateDecisionError):
                    self.decide(copy, primary)
                self.assertEqual(self.reload(copy).status, "admitted")

    def test_retained_copy_must_have_eligible_admitted_rows(self):
        for field, value in (("ledger_status", "rejected"), ("proof_class", "p3")):
            copy, primary = self.pair()
            setattr(self.rows(primary)[0], field, value)
            self.db.commit()
            with self.assertRaises(DuplicateDecisionError):
                self.decide(copy, primary)

    def test_primary_with_dependents_cannot_be_hidden(self):
        copy, primary = self.pair()
        third = self.make_copy()
        self.decide(copy, primary)
        with self.assertRaises(DuplicateDecisionError):
            self.decide(primary, third)
        self.assertEqual(self.reload(primary).status, "admitted")

    def test_cross_case_primary_is_indistinguishable_from_missing(self):
        copy = self.make_copy()
        other = self.make_copy(case=self.other_case, run=self.other_run, account=self.other_account)
        with self.assertRaises(DuplicateDecisionError) as caught:
            self.decide(copy, other)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.reload(copy).status, "admitted")

    def test_self_exclusion_and_blank_reason_are_refused(self):
        copy, primary = self.pair()
        for retained, reason in [(copy, "Reason"), (primary, " ")]:
            with self.assertRaises(DuplicateDecisionError):
                self.decide(copy, retained, reason=reason)

    def test_legacy_exclusion_cannot_be_restored_without_row_record(self):
        self.pair()
        group = self.resolve()[0]
        self.db.commit()
        copy = self.db.get(FinancialSourceDocument, group.excluded_ids[0])
        with self.assertRaises(DuplicateDecisionError):
            self.decide(copy)

    def test_later_correction_is_not_overwritten(self):
        copy, primary = self.pair()
        self.decide(copy, primary)
        old, replacement = self.rows(copy)
        old.superseded_by_id = replacement.id
        self.db.commit()
        with self.assertRaises(DuplicateDecisionError):
            self.decide(copy)
        self.assertEqual(self.reload(copy).status, "superseded")

    def test_commit_failure_rolls_back_event_and_state(self):
        copy, primary = self.pair()
        with patch.object(self.db, "commit", side_effect=RuntimeError("write failure")):
            with self.assertRaises(RuntimeError):
                self.decide(copy, primary)
        self.assertEqual(self.reload(copy).status, "admitted")
        self.assertEqual(list(self.db.scalars(select(AdjudicationEvent))), [])
