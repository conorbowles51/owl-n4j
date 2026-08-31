"""Tests for the MT940 native parser.

The limitation that opens ``test_financial_camt053`` and ``test_financial_bai2``
applies here too, and is restated rather than cross-referenced because it is
the single most important thing to know about this suite.  No corpus document
backs any of it.  The ET-Fraud corpus carries no MT940 message, so every
fixture below is constructed from the SWIFT field definitions rather than
measured from evidence.  A fixture built by the same reading of the
specification as the parser shares the parser's blind spots exactly: if the
reading is wrong, the test passes and the parser is wrong together.

What these tests establish is that the parser is self-consistent, that it
refuses what it cannot read, that the one check MT940 offers is genuinely
performed, and — the point most specific to this format — that nothing here
reaches :attr:`ProofClass.p0`, because MT940 carries no control total that
would justify it.  What only a real message from a real bank can establish is
that the reading is right.  Sourcing one remains the blocking item, alongside
the camt.053 and BAI2 files already asked for.

Three conventions are held throughout.  Every expectation is asserted against a
literal rather than against the constant the module uses, since asserting
``MT940_MAX_FILE_BYTES == MT940_MAX_FILE_BYTES`` establishes nothing.  Refusals
are asserted on their *message* and not merely on the exception type: two BAI2
tests were found passing for the wrong reason when they checked only that
something was raised, and the fix is a convention rather than a one-off.  And
the refusal paths are tested at least as heavily as the success path, because a
misreading of a specification surfaces as a message wrongly *admitted* far more
often than as one wrongly refused, and only the first of those is dangerous.
"""

from __future__ import annotations

import unittest
from typing import Optional

from postgres.models.enums import (
    LocatorKind,
    ProofClass,
    ReconciliationStatus,
    TransactionDirection,
)
from services.financial.money import Money
from services.financial.mt940 import (
    MT940_LOCATOR,
    MT940_MAX_FILE_BYTES,
    Mt940AmountError,
    Mt940CurrencyError,
    Mt940Error,
    Mt940File,
    Mt940MalformedFileError,
    Mt940MissingFieldError,
    NotAnMt940Error,
    _extract_statements,
    _fold_tags,
    _parse_amount,
    _parse_date,
    _weakest,
    parse_mt940,
)
from services.financial.proof_class import SourceShape, assign_proof_class

# ---------------------------------------------------------------------------
# Fixtures
#
# One canonical message, and a builder that replaces or drops exactly one named
# part of it.  The arithmetic is worked here once so that every test below can
# be read against it:
#
#   opening   :60F:   C 10000,00        =  1 000 000 minor units
#   debit     :61:    D  2500,00        =    250 000
#   credit    :61:    C  1000,50        =    100 050
#   computed  1000000 + 100050 - 250000 =    850 050
#   printed   :62F:   C  8500,50        =    850 050   -> delta 0, balanced
#
# The line numbers matter too, because every refusal in the module points at
# one and the tests assert on them:
#
#    1 :20:   5 :61: debit        9 :61: credit
#    2 :25:   6 supplementary    10 :86: credit narrative
#    3 :28C:  7 :86: debit        11 :62F:
#    4 :60F:  8 narrative cont.   12 :64:
# ---------------------------------------------------------------------------

_BASELINE: tuple[tuple[str, str], ...] = (
    ("reference", ":20:STMT001"),
    ("account", ":25:GB29NWBK60161331926819"),
    ("statement_number", ":28C:00123/00001"),
    ("opening", ":60F:C240115USD10000,00"),
    ("debit", ":61:2401150115DD2500,00NTRFREF001//BANKREF1\nSUPPLEMENTARY DETAIL"),
    ("debit_narrative", ":86:PAYMENT TO ACME LTD\nINVOICE 4471"),
    ("credit", ":61:2401160116C1000,50NTRFREF002"),
    ("credit_narrative", ":86:DEPOSIT"),
    ("closing", ":62F:C240116USD8500,50"),
    ("available", ":64:C240116USD8500,50"),
)

_PART_NAMES = frozenset(name for name, _ in _BASELINE)


def build(**overrides: Optional[str]) -> str:
    """The canonical message, with named parts replaced or dropped.

    Passing ``None`` drops the part.  An override naming a part that does not
    exist is an error rather than a no-op, because a typo that silently tests
    the untouched baseline is a test that passes without exercising anything.
    """
    unknown = set(overrides) - _PART_NAMES
    if unknown:
        raise AssertionError(f"no such part of the fixture: {sorted(unknown)}")
    parts = [overrides.get(name, line) for name, line in _BASELINE]
    return "\n".join(part for part in parts if part is not None)


def message(*lines: str) -> str:
    """An arbitrary message, for structures the baseline cannot express."""
    return "\n".join(lines)


def minimal(*body: str) -> str:
    """The smallest well-formed statement, wrapped around ``body``."""
    return message(
        ":20:MIN",
        ":25:ACCOUNT",
        ":28C:1",
        ":60F:C240115USD100,00",
        *body,
        ":62F:C240115USD100,00",
    )


