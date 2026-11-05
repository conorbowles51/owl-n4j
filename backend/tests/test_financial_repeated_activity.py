"""A statement repeating earlier activity under a new number is held for a person; no row moves on its own."""
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import select

from postgres.base import Base
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_judgements import FinancialJudgement
from services.financial.pdf_candidates import PdfMappingError
from services.financial.repeated_activity import (
    HOLD_MESSAGE, Line, Statement, assess_pair, carried_balance, case_report, different_number, printed_references,
    record_admitted, repeated_candidates, repeated_lines, review_statement, same_bank, same_holder,
)
from services.financial.statement_import_overlap import coverage_review, duplicate_hold, requires_decision
from tests import test_financial_duplicates as _duplicates
from tests import test_financial_statement_import as _statement_import


def line(day, amount, description, direction="debit", reference=None):
    return Line(date=day, amount=amount, direction=direction, currency="USD", description=description,
                references=printed_references(description, reference))


def statement(number, lines, holder="LASHIKA M HOPPER", bank="Merrick Bank", **extra):
    return Statement(account_id=number, institution=bank, holder=holder, number=number, currency="USD",
                     period_start="2022-06-01", period_end="2022-06-30", lines=lines, **extra)


REFERENCED = [line("2022-06-30", 15000, "7412061J500XTMJGV MOBILE PAYMENT THANK YOU"),
              line("2022-06-02", 2500, "7412061J500ABCDEF MERCHANT")]


class PairRules(unittest.TestCase):
    def test_printed_references_are_long_codes_with_a_digit(self):
        self.assertEqual(printed_references("7412061J500XTMJGV MOBILE PAYMENT"), {"7412061J500XTMJGV"})
        self.assertEqual(printed_references("MOBILEPAYMENT THANKYOU"), frozenset())
        self.assertEqual(printed_references("x", " AB 12 "), {"AB12"})

    def test_two_referenced_payments_under_a_new_number_are_a_candidate(self):
        result = assess_pair(statement("5425 3950 6522 1053", REFERENCED), statement("4120 6180 6507 0753", REFERENCED))
        self.assertEqual((result["repeated"], result["with_printed_reference"]), (2, 2))
        self.assertEqual(result["examples"][0]["date"], "2022-06-30")

    def test_one_reference_needs_a_carried_balance(self):
        one = REFERENCED[:1]
        older = statement("4120 6180 6507 0753", one, closing=-98765)
        self.assertIsNone(assess_pair(statement("5425 3950 6522 1053", one), older))
        carried = statement("5425 3950 6522 1053", one, other_lines=[line("2022-07-01", 98765, "BALANCE ADJUSTMENT")])
        result = assess_pair(carried, older)
        self.assertEqual(result["repeated"], 1)
        self.assertEqual(result["carried_balance"], "A line carries the earlier closing balance")

    def test_a_printed_balance_transfer_line_counts_and_so_does_an_equal_opening(self):
        transfer = statement("2", [line("2022-07-01", 1, "BALANCE TRANSFER FROM PREVIOUS CARD")])
        self.assertIn("BALANCE TRANSFER", carried_balance(transfer, statement("1", [])))
        self.assertEqual(carried_balance(statement("2", [], opening=500), statement("1", [], closing=500)),
                         "Opening balance equals the earlier closing balance")
        self.assertIsNone(carried_balance(statement("2", [], opening=0), statement("1", [], closing=0)))

    def test_a_recurring_fee_is_not_repeated_activity(self):
        fee = [line(f"2022-0{month}-28", 69900, "COM MEMBRESIA CUENTA") for month in range(1, 4)]
        own = fee + [line(f"2022-02-{day:02d}", 100 + day, f"PAYMENT {day}") for day in range(1, 20)]
        other = fee + [line("2023-01-01", 1, f"SALE {n}") for n in range(20)]
        self.assertIsNone(assess_pair(statement("11111", own, bank="Santander", holder="NOVAC PATRIMONIAL"),
                                      statement("22222", other, bank="Santander", holder="NOVAC PATRIMONIAL")))

    def test_another_holder_bank_currency_or_the_same_number_is_not_a_candidate(self):
        own = statement("5425 3950", REFERENCED)
        self.assertIsNone(assess_pair(own, statement("4120 6180", REFERENCED, holder="ERICA HOPPER")))
        self.assertIsNone(assess_pair(own, statement("4120 6180", REFERENCED, bank="Capital One")))
        self.assertIsNone(assess_pair(own, statement("5425 3950", REFERENCED)))
        other = statement("4120 6180", REFERENCED)
        other.currency = "EUR"
        self.assertIsNone(assess_pair(own, other))

    def test_the_masked_form_of_one_number_is_the_same_number(self):
        self.assertFalse(different_number("1053", "5425 3950 6522 1053"))
        self.assertTrue(different_number("0753", "5425 3950 6522 1053"))
        self.assertFalse(different_number("", "1053"))

    def test_names_and_banks_compare_on_their_words(self):
        self.assertTrue(same_holder("LASHIKA M HOPPER", "Lashika Hopper"))
        self.assertFalse(same_holder("ERICA HOPPER", "LASHIKA HOPPER"))
        self.assertFalse(same_holder("", "LASHIKA HOPPER"))
        self.assertTrue(same_bank("Merrick Bank", "MERRICK"))

    def test_each_payment_pairs_once_so_two_equal_payments_are_not_three(self):
        own = [line("2022-06-01", 10, "COFFEE SHOP"), line("2022-06-01", 10, "COFFEE SHOP"), line("2022-06-01", 10, "COFFEE SHOP")]
        self.assertEqual(len(repeated_lines(own, own[:2])), 2)

    def test_a_review_reads_kept_rows_and_keeps_set_aside_rows_for_the_carried_line(self):
        parsed = review_statement(dict(currency="USD", rows=[
            dict(id="1", date="2022-06-01", direction="debit", amount_minor="10", description="A"),
            dict(id="2", excluded=True, date="", amount_minor="0", description="BALANCE TRANSFER"),
            dict(id="3", amount_minor="not a number")]))
        self.assertEqual(([l.ident for l in parsed.lines], [l.ident for l in parsed.other_lines]), (["1"], ["2"]))


