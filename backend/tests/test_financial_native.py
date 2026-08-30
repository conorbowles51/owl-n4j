"""Tests for the Layer 0 adapter that turns a native parse into ledger rows.

The corpus limitation that opens the four parser suites applies here and is
worse, not better.  Those suites at least test a reading of a published
specification; this one tests a reading of four readings.  Every fixture below
is built by importing the parser suites' own builders, so nothing here is
independent evidence that the parsers are right.  What it is evidence for is
narrower and still worth having: that the seam between a parser and the ledger
loses nothing, invents nothing, and records where every value came from.

Importing the builders rather than restating them is deliberate.  A copy of the
NACHA fixed-width record layout in this file would drift from the one in
``test_financial_nacha`` the first time either changed, and the two would then
disagree silently — the worst possible failure for a fixture, because a test
that builds the wrong file still passes.  Importing means a builder that
changes breaks these tests loudly, which is the correct outcome: this module's
claims are *about* what those builders produce.

Three groups of tests carry most of the weight.

:class:`CenturyResolutionTests` pins the module's second design decision.  The
window is required because three of the four formats write two-digit years and
none carries the century, and the 99-year invariant is what makes resolution a
derivation rather than a preference.  The tests assert the four boundary
readings (``89``, ``90``, ``00``, ``99`` against a 1990–2089 window), that a
100-year window is refused at construction rather than at use, and — the case
most likely to be got wrong by a later change — that the window constrains the
*year* and not the date, so a statement's January entries remain readable in an
engagement that began in June.

:class:`PartitionTests` pins the third.  Every row a parser produced lands in
exactly one of ``rows`` or ``unmapped`` with a contiguous index across both, so
that "this file had forty entries and produced thirty-eight rows" is a
question this object can answer.  The invariant is asserted both by holding on
real files and by failing on a tampered one; a test that only checked the happy
path would pass against a :meth:`check_partition` that returned unconditionally.

:class:`SniffTests` pins the fourth.  Detection evaluates all four predicates
and requires exactly one claimant, so ``test_a_file_two_formats_claim_is_a_
refusal`` is the test that would fail if anyone reintroduced first-match
precedence — which is the tempting simplification and the one that makes the
answer a property of this file's dictionary order rather than of the evidence.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import unittest

from postgres.models.enums import (
    DateSource,
    ExtractionLayer,
    ReconciliationStatus,
    TransactionDirection,
)
from services.financial.locators import LocatorKind
from services.financial.proof_class import ProofClass, SourceShape
from services.financial.native import (
    CENTURY_WINDOW_MAX_SPAN_YEARS,
    AmbiguousFormatError,
    CenturyWindow,
    CenturyWindowError,
    DateResolutionError,
    NativeError,
    NativeFormat,
    NativeReading,
    UnrecognisedFormatError,
    detect_format,
    parser_name,
    parser_version,
    read_native,
    resolve_mmdd_near,
    sniff,
)

# The four parser suites' own fixture builders.  See the module docstring for
# why these are imported rather than restated.
from tests.test_financial_bai2 import build as bai2_build
from tests.test_financial_camt053 import build as camt_build, ntry, stmt
from tests.test_financial_mt940 import build as mt940_build, message, minimal
from tests.test_financial_nacha import (
    batch_control,
    batch_header,
    entry,
    file_control,
    file_header,
    joined,
)

D = datetime.date

#: A window wide enough for every fixture in the four parser suites, whose
#: dates run 2024 to 2026.  Named rather than repeated so that a fixture drifting
#: out of it is one edit to fix and not thirty.
WINDOW = CenturyWindow(D(2020, 1, 1), D(2029, 12, 31))


def camt_bytes(**kwargs) -> bytes:
    return camt_build(**kwargs)


def bai2_bytes(**overrides: str) -> bytes:
    return bai2_build(**overrides).encode("utf-8")


def mt940_bytes(**overrides) -> bytes:
    return mt940_build(**overrides).encode("utf-8")


def nacha_bytes(records) -> bytes:
    return joined(records).encode("utf-8")


NACHA_SIMPLE = [
    file_header(),
    batch_header(),
    entry(),
    batch_control(),
    file_control(),
]


class NativeTestCase(unittest.TestCase):
    def assertRefuses(self, exception, fragment: str, callable_, *args, **kwargs):
        """Assert both the type of a refusal and what it says.

        The message matters as much as the type, for the reason
        ``test_financial_nacha`` gives: a test that checks only the type passes
        when the code refuses for a different reason than the one under test.
        """
        with self.assertRaises(exception) as caught:
            callable_(*args, **kwargs)
        self.assertIn(fragment, str(caught.exception))


# ---------------------------------------------------------------------------
# The century window
# ---------------------------------------------------------------------------


class CenturyWindowConstructionTests(NativeTestCase):
    """What a window may be, decided when it is built rather than when it is used."""

    def test_a_window_records_the_span_it_covers(self) -> None:
        window = CenturyWindow(D(2019, 6, 1), D(2024, 5, 31))
        self.assertEqual(window.span_years, 5)

    def test_the_widest_admissible_window_is_ninety_nine_years(self) -> None:
        window = CenturyWindow(D(1990, 1, 1), D(2089, 12, 31))
        self.assertEqual(window.span_years, CENTURY_WINDOW_MAX_SPAN_YEARS)

    def test_a_hundred_year_window_is_refused_at_construction(self) -> None:
        """The refusal is at construction because the defect is in the window.

        A window that spans a century cannot resolve *any* two-digit year, so
        deferring the complaint to the first date read would report it as a
        problem with a row.
        """
        self.assertRefuses(
            CenturyWindowError,
            "names two calendar years",
            CenturyWindow,
            D(1990, 1, 1),
            D(2090, 1, 1),
        )

    def test_an_inverted_window_is_refused(self) -> None:
        self.assertRefuses(
            CenturyWindowError,
            "precedes earliest",
            CenturyWindow,
            D(2024, 1, 1),
            D(2020, 1, 1),
        )

    def test_a_timestamp_bound_is_refused_rather_than_truncated(self) -> None:
        """``datetime`` subclasses ``date``, so this needs its own guard.

        A timestamp carries a zone or pointedly does not, and taking one
        silently would answer a timezone question the window has no basis to
        answer.
        """
        stamp = datetime.datetime(2020, 1, 1, 12, 0)
        self.assertRefuses(
            CenturyWindowError, "earliest is datetime", CenturyWindow, stamp, D(2029, 1, 1)
        )
        self.assertRefuses(
            CenturyWindowError, "latest is datetime", CenturyWindow, D(2020, 1, 1), stamp
        )

    def test_a_non_date_bound_is_refused(self) -> None:
        self.assertRefuses(
            CenturyWindowError, "earliest is str", CenturyWindow, "2020-01-01", D(2029, 1, 1)
        )

    def test_a_window_is_frozen(self) -> None:
        window = CenturyWindow(D(2020, 1, 1), D(2029, 12, 31))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            window.earliest = D(1999, 1, 1)  # type: ignore[misc]


class CenturyResolutionTests(NativeTestCase):
    """Two digits to a year, computed rather than preferred.

    The window is the widest one admissible, which is where the arithmetic is
    least forgiving: at 99 years the answer flips century between two adjacent
    two-digit years, and getting the comparison off by one puts a 1990
    statement in 2090.
    """

    def setUp(self) -> None:
        self.window = CenturyWindow(D(1990, 1, 1), D(2089, 12, 31))

    def test_the_four_readings_at_the_edges_of_a_full_window(self) -> None:
        self.assertEqual(self.window.resolve_year(89, context="t"), 2089)
        self.assertEqual(self.window.resolve_year(90, context="t"), 1990)
        self.assertEqual(self.window.resolve_year(0, context="t"), 2000)
        self.assertEqual(self.window.resolve_year(99, context="t"), 1999)

    def test_a_year_outside_a_narrow_window_is_refused(self) -> None:
        narrow = CenturyWindow(D(2020, 1, 1), D(2024, 12, 31))
        self.assertEqual(narrow.resolve_year(24, context="t"), 2024)
        self.assertRefuses(
            DateResolutionError,
            "has no reading between 2020 and 2024",
            narrow.resolve_year,
            25,
            context="t",
        )

    def test_a_number_that_is_not_two_digits_is_refused(self) -> None:
        for value in (-1, 100, 1990):
            self.assertRefuses(
                DateResolutionError,
                "is not a two-digit year",
                self.window.resolve_year,
                value,
                context="t",
            )

    def test_the_window_constrains_the_year_and_not_the_date(self) -> None:
        """A mid-year engagement must still read its statement's January.

        This is the test that would fail under the tempting alternative of
        requiring the resolved date to fall between the two bounds.  Most
        engagements start mid-year, so that alternative would make the opening
        entries of the first statement unreadable.
        """
        window = CenturyWindow(D(2019, 6, 1), D(2024, 5, 31))
        self.assertEqual(window.resolve_yymmdd("190104", context="t"), D(2019, 1, 4))
        self.assertEqual(window.resolve_yymmdd("241231", context="t"), D(2024, 12, 31))

    def test_the_twenty_ninth_of_february_turns_on_the_window(self) -> None:
        """``000229`` is a date in 2000 and is not one in 1900.

        Nothing in a BAI2 or NACHA file distinguishes the two, which is the
        clearest available demonstration that the century is an assumption
        from outside the document rather than something read from it.
        """
        modern = CenturyWindow(D(2000, 1, 1), D(2029, 12, 31))
        self.assertEqual(modern.resolve_yymmdd("000229", context="t"), D(2000, 2, 29))

        victorian = CenturyWindow(D(1900, 1, 1), D(1929, 12, 31))
        self.assertRefuses(
            DateResolutionError,
            "1900-02-29 is not a date",
            victorian.resolve_yymmdd,
            "000229",
            context="t",
        )

    def test_a_malformed_six_digit_date_is_refused(self) -> None:
        for text in ("", "2401", "24011", "2401155", "24O115", "24-01-15"):
            self.assertRefuses(
                DateResolutionError,
                "is not a six-digit YYMMDD date",
                self.window.resolve_yymmdd,
                text,
                context="t",
            )

    def test_six_digits_that_are_not_a_calendar_date_are_refused(self) -> None:
        self.assertRefuses(
            DateResolutionError,
            "is not a date",
            self.window.resolve_yymmdd,
            "241332",
            context="t",
        )

    def test_the_context_a_caller_supplies_reaches_the_message(self) -> None:
        """The message has to say which field failed, not merely that one did.

        A file with two hundred dates in it and a refusal that names none of
        them is a refusal a reviewer cannot act on.
        """
        self.assertRefuses(
            DateResolutionError,
            "BAI2 group at line 2 as-of date",
            self.window.resolve_yymmdd,
            "bad",
            context="BAI2 group at line 2 as-of date",
        )


class MmddResolutionTests(NativeTestCase):
    """MT940's yearless entry date, read against the value date beside it."""

    def test_the_same_year_wins_when_it_is_nearest(self) -> None:
        self.assertEqual(resolve_mmdd_near("0701", D(2024, 1, 1), context="t"), D(2024, 7, 1))

    def test_a_december_entry_date_reads_back_across_the_new_year(self) -> None:
        """The case the function exists for.

        A statement dated 2 January carrying an entry date of 31 December means
        the December just past, not the one eleven months ahead.  Reading the
        value date's year onto it would move the entry a year forward.
        """
        self.assertEqual(resolve_mmdd_near("1231", D(2024, 1, 2), context="t"), D(2023, 12, 31))

    def test_a_january_entry_date_reads_forward_across_the_new_year(self) -> None:
        self.assertEqual(resolve_mmdd_near("0101", D(2024, 12, 31), context="t"), D(2025, 1, 1))

    def test_the_twenty_ninth_of_february_skips_a_common_year(self) -> None:
        """0229 beside a 2023 value date is 2024, because 2023 has no such day.

        The candidate is skipped rather than clamped to the 28th: a date the
        format did not state is not one to manufacture.
        """
        self.assertEqual(resolve_mmdd_near("0229", D(2023, 3, 1), context="t"), D(2024, 2, 29))

    def test_a_leap_day_with_no_leap_year_in_reach_is_refused(self) -> None:
        """Needs three consecutive common years, which 2021-2023 are.

        A value date in 2023 is not the case: it reaches 2024, and 0229 there
        is a real day.  The refusal only bites where no candidate year has the
        day at all, and the message names the three years it looked in so the
        reader can see that for themselves rather than take it on trust.
        """
        self.assertRefuses(
            DateResolutionError,
            "02-29 is not a date in 2021, 2022 or 2023",
            resolve_mmdd_near,
            "0229",
            D(2022, 7, 1),
            context="t",
        )

    def test_a_leap_day_within_reach_of_a_leap_year_is_resolved(self) -> None:
        """The near miss beside the refusal above, so the rule is not read too wide."""
        self.assertEqual(resolve_mmdd_near("0229", D(2023, 7, 1), context="t"), D(2024, 2, 29))

    def test_a_tie_goes_to_the_earlier_date(self) -> None:
        """Exercised so the rule is fixed rather than merely written down.

        A tie needs the value date exactly 183 days from the same month-day in
        two adjacent years, which takes a 366-day gap; it will not occur in
        real evidence.  The rule exists to make the function total, and a total
        function whose tiebreak is untested is one whose tiebreak can silently
        invert.
        """
        near = D(2023, 8, 31)
        self.assertEqual((D(2024, 3, 1) - near).days, 183)
        self.assertEqual((near - D(2023, 3, 1)).days, 183)
        self.assertEqual(resolve_mmdd_near("0301", near, context="t"), D(2023, 3, 1))

    def test_a_malformed_four_digit_date_is_refused(self) -> None:
        for text in ("", "070", "07011", "O701", "07-01"):
            self.assertRefuses(
                DateResolutionError,
                "is not a four-digit MMDD",
                resolve_mmdd_near,
                text,
                D(2024, 1, 1),
                context="t",
            )


