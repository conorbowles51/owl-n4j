"""Tests for the BAI2 native parser.

The same limitation that opens ``test_financial_camt053`` applies here and is
worth restating rather than cross-referencing, because it is the single most
important thing to know about this suite.  No corpus document backs any of it.
The ET-Fraud corpus carries no BAI2 file at all, so every fixture below is
constructed from the BAI2 record layout rather than measured from
evidence.  A fixture built by the same reading of the specification as the
parser shares the parser's blind spots exactly: if the reading is wrong, the
test passes and the parser is wrong together.

What these tests establish is that the parser is self-consistent, that it
refuses what it cannot read, that its three control totals are genuinely three
checks rather than one counted three times, and that nothing reaches
:attr:`ProofClass.p0` without arithmetic that closed.  What only a real file
from a real bank can establish is that the reading is right.  Sourcing one
remains the blocking item.

Two conventions are held throughout.  Every expectation is asserted against a
literal rather than against the constant the module uses, since asserting
``BAI2_VERSION == BAI2_VERSION`` establishes nothing.  And the refusal paths
are tested at least as heavily as the success path, because a misreading of the
specification surfaces as a document wrongly *admitted* far more often than as
one wrongly refused, and only the first of those is dangerous.
"""

from __future__ import annotations

import unittest
from typing import Optional, Sequence

from postgres.models.enums import (
    LocatorKind,
    ProofClass,
    ReconciliationStatus,
    TransactionDirection,
)
from services.financial.bai2 import (
    BAI2_MAX_FILE_BYTES,
    Bai2AmountError,
    _FILE_CONTROL_BASIS,
    Bai2CurrencyError,
    Bai2Error,
    Bai2MalformedFileError,
    Bai2MissingFieldError,
    NotABai2Error,
    _common_currency,
    _consume_funds_type,
    _direction_for_type_code,
    _fold_records,
    _parse_amount,
    _parse_count,
    _parse_minor_units,
    _split_physical,
    _sum_minor_units,
    _weakest,
    parse_bai2,
)
from services.financial.money import Money
from services.financial.proof_class import SourceShape, assign_proof_class

# ---------------------------------------------------------------------------
# Fixtures
#
# One canonical file, and a builder that perturbs exactly one field of it.  The
# arithmetic is worked here once so that every test below can be read against
# it:
#
#   03 amounts   10000 + 15000 + 8000 + 3000  = 36000
#   16 amounts    5000 +  3000 + 3000         = 11000
#   49 total                                  = 47000
#
#   49 records   03(1) + 16(3) + 49(1)        =     5
#   98 records   02(1) +      5 + 98(1)       =     7
#   99 records   01(1) +      7 + 99(1)       =     9
#
#   balance      10000 + 8000 - 3000          = 15000 = the 015 figure
#   summary      credits 8000/2, debits 3000/1, both as the 03 declares
# ---------------------------------------------------------------------------

_HEADER = "01,SENDER,RECEIVER,240115,0800,1,80,,{version}/"
_GROUP = "02,RECEIVER,BANK,{status},240115,0800,{currency},2/"
_ACCOUNT = "03,1234567890,{account_currency},010,10000,,,015,15000,,,100,8000,2,,400,3000,1,/"
_DETAILS = (
    "16,165,5000,0,REF1,CUST1,Deposit one/",
    "16,165,3000,0,REF2,CUST2,Deposit two/",
    "16,475,3000,0,REF3,CUST3,Payment/",
)
_ACCOUNT_TRAILER = "49,{account_total},{account_records}/"
_GROUP_TRAILER = "98,{group_total},{account_count},{group_records}/"
_FILE_TRAILER = "99,{file_total},{group_count},{file_records}/"

_DEFAULTS = {
    "version": "2",
    "status": "1",
    "currency": "USD",
    "account_currency": "USD",
    "account_total": "47000",
    "account_records": "5",
    "group_total": "47000",
    "account_count": "1",
    "group_records": "7",
    "file_total": "47000",
    "group_count": "1",
    "file_records": "9",
}


def build(**overrides: str) -> str:
    """The canonical file with named fields replaced.

    Every test that perturbs the file does it through here, so a test reads as
    the single thing it changed rather than as a wall of records in which the
    changed digit has to be found.
    """
    values = dict(_DEFAULTS)
    values.update(overrides)
    lines = [
        _HEADER.format(**values),
        _GROUP.format(**values),
        _ACCOUNT.format(**values),
        *_DETAILS,
        _ACCOUNT_TRAILER.format(**values),
        _GROUP_TRAILER.format(**values),
        _FILE_TRAILER.format(**values),
    ]
    return "".join(line + "\n" for line in lines)


def file_of(*lines: str) -> str:
    """An arbitrary record sequence as file text."""
    return "".join(line + "\n" for line in lines)


