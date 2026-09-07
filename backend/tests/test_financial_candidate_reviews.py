import unittest
from uuid import UUID, uuid4
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import event, select, update

from postgres.base import Base
from postgres.models.financial import FinancialAccount
from postgres.models.financial_candidates import FinancialCandidateReview
from services.financial.candidate_assessment import assess_candidate_amounts
from services.financial.candidate_store import CandidateStoreError
from services.financial.candidate_store import list_candidate_accounts, list_candidate_mappings
from services.financial.candidate_reviews import CandidateReviewRequest, read_candidate_review, review_candidate
from tests import test_financial_candidate_store as store_fixture


class CandidateReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = store_fixture.CandidateStoreTests()
        self.fixture.setUp()
        f = self.fixture
        Base.metadata.create_all(f.engine, tables=[FinancialAccount.__table__])
        self.account = FinancialAccount(case_id=f.case, identity_key="synthetic-review-account", currency="GBP")
        f.db.add(self.account)
        f.db.commit()
        self.saved = f.save()
        self.candidate_id = UUID(self.saved["candidates"][0]["id"])

    def tearDown(self):
        self.fixture.tearDown()

    def read(self):
        f = self.fixture
        return read_candidate_review(f.db, case_id=f.case, candidate_id=self.candidate_id)

    def reading(self, **updates):
        value = dict(account_id=str(self.account.id), currency="GBP", amount_minor="123400", direction="debit",
                     booking_date="2026-02-01", description="Synthetic reviewed transaction")
        value.update(updates)
        return value

    def review(self, status="rejected", **updates):
        f = self.fixture
        request = dict(expected_revision=self.read()["review_revision"], status=status, reason="Checked synthetic source")
        if status == "resolved":
            request["reading"] = self.reading()
        request.update(updates)
        return review_candidate(f.db, case_id=f.case, candidate_id=self.candidate_id, request=request, actor=f.actor)

    def test_initial_state_has_original_and_no_decisions(self):
        state = self.read()
        self.assertEqual(state["status"], "pending")
        self.assertEqual(state["history"], [])
        self.assertIsNone(state["reading"])
        self.assertFalse(state["applied"])

    def test_resolve_reopen_reject_preserves_every_decision_and_original(self):
        original = self.read()["original"]
        resolved = self.review("resolved")
        self.assertEqual(resolved["reading"]["amount_minor"], "123400")
        self.review("pending")
        final = self.review("rejected")
        self.assertEqual([r["status"] for r in final["history"]], ["resolved", "pending", "rejected"])
        self.assertEqual(final["original"], original)
        self.assertIsNone(final["reading"])
        self.assertFalse(final["applied"])
        self.assertEqual(self.fixture.read(self.saved)["candidates"][0]["status"], "rejected")

    def test_two_reviews_from_one_revision_only_first_applies(self):
        revision = self.read()["review_revision"]
        self.review("resolved", expected_revision=revision)
        with self.assertRaises(CandidateStoreError) as error:
            self.review("rejected", expected_revision=revision)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(self.read()["history"]), 1)

    def test_revised_reading_appends_instead_of_overwriting(self):
        first = self.review("resolved")
        second = self.review("resolved", reading=self.reading(amount_minor="1234"))
        self.assertEqual(second["history"][0], first["history"][0])
        self.assertEqual(second["reading"]["amount_minor"], "1234")

    def test_repeat_state_is_refused(self):
        self.review()
        with self.assertRaises(CandidateStoreError):
            self.review()

    def test_original_is_preserved_when_reviewed_amount_differs(self):
        result = self.review("resolved", reading=self.reading(amount_minor="1234"))
        self.assertEqual(result["original"]["cells"][1]["text"], "1234")
        self.assertEqual(result["reading"]["amount_minor"], "1234")

    def test_invalid_or_incomplete_readings_refused(self):
        for updates in ({"amount_minor": 1234}, {"amount_minor": "-1"}, {"amount_minor": "01"},
                        {"amount_minor": "9223372036854775808"}, {"booking_date": None},
                        {"booking_date": "01/02"}, {"booking_date": "2026-02-30"},
                        {"booking_date": "20260201"}, {"currency": "XYZ"}, {"direction": "unknown"}):
            with self.subTest(updates=updates), self.assertRaises(ValidationError):
                self.review("resolved", reading=self.reading(**updates))
        self.assertEqual(self.read()["history"], [])

    def test_zero_and_bigint_boundary_are_exact_strings(self):
        for value in ("0", "9223372036854775807"):
            result = self.review("resolved", reading=self.reading(amount_minor=value))
            self.assertEqual(result["reading"]["amount_minor"], value)

    def test_date_role_is_explicit_without_default_booking_date(self):
        result = self.review("resolved", reading=self.reading(booking_date=None, value_date="2026-02-01"))
        self.assertIsNone(result["reading"]["booking_date"])
        self.assertEqual(result["reading"]["value_date"], "2026-02-01")

    def test_account_must_exist_in_case_and_match_currency(self):
        for reading in (self.reading(account_id=str(uuid4())), self.reading(currency="USD")):
            with self.assertRaises(CandidateStoreError) as error:
                self.review("resolved", reading=reading)
            self.assertEqual(error.exception.status_code, 422)
        self.account.case_id = uuid4()
        self.fixture.db.commit()
        with self.assertRaises(CandidateStoreError):
            self.review("resolved")

    def test_wrong_case_cannot_read_or_review(self):
        f = self.fixture
        with self.assertRaises(CandidateStoreError) as error:
            read_candidate_review(f.db, case_id=uuid4(), candidate_id=self.candidate_id)
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(CandidateStoreError):
            review_candidate(f.db, case_id=uuid4(), candidate_id=self.candidate_id, actor=f.actor,
                request=dict(expected_revision=self.read()["review_revision"], status="rejected", reason="Synthetic"))

    def test_stale_source_refuses_new_decision_but_history_remains_readable(self):
        self.review()
        self.fixture.text.source_locations = []
        self.fixture.db.commit()
        with self.assertRaises(CandidateStoreError):
            self.review("pending")
        self.assertEqual(self.read()["status"], "rejected")

    def test_assessment_reflects_review_state_without_applying_it(self):
        self.review("resolved")
        f = self.fixture
        result = assess_candidate_amounts(f.db, case_id=f.case, candidate_id=self.candidate_id, currency="GBP")
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["review_revision"], self.read()["review_revision"])
        self.assertFalse(result["applied"])

    def test_review_history_is_immutable(self):
        self.review()
        row = self.fixture.db.scalar(select(FinancialCandidateReview))
        row.reason = "changed"
        with self.assertRaises(ValueError):
            self.fixture.db.commit()
        self.fixture.db.rollback()
        self.assertEqual(self.read()["history"][0]["reason"], "Checked synthetic source")

    def test_failure_before_review_insert_rolls_back(self):
        def fail(mapper, connection, target):
            raise RuntimeError("Synthetic write failure")
        event.listen(FinancialCandidateReview, "before_insert", fail)
        try:
            with self.assertRaises(RuntimeError):
                self.review()
        finally:
            event.remove(FinancialCandidateReview, "before_insert", fail)
        self.assertEqual(self.read()["history"], [])
        self.assertEqual(self.review()["status"], "rejected")

    def test_broken_review_chain_is_refused(self):
        self.review()
        self.fixture.db.execute(update(FinancialCandidateReview).values(previous_revision="a"*64))
        self.fixture.db.commit()
        with self.assertRaises(CandidateStoreError):
            self.read()

    def test_reason_and_resolution_shape_are_required(self):
        base = dict(expected_revision=self.read()["review_revision"], status="rejected", reason="Checked")
        for updates in ({"reason": " "}, {"status": "resolved"}, {"reading": self.reading()}, {"proof_class": "p0"}):
            with self.subTest(updates=updates), self.assertRaises(ValidationError):
                CandidateReviewRequest.model_validate({**base, **updates})

    def test_candidate_list_is_case_scoped_and_paginated(self):
        f = self.fixture
        f.mapping["columns"][1]["meaning"] = "balance"
        f.save()
        first = list_candidate_mappings(f.db, case_id=f.case, limit=1)
        second = list_candidate_mappings(f.db, case_id=f.case, limit=1, offset=1)
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertNotEqual(first["items"][0]["id"], second["items"][0]["id"])
        self.assertEqual(list_candidate_mappings(f.db, case_id=uuid4())["items"], [])

    def test_candidate_list_does_not_expose_raw_snapshots(self):
        result = list_candidate_mappings(self.fixture.db, case_id=self.fixture.case)
        self.assertEqual(result["items"][0]["candidate_count"], 2)
        self.assertNotIn("original", result["items"][0])

    def test_account_search_is_case_scoped_and_escapes_wildcards(self):
        f = self.fixture
        self.account.holder_name = "Synthetic 100% account"
        f.db.commit()
        self.assertEqual(len(list_candidate_accounts(f.db, case_id=f.case, search="100%")["items"]), 1)
        self.assertEqual(list_candidate_accounts(f.db, case_id=f.case, search="100_")["items"], [])
        self.assertEqual(list_candidate_accounts(f.db, case_id=uuid4())["items"], [])

    def test_candidate_list_limits_are_checked(self):
        for params in ({"limit": 101}, {"limit": True}, {"offset": -1}):
            with self.assertRaises(CandidateStoreError):
                list_candidate_mappings(self.fixture.db, case_id=self.fixture.case, **params)

    def test_account_search_limits_are_checked(self):
        for params in ({"search": "x"*129}, {"limit": True}, {"limit": 101}):
            with self.assertRaises(CandidateStoreError):
                list_candidate_accounts(self.fixture.db, case_id=self.fixture.case, **params)


class CandidateReviewRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_mapping_creation_uses_authenticated_actor_and_case(self):
        from routers import financial_adjudication as router
        case = uuid4()
        with patch.object(router, "actor_from_user", return_value="actor"), patch.object(router, "store_pdf_candidates", return_value={}) as call:
            await router.record_candidate_mapping("proposal", case, "user", "db")
        call.assert_called_once_with("db", case_id=case, proposal="proposal", actor="actor")

    async def test_write_requires_edit_and_uses_authenticated_actor(self):
        from routers import financial_adjudication as router
        case, candidate = uuid4(), uuid4()
        body = CandidateReviewRequest(expected_revision="a"*64, status="rejected", reason="Checked")
        with patch.object(router, "actor_from_user", return_value="actor") as actor, patch.object(router, "review_candidate", return_value={}) as call:
            await router.record_candidate_review(candidate, body, case, "user", "db")
        actor.assert_called_once_with("user")
        call.assert_called_once_with("db", case_id=case, candidate_id=candidate, request=body, actor="actor")
        self.assertEqual(router._adjudication_case_permission(None, {}), ("case", "edit"))

    async def test_stale_review_is_409(self):
        from fastapi import HTTPException
        from routers import financial_adjudication as router
        body = CandidateReviewRequest(expected_revision="a"*64, status="rejected", reason="Checked")
        with patch.object(router, "actor_from_user", return_value="actor"), patch.object(router, "review_candidate", side_effect=CandidateStoreError("Reload", 409)):
            with self.assertRaises(HTTPException) as error:
                await router.record_candidate_review(uuid4(), body, uuid4(), "user", "db")
        self.assertEqual(error.exception.status_code, 409)

    async def test_read_route_is_case_scoped(self):
        from routers import financial_ledger as router
        case, candidate = uuid4(), uuid4()
        with patch.object(router, "read_candidate_review", return_value={}) as call:
            await router.get_candidate_review(candidate, case, "db")
        call.assert_called_once_with("db", case_id=case, candidate_id=candidate)