class BaselineTests(unittest.TestCase):
    """The canonical message, read field by field."""

    def setUp(self) -> None:
        self.parsed = parse_mt940(build())
        self.statement = self.parsed.statements[0]

    def test_one_message_yields_one_statement(self) -> None:
        self.assertEqual(len(self.parsed.statements), 1)
        self.assertEqual(self.statement.first_line, 1)

    def test_the_header_fields_are_read(self) -> None:
        self.assertEqual(self.statement.transaction_reference, "STMT001")
        self.assertIsNone(self.statement.related_reference)
        self.assertEqual(
            self.statement.account_identification, "GB29NWBK60161331926819"
        )
        self.assertIsNone(self.statement.account_identifier_code)

    def test_the_statement_number_splits_on_the_slash(self) -> None:
        self.assertEqual(self.statement.statement_number, "00123")
        self.assertEqual(self.statement.sequence_number, "00001")

    def test_the_balances_are_read_with_mark_date_and_tag(self) -> None:
        opening = self.statement.opening_balance
        closing = self.statement.closing_balance
        self.assertEqual(opening.tag, "60F")
        self.assertEqual(opening.mark, "C")
        self.assertEqual(opening.date, "240115")
        self.assertEqual(opening.amount, Money.from_minor_units(1000000, "USD"))
        self.assertEqual(opening.first_line, 4)
        self.assertEqual(closing.tag, "62F")
        self.assertEqual(closing.date, "240116")
        self.assertEqual(closing.amount, Money.from_minor_units(850050, "USD"))
        self.assertEqual(closing.first_line, 11)

    def test_the_debit_line_is_read_subfield_by_subfield(self) -> None:
        line = self.statement.lines[0]
        self.assertEqual(line.value_date, "240115")
        self.assertEqual(line.entry_date, "0115")
        self.assertEqual(line.mark, "D")
        self.assertIs(line.direction, TransactionDirection.debit)
        self.assertEqual(line.funds_code, "D")
        self.assertEqual(line.amount, Money.from_minor_units(250000, "USD"))
        self.assertEqual(line.transaction_type, "NTRF")
        self.assertEqual(line.account_owner_reference, "REF001")
        self.assertEqual(line.institution_reference, "BANKREF1")
        self.assertEqual(line.supplementary_details, "SUPPLEMENTARY DETAIL")
        self.assertEqual(line.first_line, 5)

    def test_the_credit_line_states_no_funds_code_or_institution_reference(self) -> None:
        line = self.statement.lines[1]
        self.assertEqual(line.mark, "C")
        self.assertIs(line.direction, TransactionDirection.credit)
        self.assertIsNone(line.funds_code)
        self.assertEqual(line.account_owner_reference, "REF002")
        self.assertIsNone(line.institution_reference)
        self.assertIsNone(line.supplementary_details)
        self.assertEqual(line.first_line, 9)

    def test_the_closing_available_balance_is_read(self) -> None:
        available = self.statement.closing_available_balance
        assert available is not None
        self.assertEqual(available.tag, "64")
        self.assertEqual(available.amount, Money.from_minor_units(850050, "USD"))
        self.assertEqual(self.statement.forward_available_balances, ())

    def test_the_currency_comes_from_the_balances(self) -> None:
        self.assertEqual(self.statement.currency, "USD")

    def test_a_final_balance_is_not_a_fragment(self) -> None:
        self.assertFalse(self.statement.is_fragment)
        self.assertFalse(self.statement.opening_balance.is_intermediate)
        self.assertFalse(self.statement.closing_balance.is_intermediate)

    def test_the_identity_closes_and_the_message_earns_p1(self) -> None:
        self.assertIs(
            self.parsed.reconciliation_status, ReconciliationStatus.balanced
        )
        self.assertIs(self.parsed.proof_class, ProofClass.p1)

    def test_the_source_shape_is_fixed_and_not_settable(self) -> None:
        self.assertIs(
            self.parsed.source_shape, SourceShape.native_without_control_totals
        )
        # The shape is a property of the format, not a parameter a caller can
        # supply.  Nothing may hand this parser a stronger shape than MT940
        # earns, at either entry point.
        with self.assertRaises(TypeError):
            Mt940File(  # type: ignore[call-arg]
                statements=(),
                source_shape=SourceShape.native_with_control_totals,
            )
        with self.assertRaises(TypeError):
            parse_mt940(  # type: ignore[call-arg]
                build(), source_shape=SourceShape.native_with_control_totals
            )

    def test_an_mt940_row_carries_no_click_through_target(self) -> None:
        # There is no page and no rectangle: the source is a text message, not
        # a rendered document, so a locator that claimed coordinates would be
        # claiming something that does not exist.
        for locator in (
            self.statement.locator,
            self.statement.lines[0].locator,
            self.statement.opening_balance.locator,
        ):
            self.assertIs(locator.kind, LocatorKind.not_positional)
            self.assertIsNone(locator.page_number)
            self.assertIsNone(locator.rectangle)

    def test_bytes_and_text_are_read_identically(self) -> None:
        from_bytes = parse_mt940(build().encode("utf-8"))
        self.assertEqual(from_bytes.statements, self.parsed.statements)

    def test_a_bytearray_is_read_like_bytes(self) -> None:
        from_bytearray = parse_mt940(bytearray(build().encode("utf-8")))
        self.assertEqual(from_bytearray.statements, self.parsed.statements)

    def test_carriage_returns_do_not_change_the_reading(self) -> None:
        # A message that crossed a Windows box is the same message.
        crlf = parse_mt940(build().replace("\n", "\r\n"))
        self.assertEqual(crlf.statements, self.parsed.statements)
        cr_only = parse_mt940(build().replace("\n", "\r"))
        self.assertEqual(cr_only.statements, self.parsed.statements)

    def test_a_trailing_newline_does_not_change_the_reading(self) -> None:
        # Not cosmetic.  The :86: narrative is carried verbatim and hashed
        # downstream, so the same statement saved with and without a final
        # newline must produce the same string or it will produce two
        # different identities for one document.
        self.assertEqual(
            parse_mt940(build() + "\n").statements, self.parsed.statements
        )
        self.assertEqual(
            parse_mt940(build() + "\n\n\n").statements, self.parsed.statements
        )


class BalanceIdentityTests(unittest.TestCase):
    """``:60a: + ΣCredits − ΣDebits = :62a:``, the whole of MT940's arithmetic."""

    def test_the_identity_sums_the_lines_and_closes(self) -> None:
        identity = parse_mt940(build()).statements[0].balance_identity
        self.assertIs(identity.status, ReconciliationStatus.balanced)
        self.assertTrue(identity.balanced)
        self.assertEqual(identity.opening, Money.from_minor_units(1000000, "USD"))
        self.assertEqual(identity.credits, Money.from_minor_units(100050, "USD"))
        self.assertEqual(identity.debits, Money.from_minor_units(250000, "USD"))
        self.assertEqual(
            identity.computed_closing, Money.from_minor_units(850050, "USD")
        )
        self.assertEqual(
            identity.printed_closing, Money.from_minor_units(850050, "USD")
        )
        self.assertEqual(identity.delta, Money.zero("USD"))

    def test_the_counts_are_by_direction_not_by_line(self) -> None:
        identity = parse_mt940(build()).statements[0].balance_identity
        self.assertEqual(identity.credit_count, 1)
        self.assertEqual(identity.debit_count, 1)
        self.assertEqual(identity.reversal_count, 0)

    def test_a_wrong_closing_balance_is_unbalanced_and_states_the_delta(self) -> None:
        parsed = parse_mt940(build(closing=":62F:C240116USD8000,00"))
        identity = parsed.statements[0].balance_identity
        self.assertIs(identity.status, ReconciliationStatus.unbalanced)
        self.assertFalse(identity.balanced)
        # delta is computed - printed, the same orientation Bai2BalanceIdentity
        # uses, so a reviewer reads the sign identically across formats.
        self.assertEqual(identity.delta, Money.from_minor_units(50050, "USD"))
        self.assertEqual(
            identity.computed_closing, Money.from_minor_units(850050, "USD")
        )
        self.assertEqual(
            identity.printed_closing, Money.from_minor_units(800000, "USD")
        )

    def test_a_negative_delta_means_the_movements_fall_short(self) -> None:
        parsed = parse_mt940(build(closing=":62F:C240116USD9000,00"))
        identity = parsed.statements[0].balance_identity
        self.assertEqual(identity.delta, Money.from_minor_units(-49950, "USD"))

    def test_a_dropped_line_is_caught_by_the_identity(self) -> None:
        # This is the check doing the work it exists for.
        parsed = parse_mt940(build(credit=None, credit_narrative=None))
        self.assertIs(
            parsed.statements[0].balance_identity.status,
            ReconciliationStatus.unbalanced,
        )

    def test_a_statement_with_no_lines_at_all_still_checks(self) -> None:
        # Opening equals closing and nothing moved: the identity holds, and it
        # is a real check rather than a vacuous one, because an opening that
        # differed from the closing would fail it.
        parsed = parse_mt940(
            message(
                ":20:QUIET",
                ":25:ACCOUNT",
                ":28C:1",
                ":60F:C240115USD100,00",
                ":62F:C240115USD100,00",
            )
        )
        identity = parsed.statements[0].balance_identity
        self.assertIs(identity.status, ReconciliationStatus.balanced)
        self.assertEqual(identity.credits, Money.zero("USD"))
        self.assertEqual(identity.debits, Money.zero("USD"))
        self.assertEqual(identity.credit_count, 0)
        self.assertEqual(identity.debit_count, 0)

    def test_a_statement_with_no_lines_and_moving_balances_fails(self) -> None:
        parsed = parse_mt940(
            message(
                ":20:LOUD",
                ":25:ACCOUNT",
                ":28C:1",
                ":60F:C240115USD100,00",
                ":62F:C240115USD250,00",
            )
        )
        identity = parsed.statements[0].balance_identity
        self.assertIs(identity.status, ReconciliationStatus.unbalanced)
        self.assertEqual(identity.delta, Money.from_minor_units(-15000, "USD"))

    def test_the_identity_never_declines(self) -> None:
        # Both balances are mandatory and every mark this parser accepts has a
        # direction, so there is no input that reaches the check with nothing
        # to check.  A caller reading ``unavailable`` off this type has found a
        # bug, not a quiet message.
        for text in (build(), build(closing=":62F:C240116USD1,00"), minimal()):
            status = parse_mt940(text).statements[0].balance_identity.status
            self.assertIn(
                status,
                (ReconciliationStatus.balanced, ReconciliationStatus.unbalanced),
            )

    def test_the_reconciliation_status_is_the_identity_and_nothing_else(self) -> None:
        statement = parse_mt940(build()).statements[0]
        self.assertIs(
            statement.reconciliation_status, statement.balance_identity.status
        )