class BaselineTests(unittest.TestCase):
    """The canonical fixture, read end to end.

    If this class fails, nothing below it means anything: every other test
    perturbs this file and reads the difference.
    """

    def setUp(self) -> None:
        self.parsed = parse_bai2(build())

    def test_the_file_header_is_read_field_by_field(self) -> None:
        parsed = self.parsed
        self.assertEqual(parsed.sender, "SENDER")
        self.assertEqual(parsed.receiver, "RECEIVER")
        self.assertEqual(parsed.creation_date, "240115")
        self.assertEqual(parsed.creation_time, "0800")
        self.assertEqual(parsed.file_identification, "1")
        self.assertEqual(parsed.physical_record_length, 80)
        self.assertIsNone(parsed.block_size)
        self.assertEqual(parsed.version, "2")

    def test_the_group_header_is_read_field_by_field(self) -> None:
        group = self.parsed.groups[0]
        self.assertEqual(group.ultimate_receiver, "RECEIVER")
        self.assertEqual(group.originator, "BANK")
        self.assertEqual(group.status, "1")
        self.assertEqual(group.as_of_date, "240115")
        self.assertEqual(group.as_of_time, "0800")
        self.assertEqual(group.currency, "USD")
        self.assertEqual(group.as_of_date_modifier, "2")
        self.assertEqual(group.first_line, 2)

    def test_the_account_is_read_with_its_summaries(self) -> None:
        account = self.parsed.accounts[0]
        self.assertEqual(account.customer_account_number, "1234567890")
        self.assertEqual(account.currency, "USD")
        self.assertEqual(account.currency_source, "account")
        self.assertEqual(
            [entry.type_code for entry in account.summaries],
            ["010", "015", "100", "400"],
        )
        self.assertEqual(account.opening_balance, Money.from_minor_units(10000, "USD"))
        self.assertEqual(account.closing_balance, Money.from_minor_units(15000, "USD"))
        self.assertEqual(account.summary("100").item_count, 2)
        self.assertEqual(account.summary("400").item_count, 1)
        self.assertIsNone(account.summary("999"))

    def test_the_details_are_read_with_direction_and_narrative(self) -> None:
        transactions = self.parsed.transactions
        self.assertEqual(len(transactions), 3)
        self.assertEqual([txn.index for txn in transactions], [0, 1, 2])
        self.assertEqual([txn.line_number for txn in transactions], [4, 5, 6])
        self.assertEqual(
            [txn.direction for txn in transactions],
            [
                TransactionDirection.credit,
                TransactionDirection.credit,
                TransactionDirection.debit,
            ],
        )
        first = transactions[0]
        self.assertEqual(first.type_code, "165")
        self.assertEqual(first.amount, Money.from_minor_units(5000, "USD"))
        self.assertEqual(first.funds_type, "0")
        self.assertEqual(first.bank_reference, "REF1")
        self.assertEqual(first.customer_reference, "CUST1")
        self.assertEqual(first.text, "Deposit one")

    def test_every_check_passes_and_the_file_earns_p0(self) -> None:
        parsed = self.parsed
        account = parsed.accounts[0]
        self.assertIs(account.control_total.status, ReconciliationStatus.balanced)
        self.assertIs(account.balance_identity.status, ReconciliationStatus.balanced)
        self.assertIs(account.summary_identity.status, ReconciliationStatus.balanced)
        self.assertIs(parsed.groups[0].reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertEqual(parsed.admissibility_reservations, ())
        self.assertIs(parsed.proof_class, ProofClass.p0)

    def test_the_source_shape_is_fixed_and_not_settable(self) -> None:
        self.assertIs(self.parsed.source_shape, SourceShape.native_with_control_totals)
        with self.assertRaises(TypeError):
            parse_bai2(build(), source_shape=SourceShape.statement_document)  # type: ignore[call-arg]

    def test_a_bai2_row_carries_no_click_through_target(self) -> None:
        # BAI2 is a feed of records, not a rectangle on a page.  A reader that
        # offered coordinates here would be inventing them.
        self.assertIs(self.parsed.accounts[0].locator.kind, LocatorKind.not_positional)
        self.assertIs(self.parsed.transactions[0].locator.kind, LocatorKind.not_positional)

    def test_bytes_and_text_are_read_identically(self) -> None:
        from_text = parse_bai2(build())
        from_bytes = parse_bai2(build().encode("utf-8"))
        self.assertEqual(from_text, from_bytes)


class ControlTotalArithmeticTests(unittest.TestCase):
    """The three levels, and the independence of each from the others."""

    def test_the_account_total_sums_the_03_and_the_16_records(self) -> None:
        control = parse_bai2(build()).accounts[0].control_total
        self.assertEqual(control.declared_minor_units, 47000)
        self.assertEqual(control.computed_minor_units, 47000)
        self.assertEqual(control.minor_unit_delta, 0)
        self.assertEqual(control.level, "49")
        self.assertIn("03", control.basis)
        self.assertIn("16", control.basis)

    def test_a_wrong_account_total_is_unbalanced_and_states_the_delta(self) -> None:
        parsed = parse_bai2(
            build(account_total="47100", group_total="47100", file_total="47100")
        )
        control = parsed.accounts[0].control_total
        self.assertIs(control.status, ReconciliationStatus.unbalanced)
        self.assertEqual(control.minor_unit_delta, -100)
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_a_wrong_record_count_fails_even_though_the_total_agrees(self) -> None:
        # The point of counting records at all.  A lost 88 carrying a payee's
        # name moves no money and the sum will never notice it.
        control = parse_bai2(build(account_records="4")).accounts[0].control_total
        self.assertEqual(control.minor_unit_delta, 0)
        self.assertFalse(control.record_count_agrees)
        self.assertIs(control.status, ReconciliationStatus.unbalanced)
        self.assertIn("record", control.unavailable_reason)

    def test_a_wrong_account_count_fails_at_group_level(self) -> None:
        control = parse_bai2(build(account_count="2")).groups[0].control_total
        self.assertEqual(control.minor_unit_delta, 0)
        self.assertEqual(control.computed_child_count, 1)
        self.assertEqual(control.declared_child_count, 2)
        self.assertFalse(control.child_count_agrees)
        self.assertIs(control.status, ReconciliationStatus.unbalanced)

    def test_the_group_total_is_checked_against_what_the_49_declared(self) -> None:
        # The independence property.  A wrong 98 must not implicate the 49, and
        # a wrong 49 must not be absolved by a 98 that happens to match it.
        parsed = parse_bai2(build(group_total="47100", file_total="47100"))
        self.assertIs(
            parsed.accounts[0].control_total.status, ReconciliationStatus.balanced
        )
        self.assertIs(
            parsed.groups[0].control_total.status, ReconciliationStatus.unbalanced
        )
        self.assertEqual(parsed.groups[0].control_total.minor_unit_delta, -100)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.unbalanced)

    def test_a_wrong_49_summed_consistently_still_fails_through_the_accounts(self) -> None:
        # The converse, and the reason Bai2Group.reconciliation_status rolls the
        # accounts up rather than trusting the 98.  Here every trailer agrees
        # with every other trailer and the records are what disagree.
        parsed = parse_bai2(
            build(account_total="47100", group_total="47100", file_total="47100")
        )
        self.assertIs(
            parsed.groups[0].control_total.status, ReconciliationStatus.balanced
        )
        self.assertIs(
            parsed.accounts[0].control_total.status, ReconciliationStatus.unbalanced
        )
        self.assertIs(parsed.groups[0].reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_record_counts_are_physical_and_include_continuations(self) -> None:
        text = file_of(
            "01,S,R,240115,0800,1,,,2/",
            "02,R,B,1,240115,,USD,/",
            "03,111,USD,010,10000,,/",
            "88,015,11000,,/",
            "16,165,1000,0,R1,C1,Line one/",
            "88,Line two/",
            "49,22000,5/",
            "98,22000,1,7/",
            "99,22000,1,9/",
        )
        parsed = parse_bai2(text)
        self.assertEqual(parsed.accounts[0].control_total.computed_record_count, 5)
        self.assertEqual(parsed.groups[0].control_total.computed_record_count, 7)
        self.assertEqual(parsed.control_total.computed_record_count, 9)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)

    def test_an_absent_total_is_unavailable_rather_than_unbalanced(self) -> None:
        # Both keep the file off p0.  The distinction exists so the reviewer
        # looks for a missing trailer rather than for a discrepancy.
        parsed = parse_bai2(build(account_total="", group_total="", file_total=""))
        account_control = parsed.accounts[0].control_total
        self.assertIs(account_control.status, ReconciliationStatus.unavailable)
        self.assertIn("mandatory", account_control.unavailable_reason)
        self.assertIsNone(account_control.minor_unit_delta)
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_a_child_declaring_no_total_leaves_the_parent_nothing_to_sum(self) -> None:
        # Distinct from the parent declaring none itself, and the message says
        # which, because reading the missing declaration as zero would shift the
        # parent's total by the child's amount and blame the parent's trailer.
        control = parse_bai2(build(account_total="")).groups[0].control_total
        self.assertIs(control.status, ReconciliationStatus.unavailable)
        self.assertIsNone(control.computed_minor_units)
        self.assertIn("account 1 declared none", control.unavailable_reason)

    def test_an_absent_record_count_is_simply_not_compared(self) -> None:
        control = parse_bai2(build(account_records="")).accounts[0].control_total
        self.assertIsNone(control.declared_record_count)
        self.assertEqual(control.computed_record_count, 5)
        self.assertIs(control.status, ReconciliationStatus.balanced)

    def test_a_negative_control_total_is_legitimate(self) -> None:
        # A checksum over signed amounts, not a quantity of money.  A net-debit
        # account produces one and nothing is wrong with it.
        text = file_of(
            "01,S,R,240115,0800,1,,,2/",
            "02,R,B,1,240115,,USD,/",
            "03,111,USD,010,5000,,,015,4000,,/",
            "16,475,1000,0,R1,C1,Payment/",
            "49,10000,3/",
            "98,10000,1,5/",
            "99,10000,1,7/",
        )
        parsed = parse_bai2(text)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        negative = file_of(
            "01,S,R,240115,0800,1,,,2/",
            "02,R,B,1,240115,,USD,/",
            "03,111,USD,010,-5000,,,015,-6000,,/",
            "16,475,1000,0,R1,C1,Payment/",
            "49,-10000,3/",
            "98,-10000,1,5/",
            "99,-10000,1,7/",
        )
        parsed = parse_bai2(negative)
        self.assertEqual(parsed.control_total.declared_minor_units, -10000)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)


class RecordFoldingTests(unittest.TestCase):
    """Physical lines into logical records, and what survives the split."""

    def test_the_terminator_is_dropped_and_an_interior_slash_is_kept(self) -> None:
        # The interior slash is the consequential half.  Truncating the record
        # at the first ``/`` would silently discard the tail of a field this
        # module carries but does not interpret, and dates written ``01/15``
        # put one there routinely.
        self.assertEqual(_split_physical("16,165,5000/"), ("16", "165", "5000"))
        self.assertEqual(
            _split_physical("16,165,5000,0,R,C,01/15 pmt/"),
            ("16", "165", "5000", "0", "R", "C", "01/15 pmt"),
        )

    def test_fields_are_returned_unstripped(self) -> None:
        # Not cosmetic.  Every structured reader strips what it reads, so the
        # padding costs nothing there; but tail_text rejoins fields with the
        # commas that split them, and stripping first would hand back narrative
        # the sender did not write.
        self.assertEqual(_split_physical("03, 111 , USD /"), ("03", " 111 ", " USD "))

    def test_trailing_whitespace_is_padding_and_is_removed(self) -> None:
        self.assertEqual(_split_physical("16,165,5000/    "), ("16", "165", "5000"))
        self.assertEqual(_split_physical("16,165,5000    "), ("16", "165", "5000"))

    def test_a_continuation_extends_the_record_before_it(self) -> None:
        records = _fold_records("03,111,USD,010,1000,,/\n88,015,2000,,/\n")
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.code, "03")
        self.assertEqual(record.physical_record_count, 2)
        self.assertEqual(record.line_numbers, (1, 2))
        # The empty fields are real: a trailing comma before the terminator is
        # an empty field the sender wrote, and the quad reader depends on them
        # being there to keep its stride.
        self.assertEqual(
            record.fields,
            ("03", "111", "USD", "010", "1000", "", "", "015", "2000", "", ""),
        )

    def test_blank_lines_are_skipped_but_still_numbered(self) -> None:
        # The line number is what an error message sends a reader to, so it has
        # to be the number in the file rather than the number among the records
        # this parser kept.
        records = _fold_records("01,S,R/\n\n02,R,B/\n")
        self.assertEqual([record.first_line for record in records], [1, 3])

    def test_a_continuation_with_nothing_to_continue_is_refused(self) -> None:
        with self.assertRaises(Bai2MalformedFileError) as caught:
            _fold_records("88,orphaned/\n")
        self.assertIn("continuation", str(caught.exception))

    def test_a_record_that_does_not_open_with_two_digits_is_refused(self) -> None:
        with self.assertRaises(Bai2MalformedFileError):
            _fold_records("1,S,R/\n")
        with self.assertRaises(Bai2MalformedFileError):
            _fold_records("ab,S,R/\n")

    def test_segments_are_kept_apart_so_a_line_break_survives(self) -> None:
        records = _fold_records("16,165,1,0,R,C,first/\n88,second/\n")
        self.assertEqual(len(records[0].segments), 2)
        self.assertEqual(records[0].tail_text(6), "first\nsecond")