class Ledger(_duplicates.DuplicateTestCase):
    def setUp(self):
        super().setUp()
        Base.metadata.create_all(self.engine, tables=[FinancialJudgement.__table__])
        self.document = self.make_copy()
        self.rows = list(self.db.scalars(select(FinancialTransaction).where(
            FinancialTransaction.source_document_id == self.document.id).order_by(FinancialTransaction.row_index)))
        for index, row in enumerate(self.rows):
            row.description = f"7412061J50{index}XTMJGV CARD PAYMENT"
        account = self.rows[0].account
        self.holder, self.bank = account.holder_name or "Holder Name", account.institution_name or "Test Bank"
        account.holder_name, account.institution_name, account.identifier_as_printed = self.holder, self.bank, "1111222233"
        self.db.commit()

    def review(self, number="9999888877", file_id=None):
        rows = [dict(id=str(r.id), date=r.ordering_date.isoformat(), amount_minor=str(r.amount_minor), direction=r.direction,
                     description=r.description) for r in self.rows]
        return dict(rows=rows, holder=self.holder, institution=self.bank, account_number=number, currency=self.rows[0].currency,
                    period_start="2026-01-01", period_end="2026-01-31")

    def state(self):
        self.db.expire_all()
        return sorted(str(v) for v in self.db.execute(select(
            FinancialTransaction.id, FinancialTransaction.amount_minor, FinancialTransaction.ledger_status)).all())

    def test_a_statement_under_review_names_the_admitted_statement_it_repeats_and_changes_nothing(self):
        before = self.state()
        found = repeated_candidates(self.db, case_id=self.case.id, file_id=uuid4(), request=self.review())
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["source_document_id"], str(self.document.id))
        self.assertEqual(found[0]["status"], "imported")
        self.assertTrue(found[0]["matching_statement"])
        self.assertEqual(found[0]["repeated_activity"]["repeated"], len(self.rows))
        self.assertEqual(found[0]["repeated_activity"]["other_number"], "1111222233")
        self.assertEqual(self.state(), before)

    def test_its_own_file_a_replacement_or_the_switch_off_finds_nothing(self):
        file_id = self.document.evidence_file_id
        self.assertEqual(repeated_candidates(self.db, case_id=self.case.id, file_id=file_id, request=self.review()), [])
        replacing = dict(self.review(), replaces_source_document_id=str(self.document.id))
        self.assertEqual(repeated_candidates(self.db, case_id=self.case.id, file_id=uuid4(), request=replacing), [])
        with patch("services.financial.repeated_activity.HOLD", False):
            self.assertEqual(repeated_candidates(self.db, case_id=self.case.id, file_id=uuid4(), request=self.review()), [])

    def test_another_case_is_never_compared(self):
        self.assertEqual(repeated_candidates(self.db, case_id=self.other_case.id, file_id=uuid4(), request=self.review()), [])

    def test_admitted_pairs_become_judgement_calls_once_and_rows_stay(self):
        before = self.state()
        other = statement("9999888877", [line(r.ordering_date.isoformat(), r.amount_minor, r.description, r.direction)
                                         for r in self.rows], holder=self.holder, bank=self.bank)
        other.currency = self.rows[0].currency
        other.lines = [Line(date=l.date, amount=l.amount, direction=l.direction, currency=other.currency,
                            description=l.description, references=l.references) for l in other.lines]
        other.account_id = str(uuid4())
        other.source = dict(file_id=str(uuid4()), source_document_id=str(uuid4()), statement_period_id=str(uuid4()), filename="new.pdf")
        report = case_report(self.db, case_id=self.case.id, pending=[other])
        self.assertEqual(len(report), 1)
        self.assertFalse(report[0]["newer"]["pending"] and report[0]["older"]["pending"])
        with patch("services.financial.repeated_activity.case_report", return_value=report):
            for _ in range(2):
                self.assertEqual(record_admitted(self.db, case_id=self.case.id), dict(candidates=1, recorded=1))
        self.db.commit()
        self.assertEqual(len(list(self.db.scalars(select(FinancialJudgement)))), 1)
        self.assertEqual(self.state(), before)