class ProofClassTests(unittest.TestCase):
    """Why MT940 sits at p1, and the one case where it sits lower."""

    def test_a_clean_message_earns_p1_and_deliberately_not_p0(self) -> None:
        # This is the most consequential decision in the module and the one
        # most likely to be "corrected" by someone who notes that MT940 is
        # parsed natively, like camt.053, BAI2 and NACHA, and concludes it
        # must therefore be P0 like them.
        #
        # It is not.  P0 means a bank-originated file
        # with mandatory control totals, and MT940 has none: no record count,
        # no entry count, no declared credit or debit total.  Two :61: lines
        # merged in carriage, or one of net zero dropped entirely, leave a
        # message whose balance identity still closes perfectly.  A BAI2 49
        # record count catches both; MT940 has nothing that can.
        self.assertIs(parse_mt940(build()).proof_class, ProofClass.p1)

    def test_the_class_is_computed_from_the_shape_rather_than_asserted(self) -> None:
        parsed = parse_mt940(build())
        self.assertIs(
            parsed.proof_class,
            assign_proof_class(parsed.source_shape, parsed.reconciliation_status),
        )

    def test_the_shape_is_what_costs_the_p0_and_nothing_else(self) -> None:
        # Stated as an equation so that the cost of the decision is visible:
        # the same balanced outcome under the stronger shape would be p0, and
        # the only thing standing between MT940 and p0 is the absent control
        # total.
        self.assertIs(
            assign_proof_class(
                SourceShape.native_with_control_totals,
                ReconciliationStatus.balanced,
            ),
            ProofClass.p0,
        )
        self.assertIs(
            assign_proof_class(
                SourceShape.native_without_control_totals,
                ReconciliationStatus.balanced,
            ),
            ProofClass.p1,
        )

    def test_a_failing_identity_still_falls_to_p3(self) -> None:
        # MT940 behaves better than a bare "format validation only" reading of
        # P1 would suggest, because assign_proof_class tests the
        # outcome before it dispatches on the shape.  A message whose
        # arithmetic did not close is p3 whatever its shape.
        parsed = parse_mt940(build(closing=":62F:C240116USD8000,00"))
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_nothing_in_this_module_can_reach_p0(self) -> None:
        for text in (
            build(),
            build(closing=":62F:C240116USD8000,00"),
            minimal(),
            message(
                ":20:F", ":25:A", ":28C:1/2",
                ":60M:C240115USD100,00", ":62M:C240115USD100,00",
            ),
        ):
            self.assertIsNot(parse_mt940(text).proof_class, ProofClass.p0)


class ReversalTests(unittest.TestCase):
    """``RC`` and ``RD``: which side they land on, and that they stay visible."""

    def setUp(self) -> None:
        #  1000,00 opening
        # +  200,00 RD, a reversal of a debit, which returns money
        # -  100,00 RC, a reversal of a credit, which takes it back
        # = 1100,00 closing
        self.parsed = parse_mt940(
            message(
                ":20:REV",
                ":25:ACCOUNT",
                ":28C:1",
                ":60F:C240115USD1000,00",
                ":61:240115RD200,00NTRFREVERSED-DEBIT",
                ":61:240115RC100,00NTRFREVERSED-CREDIT",
                ":62F:C240115USD1100,00",
            )
        )
        self.lines = self.parsed.statements[0].lines

    def test_a_reversed_debit_lands_on_the_credit_side(self) -> None:
        line = self.lines[0]
        self.assertEqual(line.mark, "RD")
        self.assertIs(line.direction, TransactionDirection.credit)
        self.assertEqual(line.signed_amount, Money.from_minor_units(20000, "USD"))

    def test_a_reversed_credit_lands_on_the_debit_side(self) -> None:
        line = self.lines[1]
        self.assertEqual(line.mark, "RC")
        self.assertIs(line.direction, TransactionDirection.debit)
        self.assertEqual(line.signed_amount, Money.from_minor_units(-10000, "USD"))

    def test_the_two_character_mark_is_not_read_as_one(self) -> None:
        # RC must not parse as an unknown R followed by a C, which would leave
        # a credit where a debit belongs and move the delta by twice the
        # amount.  The regex orders the two-character marks first; this is what
        # holds that ordering in place.
        self.assertEqual([line.mark for line in self.lines], ["RD", "RC"])
        self.assertIsNone(self.lines[0].funds_code)
        self.assertIsNone(self.lines[1].funds_code)

    def test_a_reversal_stays_visibly_a_reversal_after_the_direction_flattens_it(
        self,
    ) -> None:
        # direction is what the identity needs; is_reversal is what a reader
        # needs.  A reversal is a correction to a figure the bank stated
        # earlier, and collapsing it into an ordinary movement would lose the
        # only signal that the earlier figure was withdrawn.
        self.assertTrue(all(line.is_reversal for line in self.lines))
        self.assertFalse(
            any(line.is_reversal for line in parse_mt940(build()).statements[0].lines)
        )

    def test_the_reversal_count_is_reported_alongside_the_identity(self) -> None:
        identity = self.parsed.statements[0].balance_identity
        self.assertIs(identity.status, ReconciliationStatus.balanced)
        self.assertEqual(identity.reversal_count, 2)
        self.assertEqual(identity.credit_count, 1)
        self.assertEqual(identity.debit_count, 1)