class LexicalHelperTests(unittest.TestCase):
    """The small readers, tested where a wrong answer would be invisible."""

    def test_an_amount_is_an_integer_count_of_minor_units(self) -> None:
        self.assertEqual(
            _parse_amount("5000", "USD", context="c"),
            Money.from_minor_units(5000, "USD"),
        )
        self.assertEqual(
            _parse_amount("-5000", "USD", context="c"),
            Money.from_minor_units(-5000, "USD"),
        )
        self.assertEqual(
            _parse_amount("  5000  ", "USD", context="c"),
            Money.from_minor_units(5000, "USD"),
        )

    def test_an_amount_with_a_decimal_point_is_refused(self) -> None:
        # A BAI2 amount never carries one, so text that does is not a BAI2
        # amount written oddly — it is a figure from somewhere else, and
        # reading "50.00" as 5000 minor units would be right by coincidence and
        # wrong for "50.5".
        with self.assertRaises(Bai2AmountError):
            _parse_amount("50.00", "USD", context="c")

    def test_an_underscore_separator_is_refused_because_int_accepts_it(self) -> None:
        # The whole reason the regex runs before int does.  int("1_000") is a
        # thousand, from a file that said no such thing.
        with self.assertRaises(Bai2AmountError):
            _parse_amount("1_000", "USD", context="c")

    def test_an_empty_amount_is_a_missing_field_not_a_zero(self) -> None:
        with self.assertRaises(Bai2MissingFieldError):
            _parse_amount("", "USD", context="c")

    def test_a_count_is_non_negative_and_a_negative_one_is_refused(self) -> None:
        self.assertEqual(_parse_count("0", context="c"), 0)
        self.assertEqual(_parse_count(" 12 ", context="c"), 12)
        with self.assertRaises(Bai2MalformedFileError):
            _parse_count("-1", context="c")
        with self.assertRaises(Bai2MissingFieldError):
            _parse_count("", context="c")

    def test_a_control_total_may_be_negative_and_carries_no_currency(self) -> None:
        self.assertEqual(_parse_minor_units("-10000", context="c"), -10000)
        self.assertEqual(_parse_minor_units("+250", context="c"), 250)
        with self.assertRaises(Bai2AmountError):
            _parse_minor_units("abc", context="c")
        with self.assertRaises(Bai2MissingFieldError):
            _parse_minor_units("  ", context="c")

    def test_the_direction_ranges_are_the_specifications(self) -> None:
        self.assertIs(_direction_for_type_code("100"), TransactionDirection.credit)
        self.assertIs(_direction_for_type_code("399"), TransactionDirection.credit)
        self.assertIs(_direction_for_type_code("400"), TransactionDirection.debit)
        self.assertIs(_direction_for_type_code("699"), TransactionDirection.debit)

    def test_a_code_outside_the_ranges_fixes_no_direction(self) -> None:
        # 700 and above is loan, unassigned or customer-defined: a convention
        # between two institutions this parser has no access to.  None, not a
        # guess, because a guess puts a real amount on the wrong side.
        self.assertIsNone(_direction_for_type_code("700"))
        self.assertIsNone(_direction_for_type_code("890"))
        self.assertIsNone(_direction_for_type_code("010"))
        self.assertIsNone(_direction_for_type_code("16"))
        self.assertIsNone(_direction_for_type_code("abc"))

    def test_the_weakest_status_governs(self) -> None:
        self.assertIs(
            _weakest([ReconciliationStatus.balanced, ReconciliationStatus.balanced]),
            ReconciliationStatus.balanced,
        )
        self.assertIs(
            _weakest([ReconciliationStatus.balanced, ReconciliationStatus.unavailable]),
            ReconciliationStatus.unavailable,
        )
        self.assertIs(
            _weakest(
                [ReconciliationStatus.unavailable, ReconciliationStatus.unbalanced]
            ),
            ReconciliationStatus.unbalanced,
        )
        self.assertIs(
            _weakest(
                [ReconciliationStatus.balanced, ReconciliationStatus.not_attempted]
            ),
            ReconciliationStatus.not_attempted,
        )

    def test_no_checks_at_all_is_not_attempted_rather_than_balanced(self) -> None:
        # An empty run has not passed anything.  Returning balanced would let a
        # file with no checks in it present as a file whose checks all passed.
        self.assertIs(_weakest([]), ReconciliationStatus.not_attempted)

    def test_a_shared_currency_is_named_and_a_mixed_one_is_not(self) -> None:
        self.assertEqual(_common_currency(["USD", "USD"]), "USD")
        self.assertIsNone(_common_currency(["USD", "EUR"]))
        self.assertIsNone(_common_currency([]))

    def test_the_checksum_sum_skips_absent_amounts_and_keeps_the_sign(self) -> None:
        self.assertEqual(
            _sum_minor_units(
                [
                    Money.from_minor_units(100, "USD"),
                    None,
                    Money.from_minor_units(-50, "USD"),
                ]
            ),
            50,
        )
        self.assertEqual(_sum_minor_units([]), 0)
        self.assertEqual(_sum_minor_units([None, None]), 0)


class FundsTypeTests(unittest.TestCase):
    """The field-misalignment hazard, tested type by type.

    A funds type read as one field when it announces four shifts every field
    after it.  The record still parses, the file still balances, and the bank
    reference now holds an availability amount.  Nothing downstream can detect
    that, which is why each type gets its own test.
    """

    def test_a_plain_funds_type_announces_nothing(self) -> None:
        self.assertEqual(
            _consume_funds_type(("16", "165", "5000", "0", "REF"), 3, context="c"),
            ("0", 4),
        )

    def test_an_empty_funds_type_is_absent_rather_than_unrecognised(self) -> None:
        self.assertEqual(
            _consume_funds_type(("16", "165", "5000", "", "REF"), 3, context="c"),
            (None, 4),
        )

    def test_type_s_announces_three_availability_amounts(self) -> None:
        fields = ("16", "165", "5000", "S", "100", "200", "300", "REF", "CUST", "txt")
        self.assertEqual(_consume_funds_type(fields, 3, context="c"), ("S", 7))
        self.assertEqual(fields[7], "REF")

    def test_type_v_announces_a_value_date_and_time(self) -> None:
        fields = ("16", "165", "5000", "V", "240115", "0800", "REF")
        self.assertEqual(_consume_funds_type(fields, 3, context="c"), ("V", 6))
        self.assertEqual(fields[6], "REF")

    def test_type_d_announces_a_count_and_that_many_pairs(self) -> None:
        fields = ("16", "165", "5000", "D", "2", "0", "1000", "1", "4000", "REF")
        self.assertEqual(_consume_funds_type(fields, 3, context="c"), ("D", 9))
        self.assertEqual(fields[9], "REF")

    def test_an_unrecognised_funds_type_is_refused_not_assumed_empty(self) -> None:
        # Assuming it announces nothing is the failure mode this whole function
        # exists to prevent, and it is silent.
        with self.assertRaises(Bai2MalformedFileError) as caught:
            _consume_funds_type(("16", "165", "5000", "X", "REF"), 3, context="c")
        self.assertIn("shifts every field", str(caught.exception))

    def test_a_funds_type_whose_sub_fields_run_off_the_end_is_refused(self) -> None:
        with self.assertRaises(Bai2MalformedFileError):
            _consume_funds_type(("16", "165", "5000", "S", "100"), 3, context="c")
        with self.assertRaises(Bai2MalformedFileError):
            _consume_funds_type(("16", "165", "5000", "D"), 3, context="c")
        with self.assertRaises(Bai2MalformedFileError):
            _consume_funds_type(
                ("16", "165", "5000", "D", "3", "0", "100"), 3, context="c"
            )

    def test_a_record_ending_at_the_funds_type_reports_no_type(self) -> None:
        self.assertEqual(
            _consume_funds_type(("16", "165", "5000"), 3, context="c"), (None, 3)
        )

    def test_the_fields_after_a_wide_funds_type_stay_aligned_end_to_end(self) -> None:
        # The same hazard through the real parser rather than the helper.
        text = file_of(
            "01,S,R,240115,0800,1,,,2/",
            "02,R,B,1,240115,,USD,/",
            "03,111,USD,010,10000,,,015,10000,,/",
            "16,165,1000,S,100,200,700,BANKREF,CUSTREF,Narrative here/",
            "16,475,1000,D,2,0,600,1,400,BREF2,CREF2,Second/",
            "49,22000,4/",
            "98,22000,1,6/",
            "99,22000,1,8/",
        )
        first, second = parse_bai2(text).transactions
        self.assertEqual(first.funds_type, "S")
        self.assertEqual(first.bank_reference, "BANKREF")
        self.assertEqual(first.customer_reference, "CUSTREF")
        self.assertEqual(first.text, "Narrative here")
        self.assertEqual(second.funds_type, "D")
        self.assertEqual(second.bank_reference, "BREF2")
        self.assertEqual(second.customer_reference, "CREF2")
        self.assertEqual(second.text, "Second")