# ---------------------------------------------------------------------------
# Parser identity
# ---------------------------------------------------------------------------


class ParserIdentityTests(NativeTestCase):
    """What gets written into ``parser_name`` and ``parser_version``."""

    def test_the_name_is_the_importable_module(self) -> None:
        self.assertEqual(parser_name(NativeFormat.camt053), "services.financial.camt053")
        self.assertEqual(parser_name(NativeFormat.nacha), "services.financial.nacha")

    def test_the_version_names_the_format_and_its_own_digest(self) -> None:
        value = parser_version(NativeFormat.bai2)
        prefix, _, digest = value.partition("+")
        self.assertEqual(prefix, "bai2")
        self.assertTrue(digest)
        self.assertTrue(
            all(character in "0123456789abcdef" for character in digest),
            f"digest is not hexadecimal: {value!r}",
        )

    def test_every_version_fits_the_column_it_is_written_to(self) -> None:
        """``FinancialSourceDocument.parser_version`` is ``String(32)``."""
        for fmt in NativeFormat:
            self.assertLessEqual(len(parser_version(fmt)), 32, fmt.value)

    def test_the_four_parsers_carry_four_different_digests(self) -> None:
        """The point of fingerprinting per module rather than per package.

        A package-wide digest would give all four the same value and change all
        four whenever any one of them was touched, so two documents read by
        byte-identical code would record different versions.

        Asserted on the digest half rather than the whole string, because the
        format prefix makes the four strings differ whatever the digest is: a
        version built from one package-wide fingerprint would still pass a
        distinctness check on the full value while recording exactly the thing
        this design exists to avoid.
        """
        digests = {parser_version(fmt).split("+", 1)[1] for fmt in NativeFormat}
        self.assertEqual(len(digests), len(NativeFormat))

    def test_the_version_is_stable_across_calls(self) -> None:
        self.assertEqual(
            parser_version(NativeFormat.mt940), parser_version(NativeFormat.mt940)
        )


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class SniffTests(NativeTestCase):
    """Which of the four a file is, decided by exclusive claim."""

    def test_each_format_is_claimed_by_itself_alone(self) -> None:
        for expected, data in (
            (NativeFormat.camt053, camt_bytes()),
            (NativeFormat.bai2, bai2_bytes()),
            (NativeFormat.mt940, mt940_bytes()),
            (NativeFormat.nacha, nacha_bytes(NACHA_SIMPLE)),
        ):
            with self.subTest(expected.value):
                self.assertEqual(sniff(data), (expected,))
                self.assertIs(detect_format(data), expected)

    def test_a_file_no_format_claims_is_a_refusal(self) -> None:
        self.assertRefuses(
            UnrecognisedFormatError,
            "no native parser claims this input",
            detect_format,
            b"Dear Sir,\n\nPlease find enclosed the statements you asked for.\n",
        )

    def test_an_empty_file_is_a_refusal(self) -> None:
        self.assertRefuses(
            UnrecognisedFormatError, "no native parser claims", detect_format, b""
        )

    def test_a_file_two_formats_claim_is_a_refusal(self) -> None:
        """Ambiguity is reported, not resolved by precedence.

        This is the test that fails if anyone replaces exclusive claim with
        first-match.  Under first-match this input reads as camt.053 because
        camt.053 happens to be declared first in :class:`NativeFormat`, which
        makes the answer a property of the declaration order rather than of the
        evidence.
        """
        contrived = (
            b'<?xml version="1.0"?>'
            b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">'
            b"<BkToCstmrStmt><Nrtv>{4:</Nrtv></BkToCstmrStmt></Document>"
        )
        self.assertEqual(
            sniff(contrived), (NativeFormat.camt053, NativeFormat.mt940)
        )
        self.assertRefuses(
            AmbiguousFormatError,
            "camt053, mt940 all claim this input",
            detect_format,
            contrived,
        )

    def test_naming_camt_in_a_narrative_does_not_make_a_file_camt(self) -> None:
        """Why the camt predicate opens on the angle bracket rather than the name.

        A bank's own description text is free-form and can say anything,
        including the name of another format: a BAI2 line reading "camt.053
        restatement" and an MT940 narrative quoting "BkToCstmrStmt" are both
        things a real statement can contain.  Matching on the signature strings
        alone would give camt.053 a second claim on each, and because claims
        are exclusive, two ordinary files would stop being readable at all.
        """
        bai2_naming_camt = bai2_bytes().replace(
            b"Deposit one", b"camt.053 restatement"
        )
        self.assertEqual(sniff(bai2_naming_camt), (NativeFormat.bai2,))
        self.assertIs(detect_format(bai2_naming_camt), NativeFormat.bai2)

        mt940_naming_camt = mt940_bytes().replace(
            b"PAYMENT TO ACME LTD", b"BkToCstmrStmt CAMT"
        )
        self.assertEqual(sniff(mt940_naming_camt), (NativeFormat.mt940,))
        self.assertIs(detect_format(mt940_naming_camt), NativeFormat.mt940)

    def test_a_utf_16_camt_file_is_still_recognised(self) -> None:
        """The case that motivates honouring byte-order marks at all.

        A camt.053 written by a Windows tool is very often UTF-16, and every
        character of its signature is invisible if the bytes are read one at a
        time.
        """
        encoded = camt_bytes().decode("utf-8").encode("utf-16")
        self.assertTrue(encoded.startswith(b"\xff\xfe") or encoded.startswith(b"\xfe\xff"))
        self.assertIs(detect_format(encoded), NativeFormat.camt053)

    def test_a_utf_8_bom_does_not_hide_the_signature(self) -> None:
        self.assertIs(detect_format(b"\xef\xbb\xbf" + camt_bytes()), NativeFormat.camt053)

    def test_a_short_line_beginning_101_is_not_a_nacha_file(self) -> None:
        """The width test is what stops ``101`` being a coincidence.

        Every NACHA record is exactly ninety-four characters.  Without the
        length check, any text file whose first line happened to start with
        those three digits would be handed to the ACH parser.
        """
        self.assertEqual(sniff(b"101 EASTERN AVENUE\nSUITE 4\n"), ())

    def test_a_bai2_claim_needs_the_format_comma(self) -> None:
        """``01`` alone is not a BAI2 header; ``01,`` is.

        A bare ``01`` at the head of a file is as likely to be a line number as
        a record code.
        """
        self.assertEqual(sniff(b"01 SENDER RECEIVER 240115\n"), ())
        self.assertEqual(sniff(b"01,SENDER,RECEIVER,240115,0800,1,80,,2/\n"), (NativeFormat.bai2,))

    def test_a_bare_mt940_statement_is_claimed_without_an_envelope(self) -> None:
        """Banks deliver MT940 both wrapped in SWIFT blocks and bare."""
        bare = mt940_bytes()
        self.assertNotIn(b"{4:", bare)
        self.assertIs(detect_format(bare), NativeFormat.mt940)

    def test_leading_blank_lines_do_not_hide_a_signature(self) -> None:
        self.assertIs(detect_format(b"\n\n   \n" + bai2_bytes()), NativeFormat.bai2)

    def test_a_non_ascii_byte_further_along_does_not_change_the_answer(self) -> None:
        """Decoding is lenient because all four signatures are ASCII.

        Refusing a file over an accented character in a payee's name would be a
        refusal about the wrong thing entirely.
        """
        mangled = bai2_bytes().replace(b"Deposit one", b"Caf\xe9 receipts")
        self.assertIs(detect_format(mangled), NativeFormat.bai2)