class SignedBalanceTests(unittest.TestCase):
    """A ``D`` mark makes a balance negative, because an overdraft is negative."""

    def setUp(self) -> None:
        self.parsed = parse_mt940(
            message(
                ":20:OD",
                ":25:ACCOUNT",
                ":28C:1",
                ":60F:D240115USD500,00",
                ":61:240115C300,00NTRFDEPOSIT",
                ":62F:D240115USD200,00",
            )
        )
        self.statement = self.parsed.statements[0]

    def test_a_debit_marked_balance_is_negative(self) -> None:
        self.assertEqual(
            self.statement.opening_balance.amount,
            Money.from_minor_units(-50000, "USD"),
        )
        self.assertEqual(
            self.statement.closing_balance.amount,
            Money.from_minor_units(-20000, "USD"),
        )

    def test_the_mark_the_file_wrote_is_kept_beside_the_sign(self) -> None:
        self.assertEqual(self.statement.opening_balance.mark, "D")
        self.assertEqual(self.statement.closing_balance.mark, "D")

    def test_the_identity_closes_across_zero(self) -> None:
        identity = self.statement.balance_identity
        self.assertIs(identity.status, ReconciliationStatus.balanced)
        self.assertEqual(identity.delta, Money.zero("USD"))
        self.assertEqual(
            identity.computed_closing, Money.from_minor_units(-20000, "USD")
        )

    def test_an_account_crossing_from_overdrawn_into_credit_is_read(self) -> None:
        parsed = parse_mt940(
            message(
                ":20:CROSS",
                ":25:ACCOUNT",
                ":28C:1",
                ":60F:D240115USD100,00",
                ":61:240115C250,00NTRFBIG",
                ":62F:C240115USD150,00",
            )
        )
        self.assertIs(
            parsed.statements[0].balance_identity.status,
            ReconciliationStatus.balanced,
        )


class FragmentTests(unittest.TestCase):
    """``:60M:`` and ``:62M:``: recorded, and deliberately not a demotion."""

    def setUp(self) -> None:
        self.parsed = parse_mt940(
            message(
                ":20:FRAG",
                ":25:ACCOUNT",
                ":28C:00123/00002",
                ":60M:C240115USD100,00",
                ":61:240115C50,00NTRFMID",
                ":62M:C240115USD150,00",
            )
        )
        self.statement = self.parsed.statements[0]

    def test_an_intermediate_balance_marks_the_statement_a_fragment(self) -> None:
        self.assertTrue(self.statement.opening_balance.is_intermediate)
        self.assertTrue(self.statement.closing_balance.is_intermediate)
        self.assertTrue(self.statement.is_fragment)

    def test_either_intermediate_balance_alone_is_enough(self) -> None:
        opening_only = parse_mt940(
            message(
                ":20:F", ":25:A", ":28C:1",
                ":60M:C240115USD100,00", ":62F:C240115USD100,00",
            )
        ).statements[0]
        closing_only = parse_mt940(
            message(
                ":20:F", ":25:A", ":28C:1",
                ":60F:C240115USD100,00", ":62M:C240115USD100,00",
            )
        ).statements[0]
        self.assertTrue(opening_only.is_fragment)
        self.assertTrue(closing_only.is_fragment)

    def test_a_fragment_is_not_demoted_for_being_one(self) -> None:
        # A fragment's own arithmetic is sound: opening plus movements equals
        # closing within the fragment.  The BAI2 test-or-deletion precedent
        # deliberately does not carry over — a BAI2 test group asserts nothing
        # about money that moved, while a :62M: statement asserts exactly what
        # moved and merely does not finish.  Whether the fragments in hand
        # cover the period is periods.py's question, not this parser's.
        self.assertIs(
            self.statement.reconciliation_status, ReconciliationStatus.balanced
        )
        self.assertIs(self.parsed.proof_class, ProofClass.p1)
        self.assertEqual(self.parsed.admissibility_reservations, ())

    def test_a_fragment_whose_own_arithmetic_fails_is_still_caught(self) -> None:
        parsed = parse_mt940(
            message(
                ":20:F", ":25:A", ":28C:1",
                ":60M:C240115USD100,00",
                ":61:240115C50,00NTRFMID",
                ":62M:C240115USD999,00",
            )
        )
        self.assertIs(parsed.proof_class, ProofClass.p3)


class AmountTests(unittest.TestCase):
    """The SWIFT ``15d`` amount, which is stricter than it first looks."""

    def test_the_comma_is_the_decimal_point(self) -> None:
        self.assertEqual(
            _parse_amount("1000,00", "USD", context="c"),
            Money.from_minor_units(100000, "USD"),
        )

    def test_a_single_decimal_digit_is_tenths_not_hundredths(self) -> None:
        # 1000,5 is one thousand and fifty cents.  Reading the 5 as five cents
        # would understate every such figure by a factor of ten.
        self.assertEqual(
            _parse_amount("1000,5", "USD", context="c"),
            Money.from_minor_units(100050, "USD"),
        )

    def test_a_trailing_comma_with_no_decimals_is_whole_units(self) -> None:
        self.assertEqual(
            _parse_amount("1000,", "USD", context="c"),
            Money.from_minor_units(100000, "USD"),
        )

    def test_a_currency_with_no_minor_unit_takes_no_decimals(self) -> None:
        self.assertEqual(
            _parse_amount("1500,", "JPY", context="c"),
            Money.from_minor_units(1500, "JPY"),
        )
        with self.assertRaises(Mt940AmountError) as caught:
            _parse_amount("1500,00", "JPY", context="c")
        self.assertIn("carries 2 decimal digits and JPY has 0", str(caught.exception))

    def test_a_three_decimal_currency_takes_three(self) -> None:
        self.assertEqual(
            _parse_amount("10,500", "KWD", context="c"),
            Money.from_minor_units(10500, "KWD"),
        )

    def test_a_period_is_refused_because_the_two_readings_differ_by_a_thousand(
        self,
    ) -> None:
        # The single most dangerous input this parser can be handed.  SWIFT has
        # no thousands separator at all, so a file writing one is
        # non-conformant, and '1.000,00' and '1,000.00' are both plausible
        # readings of it that differ by three orders of magnitude.  Guessing
        # produces a ledger figure nothing downstream can question.
        for text in ("1.000,00", "1,000.00", "1.000.000,00"):
            with self.assertRaises(Mt940AmountError) as caught:
                _parse_amount(text, "USD", context="c")
            self.assertIn("contains a period", str(caught.exception))
            self.assertIn("three orders of magnitude", str(caught.exception))

    def test_an_amount_with_no_comma_at_all_is_refused(self) -> None:
        with self.assertRaises(Mt940AmountError) as caught:
            _parse_amount("100", "USD", context="c")
        self.assertIn("is not a SWIFT amount", str(caught.exception))
        self.assertIn("mandatory comma", str(caught.exception))

    def test_more_decimals_than_the_currency_has_is_refused_not_rounded(self) -> None:
        with self.assertRaises(Mt940AmountError) as caught:
            _parse_amount("100,005", "USD", context="c")
        self.assertIn("refusing to round evidence", str(caught.exception))

    def test_an_empty_amount_is_a_missing_field_not_a_zero(self) -> None:
        with self.assertRaises(Mt940AmountError) as caught:
            _parse_amount("", "USD", context="c")
        self.assertIn("the amount is empty", str(caught.exception))

    def test_a_zero_amount_is_legitimate(self) -> None:
        self.assertEqual(_parse_amount("0,", "USD", context="c"), Money.zero("USD"))
        self.assertEqual(_parse_amount("0,00", "USD", context="c"), Money.zero("USD"))

    def test_the_fifteen_digit_ceiling_is_the_specifications(self) -> None:
        fifteen = "9" * 15
        self.assertEqual(
            _parse_amount(f"{fifteen},", "USD", context="c").minor_units,
            int(fifteen) * 100,
        )
        with self.assertRaises(Mt940AmountError) as caught:
            _parse_amount("9" * 16 + ",", "USD", context="c")
        self.assertIn("is not a SWIFT amount", str(caught.exception))

    def test_a_signed_amount_is_refused_because_the_mark_carries_the_sign(self) -> None:
        # A minus inside the amount would be a second, contradictable source of
        # truth for the sign the C/D mark already states.
        for text in ("-100,00", "+100,00"):
            with self.assertRaises(Mt940AmountError):
                _parse_amount(text, "USD", context="c")

    def test_the_context_names_the_line_the_reader_must_look_at(self) -> None:
        with self.assertRaises(Mt940AmountError) as caught:
            _parse_amount("bad", "USD", context="line 5 (:61: statement line)")
        self.assertIn("line 5 (:61: statement line)", str(caught.exception))