class FileStructureRefusalTests(unittest.TestCase):
    """What the parser declines to read at all.

    Every one of these is a case where producing *something* would be worse
    than producing nothing, because what it produced would look like a parsed
    file.
    """

    def test_an_empty_file_is_not_a_bai2_file(self) -> None:
        for empty in ("", "   ", "\n\n"):
            with self.subTest(empty=empty):
                with self.assertRaises(NotABai2Error):
                    parse_bai2(empty)

    def test_a_file_that_does_not_open_with_an_01_is_refused(self) -> None:
        with self.assertRaises(NotABai2Error) as caught:
            parse_bai2(file_of("02,R,B,1,240115,,USD,/", "99,0,0,2/"))
        self.assertIn("01", str(caught.exception))

    def test_a_file_never_closed_by_a_99_is_refused(self) -> None:
        # The specific danger of a truncated transfer: the records that arrived
        # are individually well-formed, and the total that would have caught
        # the loss is the one that did not arrive.
        text = file_of(
            "01,S,R,240115,0800,1,,,2/",
            "02,R,B,1,240115,,USD,/",
            "03,111,USD,010,10000,,,015,10000,,/",
            "16,165,1000,0,R1,C1,In/",
            "16,475,1000,0,R2,C2,Out/",
            "49,22000,4/",
            "98,22000,1,6/",
        )
        with self.assertRaises(Bai2MalformedFileError) as caught:
            parse_bai2(text)
        self.assertIn("truncated", str(caught.exception))

    def test_a_record_after_the_99_is_refused(self) -> None:
        # It sits outside every control total, so it would enter the ledger
        # uncounted by anything.
        text = build() + "16,165,9999,0,R9,C9,Appended/\n"
        with self.assertRaises(Bai2MalformedFileError) as caught:
            parse_bai2(text)
        self.assertIn("uncounted", str(caught.exception))

    def test_an_account_not_closed_by_a_49_is_refused(self) -> None:
        # The refusal has to name the account, not merely happen.  A parser
        # that accepted the 98 as though it were the 49 would still fail
        # somewhere further down — the group would then find a 99 where its
        # own 98 should be — and the reader would be sent to the group
        # trailer to look for a fault that is four lines above it.
        text = file_of(
            "01,S,R,240115,0800,1,,,2/",
            "02,R,B,1,240115,,USD,/",
            "03,111,USD,010,10000,,,015,10000,,/",
            "16,165,1000,0,R1,C1,In/",
            "98,22000,1,6/",
            "99,22000,1,8/",
        )
        with self.assertRaises(Bai2MalformedFileError) as caught:
            parse_bai2(text)
        message = str(caught.exception)
        self.assertIn("49", message)
        self.assertIn("account", message)
        # The line the account was opened at, and the code actually found.
        self.assertIn("line 3", message)
        self.assertIn("'98'", message)

    def test_a_second_03_where_the_49_should_be_is_refused(self) -> None:
        # A group whose first account is never closed and whose second opens
        # anyway.  This is the shape a dropped 49 leaves behind, and it is the
        # dangerous one: the record sitting in the trailer's place has fields
        # where the trailer's total and count would be, so a parser that did
        # not check the code would read an account number as a total and a
        # currency as a record count and report the fault as a bad count.
        text = file_of(
            "01,S,R,240115,0800,1,,,2/",
            "02,R,B,1,240115,,USD,/",
            "03,111,USD,010,10000,,,015,13000,,/",
            "16,165,3000,0,REF1,CUST1,Text/",
            "03,222,USD,010,1000,,/",
            "49,26000,3/",
            "98,26000,1,5/",
            "99,26000,1,7/",
        )
        with self.assertRaises(Bai2MalformedFileError) as caught:
            parse_bai2(text)
        message = str(caught.exception)
        self.assertIn("49", message)
        self.assertIn("'03'", message)
        # Not a complaint about the count field, which is what reading the
        # 03 as a trailer would produce.
        self.assertNotIn("is not a count", message)

    def test_a_group_not_closed_by_a_98_is_refused(self) -> None:
        # As with the 49 above, the refusal has to name the group.  The 99
        # sitting in the 98's place carries a total, a count and a record
        # count in the same positions, so a parser that did not check the
        # code would accept it as the group trailer, find no 99 afterwards,
        # and report a truncated file.
        text = file_of(
            "01,S,R,240115,0800,1,,,2/",
            "02,R,B,1,240115,,USD,/",
            "03,111,USD,010,10000,,,015,10000,,/",
            "16,165,1000,0,R1,C1,In/",
            "16,475,1000,0,R2,C2,Out/",
            "49,22000,4/",
            "99,22000,1,8/",
        )
        with self.assertRaises(Bai2MalformedFileError) as caught:
            parse_bai2(text)
        message = str(caught.exception)
        self.assertIn("98", message)
        self.assertIn("group", message)
        self.assertIn("line 2", message)
        self.assertIn("'99'", message)

    def test_whatever_stands_where_the_98_should_be_is_named(self) -> None:
        # Three record codes, three different faults, one branch.  The 02 is a
        # group opened before the last was closed; the 16 is a detail record
        # belonging to no account at all, which would otherwise enter the
        # ledger attached to nothing.
        for intruder in ("02,R,B2,1,240115,,USD,/", "16,165,999,0,R9,C9,Orphan/"):
            with self.subTest(intruder=intruder):
                text = file_of(
                    "01,S,R,240115,0800,1,,,2/",
                    "02,R,B,1,240115,,USD,/",
                    "03,111,USD,010,10000,,,015,13000,,/",
                    "16,165,3000,0,REF1,CUST1,Text/",
                    "49,26000,3/",
                    intruder,
                    "98,26000,1,5/",
                    "99,26000,1,7/",
                )
                with self.assertRaises(Bai2MalformedFileError) as caught:
                    parse_bai2(text)
                message = str(caught.exception)
                self.assertIn("98", message)
                self.assertIn(f"'{intruder[:2]}'", message)
                self.assertIn("line 6", message)

    def test_a_stated_version_other_than_2_is_refused(self) -> None:
        # A different version is a different record layout, and this parser
        # would read it cleanly into the wrong fields.
        with self.assertRaises(Bai2MalformedFileError) as caught:
            parse_bai2(build(version="1"))
        self.assertIn("record layout", str(caught.exception))

    def test_an_absent_version_is_recorded_rather_than_refused(self) -> None:
        # The asymmetry.  Silence asserts nothing, and the layout this parser
        # assumes is confirmed three times over by the control totals.
        parsed = parse_bai2(build(version=""))
        self.assertIsNone(parsed.version)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)

    def test_bytes_that_are_not_utf_8_are_refused_rather_than_salvaged(self) -> None:
        # A latin-1 fallback succeeds on every input, so it would turn a payee
        # name into mojibake nothing downstream could tell from a real name.
        with self.assertRaises(Bai2MalformedFileError) as caught:
            parse_bai2(build().encode("utf-8").replace(b"SENDER", b"SEND\xffR"))
        self.assertIn("UTF-8", str(caught.exception))

    def test_a_file_over_the_ceiling_is_refused_before_it_is_decoded(self) -> None:
        self.assertEqual(BAI2_MAX_FILE_BYTES, 67108864)
        with self.assertRaises(Bai2MalformedFileError) as caught:
            parse_bai2(bytes(BAI2_MAX_FILE_BYTES + 1))
        self.assertIn("ceiling", str(caught.exception))

    def test_something_that_is_neither_bytes_nor_text_is_refused(self) -> None:
        for wrong in (12345, None, ["01,S,R/"]):
            with self.subTest(wrong=wrong):
                with self.assertRaises(Bai2MalformedFileError):
                    parse_bai2(wrong)  # type: ignore[arg-type]

    def test_a_bytearray_is_read_like_bytes(self) -> None:
        self.assertEqual(
            parse_bai2(bytearray(build().encode("utf-8"))), parse_bai2(build())
        )

    def test_every_refusal_is_a_bai2_error(self) -> None:
        # So a caller that wants to catch "this file could not be read" can do
        # it with one except clause and not miss a case.
        for constructor in (
            lambda: parse_bai2(""),
            lambda: parse_bai2(build(version="1")),
            lambda: parse_bai2(build(account_currency="", currency="")),
        ):
            with self.assertRaises(Bai2Error):
                constructor()