# ---------------------------------------------------------------------------
# Per-format adapters
# ---------------------------------------------------------------------------


class Camt053AdapterTests(NativeTestCase):
    """camt.053 entries as ledger rows."""

    def setUp(self) -> None:
        self.reading = read_native(camt_bytes(), window=WINDOW)

    def test_the_baseline_reads_as_three_booked_rows(self) -> None:
        self.assertIs(self.reading.format, NativeFormat.camt053)
        self.assertEqual(self.reading.row_count, 3)
        self.assertEqual(self.reading.unmapped, ())
        self.assertIs(self.reading.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(self.reading.proof_class, ProofClass.p0)
        self.assertIs(self.reading.source_shape, SourceShape.native_with_control_totals)

    def test_a_row_carries_the_fields_the_ledger_needs(self) -> None:
        row = self.reading.rows[0]
        self.assertEqual(row.row_index, 0)
        self.assertEqual(row.account_key, "GB29NWBK60161331926819")
        self.assertEqual(row.ordering_date, D(2026, 2, 10))
        self.assertIs(row.ordering_date_source, DateSource.posted)
        self.assertFalse(row.is_reversal)
        self.assertEqual(row.reading.currency, "USD")
        self.assertEqual(row.reading.amount_minor, 300000)
        self.assertIs(row.reading.direction, TransactionDirection.credit)
        self.assertEqual(row.reading.posted_date, D(2026, 2, 10))
        self.assertEqual(row.reading.value_date, D(2026, 2, 11))
        self.assertEqual(row.reading.bank_reference, "E1")

    def test_booking_date_orders_and_the_choice_is_recorded(self) -> None:
        """Posting orders because a statement's totals are drawn against it."""
        for row in self.reading.rows:
            self.assertIs(row.ordering_date_source, DateSource.posted)
            self.assertEqual(row.ordering_date, row.reading.posted_date)

    def test_the_debit_lands_on_the_debit_side_as_a_magnitude(self) -> None:
        """Direction is a field, not a sign.  ``RowReading`` refuses a negative."""
        debit = self.reading.rows[2]
        self.assertIs(debit.reading.direction, TransactionDirection.debit)
        self.assertEqual(debit.reading.amount_minor, 250000)

    def test_a_pending_entry_is_recorded_as_unmapped_rather_than_admitted(self) -> None:
        """The one error a statement reader must not make.

        A ``PDNG`` entry is the bank's statement of intent.  Admitting it as
        money that moved puts a transaction in the ledger that may never
        happen, and the index shows it was seen rather than lost.
        """
        entries = (
            ntry("3000.00", "CRDT", reference="E1")
            + ntry("2000.00", "CRDT", reference="E2", status="PDNG")
            + ntry("2500.00", "DBIT", reference="E3")
        )
        reading = read_native(camt_bytes(statements=stmt(entries=entries)), window=WINDOW)
        self.assertEqual(reading.row_count, 2)
        self.assertEqual(len(reading.unmapped), 1)
        skipped = reading.unmapped[0]
        self.assertEqual(skipped.row_index, 1)
        self.assertIn("is not BOOK", skipped.reason)
        self.assertIn("does not assert that money moved", skipped.reason)
        reading.check_partition()

    def test_a_reversal_indicator_reaches_the_row(self) -> None:
        entries = ntry("3000.00", "CRDT", reference="E1", reversal=True)
        reading = read_native(camt_bytes(statements=stmt(entries=entries)), window=WINDOW)
        self.assertTrue(reading.rows[0].is_reversal)

    def test_the_locator_says_the_format_has_no_positions(self) -> None:
        """``not_positional``, not ``unlocated``.

        A camt.053 file has no pages, so there is no coordinate to record.
        ``unlocated`` would say a reader looked for one and failed, which is a
        false statement about a format where there was never anything to look
        for.
        """
        locator = self.reading.rows[0].locator
        self.assertIs(locator.kind, LocatorKind.not_positional)
        self.assertIsNone(locator.page_number)

    def test_a_duplicate_message_is_held_back_from_auto_admission(self) -> None:
        """``DUPL`` and ``CODU`` say these entries have been stated before.

        The arithmetic of a duplicate is not merely sound, it is identical to
        the original's, so the reconciliation status stays balanced and the
        proof class is withheld instead.  Reporting an arithmetic failure that
        did not happen would send a reviewer hunting a discrepancy in a file
        that has none.
        """
        for indicator in ("DUPL", "CODU"):
            with self.subTest(indicator):
                statements = stmt().replace(
                    "<Acct>", f"<CpyDplctInd>{indicator}</CpyDplctInd><Acct>"
                )
                reading = read_native(camt_bytes(statements=statements), window=WINDOW)
                self.assertIs(reading.reconciliation_status, ReconciliationStatus.balanced)
                self.assertIs(reading.proof_class, ProofClass.p3)
                self.assertEqual(len(reading.admissibility_reservations), 1)
                self.assertIn(indicator, reading.admissibility_reservations[0])
                self.assertIn("count the same money twice", reading.admissibility_reservations[0])

    def test_a_copy_draws_no_reservation(self) -> None:
        """A copy is one assertion delivered to a second party, made once.

        Treating ``COPY`` like ``DUPL`` would withhold p0 from every statement
        a bank courtesy-copied to counsel, which is a large fraction of the
        statements that reach an investigation at all.
        """
        statements = stmt().replace("<Acct>", "<CpyDplctInd>COPY</CpyDplctInd><Acct>")
        reading = read_native(camt_bytes(statements=statements), window=WINDOW)
        self.assertEqual(reading.admissibility_reservations, ())
        self.assertIs(reading.proof_class, ProofClass.p0)

    def test_a_statement_with_no_indicator_draws_no_reservation(self) -> None:
        self.assertEqual(self.reading.admissibility_reservations, ())


class Bai2AdapterTests(NativeTestCase):
    """BAI2 ``16`` records as ledger rows."""

    def setUp(self) -> None:
        self.reading = read_native(bai2_bytes(), window=WINDOW)

    def test_the_baseline_reads_as_three_rows(self) -> None:
        self.assertIs(self.reading.format, NativeFormat.bai2)
        self.assertEqual(self.reading.row_count, 3)
        self.assertEqual(self.reading.unmapped, ())
        self.assertIs(self.reading.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(self.reading.proof_class, ProofClass.p0)

    def test_a_row_carries_the_fields_the_ledger_needs(self) -> None:
        row = self.reading.rows[0]
        self.assertEqual(row.account_key, "1234567890")
        self.assertEqual(row.reading.currency, "USD")
        self.assertEqual(row.reading.amount_minor, 5000)
        self.assertIs(row.reading.direction, TransactionDirection.credit)
        self.assertEqual(row.reading.transaction_type, "165")
        self.assertEqual(row.reading.bank_reference, "REF1")
        self.assertEqual(row.reading.description, "Deposit one")

    def test_the_group_as_of_date_is_the_row_date(self) -> None:
        """A ``16`` states no date; BAI2 puts it on the ``02`` above.

        The group's as-of date is not an approximation of the row's date, it is
        the only date the format asserts for that movement, and it is recorded
        as ``posted_date`` because "as of" is a posting statement.
        """
        for row in self.reading.rows:
            self.assertEqual(row.ordering_date, D(2024, 1, 15))
            self.assertIs(row.ordering_date_source, DateSource.posted)
            self.assertEqual(row.reading.posted_date, D(2024, 1, 15))

    def test_the_two_digit_year_is_resolved_through_the_window(self) -> None:
        """The same file reads as 1924 or 2024 depending only on the window."""
        old = read_native(bai2_bytes(), window=CenturyWindow(D(1920, 1, 1), D(1929, 12, 31)))
        self.assertEqual(old.rows[0].ordering_date, D(1924, 1, 15))

    def test_a_file_dated_outside_the_window_is_refused_outright(self) -> None:
        """Refused rather than recorded row by row, because the window is wrong.

        A window that cannot read this file's date cannot read any of its
        dates, so recording the failure per row would produce a file that
        parsed successfully and yielded nothing.
        """
        self.assertRefuses(
            DateResolutionError,
            "as-of date",
            read_native,
            bai2_bytes(),
            window=CenturyWindow(D(2030, 1, 1), D(2039, 12, 31)),
        )

    def test_a_type_code_with_no_direction_is_recorded_as_unmapped(self) -> None:
        """700 and above is local convention between two institutions.

        The parser reports ``None`` rather than guessing, and guessing here
        would be the same mistake one layer later — with the guess written into
        a ``NOT NULL`` column where nothing marks it as one.
        """
        data = bai2_bytes().replace(b"16,165,3000,0,REF2", b"16,720,3000,0,REF2")
        reading = read_native(data, window=WINDOW)
        self.assertEqual(reading.row_count, 2)
        self.assertEqual(len(reading.unmapped), 1)
        skipped = reading.unmapped[0]
        self.assertEqual(skipped.row_index, 1)
        self.assertIn("'720'", skipped.reason)
        self.assertIn("no side to land on", skipped.reason)
        reading.check_partition()

    def test_every_row_under_a_dateless_group_is_recorded_as_unmapped(self) -> None:
        """``ordering_date`` is ``NOT NULL`` and there is no other date to take."""
        data = bai2_bytes().replace(
            b"02,RECEIVER,BANK,1,240115,0800,USD,2/", b"02,RECEIVER,BANK,1,,0800,USD,2/"
        )
        reading = read_native(data, window=WINDOW)
        self.assertEqual(reading.row_count, 0)
        self.assertEqual(len(reading.unmapped), 3)
        self.assertEqual([row.row_index for row in reading.unmapped], [0, 1, 2])
        for row in reading.unmapped:
            self.assertIn("no as-of date", row.reason)
        reading.check_partition()

    def test_a_default_currency_reaches_the_bai2_parser(self) -> None:
        """The precedent this module's window follows.

        BAI2 may state no currency anywhere, so the parser already required the
        caller to supply one rather than assuming dollars.  The adapter passes
        it through unchanged.
        """
        reading = read_native(
            bai2_bytes(currency="", account_currency=""),
            window=WINDOW,
            default_currency="EUR",
        )
        self.assertEqual(reading.row_count, 3)
        for row in reading.rows:
            self.assertEqual(row.reading.currency, "EUR")

    def test_a_default_currency_is_accepted_and_ignored_by_the_others(self) -> None:
        """So a caller reading a mixed batch need not know the format first."""
        reading = read_native(camt_bytes(), window=WINDOW, default_currency="EUR")
        self.assertEqual(reading.rows[0].reading.currency, "USD")


class Mt940AdapterTests(NativeTestCase):
    """MT940 ``:61:`` lines as ledger rows."""

    def setUp(self) -> None:
        self.reading = read_native(mt940_bytes(), window=WINDOW)

    def test_the_baseline_reads_as_two_rows(self) -> None:
        self.assertIs(self.reading.format, NativeFormat.mt940)
        self.assertEqual(self.reading.row_count, 2)
        self.assertEqual(self.reading.unmapped, ())
        self.assertIs(self.reading.reconciliation_status, ReconciliationStatus.balanced)

    def test_mt940_is_p1_because_the_format_states_no_control_totals(self) -> None:
        """The deliberate asymmetry with the other three.

        MT940 carries an opening and a closing balance and nothing else: no
        entry count, no separate debit and credit sums.  A balance identity
        that holds is real evidence and it is weaker evidence, so the format
        tops out one class below the three that mandate totals.
        """
        self.assertIs(self.reading.source_shape, SourceShape.native_without_control_totals)
        self.assertIs(self.reading.proof_class, ProofClass.p1)

    def test_a_row_carries_the_fields_the_ledger_needs(self) -> None:
        row = self.reading.rows[0]
        self.assertEqual(row.account_key, "GB29NWBK60161331926819")
        self.assertEqual(row.reading.currency, "USD")
        self.assertEqual(row.reading.amount_minor, 250000)
        self.assertIs(row.reading.direction, TransactionDirection.debit)
        self.assertEqual(row.reading.transaction_type, "NTRF")
        self.assertEqual(row.reading.description, "PAYMENT TO ACME LTD\nINVOICE 4471")

    def test_value_date_orders_because_it_is_the_only_date_every_line_carries(self) -> None:
        """Entry date is optional in the format.

        Ordering by a field that is sometimes absent would sequence part of a
        statement one way and the rest another.
        """
        self.assertEqual(
            [row.ordering_date for row in self.reading.rows], [D(2024, 1, 15), D(2024, 1, 16)]
        )
        for row in self.reading.rows:
            self.assertIs(row.ordering_date_source, DateSource.value)
            self.assertEqual(row.ordering_date, row.reading.value_date)

    def test_the_entry_date_is_kept_as_the_posted_date(self) -> None:
        self.assertEqual(self.reading.rows[0].reading.posted_date, D(2024, 1, 15))
        self.assertEqual(self.reading.rows[1].reading.posted_date, D(2024, 1, 16))

    def test_the_bank_reference_is_the_institutions_and_not_the_owners(self) -> None:
        """A dispute is put to the bank, so the bank's reference is the one kept.

        The account owner's reference is what the customer called the payment;
        the institution's is what the bank will answer a query on.
        """
        self.assertEqual(self.reading.rows[0].reading.bank_reference, "BANKREF1")
        self.assertIsNone(self.reading.rows[1].reading.bank_reference)

    def test_a_line_with_no_entry_date_still_reads(self) -> None:
        """The entry date is optional, and its absence is not a defect."""
        body = ":61:240115D2500,00NTRFREF001"
        reading = read_native(minimal(body).encode("utf-8"), window=WINDOW)
        row = reading.rows[0]
        self.assertEqual(row.ordering_date, D(2024, 1, 15))
        self.assertIsNone(row.reading.posted_date)

    def test_a_reversal_mark_reaches_the_row(self) -> None:
        """``RD`` is a reversed debit: a credit that undoes one."""
        statement = message(
            ":20:REV",
            ":25:ACCOUNT",
            ":28C:1",
            ":60F:C240115USD100,00",
            ":61:2401150115RD2500,00NTRFREF001",
            ":62F:C240115USD2600,00",
        )
        reading = read_native(statement.encode("utf-8"), window=WINDOW)
        row = reading.rows[0]
        self.assertTrue(row.is_reversal)
        self.assertIs(row.reading.direction, TransactionDirection.credit)


class NachaAdapterTests(NativeTestCase):
    """NACHA ``6`` entry details as ledger rows."""

    def setUp(self) -> None:
        self.reading = read_native(nacha_bytes(NACHA_SIMPLE), window=WINDOW)

    def test_the_baseline_reads_as_one_row(self) -> None:
        self.assertIs(self.reading.format, NativeFormat.nacha)
        self.assertEqual(self.reading.row_count, 1)
        self.assertEqual(self.reading.unmapped, ())
        self.assertIs(self.reading.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(self.reading.proof_class, ProofClass.p0)

    def test_a_row_carries_the_fields_the_ledger_needs(self) -> None:
        row = self.reading.rows[0]
        self.assertEqual(row.reading.currency, "USD")
        self.assertEqual(row.reading.amount_minor, 150000)
        self.assertIs(row.reading.direction, TransactionDirection.credit)
        self.assertEqual(row.reading.transaction_type, "22")
        self.assertEqual(row.reading.bank_reference, "091000010000001")
        self.assertEqual(row.reading.description, "PAYROLL")

    def test_the_account_key_joins_the_routing_and_account_numbers(self) -> None:
        """An account number alone is not unique; two banks may issue the same one.

        The routing number carries its check digit, so the key is the full
        nine-digit number rather than the eight-digit prefix the record splits
        it into.
        """
        self.assertEqual(self.reading.rows[0].account_key, "021000021/111111")

    def test_nacha_is_the_only_format_with_a_structured_counterparty(self) -> None:
        """The ``6`` record carries a name field rather than a narrative.

        The other three bury the counterparty inside free text, if they carry
        it at all, so this is the one place ``counterparty_raw`` is populated
        without a layer of name extraction above it.
        """
        self.assertEqual(self.reading.rows[0].reading.counterparty_raw, "ALICE SMITH")
        for data in (camt_bytes(), bai2_bytes(), mt940_bytes()):
            reading = read_native(data, window=WINDOW)
            for row in reading.rows:
                self.assertIsNone(row.reading.counterparty_raw)

    def test_the_batch_effective_date_orders_and_is_recorded(self) -> None:
        """Not the file's creation date.

        A file transmitted days ahead of settlement was written on a day the
        money did not move.  The effective entry date is the day the originator
        asked for it to move, and it is the only date NACHA puts on an entry.
        """
        row = self.reading.rows[0]
        self.assertEqual(row.ordering_date, D(2026, 9, 1))
        self.assertIs(row.ordering_date_source, DateSource.effective)
        self.assertEqual(row.reading.effective_date, D(2026, 9, 1))
        self.assertIsNone(row.reading.posted_date)

    def test_a_prenotification_is_recorded_as_unmapped_rather_than_admitted(self) -> None:
        """The format's one genuinely counter-intuitive exclusion.

        A prenote carries a real routing number, a real account number and an
        amount of zero.  It exists to test that an account will accept a later
        entry, which is to say it asserts that money will *not* move under it.
        Admitting it would put a row in the ledger for a transaction that by
        definition never happened — and because it satisfies every control
        total, nothing in the arithmetic would object.
        """
        records = [
            file_header(),
            batch_header(),
            entry(code="23", cents=0),
            batch_control(count=1, entry_hash=2100002, debits=0, credits=0),
            file_control(count=1, entry_hash=2100002, debits=0, credits=0),
        ]
        reading = read_native(nacha_bytes(records), window=WINDOW)
        self.assertIs(reading.reconciliation_status, ReconciliationStatus.balanced)
        self.assertEqual(reading.row_count, 0)
        self.assertEqual(len(reading.unmapped), 1)
        self.assertIn("prenotification", reading.unmapped[0].reason)
        self.assertIn("asserts that no money moves", reading.unmapped[0].reason)
        reading.check_partition()

    def test_a_prenotification_also_draws_a_reservation_from_the_parser(self) -> None:
        """Two independent mechanisms, and both are wanted.

        The unmapped row explains why the ledger is one row short of the file.
        The reservation explains why a file whose totals all balance still must
        not auto-admit.
        """
        records = [
            file_header(),
            batch_header(),
            entry(code="23", cents=0),
            batch_control(count=1, entry_hash=2100002, debits=0, credits=0),
            file_control(count=1, entry_hash=2100002, debits=0, credits=0),
        ]
        reading = read_native(nacha_bytes(records), window=WINDOW)
        self.assertEqual(len(reading.admissibility_reservations), 1)
        self.assertIn("prenotification", reading.admissibility_reservations[0])
        self.assertIs(reading.proof_class, ProofClass.p3)

    def test_a_code_outside_the_direction_table_is_unmapped_not_guessed(self) -> None:
        """A separate guard from the prenotification one, and it is needed.

        ``25`` is not in NACHA's direction table and is not a prenotification
        either.  With a zero amount it blocks no control total, so the file
        still reconciles and still earns ``p0``: the arithmetic has nothing to
        object to.  What is missing is a side for the row to land on, and the
        ledger has no column for a transaction that is neither a debit nor a
        credit.  Recording it as unmapped says that plainly; picking a side
        would put a direction in the record that the file never stated.
        """
        records = [
            file_header(),
            batch_header(),
            entry(code="25", cents=0),
            batch_control(count=1, entry_hash=2100002, debits=0, credits=0),
            file_control(count=1, entry_hash=2100002, debits=0, credits=0),
        ]
        reading = read_native(nacha_bytes(records), window=WINDOW)
        self.assertIs(reading.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(reading.proof_class, ProofClass.p0)
        self.assertEqual(reading.admissibility_reservations, ())
        self.assertEqual(reading.row_count, 0)
        self.assertEqual(len(reading.unmapped), 1)
        self.assertIn("is not in NACHA's direction table", reading.unmapped[0].reason)
        self.assertIn("no side to land on", reading.unmapped[0].reason)
        reading.check_partition()

    def test_a_debit_entry_lands_on_the_debit_side(self) -> None:
        records = [
            file_header(),
            batch_header(service_class="225"),
            entry(code="27"),
            batch_control(service_class="225", debits=150000, credits=0),
            file_control(debits=150000, credits=0),
        ]
        reading = read_native(nacha_bytes(records), window=WINDOW)
        row = reading.rows[0]
        self.assertIs(row.reading.direction, TransactionDirection.debit)
        self.assertEqual(row.reading.amount_minor, 150000)


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------


class PartitionTests(NativeTestCase):
    """Rows in equals rows out, or the difference is recorded."""

    def test_the_invariant_holds_for_every_format(self) -> None:
        for label, data in (
            ("camt053", camt_bytes()),
            ("bai2", bai2_bytes()),
            ("mt940", mt940_bytes()),
            ("nacha", nacha_bytes(NACHA_SIMPLE)),
        ):
            with self.subTest(label):
                reading = read_native(data, window=WINDOW)
                reading.check_partition()
                self.assertEqual(
                    reading.parsed_row_count, len(reading.rows) + len(reading.unmapped)
                )

    def test_the_index_runs_across_both_lists_and_not_within_each(self) -> None:
        """A collector numbering the two lists separately would satisfy nothing.

        Here the pending entry is second of three, so the two mapped rows must
        be 0 and 2 rather than 0 and 1.  If the mapped list were numbered on its
        own, this would read 0 and 1 and the unmapped row's index would collide
        with a real one.
        """
        entries = (
            ntry("3000.00", "CRDT", reference="E1")
            + ntry("2000.00", "CRDT", reference="E2", status="PDNG")
            + ntry("2500.00", "DBIT", reference="E3")
        )
        reading = read_native(camt_bytes(statements=stmt(entries=entries)), window=WINDOW)
        self.assertEqual([row.row_index for row in reading.rows], [0, 2])
        self.assertEqual([row.row_index for row in reading.unmapped], [1])
        self.assertEqual(reading.parsed_row_count, 3)

    def test_a_broken_partition_is_reported_rather_than_tolerated(self) -> None:
        """Asserted by breaking it, because the happy path alone proves nothing.

        A :meth:`check_partition` that returned unconditionally would pass
        every other test in this class.
        """
        reading = read_native(camt_bytes(), window=WINDOW)
        duplicated = dataclasses.replace(
            reading,
            rows=reading.rows + (dataclasses.replace(reading.rows[0], row_index=0),),
        )
        self.assertRefuses(
            NativeError, "are not the contiguous run", duplicated.check_partition
        )

        gapped = dataclasses.replace(
            reading, rows=(dataclasses.replace(reading.rows[0], row_index=7),) + reading.rows[1:]
        )
        self.assertRefuses(NativeError, "missing from both lists", gapped.check_partition)

    def test_the_invariant_is_checked_on_every_read_and_not_only_in_tests(self) -> None:
        """``read_native`` calls it itself.

        The check is cheap and the failure it catches — a row counted twice or
        not at all — would otherwise surface much later as a total that is
        quietly wrong.
        """
        import inspect

        source = inspect.getsource(read_native)
        self.assertIn("check_partition()", source)


# ---------------------------------------------------------------------------
# The reading as a record
# ---------------------------------------------------------------------------


class ReadingTests(NativeTestCase):
    """What a caller gets back, and what it is safe to write down."""

    def test_every_reading_records_the_native_layer(self) -> None:
        """The field that lets a later reader tell read from inferred.

        Months after ingestion both are numbers in the same table, and `13`
        §2.1 grants the native layer its proof class on the strength of this
        field alone.
        """
        for data in (camt_bytes(), bai2_bytes(), mt940_bytes(), nacha_bytes(NACHA_SIMPLE)):
            reading = read_native(data, window=WINDOW)
            self.assertIs(reading.extraction_layer, ExtractionLayer.native)
            self.assertEqual(int(reading.extraction_layer), 0)

    def test_the_reading_records_which_parser_read_it(self) -> None:
        reading = read_native(camt_bytes(), window=WINDOW)
        self.assertEqual(reading.parser_name, "services.financial.camt053")
        self.assertEqual(reading.parser_version, parser_version(NativeFormat.camt053))

    def test_the_parsed_document_is_kept_for_anything_the_rows_dropped(self) -> None:
        """The adapter is lossy on purpose; the document beside it is not.

        A ledger row is a deliberate narrowing.  Keeping the parse means a
        later question about a field this module chose not to map is answerable
        without re-reading the file.
        """
        reading = read_native(nacha_bytes(NACHA_SIMPLE), window=WINDOW)
        # The field is ten characters wide and the fixture writes it with the
        # leading blank the format expects; the parser strips that padding, so
        # what survives is the routing number rather than the padded field.
        self.assertEqual(reading.document.immediate_destination, "021000021")
        self.assertEqual(len(reading.document.batches), 1)

    def test_the_readings_hash_and_cite(self) -> None:
        data = camt_bytes()
        reading = read_native(data, window=WINDOW)
        digest = hashlib.sha256(data).hexdigest()

        hashes = reading.content_hashes()
        self.assertEqual(len(hashes), reading.row_count)
        self.assertEqual(len(set(hashes)), reading.row_count)

        references = reading.ref_ids(digest)
        self.assertEqual(len(references), reading.row_count)
        self.assertEqual(len(set(references)), reading.row_count)

    def test_the_same_bytes_cite_the_same_way_twice(self) -> None:
        """References are content-derived, so re-ingestion reproduces them.

        A reference that changed on re-ingestion would break every citation in
        a report written against the first read.
        """
        data = bai2_bytes()
        digest = hashlib.sha256(data).hexdigest()
        first = read_native(data, window=WINDOW).ref_ids(digest)
        second = read_native(data, window=WINDOW).ref_ids(digest)
        self.assertEqual(first, second)

    def test_a_declared_format_overrides_detection(self) -> None:
        """For a format already known from outside the bytes."""
        reading = read_native(camt_bytes(), window=WINDOW, fmt=NativeFormat.camt053)
        self.assertIs(reading.format, NativeFormat.camt053)
        self.assertEqual(reading.row_count, 3)

    def test_a_wrongly_declared_format_fails_in_the_parser_it_names(self) -> None:
        """The override is trusted, and being wrong about it is loud.

        It hands the bytes to a parser that will refuse them, rather than
        silently producing nothing.
        """
        with self.assertRaises(Exception) as caught:
            read_native(camt_bytes(), window=WINDOW, fmt=NativeFormat.nacha)
        self.assertNotIsInstance(caught.exception, UnrecognisedFormatError)

    def test_a_reading_is_frozen(self) -> None:
        reading = read_native(camt_bytes(), window=WINDOW)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            reading.rows = ()  # type: ignore[misc]

    def test_the_row_lists_are_tuples_and_not_the_collectors_lists(self) -> None:
        """So a caller cannot append to a reading it was handed."""
        reading = read_native(camt_bytes(), window=WINDOW)
        self.assertIsInstance(reading.rows, tuple)
        self.assertIsInstance(reading.unmapped, tuple)
        self.assertIsInstance(reading.admissibility_reservations, tuple)

    def test_an_unreadable_file_refuses_before_it_reaches_a_parser(self) -> None:
        self.assertRefuses(
            UnrecognisedFormatError,
            "needs a layer above zero",
            read_native,
            b"not a bank file at all\n",
            window=WINDOW,
        )


class NativeRowTests(NativeTestCase):
    """The guards on a row, which are about what gets written to the column."""

    def setUp(self) -> None:
        self.row = read_native(camt_bytes(), window=WINDOW).rows[0]

    def test_a_timestamp_ordering_date_is_refused(self) -> None:
        """``ordering_date`` is a ``DATE``; a timestamp would be truncated silently."""
        with self.assertRaises(Exception) as caught:
            dataclasses.replace(self.row, ordering_date=datetime.datetime(2026, 2, 10, 9))
        self.assertIn("would be silently truncated", str(caught.exception))

    def test_a_source_that_is_not_a_date_source_is_refused(self) -> None:
        """The point of the field is that the choice was recorded, not inferred."""
        with self.assertRaises(Exception) as caught:
            dataclasses.replace(self.row, ordering_date_source="posted")
        self.assertIn("is not a", str(caught.exception))

    def test_a_row_is_frozen(self) -> None:
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.row.account_key = "other"  # type: ignore[misc]


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