class ImportHold(unittest.TestCase):
    def setUp(self):
        self.f = _statement_import.StatementImportTests("test_existing_import_and_same_request_keep_the_saved_account_for_navigation")
        self.f.setUp()
        self.addCleanup(self.f.tearDown)

    def candidate(self):
        return dict(file_id=str(uuid4()), statement_id=None, source_document_id=str(uuid4()), filename="earlier.pdf",
                    status="imported", period_start="2023-01-01", period_end="2023-01-31", matching_statement=True,
                    same_file_statement=False, repeated_activity=dict(repeated=3, with_printed_reference=2))

    def payments(self):
        with self.f.SessionLocal() as db:
            return list(db.scalars(select(FinancialTransaction)))

    def test_the_import_is_held_until_a_person_records_why_and_then_goes_through(self):
        with patch("services.financial.repeated_activity.repeated_candidates", return_value=[self.candidate()]):
            request = self.f.request()
            with self.assertRaises(PdfMappingError) as held:
                self.f.confirm(request)
            self.assertEqual(str(held.exception), HOLD_MESSAGE)
            self.assertEqual(self.payments(), [])
            with self.f.SessionLocal() as db:
                review = coverage_review(db, case_id=self.f.case.id, file_id=self.f.file.id, request=request, repeated=True)
            self.assertTrue(review["repeated_activity"])
            self.assertTrue(duplicate_hold(review, request))
            decided = dict(request, coverage_review_revision=review["revision"],
                           coverage_review_reason="Compared both originals; separate activity")
            self.assertFalse(requires_decision(review, decided))
            self.f.confirm(decided)
        self.assertTrue(self.payments())

    def test_with_no_candidate_the_import_is_as_before(self):
        with patch("services.financial.repeated_activity.repeated_candidates", return_value=[]):
            self.f.confirm()
        self.assertTrue(self.payments())

    def test_other_coverage_callers_do_not_ask_for_the_comparison(self):
        with patch("services.financial.repeated_activity.repeated_candidates", side_effect=AssertionError):
            with self.f.SessionLocal() as db:
                self.assertEqual(coverage_review(db, case_id=self.f.case.id, file_id=self.f.file.id, request=self.f.request())["candidates"], [])