class DateTests(unittest.TestCase):
    """``YYMMDD``, recorded rather than resolved."""

    def test_a_date_is_returned_as_its_six_digits(self) -> None:
        self.assertEqual(_parse_date("240115", context="c"), "240115")

    def test_the_century_is_not_resolved_here_or_anywhere(self) -> None:
        # 980115 is 1998 or 2098 and the message does not say.  A sliding
        # window would pick silently, and would pick wrong for exactly the
        # archival material an investigation most often reads.  This follows
        # the BAI2 precedent, where as_of_date and creation_date are also kept
        # as raw digits.
        self.assertEqual(_parse_date("980115", context="c"), "980115")
        self.assertEqual(_parse_date("000229", context="c"), "000229")
        parsed = parse_mt940(
            build(
                opening=":60F:C980115USD10000,00",
                closing=":62F:C980116USD8500,50",
            )
        )
        self.assertEqual(parsed.statements[0].opening_balance.date, "980115")
        self.assertIsInstance(parsed.statements[0].opening_balance.date, str)

    def test_a_month_outside_one_to_twelve_is_refused(self) -> None:
        for text, month in (("241315", 13), ("240015", 0)):
            with self.assertRaises(Mt940MalformedFileError) as caught:
                _parse_date(text, context="c")
            self.assertIn(f"states month {month:02d}", str(caught.exception))

    def test_a_day_outside_one_to_thirty_one_is_refused(self) -> None:
        for text, day in (("240132", 32), ("240100", 0)):
            with self.assertRaises(Mt940MalformedFileError) as caught:
                _parse_date(text, context="c")
            self.assertIn(f"states day {day:02d}", str(caught.exception))

    def test_the_day_is_not_checked_against_the_month(self) -> None:
        # 31 February is accepted, and that is the intended limit of this
        # check.  Validating the day against the month needs the century, which
        # the message does not state, so a parser that tried would be resolving
        # the century by the back door in order to reject a date.
        self.assertEqual(_parse_date("240231", context="c"), "240231")

    def test_something_that_is_not_six_digits_is_refused(self) -> None:
        for text in ("24011", "2401155", "24011a", "", "2401-5"):
            with self.assertRaises(Mt940MalformedFileError) as caught:
                _parse_date(text, context="c")
            self.assertIn("is not a YYMMDD date", str(caught.exception))

    def test_a_bad_date_in_a_message_names_its_line(self) -> None:
        with self.assertRaises(Mt940MalformedFileError) as caught:
            parse_mt940(build(opening=":60F:C241315USD10000,00"))
        self.assertIn("line 4", str(caught.exception))
        self.assertIn("states month 13", str(caught.exception))


class TagFoldingTests(unittest.TestCase):
    """A tag and the lines that continue it.

    MT940 has no continuation marker: a line simply belongs to the tag above it
    unless it opens a tag of its own.  Getting this wrong is quiet — a
    narrative line read as a tag, or a tag read as narrative, changes what the
    ledger records without failing anything.
    """

    def test_continuation_lines_join_with_a_newline(self) -> None:
        # Not a space.  The bank chose where to break, and a narrative rejoined
        # on spaces cannot be broken back the way it was written.
        tags = _fold_tags(":20:A\ncont1\ncont2\n:25:B\n")
        self.assertEqual([t.tag for t in tags], ["20", "25"])
        self.assertEqual(tags[0].value, "A\ncont1\ncont2")
        self.assertEqual(tags[0].line_count, 3)
        self.assertEqual(tags[1].value, "B")

    def test_a_tag_records_the_line_it_opened_on(self) -> None:
        tags = _fold_tags(":20:A\ncont\n:25:B\n")
        self.assertEqual(tags[0].first_line, 1)
        self.assertEqual(tags[1].first_line, 3)

    def test_the_block_terminator_is_not_narrative(self) -> None:
        # A lone '-' closes SWIFT block 4.  Folded into the tag above it, it
        # would land in the ledger as a line of the bank's narrative.
        self.assertEqual([(t.tag, t.value) for t in _fold_tags(":20:A\n-\n")], [("20", "A")])
        self.assertEqual(
            [(t.tag, t.value) for t in _fold_tags(":20:A\n-\n:25:B\n")],
            [("20", "A"), ("25", "B")],
        )

    def test_interior_blank_lines_are_kept(self) -> None:
        # The counterpart to the trailing-newline rule.  A blank line between
        # two pieces of narrative is something the bank wrote; dropping it
        # would alter the record.
        parsed = parse_mt940(
            message(
                ":20:X",
                ":25:A",
                ":28C:1",
                ":60F:C240115USD0,",
                ":62F:C240115USD0,",
                ":86:ONE",
                "",
                "TWO",
            )
        )
        self.assertEqual(parsed.statements[0].information, "ONE\n\nTWO")

    def test_content_before_the_first_tag_is_refused(self) -> None:
        with self.assertRaises(NotAnMt940Error) as caught:
            parse_mt940(
                message(
                    "GARBAGE HEADER",
                    ":20:X",
                    ":25:A",
                    ":28C:1",
                    ":60F:C240115USD1,00",
                    ":62F:C240115USD1,00",
                )
            )
        message_text = str(caught.exception)
        self.assertIn("line 1", message_text)
        self.assertIn("appears before any tagged field", message_text)