class CurrencyResolutionTests(unittest.TestCase):
    """Where the scale of every figure in an account comes from.

    A BAI2 amount is an integer count of minor units, so a wrong currency does
    not produce a slightly wrong figure — it produces one wrong by a factor of
    a hundred, uniformly, with every check still passing.
    """

    def test_the_account_currency_wins_and_is_recorded_as_the_source(self) -> None:
        account = parse_bai2(build()).accounts[0]
        self.assertEqual(account.currency, "USD")
        self.assertEqual(account.currency_source, "account")

    def test_the_group_currency_is_used_where_the_account_states_none(self) -> None:
        account = parse_bai2(build(account_currency="")).accounts[0]
        self.assertEqual(account.currency, "USD")
        self.assertEqual(account.currency_source, "group")

    def test_the_caller_default_is_used_only_where_the_file_states_nothing(self) -> None:
        parsed = parse_bai2(
            build(account_currency="", currency=""), default_currency="GBP"
        )
        account = parsed.accounts[0]
        self.assertEqual(account.currency, "GBP")
        self.assertEqual(account.currency_source, "caller")
        # And the source is recorded because the three are not equally strong
        # evidence: the bank said so, or the caller did.
        self.assertNotEqual(account.currency_source, "account")

    def test_no_currency_anywhere_is_refused_rather_than_assumed(self) -> None:
        with self.assertRaises(Bai2CurrencyError) as caught:
            parse_bai2(build(account_currency="", currency=""))
        self.assertIn("minor units", str(caught.exception))

    def test_a_currency_that_is_not_a_currency_is_refused(self) -> None:
        with self.assertRaises(Bai2CurrencyError):
            parse_bai2(build(account_currency="ZZZ"))

    def test_a_lowercase_currency_is_normalised_rather_than_refused(self) -> None:
        self.assertEqual(parse_bai2(build(account_currency="usd")).accounts[0].currency, "USD")

    def test_an_account_may_state_a_currency_its_group_does_not(self) -> None:
        # Not a defect.  The 02 currency is a default for the accounts beneath
        # it, not a constraint on them, and a corporate group holding accounts
        # in several currencies is an ordinary shape.
        parsed = parse_bai2(build(currency="EUR", account_currency="USD"))
        self.assertEqual(parsed.groups[0].currency, "EUR")
        self.assertEqual(parsed.accounts[0].currency, "USD")
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)


def _account_file(
    account: str, *details: str, total: str, records: str, status: str = "1"
) -> str:
    """A one-account, one-group file around a hand-written ``03`` and its ``16``s.

    The three trailers are derived from ``total`` and ``records`` rather than
    passed separately, because a test about the balance identity that also has
    to get three trailers right is a test that fails for the wrong reason.

    ``status`` is the ``02`` group status, defaulting to ``1`` (update) so that
    every caller not interested in admissibility gets a group that auto-admits.
    """
    account_records = int(records)
    return file_of(
        "01,S,R,240115,0800,1,,,2/",
        f"02,R,B,{status},240115,,USD,/",
        account,
        *details,
        f"49,{total},{account_records}/",
        f"98,{total},1,{account_records + 2}/",
        f"99,{total},1,{account_records + 4}/",
    )


_IN = "16,165,3000,0,R1,C1,In/"
_OUT = "16,475,1000,0,R2,C2,Out/"


class BalanceIdentityTests(unittest.TestCase):
    """``010 + ΣCredits − ΣDebits = 015``, and the four things that stop it.

    Each stop is ``unavailable`` and not ``unbalanced``, because in none of them
    has any arithmetic disagreed.  Reporting them as failures would send a
    reviewer hunting for a discrepancy in a file that has none.
    """

    def test_the_identity_closes_on_a_conformant_account(self) -> None:
        # 10000 + 3000 - 1000 = 12000, which is what the 015 states.
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,/", _IN, _OUT,
                total="26000", records="4",
            )
        )
        identity = parsed.accounts[0].balance_identity
        self.assertIs(identity.status, ReconciliationStatus.balanced)
        self.assertEqual(identity.opening, Money.from_minor_units(10000, "USD"))
        self.assertEqual(identity.printed_closing, Money.from_minor_units(12000, "USD"))
        self.assertEqual(identity.computed_closing, Money.from_minor_units(12000, "USD"))
        self.assertEqual(identity.credits, Money.from_minor_units(3000, "USD"))
        self.assertEqual(identity.debits, Money.from_minor_units(1000, "USD"))
        self.assertEqual(identity.credit_count, 1)
        self.assertEqual(identity.debit_count, 1)
        self.assertEqual(identity.undirected_count, 0)
        self.assertTrue(identity.delta.is_zero)

    def test_a_closing_balance_the_transactions_do_not_reach_is_unbalanced(self) -> None:
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12500,,/", _IN, _OUT,
                total="26500", records="4",
            )
        )
        account = parsed.accounts[0]
        identity = account.balance_identity
        self.assertIs(identity.status, ReconciliationStatus.unbalanced)
        self.assertEqual(identity.delta, Money.from_minor_units(-500, "USD"))
        # The control total is untouched: the amounts arrived as sent, they
        # simply do not account for the movement the balances describe.  Two
        # checks, two different things established.
        self.assertIs(account.control_total.status, ReconciliationStatus.balanced)
        self.assertIs(account.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_no_opening_balance_declines_rather_than_substituting_zero(self) -> None:
        # Substituting zero manufactures a delta equal to the real opening
        # balance, which reads as a large unexplained discrepancy.
        parsed = parse_bai2(
            _account_file("03,111,USD,015,12000,,/", _IN, _OUT, total="16000", records="4")
        )
        identity = parsed.accounts[0].balance_identity
        self.assertIs(identity.status, ReconciliationStatus.unavailable)
        self.assertIsNone(identity.opening)
        self.assertIsNone(identity.delta)
        self.assertIn("opening", identity.unavailable_reason)

    def test_no_closing_balance_declines_for_the_same_reason(self) -> None:
        parsed = parse_bai2(
            _account_file("03,111,USD,010,10000,,/", _IN, _OUT, total="14000", records="4")
        )
        identity = parsed.accounts[0].balance_identity
        self.assertIs(identity.status, ReconciliationStatus.unavailable)
        self.assertIsNone(identity.printed_closing)
        self.assertIn("closing", identity.unavailable_reason)

    def test_a_transaction_with_no_fixed_direction_stops_the_sum(self) -> None:
        # 890 is customer-defined.  Assigning it a side would put a real amount
        # on a guess, and the identity would then close or fail on that guess.
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,/",
                _IN, _OUT, "16,890,500,0,R3,C3,Local convention/",
                total="26500", records="5",
            )
        )
        identity = parsed.accounts[0].balance_identity
        self.assertIs(identity.status, ReconciliationStatus.unavailable)
        self.assertEqual(identity.undirected_count, 1)
        self.assertIn("neither credit nor debit", identity.unavailable_reason)

    def test_a_zero_amount_with_no_direction_does_not_stop_the_sum(self) -> None:
        # It contributes nothing to either side, so not knowing which side it
        # belongs on costs nothing.  Counting it would decline an identity that
        # is in fact complete.
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,/",
                _IN, _OUT, "16,890,0,0,R3,C3,Zero value/",
                total="26000", records="5",
            )
        )
        identity = parsed.accounts[0].balance_identity
        self.assertIs(identity.status, ReconciliationStatus.balanced)
        self.assertEqual(identity.undirected_count, 0)

    def test_a_summary_only_account_declines_rather_than_failing(self) -> None:
        # It has not failed a check.  It has declined to itemise, which is an
        # ordinary thing for a BAI2 file to do.
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,,100,3000,1,,400,1000,1,/",
                total="26000", records="2",
            )
        )
        account = parsed.accounts[0]
        self.assertIs(account.balance_identity.status, ReconciliationStatus.unavailable)
        self.assertIn("itemised", account.balance_identity.unavailable_reason)
        # And the mandatory check still governs: the 49 balanced, and an
        # optional check that declined does not weaken it.
        self.assertIs(account.control_total.status, ReconciliationStatus.balanced)
        self.assertIs(account.reconciliation_status, ReconciliationStatus.balanced)


class SummaryIdentityTests(unittest.TestCase):
    """The ``03`` record's own ``100``/``400`` declarations against its ``16`` records."""

    def test_declaring_nothing_is_not_attempted_rather_than_balanced(self) -> None:
        # Nothing was claimed, so nothing is contradicted — but nothing is
        # corroborated either, and the two must not read alike.
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,/", _IN, _OUT,
                total="26000", records="4",
            )
        )
        identity = parsed.accounts[0].summary_identity
        self.assertIs(identity.status, ReconciliationStatus.not_attempted)
        self.assertIsNone(identity.declared_credits)
        self.assertIsNone(identity.credit_delta)

    def test_declarations_that_match_the_details_balance(self) -> None:
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,,100,3000,1,,400,1000,1,/",
                _IN, _OUT, total="30000", records="4",
            )
        )
        identity = parsed.accounts[0].summary_identity
        self.assertIs(identity.status, ReconciliationStatus.balanced)
        self.assertEqual(identity.declared_credits, Money.from_minor_units(3000, "USD"))
        self.assertEqual(identity.observed_credits, Money.from_minor_units(3000, "USD"))
        self.assertTrue(identity.credit_delta.is_zero)
        self.assertTrue(identity.debit_delta.is_zero)

    def test_a_declared_total_the_details_do_not_reach_is_unbalanced(self) -> None:
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,,100,3500,1,,400,1000,1,/",
                _IN, _OUT, total="30500", records="4",
            )
        )
        account = parsed.accounts[0]
        self.assertIs(account.summary_identity.status, ReconciliationStatus.unbalanced)
        self.assertEqual(
            account.summary_identity.credit_delta, Money.from_minor_units(-500, "USD")
        )
        self.assertIs(account.reconciliation_status, ReconciliationStatus.unbalanced)

    def test_a_declared_item_count_is_checked_even_when_the_amount_agrees(self) -> None:
        # The same reasoning as the record count on a trailer.  A missing
        # zero-value entry moves no money and no sum will notice it.
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,,100,3000,2,,400,1000,1,/",
                _IN, _OUT, total="30000", records="4",
            )
        )
        identity = parsed.accounts[0].summary_identity
        self.assertIs(identity.status, ReconciliationStatus.unbalanced)
        self.assertTrue(identity.credit_delta.is_zero)
        self.assertEqual(identity.declared_credit_count, 2)
        self.assertEqual(identity.observed_credit_count, 1)

    def test_declarations_with_no_details_to_check_them_are_unavailable(self) -> None:
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,,100,3000,1,,400,1000,1,/",
                total="26000", records="2",
            )
        )
        identity = parsed.accounts[0].summary_identity
        self.assertIs(identity.status, ReconciliationStatus.unavailable)
        self.assertIn("no 16 transaction detail records", identity.unavailable_reason)

    def test_only_one_side_declared_is_checked_on_that_side_alone(self) -> None:
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,,100,3000,1,/",
                _IN, _OUT, total="29000", records="4",
            )
        )
        identity = parsed.accounts[0].summary_identity
        self.assertIs(identity.status, ReconciliationStatus.balanced)
        self.assertIsNone(identity.declared_debits)
        self.assertIsNone(identity.debit_delta)
        self.assertEqual(identity.observed_debits, Money.from_minor_units(1000, "USD"))


class AdmissibilityTests(unittest.TestCase):
    """Group status, and the one promotion this module withholds by hand.

    The reservation is deliberately kept out of the arithmetic.  A test group's
    totals are generated to be flawless, so folding the reservation into
    ``reconciliation_status`` would report a discrepancy that does not exist and
    send a reviewer hunting through a file that adds up perfectly.  The file
    adds up; it is simply not about money that moved.  So the status stays
    ``balanced`` and the class drops instead.
    """

    def _with_status(self, status: str) -> str:
        return _account_file(
            "03,111,USD,010,10000,,,015,12000,,/",
            _IN,
            _OUT,
            total="26000",
            records="4",
            status=status,
        )

    def test_an_update_group_auto_admits(self) -> None:
        parsed = parse_bai2(self._with_status("1"))
        self.assertEqual(parsed.admissibility_reservations, ())
        self.assertIs(parsed.proof_class, ProofClass.p0)

    def test_a_correction_group_auto_admits_too(self) -> None:
        # A correction does assert what moved.  That it supersedes an earlier
        # file is a question for intake and de-duplication, not a reason to
        # distrust this one.
        parsed = parse_bai2(self._with_status("3"))
        self.assertEqual(parsed.admissibility_reservations, ())
        self.assertIs(parsed.proof_class, ProofClass.p0)

    def test_a_test_group_balances_and_still_does_not_reach_p0(self) -> None:
        parsed = parse_bai2(self._with_status("4"))
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)
        self.assertEqual(len(parsed.admissibility_reservations), 1)
        reason = parsed.admissibility_reservations[0]
        self.assertIn("status 4 (test)", reason)
        self.assertIn("asserts nothing about money that moved", reason)

    def test_a_deletion_group_is_reserved_the_same_way(self) -> None:
        parsed = parse_bai2(self._with_status("2"))
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)
        reason = parsed.admissibility_reservations[0]
        self.assertIn("status 2 (deletion)", reason)
        self.assertIn("withdraws data sent earlier", reason)

    def test_an_unrecognised_status_is_reserved_rather_than_ignored(self) -> None:
        # The safe direction is not symmetric.  A status this parser does not
        # know might mean anything, and the one reading that must not be
        # assumed is the one that auto-admits.
        parsed = parse_bai2(self._with_status("9"))
        self.assertIs(parsed.proof_class, ProofClass.p3)
        reason = parsed.admissibility_reservations[0]
        self.assertIn("'9'", reason)
        self.assertIn("not a BAI2 group status this parser recognises", reason)

    def test_an_absent_status_draws_no_reservation(self) -> None:
        # Absence is not a claim.  The field is optional, and refusing a file
        # for not stating something it need not state would quarantine ordinary
        # traffic.
        parsed = parse_bai2(self._with_status(""))
        self.assertIsNone(parsed.groups[0].status)
        self.assertEqual(parsed.admissibility_reservations, ())
        self.assertIs(parsed.proof_class, ProofClass.p0)

    def test_the_reservation_names_the_line_it_came_from(self) -> None:
        parsed = parse_bai2(self._with_status("4"))
        self.assertIn("line 2", parsed.admissibility_reservations[0])

    def test_the_reservation_is_visible_on_the_group_as_well_as_the_file(self) -> None:
        parsed = parse_bai2(self._with_status("4"))
        self.assertEqual(
            parsed.groups[0].admissibility_reservations,
            parsed.admissibility_reservations,
        )

    def test_a_reservation_cannot_promote_a_file_that_already_failed(self) -> None:
        # The withholding only ever moves p0 down.  A file whose arithmetic
        # failed is p3 on its own account, and stays p3.
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,/",
                _IN,
                _OUT,
                total="99999",
                records="4",
                status="4",
            )
        )
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)


class ProofClassTests(unittest.TestCase):
    """That the class is computed from shape and outcome, and not asserted here."""

    def test_the_shape_is_native_with_control_totals(self) -> None:
        parsed = parse_bai2(build())
        self.assertIs(parsed.source_shape, SourceShape.native_with_control_totals)

    def test_a_file_whose_arithmetic_closes_is_p0(self) -> None:
        parsed = parse_bai2(build())
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(parsed.proof_class, ProofClass.p0)

    def test_a_file_whose_arithmetic_fails_is_p3_not_p1(self) -> None:
        # The demotion rule in assign_proof_class: a document that fails the
        # check its own format guarantees is the strongest available signal
        # that something is wrong with it, whatever the format affords.
        parsed = parse_bai2(build(file_total="99999"))
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_the_class_agrees_with_assign_proof_class_on_the_same_inputs(self) -> None:
        # This module supplies two inputs and has no vote on what they add up
        # to.  Where there is no reservation, the answer must be exactly the
        # one the shared function gives.
        for source in (build(), build(file_total="99999")):
            parsed = parse_bai2(source)
            self.assertEqual(parsed.admissibility_reservations, ())
            self.assertIs(
                parsed.proof_class,
                assign_proof_class(parsed.source_shape, parsed.reconciliation_status),
            )

    def test_a_reserved_file_departs_from_assign_proof_class_downward_only(self) -> None:
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,12000,,/",
                _IN,
                _OUT,
                total="26000",
                records="4",
                status="4",
            )
        )
        earned = assign_proof_class(parsed.source_shape, parsed.reconciliation_status)
        self.assertIs(earned, ProofClass.p0)
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_the_shape_cannot_be_set_by_a_caller(self) -> None:
        parsed = parse_bai2(build())
        with self.assertRaises(AttributeError):
            parsed.source_shape = SourceShape.unstructured_narrative  # type: ignore[misc]