class EnvelopeTests(unittest.TestCase):
    """Bare block 4, or a whole FIN message wrapped around it."""

    def test_a_bare_body_passes_through(self) -> None:
        body = message(*(line for _, line in _BASELINE))
        self.assertTrue(_extract_statements(body).startswith(":20:STMT001"))

    def test_a_fin_envelope_is_stripped(self) -> None:
        wrapped = "{1:F01BANKGB2LAXXX0000000000}{2:O9401200}{4:\n" + build() + "\n-}"
        self.assertEqual(parse_mt940(wrapped).statements, parse_mt940(build()).statements)

    def test_concatenated_messages_are_all_read(self) -> None:
        # A day's statements arrive as several FIN messages in one file.
        # Reading only the first would silently drop the rest.
        wrapped = "{1:F01BANKGB2LAXXX0000000000}{4:\n" + build() + "\n-}"
        parsed = parse_mt940(wrapped + wrapped)
        self.assertEqual(len(parsed.statements), 2)

    def test_a_truncated_application_block_is_refused(self) -> None:
        # Refused rather than read up to where it stops: the missing tail is
        # exactly where the closing balance lives, so a truncated message read
        # leniently would lose the only check the format carries.
        with self.assertRaises(NotAnMt940Error) as caught:
            parse_mt940("{1:F01BANKGB2LAXXX0000000000}{4:\n" + build())
        message_text = str(caught.exception)
        self.assertIn("'{4:'", message_text)
        self.assertIn("no block that closes with '-}'", message_text)


class StructuralRefusalTests(unittest.TestCase):
    """What the parser will not accept as a statement.

    Each of these is a message that would parse into something plausible if the
    parser guessed.  The assertion is that it does not guess.
    """

    def test_a_bare_opening_balance_tag_is_refused(self) -> None:
        with self.assertRaises(Mt940MalformedFileError) as caught:
            parse_mt940(build(opening=":60:C240115USD10000,00"))
        message_text = str(caught.exception)
        self.assertIn("no subfield letter", message_text)
        self.assertIn("refused rather than assumed to be final", message_text)

    def test_a_bare_closing_balance_tag_is_refused(self) -> None:
        with self.assertRaises(Mt940MalformedFileError) as caught:
            parse_mt940(build(closing=":62:C240116USD8500,50"))
        self.assertIn("no subfield letter", str(caught.exception))

    def test_a_statement_that_is_never_closed_is_refused(self) -> None:
        with self.assertRaises(Mt940MissingFieldError) as caught:
            parse_mt940(build(closing=None, available=None))
        message_text = str(caught.exception)
        self.assertIn("never closed", message_text)
        self.assertIn("truncated in carriage", message_text)

    def test_a_statement_with_no_opening_balance_is_refused(self) -> None:
        with self.assertRaises(Mt940MissingFieldError) as caught:
            parse_mt940(build(opening=None))
        message_text = str(caught.exception)
        self.assertIn(":60F: or :60M: opening balance", message_text)
        self.assertIn("found :61: instead", message_text)

    def test_a_statement_with_no_account_is_refused(self) -> None:
        # Without :25: the movements belong to no account, and a ledger row
        # that names no account is worse than no row.
        with self.assertRaises(Mt940MissingFieldError) as caught:
            parse_mt940(build(account=None))
        message_text = str(caught.exception)
        self.assertIn(":25: account identification", message_text)
        self.assertIn("found :28C: instead", message_text)

    def test_a_tag_after_the_closing_balance_is_refused(self) -> None:
        # Anything past the closing balance sits outside the balance identity,
        # so it would enter the ledger with nothing checking it.
        with self.assertRaises(Mt940MalformedFileError) as caught:
            parse_mt940(build(available=":13D:2401151200+0100"))
        message_text = str(caught.exception)
        self.assertIn(":13D: follows the closing balance", message_text)
        self.assertIn("only a :20: opening the next statement", message_text)

    def test_a_narrative_where_the_closing_balance_belongs_is_refused(self) -> None:
        with self.assertRaises(Mt940MissingFieldError) as caught:
            parse_mt940(
                message(
                    ":20:X", ":25:A", ":28C:1", ":60F:C240115USD0,", ":86:ORPHAN"
                )
            )
        self.assertIn("never closed", str(caught.exception))

    def test_input_that_does_not_open_with_a_reference_is_refused(self) -> None:
        with self.assertRaises(NotAnMt940Error) as caught:
            parse_mt940(message(":25:ACC", ":60F:C240115USD1,00"))
        message_text = str(caught.exception)
        self.assertIn("opens with :25:", message_text)
        self.assertIn("opens with a :20: transaction reference", message_text)

    def test_empty_input_is_refused(self) -> None:
        for text in ("", "   ", "\n\n", "  \n  \n"):
            with self.assertRaises(NotAnMt940Error) as caught:
                parse_mt940(text)
            self.assertIn("the input is empty", str(caught.exception))


class StatementLineRefusalTests(unittest.TestCase):
    """Marks and funds codes on :61:."""

    def test_an_mt942_interim_mark_is_named_as_such(self) -> None:
        # EC and ED are MT942 constructs.  A file carrying them is either an
        # MT942 mislabelled, or an MT940 emitted by something that confused the
        # two — and in both cases the amounts are interim, not settled.  The
        # message says so, because a bare "unrecognised mark" would send the
        # reader looking for a typo.
        with self.assertRaises(Mt940MalformedFileError) as caught:
            parse_mt940(build(debit=":61:240115EC2500,00NTRFREF001"))
        message_text = str(caught.exception)
        self.assertIn("EC and ED are MT942 interim marks", message_text)
        self.assertIn("line 5", message_text)

    def test_an_unrecognised_mark_is_refused(self) -> None:
        with self.assertRaises(Mt940MalformedFileError) as caught:
            parse_mt940(build(debit=":61:240115Z2500,00NTRFREF001"))
        self.assertIn("is not a statement line", str(caught.exception))

    def test_a_funds_code_disagreeing_with_the_currency_is_refused(self) -> None:
        # The funds code is the third character of the currency of the amount.
        # 'E' against a USD statement means this line may be in EUR, and a
        # line in the wrong currency added to the identity is a false balance.
        with self.assertRaises(Mt940CurrencyError) as caught:
            parse_mt940(build(debit=":61:240115DE2500,00NTRFREF001"))
        message_text = str(caught.exception)
        self.assertIn("the funds code is 'E'", message_text)
        self.assertIn("whose third character is 'D'", message_text)

    def test_a_funds_code_agreeing_with_the_currency_is_accepted(self) -> None:
        parsed = parse_mt940(build(debit=":61:240115DD2500,00NTRFREF001"))
        self.assertEqual(parsed.statements[0].lines[0].funds_code, "D")
        self.assertEqual(
            parsed.statements[0].balance_identity.status, ReconciliationStatus.balanced
        )