class NarrativeFidelityTests(unittest.TestCase):
    """The free-text field comes back exactly as the sender wrote it.

    Narrative is carried and not read, the same treatment MT940's ``:86:``
    gets and for the same reason.  But carrying it means carrying it verbatim: a
    string that may end up quoted in an exhibit must not have been quietly
    edited on the way through.
    """

    def _text(self, detail: str) -> Optional[str]:
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,13000,,/",
                detail,
                total="26000",
                records="3",
            )
        )
        return parsed.transactions[0].text

    def test_a_comma_in_the_narrative_survives_with_its_spacing(self) -> None:
        # The field split broke this apart on the comma; rejoining restores it
        # only because _split_physical does not strip.  "PAID,THEN REVERSED"
        # would be a quiet edit.
        self.assertEqual(
            self._text("16,165,3000,0,REF1,CUST1,PAID, THEN REVERSED/"),
            "PAID, THEN REVERSED",
        )

    def test_an_interior_slash_is_not_treated_as_a_terminator(self) -> None:
        # Dates written 01/15, reference fragments, account numbers.  Cutting
        # the record at the first slash would discard the remainder silently.
        self.assertEqual(
            self._text("16,165,3000,0,REF1,CUST1,INV 01/15 PARTIAL/"),
            "INV 01/15 PARTIAL",
        )

    def test_a_continuation_keeps_the_line_break_the_sender_chose(self) -> None:
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,13000,,/",
                "16,165,3000,0,REF1,CUST1,FIRST LINE/",
                "88,SECOND LINE/",
                total="26000",
                records="4",
            )
        )
        self.assertEqual(len(parsed.transactions), 1)
        self.assertEqual(parsed.transactions[0].text, "FIRST LINE\nSECOND LINE")

    def test_an_empty_narrative_field_is_none_rather_than_empty_string(self) -> None:
        self.assertIsNone(self._text("16,165,3000,0,REF1,CUST1,/"))

    def test_an_absent_narrative_field_is_none_too(self) -> None:
        # Nothing distinguishes "wrote nothing" from "wrote an empty field",
        # and inventing a distinction the format does not make would be a claim
        # about the sender rather than a reading of the file.
        self.assertIsNone(self._text("16,165,3000,0,REF1,CUST1/"))

    def test_trailing_padding_is_stripped_but_interior_spacing_is_not(self) -> None:
        # The outer edges are padding to the record length rather than content.
        self.assertEqual(
            self._text("16,165,3000,0,REF1,CUST1,WIRE  IN   FULL   /"),
            "WIRE  IN   FULL",
        )

    def test_the_references_are_carried_verbatim_as_well(self) -> None:
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,13000,,/",
                "16,165,3000,0,BNK-REF/001,CUS REF 2,Memo/",
                total="26000",
                records="3",
            )
        )
        txn = parsed.transactions[0]
        self.assertEqual(txn.bank_reference, "BNK-REF/001")
        self.assertEqual(txn.customer_reference, "CUS REF 2")


class RollUpTests(unittest.TestCase):
    """Several accounts and several groups, and what the upper totals can say.

    The comparison at every level is integral, because a BAI2 control total is
    a checksum over transmitted digits rather than a financial quantity.  The
    ``Money`` fields are populated in addition, and only where every
    contributing amount shares one currency.  Modelling it the other way round
    would leave a multi-currency file uncheckable at the top two levels and
    keep it off P0 for nothing the file is answerable for.
    """

    #: Two accounts in one group, in two currencies.
    #:
    #:   USD account   010 10000 + 015 12000            = 22000
    #:                 16s 3000 + 1000                  =  4000
    #:                 49  26000, records 03+16+16+49   =     4
    #:   EUR account   010  5000 + 015  7000            = 12000
    #:                 16s 2000                         =  2000
    #:                 49  14000, records 03+16+49      =     3
    #:   98            26000 + 14000 = 40000, accounts 2, records 1+4+3+1 = 9
    #:   99            40000, groups 1, records 1+9+1 = 11
    _MIXED = (
        "01,S,R,240115,0800,1,,,2/",
        "02,R,B,1,240115,,,/",
        "03,AAA,USD,010,10000,,,015,12000,,/",
        "16,165,3000,0,R1,C1,In/",
        "16,475,1000,0,R2,C2,Out/",
        "49,26000,4/",
        "03,BBB,EUR,010,5000,,,015,7000,,/",
        "16,165,2000,0,R3,C3,In/",
        "49,14000,3/",
        "98,40000,2,9/",
        "99,40000,1,11/",
    )

    def test_a_mixed_currency_group_still_reaches_p0(self) -> None:
        parsed = parse_bai2(file_of(*self._MIXED))
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(parsed.proof_class, ProofClass.p0)

    def test_the_mixed_total_is_checked_integrally_and_carries_no_money(self) -> None:
        parsed = parse_bai2(file_of(*self._MIXED))
        group_total = parsed.groups[0].control_total
        self.assertIs(group_total.status, ReconciliationStatus.balanced)
        self.assertEqual(group_total.declared_minor_units, 40000)
        self.assertEqual(group_total.computed_minor_units, 40000)
        self.assertEqual(group_total.minor_unit_delta, 0)
        # No currency the sum could honestly be denominated in, so none is
        # invented.
        self.assertIsNone(group_total.currency)
        self.assertIsNone(group_total.declared_total)
        self.assertIsNone(group_total.computed_total)
        self.assertIsNone(group_total.total_delta)

    def test_the_accounts_beneath_it_keep_their_own_currencies(self) -> None:
        parsed = parse_bai2(file_of(*self._MIXED))
        self.assertEqual([a.currency for a in parsed.accounts], ["USD", "EUR"])
        self.assertEqual(
            [a.currency_source for a in parsed.accounts], ["account", "account"]
        )
        # And each account total is money, because a BAI2 account is
        # single-currency by construction.
        self.assertEqual(
            parsed.accounts[0].control_total.declared_total,
            Money.from_minor_units(26000, "USD"),
        )
        self.assertEqual(
            parsed.accounts[1].control_total.declared_total,
            Money.from_minor_units(14000, "EUR"),
        )

    def test_a_group_with_no_stated_currency_reports_none(self) -> None:
        parsed = parse_bai2(file_of(*self._MIXED))
        self.assertIsNone(parsed.groups[0].currency)

    def test_one_currency_throughout_populates_money_at_every_level(self) -> None:
        parsed = parse_bai2(
            file_of(
                "01,S,R,240115,0800,1,,,2/",
                "02,R,B,1,240115,,USD,/",
                "03,AAA,USD,010,10000,,,015,12000,,/",
                "16,165,3000,0,R1,C1,In/",
                "16,475,1000,0,R2,C2,Out/",
                "49,26000,4/",
                "03,BBB,USD,010,5000,,,015,7000,,/",
                "16,165,2000,0,R3,C3,In/",
                "49,14000,3/",
                "98,40000,2,9/",
                "99,40000,1,11/",
            )
        )
        for total in (parsed.groups[0].control_total, parsed.control_total):
            self.assertEqual(total.currency, "USD")
            self.assertEqual(total.declared_total, Money.from_minor_units(40000, "USD"))
            self.assertEqual(total.total_delta, Money.from_minor_units(0, "USD"))
        self.assertIs(parsed.proof_class, ProofClass.p0)

    #: Two groups.  The second exists to prove the 99 sums the 98s rather than
    #: reaching past them.
    #:
    #:   group 1   49 26000/4   →  98 26000, accounts 1, records 1+4+1 = 6
    #:   group 2   49  6000/3   →  98  6000, accounts 1, records 1+3+1 = 5
    #:   99        26000 + 6000 = 32000, groups 2, records 1+6+5+1 = 13
    _TWO_GROUPS = (
        "01,S,R,240115,0800,1,,,2/",
        "02,R,B,1,240115,,USD,/",
        "03,AAA,USD,010,10000,,,015,12000,,/",
        "16,165,3000,0,R1,C1,In/",
        "16,475,1000,0,R2,C2,Out/",
        "49,26000,4/",
        "98,26000,1,6/",
        "02,R,B2,1,240115,,USD,/",
        "03,BBB,USD,010,2000,,,015,3000,,/",
        "16,165,1000,0,R3,C3,In/",
        "49,6000,3/",
        "98,6000,1,5/",
        "99,32000,2,13/",
    )

    def test_a_two_group_file_rolls_up_through_both_trailers(self) -> None:
        parsed = parse_bai2(file_of(*self._TWO_GROUPS))
        self.assertEqual(len(parsed.groups), 2)
        self.assertEqual(len(parsed.accounts), 2)
        self.assertEqual(len(parsed.transactions), 3)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(parsed.proof_class, ProofClass.p0)

    def test_the_file_trailer_counts_groups_and_every_physical_record(self) -> None:
        parsed = parse_bai2(file_of(*self._TWO_GROUPS))
        total = parsed.control_total
        self.assertEqual(total.declared_child_count, 2)
        self.assertEqual(total.computed_child_count, 2)
        self.assertEqual(total.declared_record_count, 13)
        self.assertEqual(total.computed_record_count, 13)
        self.assertEqual(total.basis, _FILE_CONTROL_BASIS)

    def test_the_file_total_sums_the_98s_and_not_the_records_beneath_them(self) -> None:
        # The distinction is what makes three levels three checks.  Here the
        # second group's 98 understates its own 49 by 1000.  The 99 agrees with
        # the understated 98 — so the file total passes while the group total
        # fails, and the file is unbalanced because the group is, not because
        # the 99 noticed anything.
        lines = list(self._TWO_GROUPS)
        lines[11] = "98,5000,1,5/"
        lines[12] = "99,31000,2,13/"
        parsed = parse_bai2(file_of(*lines))
        self.assertIs(parsed.control_total.status, ReconciliationStatus.balanced)
        self.assertIs(
            parsed.groups[1].control_total.status, ReconciliationStatus.unbalanced
        )
        # The delta is computed minus declared: the 49 beneath holds 6000 and
        # the 98 claims 5000, so under-declaring reads positive.
        self.assertEqual(parsed.groups[1].control_total.minor_unit_delta, 1000)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_one_failed_account_carries_all_the_way_to_the_file(self) -> None:
        lines = list(self._TWO_GROUPS)
        lines[10] = "49,5000,3/"
        lines[11] = "98,5000,1,5/"
        lines[12] = "99,31000,2,13/"
        parsed = parse_bai2(file_of(*lines))
        self.assertIs(
            parsed.accounts[1].control_total.status, ReconciliationStatus.unbalanced
        )
        self.assertIs(
            parsed.groups[0].reconciliation_status, ReconciliationStatus.balanced
        )
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_transactions_and_accounts_are_returned_in_file_order(self) -> None:
        parsed = parse_bai2(file_of(*self._TWO_GROUPS))
        self.assertEqual(
            [a.customer_account_number for a in parsed.accounts], ["AAA", "BBB"]
        )
        self.assertEqual(
            [txn.bank_reference for txn in parsed.transactions], ["R1", "R2", "R3"]
        )


class AvailabilityAmountTests(unittest.TestCase):
    """The availability amounts of an ``S``/``V``/``D`` funds type are not summed.

    The specification's wording — the sum of the amount fields — does not settle
    whether the availability breakdown counts, and implementations differ.  One
    reading is fixed in the module, the dominant one, because a parser that
    tried both and kept whichever balanced would report a passing control total
    on a file whose totals agree with nothing, having chosen the reading that
    made the failure disappear.

    These tests exist because the choice is invisible from the outside: a file
    written to either convention parses, and only the arithmetic tells them
    apart.  Without them the constant could be flipped and every other test in
    this suite would still pass.
    """

    #: One ``16`` with an ``S`` funds type: 3000 immediate, then 1000/1500/500
    #: available across three windows.  Under the convention the module fixes,
    #: the account total is 10000 + 13000 + 3000 = 26000.  Under the other it
    #: would be 29000.
    _SPLIT = "16,165,3000,S,1000,1500,500,REF1,CUST1,Split availability/"

    def _parsed(self, total: str = "26000"):
        return parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,13000,,/",
                self._SPLIT,
                total=total,
                records="3",
            )
        )

    def test_only_the_primary_amount_counts_toward_the_control_total(self) -> None:
        control = self._parsed().accounts[0].control_total
        self.assertIs(control.status, ReconciliationStatus.balanced)
        self.assertEqual(control.computed_minor_units, 26000)

    def test_a_file_written_to_the_other_convention_is_reported_unbalanced(self) -> None:
        # 26000 + 1000 + 1500 + 500.  Not silently accommodated: the file says
        # something this parser reads differently, and saying so is the point.
        control = self._parsed(total="29000").accounts[0].control_total
        self.assertIs(control.status, ReconciliationStatus.unbalanced)
        self.assertEqual(control.minor_unit_delta, -3000)

    def test_the_availability_split_does_not_reach_the_balance_identity(self) -> None:
        # 10000 + 3000 = 13000, the stated closing figure.  Adding the
        # availability windows would put it 3000 out.
        identity = self._parsed().accounts[0].balance_identity
        self.assertIs(identity.status, ReconciliationStatus.balanced)
        self.assertEqual(identity.credits, Money.from_minor_units(3000, "USD"))
        self.assertEqual(identity.credit_count, 1)

    def test_the_fields_after_the_funds_type_are_still_read_correctly(self) -> None:
        # The whole hazard of the funds type is silent misalignment: read the
        # S as one field and every field after it shifts by three, the record
        # still parses, and the file still balances.
        txn = self._parsed().transactions[0]
        self.assertEqual(txn.funds_type, "S")
        self.assertEqual(txn.amount, Money.from_minor_units(3000, "USD"))
        self.assertEqual(txn.bank_reference, "REF1")
        self.assertEqual(txn.customer_reference, "CUST1")
        self.assertEqual(txn.text, "Split availability")

    def test_the_same_holds_for_a_d_funds_type_with_its_day_pairs(self) -> None:
        # D announces a count and then that many day/amount pairs, so the shift
        # is variable rather than fixed.
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,13000,,/",
                "16,165,3000,D,2,1,1000,3,2000,REF9,CUST9,Deferred/",
                total="26000",
                records="3",
            )
        )
        txn = parsed.transactions[0]
        self.assertEqual(txn.funds_type, "D")
        self.assertEqual(txn.bank_reference, "REF9")
        self.assertEqual(txn.customer_reference, "CUST9")
        self.assertEqual(txn.text, "Deferred")
        self.assertIs(
            parsed.accounts[0].control_total.status, ReconciliationStatus.balanced
        )
        self.assertIs(parsed.proof_class, ProofClass.p0)


class TypeCodeValidationTests(unittest.TestCase):
    """The three-digit rule, enforced at both places a type code appears.

    A type code is what says whether a figure is a ledger balance, an
    available balance, a credit or a debit, and the whole of
    :func:`_direction_for_type_code` is a reading of its numeric range.  A
    code that is not three digits has no range, so anything built on top of
    it is built on a guess.

    Both call sites are covered deliberately.  The two are separate branches
    over separate fields, and a summary carrying a bad code is the likelier
    fault of the two: the ``03`` record interleaves code, amount and count in
    threes, so a single dropped field shifts every code after it into a
    position where it is read as an amount and every amount into a position
    where it is read as a code.
    """

    _MALFORMED = ("01", "0100", "ABC", "10A", "1", "16.5", "-10")

    def test_a_malformed_type_code_in_an_03_summary_is_refused(self) -> None:
        for bad in self._MALFORMED:
            with self.subTest(type_code=bad):
                with self.assertRaises(Bai2MalformedFileError) as caught:
                    parse_bai2(
                        _account_file(
                            f"03,111,USD,{bad},10000,,/",
                            "16,165,3000,0,REF1,CUST1,Text/",
                            total="13000",
                            records="3",
                        )
                    )
                message = str(caught.exception)
                self.assertIn("three-digit", message)
                self.assertIn(repr(bad), message)

    def test_a_malformed_type_code_in_a_16_detail_is_refused(self) -> None:
        for bad in self._MALFORMED:
            with self.subTest(type_code=bad):
                with self.assertRaises(Bai2MalformedFileError) as caught:
                    parse_bai2(
                        _account_file(
                            "03,111,USD,010,10000,,,015,13000,,/",
                            f"16,{bad},3000,0,REF1,CUST1,Text/",
                            total="26000",
                            records="3",
                        )
                    )
                message = str(caught.exception)
                self.assertIn("three-digit", message)
                self.assertIn(repr(bad), message)

    def test_the_refusal_names_the_record_the_bad_code_sits_in(self) -> None:
        # Two records, one fault, and the reader has to be sent to the right
        # line.  The summary code is on line 3 and the detail code on line 4.
        with self.assertRaises(Bai2MalformedFileError) as caught:
            parse_bai2(
                _account_file(
                    "03,111,USD,ABC,10000,,/",
                    "16,165,3000,0,REF1,CUST1,Text/",
                    total="13000",
                    records="3",
                )
            )
        self.assertIn("line 3", str(caught.exception))

        with self.assertRaises(Bai2MalformedFileError) as caught:
            parse_bai2(
                _account_file(
                    "03,111,USD,010,10000,,,015,13000,,/",
                    "16,ABC,3000,0,REF1,CUST1,Text/",
                    total="26000",
                    records="3",
                )
            )
        self.assertIn("line 4", str(caught.exception))

    def test_a_three_digit_code_outside_the_known_ranges_is_still_read(self) -> None:
        # The rule is three digits, not three digits from a list this parser
        # happens to know.  890 is a valid status code with no direction, and
        # refusing it would be refusing a well-formed file over a lookup
        # table that is nobody's authority.
        parsed = parse_bai2(
            _account_file(
                "03,111,USD,010,10000,,,015,13000,,/",
                "16,890,3000,0,REF1,CUST1,Memo only/",
                total="26000",
                records="3",
            )
        )
        txn = parsed.transactions[0]
        self.assertEqual(txn.type_code, "890")
        self.assertIsNone(_direction_for_type_code(txn.type_code))
        self.assertIs(parsed.proof_class, ProofClass.p0)

    def test_a_leading_zero_code_keeps_its_zero(self) -> None:
        # 010 is the ledger balance and 100 is a credit total.  Reading 010 as
        # the integer 10 and formatting it back would produce neither.
        parsed = parse_bai2(build())
        self.assertEqual(
            [entry.type_code for entry in parsed.accounts[0].summaries],
            ["010", "015", "100", "400"],
        )