class CurrencyTests(unittest.TestCase):
    """One statement, one currency."""

    def test_opening_and_closing_in_different_currencies_are_refused(self) -> None:
        # The identity subtracts one from the other.  Two currencies do not
        # make it wrong, they make it meaningless.
        with self.assertRaises(Mt940CurrencyError) as caught:
            parse_mt940(build(closing=":62F:C240116EUR8500,50", available=None))
        message_text = str(caught.exception)
        self.assertIn("opening balance at line 4 is in USD", message_text)
        self.assertIn("closing balance at line 11 is in EUR", message_text)

    def test_an_available_balance_in_another_currency_is_refused(self) -> None:
        with self.assertRaises(Mt940CurrencyError) as caught:
            parse_mt940(build(available=":64:C240116EUR8500,50"))
        message_text = str(caught.exception)
        self.assertIn("the :64: balance is in EUR", message_text)
        self.assertIn("one of them is not this account's", message_text)

    def test_a_forward_balance_in_another_currency_is_refused(self) -> None:
        with self.assertRaises(Mt940CurrencyError) as caught:
            parse_mt940(build() + "\n:65:C240117EUR8500,50")
        self.assertIn("the :65: balance is in EUR", str(caught.exception))

    def test_an_unrecognised_currency_is_refused(self) -> None:
        with self.assertRaises(Mt940CurrencyError) as caught:
            parse_mt940(
                build(
                    opening=":60F:C240115ZZZ10000,00",
                    closing=":62F:C240116ZZZ8500,50",
                    available=None,
                )
            )
        self.assertIn("ZZZ is not a recognised ISO 4217 currency", str(caught.exception))

    def test_statements_in_a_file_may_differ_in_currency(self) -> None:
        # The constraint is per statement, not per file: a bank sends a USD
        # statement and a EUR statement in one carriage every day.
        parsed = parse_mt940(
            build()
            + "\n"
            + message(
                ":20:STMT002",
                ":25:GB29NWBK60161331926820",
                ":28C:00124/00001",
                ":60F:C240115EUR500,00",
                ":62F:C240115EUR500,00",
            )
        )
        self.assertEqual([s.currency for s in parsed.statements], ["USD", "EUR"])
        self.assertEqual(parsed.reconciliation_status, ReconciliationStatus.balanced)


class NarrativeFidelityTests(unittest.TestCase):
    """:86: is carried, not interpreted.

    The narrative is unstructured and every bank fills it differently.
    Parsing it would mean inventing a structure the
    format does not have and attributing the invention to the bank.  So it is
    stored verbatim and left for a later, separately-labelled layer.
    """

    def setUp(self) -> None:
        self.parsed = parse_mt940(build())

    def test_a_line_narrative_keeps_its_line_breaks(self) -> None:
        self.assertEqual(
            self.parsed.statements[0].lines[0].information,
            "PAYMENT TO ACME LTD\nINVOICE 4471",
        )

    def test_leading_and_trailing_spaces_inside_a_narrative_survive(self) -> None:
        # Column position carries meaning in some banks' narratives.  Stripping
        # it is a silent edit to evidence.
        parsed = parse_mt940(
            message(
                ":20:X",
                ":25:A",
                ":28C:1",
                ":60F:C240115USD0,",
                ":61:240115C1,00NTRFR",
                ":86:LINE ONE",
                "  SPACED  ",
                ":62F:C240115USD1,00",
            )
        )
        self.assertEqual(
            parsed.statements[0].lines[0].information, "LINE ONE\n  SPACED  "
        )

    def test_a_narrative_before_the_closing_balance_belongs_to_its_line(self) -> None:
        self.assertEqual(self.parsed.statements[0].lines[1].information, "DEPOSIT")
        self.assertIsNone(self.parsed.statements[0].information)

    def test_a_narrative_after_the_closing_balance_belongs_to_the_statement(self) -> None:
        # Same tag, two meanings, decided only by where it sits.  Attaching a
        # statement-level narrative to the last transaction would put words
        # about the whole period onto one payment.
        parsed = parse_mt940(build() + "\n:86:STATEMENT LEVEL INFO")
        self.assertEqual(parsed.statements[0].information, "STATEMENT LEVEL INFO")
        self.assertEqual(parsed.statements[0].lines[1].information, "DEPOSIT")

    def test_the_narrative_is_not_parsed_into_fields(self) -> None:
        # A narrative in the German structured convention is still stored as
        # written.  Reading '?20' as a field here would attribute a structure
        # to the bank that this parser only guessed at.
        text = "?00GUTSCHRIFT?100000?20EREF+INV4471?21SVWZ+ACME"
        parsed = parse_mt940(
            message(
                ":20:X",
                ":25:A",
                ":28C:1",
                ":60F:C240115USD0,",
                ":61:240115C1,00NTRFR",
                f":86:{text}",
                ":62F:C240115USD1,00",
            )
        )
        self.assertEqual(parsed.statements[0].lines[0].information, text)


class OptionalFieldTests(unittest.TestCase):
    """Fields SWIFT marks optional, read when present and absent when not."""

    def test_a_related_reference_is_read(self) -> None:
        parsed = parse_mt940(build(reference=":20:STMT001\n:21:RELATED9"))
        self.assertEqual(parsed.statements[0].related_reference, "RELATED9")

    def test_a_missing_related_reference_is_none(self) -> None:
        self.assertIsNone(parse_mt940(build()).statements[0].related_reference)

    def test_the_two_line_account_form_splits_identifier_from_code(self) -> None:
        parsed = parse_mt940(
            build(account=":25P:GB29NWBK60161331926819\nNWBKGB2L")
        )
        statement = parsed.statements[0]
        self.assertEqual(statement.account_identification, "GB29NWBK60161331926819")
        self.assertEqual(statement.account_identifier_code, "NWBKGB2L")

    def test_a_statement_number_without_a_sequence_leaves_the_sequence_unset(self) -> None:
        # ':28:00123' states a statement number and no page.  Defaulting the
        # sequence to 1 would assert a page the bank did not.
        parsed = parse_mt940(build(statement_number=":28:00123"))
        self.assertEqual(parsed.statements[0].statement_number, "00123")
        self.assertIsNone(parsed.statements[0].sequence_number)

    def test_an_available_balance_is_read(self) -> None:
        balance = parse_mt940(build()).statements[0].closing_available_balance
        self.assertIsNotNone(balance)
        self.assertEqual(balance.amount.minor_units, 850050)
        self.assertEqual(balance.tag, "64")

    def test_forward_available_balances_accumulate_in_order(self) -> None:
        parsed = parse_mt940(
            build() + "\n:65:C240117USD9000,00\n:65:C240118USD9500,00"
        )
        forward = parsed.statements[0].forward_available_balances
        self.assertEqual([b.amount.minor_units for b in forward], [900000, 950000])
        self.assertEqual([b.date for b in forward], ["240117", "240118"])

    def test_no_forward_balances_is_an_empty_tuple(self) -> None:
        self.assertEqual(parse_mt940(build()).statements[0].forward_available_balances, ())

    def test_supplementary_details_are_kept_apart_from_the_narrative(self) -> None:
        # The continuation of :61: is the bank's own detail about the entry;
        # :86: is its narrative.  Merging them would make it impossible to say
        # afterwards which the bank had put where.
        line = parse_mt940(build()).statements[0].lines[0]
        self.assertEqual(line.supplementary_details, "SUPPLEMENTARY DETAIL")
        self.assertEqual(line.information, "PAYMENT TO ACME LTD\nINVOICE 4471")

    def test_an_institution_reference_is_split_on_the_double_slash(self) -> None:
        line = parse_mt940(build()).statements[0].lines[0]
        self.assertEqual(line.account_owner_reference, "REF001")
        self.assertEqual(line.institution_reference, "BANKREF1")

    def test_a_reference_without_an_institution_part_leaves_it_unset(self) -> None:
        line = parse_mt940(build(credit=":61:2401160116C1000,50NTRFREF002")).statements[0].lines[1]
        self.assertEqual(line.account_owner_reference, "REF002")
        self.assertIsNone(line.institution_reference)

    def test_an_entry_date_is_read_when_present_and_absent_when_not(self) -> None:
        with_entry = parse_mt940(build()).statements[0].lines[0]
        self.assertEqual(with_entry.value_date, "240115")
        self.assertEqual(with_entry.entry_date, "0115")
        without = parse_mt940(
            build(debit=":61:240115DD2500,00NTRFREF001")
        ).statements[0].lines[0]
        self.assertEqual(without.value_date, "240115")
        self.assertIsNone(without.entry_date)


class MultiStatementTests(unittest.TestCase):
    """Several statements in one carriage."""

    _SECOND = (
        ":20:STMT002",
        ":25:GB29NWBK60161331926820",
        ":28C:00124/00001",
        ":60F:C240116USD500,00",
        ":61:240116C250,00NTRFREF003",
        ":62F:C240116USD750,00",
    )

    def two(self, *closing: str) -> str:
        body = list(self._SECOND)
        if closing:
            body[-1] = closing[0]
        return build() + "\n" + message(*body)

    def test_each_statement_is_read_separately(self) -> None:
        parsed = parse_mt940(self.two())
        self.assertEqual(
            [s.transaction_reference for s in parsed.statements], ["STMT001", "STMT002"]
        )
        self.assertEqual([len(s.lines) for s in parsed.statements], [2, 1])

    def test_the_file_aggregates_every_line_in_order(self) -> None:
        parsed = parse_mt940(self.two())
        self.assertEqual(
            [line.account_owner_reference for line in parsed.lines],
            ["REF001", "REF002", "REF003"],
        )

    def test_one_failing_statement_governs_the_whole_file(self) -> None:
        # The weakest link, not the average.  A file reported balanced because
        # most of it balanced would be the single most dangerous thing this
        # module could say.
        parsed = parse_mt940(self.two(":62F:C240116USD9999,00"))
        self.assertEqual(
            [s.balance_identity.status for s in parsed.statements],
            [ReconciliationStatus.balanced, ReconciliationStatus.unbalanced],
        )
        self.assertEqual(parsed.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertEqual(parsed.proof_class, ProofClass.p3)

    def test_a_file_of_sound_statements_is_balanced(self) -> None:
        parsed = parse_mt940(self.two())
        self.assertEqual(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertEqual(parsed.proof_class, ProofClass.p1)


class WeakestTests(unittest.TestCase):
    """The rule that rolls statement outcomes up to a file outcome."""

    def test_nothing_to_roll_up_is_not_attempted(self) -> None:
        # Deliberately not 'balanced'.  An empty file has not passed a check;
        # it has not taken one.
        self.assertEqual(_weakest([]), ReconciliationStatus.not_attempted)

    def test_all_balanced_is_balanced(self) -> None:
        self.assertEqual(
            _weakest([ReconciliationStatus.balanced, ReconciliationStatus.balanced]),
            ReconciliationStatus.balanced,
        )

    def test_one_unbalanced_governs(self) -> None:
        self.assertEqual(
            _weakest([ReconciliationStatus.balanced, ReconciliationStatus.unbalanced]),
            ReconciliationStatus.unbalanced,
        )

    def test_unavailable_outranks_balanced(self) -> None:
        self.assertEqual(
            _weakest([ReconciliationStatus.balanced, ReconciliationStatus.unavailable]),
            ReconciliationStatus.unavailable,
        )

    def test_not_attempted_outranks_balanced(self) -> None:
        self.assertEqual(
            _weakest([ReconciliationStatus.balanced, ReconciliationStatus.not_attempted]),
            ReconciliationStatus.not_attempted,
        )


class DecodeTests(unittest.TestCase):
    """What may be handed to the parser."""

    def test_bytes_bytearray_and_str_read_identically(self) -> None:
        text = build()
        expected = parse_mt940(text).statements
        self.assertEqual(parse_mt940(text.encode("utf-8")).statements, expected)
        self.assertEqual(parse_mt940(bytearray(text.encode("utf-8"))).statements, expected)

    def test_bytes_that_are_not_utf8_are_refused(self) -> None:
        with self.assertRaises(Mt940MalformedFileError) as caught:
            parse_mt940(b"\xff\xfe:20:X")
        self.assertIn("is not valid UTF-8", str(caught.exception))

    def test_anything_other_than_text_or_bytes_is_refused(self) -> None:
        # Refused as a malformed file rather than as a TypeError, matching
        # parse_bai2: a caller handing this parser the wrong thing is a caller
        # whose ingest has gone wrong, and it should land in the same place as
        # every other reason a file could not be read.
        for value in (12345, None, [":20:X"], {"a": 1}):
            with self.assertRaises(Mt940MalformedFileError) as caught:
                parse_mt940(value)
            self.assertIn("parse_mt940 takes bytes or str", str(caught.exception))

    def test_the_refused_type_is_named(self) -> None:
        with self.assertRaises(Mt940MalformedFileError) as caught:
            parse_mt940(12345)
        self.assertIn("got int", str(caught.exception))

    def test_a_file_over_the_ceiling_is_refused_before_it_is_parsed(self) -> None:
        # The ceiling exists so that a mis-sent archive cannot exhaust memory
        # on the way to being refused for not being an MT940 at all.
        with self.assertRaises(Mt940MalformedFileError) as caught:
            parse_mt940(b"x" * (MT940_MAX_FILE_BYTES + 1))
        message_text = str(caught.exception)
        self.assertIn(f"is {MT940_MAX_FILE_BYTES + 1} bytes", message_text)
        self.assertIn(f"over the {MT940_MAX_FILE_BYTES}-byte ceiling", message_text)

    def test_the_ceiling_is_sixty_four_mebibytes(self) -> None:
        self.assertEqual(MT940_MAX_FILE_BYTES, 67108864)


class AdmissibilityTests(unittest.TestCase):
    """The interface the downstream layers read."""

    def test_a_clean_file_carries_no_reservations(self) -> None:
        self.assertEqual(parse_mt940(build()).admissibility_reservations, ())

    def test_reservations_are_a_tuple_for_interface_parity(self) -> None:
        # camt.053 and BAI2 both expose this, and a caller that has to ask
        # which parser produced a file before reading its reservations has no
        # interface at all.
        self.assertIsInstance(parse_mt940(build()).admissibility_reservations, tuple)

    def test_the_locator_records_that_the_format_has_no_pages(self) -> None:
        # A wire format has no page or rectangle to point at.  Saying so
        # explicitly is what stops a later exhibit layer from inventing one.
        parsed = parse_mt940(build())
        for locator in (
            parsed.statements[0].locator,
            parsed.statements[0].lines[0].locator,
            parsed.statements[0].opening_balance.locator,
        ):
            self.assertIs(locator, MT940_LOCATOR)
            self.assertEqual(locator.kind, LocatorKind.not_positional)
            self.assertIsNone(locator.page_number)
            self.assertIsNone(locator.rectangle)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
