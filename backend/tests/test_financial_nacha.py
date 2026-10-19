"""Tests for the NACHA native parser.

The limitation that opens ``test_financial_camt053``, ``test_financial_bai2``
and ``test_financial_mt940`` applies here too, and is restated rather than
cross-referenced because it is the single most important thing to know about
this suite.  No corpus document backs any of it.  The ET-Fraud corpus carries
no ACH file, so every fixture below is constructed from the NACHA Operating
Rules record layouts rather than measured from evidence.  A fixture built by
the same reading of the specification as the parser shares the parser's blind
spots exactly: if the reading is wrong, the test passes and the parser is wrong
together.  Sourcing one real ACH file remains the blocking item, alongside the
camt.053, BAI2 and MT940 files already asked for.

There is one exception, and it is worth naming because it is the only external
check in any of the four suites.  :class:`RoutingCheckDigitTests` asserts the
ABA check digit algorithm against five routing numbers that exist in the world
and whose ninth digit was not chosen by this codebase.  If the weights or the
modulus were wrong, those five would fail.  It establishes one small thing
about one small function, and it establishes it against reality rather than
against a re-reading of the same document — which is more than the rest of
this file can say.

What these tests establish beyond that is that the parser is self-consistent,
that it refuses what it cannot read, and — the point most specific to this
format — that the checks NACHA offers are genuinely independent of one another.
Three tests carry most of that weight:

``test_direction_error_fails_both_money_totals`` is the claim that makes NACHA
stronger than its three siblings.  Every other format states a net, and a net
conceals a compensating pair.  Here the two sides are declared separately, so
reading a debit as a credit moves the amount out of one declared figure and
into the other, and both halves fail in opposite directions by the same amount.
The test asserts on the two deltas, not merely on the status, because the
status alone would pass if only one side had failed.

``test_retargeted_entry_fails_only_the_hash`` is the converse: an entry
readdressed to a different bank with its amount untouched passes both money
totals and fails only the entry hash.  Together the two tests establish that
the money checks and the hash see different things, which is the whole reason
the format carries both.

``test_a_batch_that_lies_fails_only_at_batch_level`` fixes the decision that
the file trailer is computed from what the batches *declared* rather than from
their contents.  That is a real design choice with a real alternative, so it is
pinned by a test that would fail under the alternative.

Three conventions are held throughout, unchanged from the sibling suites.
Every expectation is asserted against a literal rather than against the
constant the module uses, since asserting ``NACHA_RECORD_LENGTH ==
NACHA_RECORD_LENGTH`` establishes nothing.  Refusals are asserted on their
*message* and not merely on the exception type: two BAI2 tests were found
passing for the wrong reason when they checked only that something was raised.
And the refusal paths are tested at least as heavily as the success path,
because a misreading of a specification surfaces as a file wrongly *admitted*
far more often than as one wrongly refused, and only the first of those is
dangerous.
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
from services.financial.money import Money
from services.financial.nacha import (
    NACHA_LOCATOR,
    NACHA_MAX_FILE_BYTES,
    NACHA_TRANSACTION_CODE_DIRECTIONS,
    NachaAmountError,
    NachaBatch,
    NachaError,
    NachaFile,
    NachaMalformedFileError,
    NachaMissingFieldError,
    NotANachaError,
    _aba_check_digit,
    _entry_hash,
    _split_records,
    _truncate_hash,
    _verify_offsets,
    _weakest,
    parse_nacha,
)
from services.financial.proof_class import SourceShape, assign_proof_class


# ---------------------------------------------------------------------------
# Fixture construction
# ---------------------------------------------------------------------------
#
# Records are built field by field from the layouts rather than pasted as
# ninety-four character literals, so that a test which changes one field says
# which field it changed.  Every builder pads to the record length and asserts
# it did not overrun, which catches a fixture that is wrong before it can be
# mistaken for a parser that is wrong.

RECORD_LENGTH = 94


def pad(text: str) -> str:
    assert len(text) <= RECORD_LENGTH, f"fixture is {len(text)} characters: {text!r}"
    return text.ljust(RECORD_LENGTH)


def file_header(
    *,
    record_size: str = "094",
    blocking_factor: str = "10",
    format_code: str = "1",
    destination: str = " 021000021",
    origin: str = "1234567890",
) -> str:
    return pad(
        "1"
        "01"
        + destination
        + origin
        + "260830"
        + "1430"
        + "A"
        + record_size
        + blocking_factor
        + format_code
        + "JPMORGAN CHASE".ljust(23)
        + "OWL CONSULTANCY GROUP".ljust(23)
        + "REF00001"
    )


def batch_header(
    *,
    service_class: str = "200",
    sec: str = "PPD",
    batch: str = "0000001",
    odfi: str = "09100001",
    company: str = "1234567890",
) -> str:
    return pad(
        "5"
        + service_class
        + "OWL CONSULTANCY".ljust(16)
        + " " * 20
        + company
        + sec
        + "PAYROLL".ljust(10)
        + "260830"
        + "260901"
        + "   "
        + "1"
        + odfi
        + batch
    )


def entry(
    *,
    code: str = "22",
    rdfi: str = "02100002",
    check_digit: str = "1",
    account: str = "111111",
    cents: int = 150000,
    name: str = "ALICE SMITH",
    trace: str = "091000010000001",
    addenda_indicator: str = "0",
    identification: str = "",
) -> str:
    return pad(
        "6"
        + code
        + rdfi
        + check_digit
        + account.ljust(17)
        + f"{cents:010d}"
        + identification.ljust(15)
        + name.ljust(22)
        + "  "
        + addenda_indicator
        + trace
    )


def addenda(
    *, type_code: str = "05", info: str = "REMITTANCE", seq: int = 1,
    entry_sequence: str = "0000001",
) -> str:
    return pad("7" + type_code + info.ljust(80) + f"{seq:04d}" + entry_sequence)


def batch_control(
    *,
    service_class: str = "200",
    count: int = 1,
    entry_hash: int = 2100002,
    debits: int = 0,
    credits: int = 150000,
    company: str = "1234567890",
    odfi: str = "09100001",
    batch: str = "0000001",
) -> str:
    return pad(
        "8"
        + service_class
        + f"{count:06d}"
        + f"{entry_hash:010d}"
        + f"{debits:012d}"
        + f"{credits:012d}"
        + company
        + " " * 19
        + " " * 6
        + odfi
        + batch
    )


def file_control(
    *,
    batches: int = 1,
    blocks: int = 1,
    count: int = 1,
    entry_hash: int = 2100002,
    debits: int = 0,
    credits: int = 150000,
) -> str:
    return pad(
        "9"
        + f"{batches:06d}"
        + f"{blocks:06d}"
        + f"{count:08d}"
        + f"{entry_hash:010d}"
        + f"{debits:012d}"
        + f"{credits:012d}"
        + " " * 39
    )


FILLER = "9" * RECORD_LENGTH


def blocked(records: Sequence[str]) -> list[str]:
    """Pad a record run out to a multiple of ten with filler, as a real file is."""
    out = list(records)
    while len(out) % 10:
        out.append(FILLER)
    return out


def joined(records: Sequence[str]) -> str:
    return "\n".join(blocked(records))


def simple(**overrides) -> str:
    """The smallest conformant file: one batch, one credit entry, balanced."""
    return joined(
        [
            file_header(),
            batch_header(),
            entry(),
            batch_control(),
            file_control(),
        ]
    )


class NachaTestCase(unittest.TestCase):
    def assertRefuses(self, exception, fragment: str, callable_, *args, **kwargs):
        """Assert both the type of a refusal and what it says.

        The message matters as much as the type.  A test that checks only the
        type passes when the parser refuses for a different reason than the one
        under test, which is how two BAI2 tests came to pass while asserting
        nothing.
        """
        with self.assertRaises(exception) as caught:
            callable_(*args, **kwargs)
        self.assertIn(fragment, str(caught.exception))
        return caught.exception


# ---------------------------------------------------------------------------


class BaselineTests(NachaTestCase):
    """The smallest conformant file, read end to end."""

    def setUp(self) -> None:
        self.file = parse_nacha(simple())

    def test_returns_a_nacha_file(self) -> None:
        self.assertIsInstance(self.file, NachaFile)

    def test_reads_the_file_header(self) -> None:
        self.assertEqual(self.file.immediate_destination, "021000021")
        self.assertEqual(self.file.immediate_origin, "1234567890")
        self.assertEqual(self.file.creation_date, "260830")
        self.assertEqual(self.file.creation_time, "1430")
        self.assertEqual(self.file.file_id_modifier, "A")
        self.assertEqual(self.file.record_size, "094")
        self.assertEqual(self.file.blocking_factor, "10")
        self.assertEqual(self.file.format_code, "1")
        self.assertEqual(self.file.destination_name, "JPMORGAN CHASE")
        self.assertEqual(self.file.origin_name, "OWL CONSULTANCY GROUP")
        self.assertEqual(self.file.reference_code, "REF00001")

    def test_reads_one_batch(self) -> None:
        self.assertEqual(len(self.file.batches), 1)
        batch = self.file.batches[0]
        self.assertIsInstance(batch, NachaBatch)
        self.assertEqual(batch.service_class, "200")
        self.assertEqual(batch.standard_entry_class, "PPD")
        self.assertEqual(batch.company_name, "OWL CONSULTANCY")
        self.assertEqual(batch.company_identification, "1234567890")
        self.assertEqual(batch.entry_description, "PAYROLL")
        self.assertEqual(batch.descriptive_date, "260830")
        self.assertEqual(batch.effective_entry_date, "260901")
        self.assertEqual(batch.settlement_date, "")
        self.assertEqual(batch.originator_status, "1")
        self.assertEqual(batch.originating_dfi, "09100001")
        self.assertEqual(batch.batch_number, "0000001")

    def test_reads_one_entry(self) -> None:
        self.assertEqual(len(self.file.entries), 1)
        item = self.file.entries[0]
        self.assertEqual(item.transaction_code, "22")
        self.assertEqual(item.direction, TransactionDirection.credit)
        self.assertEqual(item.receiving_dfi, "02100002")
        self.assertEqual(item.check_digit, "1")
        self.assertEqual(item.routing_number, "021000021")
        self.assertEqual(item.account_number, "111111")
        self.assertEqual(item.amount, Money.from_minor_units(150000, "USD"))
        self.assertEqual(item.individual_name, "ALICE SMITH")
        self.assertEqual(item.addenda_indicator, "0")
        self.assertEqual(item.trace_number, "091000010000001")
        self.assertEqual(item.addenda, ())

    def test_amount_is_a_count_of_cents_and_is_not_scaled(self) -> None:
        # The ten-digit field carries two implied decimals, which is exactly
        # the exponent of USD.  Nothing is multiplied on the way in.
        self.assertEqual(self.file.entries[0].amount.minor_units, 150000)
        self.assertEqual(str(self.file.entries[0].amount), "1,500.00 USD")

    def test_records_are_counted_including_filler(self) -> None:
        self.assertEqual(self.file.physical_record_count, 10)

    def test_source_shape_is_fixed(self) -> None:
        self.assertIs(
            self.file.source_shape, SourceShape.native_with_control_totals
        )

    def test_source_shape_cannot_be_supplied_by_a_caller(self) -> None:
        # ``init=False``: the shape is a property of the format, so a caller
        # who could set it could claim control totals a file does not have.
        with self.assertRaises(TypeError):
            NachaFile(  # type: ignore[call-arg]
                immediate_destination="",
                immediate_origin="",
                creation_date="",
                creation_time="",
                file_id_modifier="",
                record_size="",
                blocking_factor="",
                format_code="",
                destination_name="",
                origin_name="",
                reference_code="",
                batches=(),
                control_total=self.file.control_total,
                physical_record_count=0,
                source_shape=SourceShape.statement_document,
            )

    def test_locator_is_not_positional(self) -> None:
        # An ACH file has no pages and no rectangles; a coordinate would be a
        # claim about a document that does not exist.
        self.assertIs(NACHA_LOCATOR.kind, LocatorKind.not_positional)
        self.assertIs(self.file.entries[0].locator.kind, LocatorKind.not_positional)

    def test_a_clean_file_balances_and_reaches_p0(self) -> None:
        self.assertIs(self.file.reconciliation_status, ReconciliationStatus.balanced)
        self.assertEqual(self.file.admissibility_reservations, ())
        self.assertIs(self.file.proof_class, ProofClass.p0)

    def test_no_check_failed(self) -> None:
        self.assertEqual(self.file.control_total.failed_checks, ())
        self.assertEqual(self.file.batches[0].control_total.failed_checks, ())


class ControlTotalTests(NachaTestCase):
    """The four batch figures and the six file figures, each on its own."""

    def test_batch_declares_four_quantities(self) -> None:
        control = parse_nacha(simple()).batches[0].control_total
        self.assertEqual(control.declared_entry_addenda_count, 1)
        self.assertEqual(control.declared_entry_hash, 2100002)
        self.assertEqual(control.declared_debit_total, Money.from_minor_units(0, "USD"))
        self.assertEqual(
            control.declared_credit_total, Money.from_minor_units(150000, "USD")
        )

    def test_file_declares_six_quantities(self) -> None:
        control = parse_nacha(simple()).control_total
        self.assertEqual(control.declared_batch_count, 1)
        self.assertEqual(control.declared_block_count, 1)
        self.assertEqual(control.declared_entry_addenda_count, 1)
        self.assertEqual(control.declared_entry_hash, 2100002)
        self.assertEqual(control.declared_debit_total, Money.from_minor_units(0, "USD"))
        self.assertEqual(
            control.declared_credit_total, Money.from_minor_units(150000, "USD")
        )

    def test_batch_basis_names_what_was_compared(self) -> None:
        control = parse_nacha(simple()).batches[0].control_total
        self.assertIn("between this batch's 5 header", control.basis)

    def test_file_basis_names_the_batch_declarations(self) -> None:
        control = parse_nacha(simple()).control_total
        self.assertIn("declared by the 8 batch control records", control.basis)

    def test_a_wrong_credit_total_fails_only_the_credit_check(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(),
                batch_control(credits=150001),
                file_control(credits=150001),
            ]
        )
        control = parse_nacha(text).batches[0].control_total
        self.assertEqual(control.failed_checks, ("total credits",))
        self.assertEqual(control.credit_delta, Money.from_minor_units(-1, "USD"))
        self.assertEqual(control.debit_delta, Money.from_minor_units(0, "USD"))
        self.assertIs(control.status, ReconciliationStatus.unbalanced)

    def test_a_wrong_entry_count_fails_only_the_count_check(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(),
                batch_control(count=2),
                file_control(count=2),
            ]
        )
        control = parse_nacha(text).batches[0].control_total
        self.assertEqual(control.failed_checks, ("entry and addenda count",))
        self.assertEqual(control.computed_entry_addenda_count, 1)

    def test_a_wrong_file_batch_count_fails_only_the_batch_count(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(),
                batch_control(),
                file_control(batches=2),
            ]
        )
        control = parse_nacha(text).control_total
        self.assertEqual(control.failed_checks, ("batch count",))
        self.assertEqual(control.declared_batch_count, 2)
        self.assertEqual(control.computed_batch_count, 1)
        self.assertIs(control.status, ReconciliationStatus.unbalanced)

    def test_a_wrong_file_block_count_fails_only_the_block_count(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(),
                batch_control(),
                file_control(blocks=2),
            ]
        )
        control = parse_nacha(text).control_total
        self.assertEqual(control.failed_checks, ("block count",))
        self.assertIs(control.status, ReconciliationStatus.unbalanced)

    def test_the_block_count_rounds_up_not_down(self) -> None:
        # Eleven physical records occupy two blocks, not one.  Nothing forces a
        # NACHA file's record count to land on a block boundary — the blocking
        # factor is checked as a *declaration* in the file header, not enforced
        # against the records — so a short final block is reachable, and the
        # ceiling is what makes it come out right.  Every other fixture in this
        # module is an exact multiple of ten, where a floor and a ceiling agree
        # and neither can be told from the other.
        records = [
            file_header(),
            batch_header(),
            entry(),
            batch_control(),
            file_control(blocks=2),
        ] + [FILLER] * 6
        text = "\n".join(records)
        parsed = parse_nacha(text)
        self.assertEqual(parsed.physical_record_count, 11)
        self.assertEqual(parsed.control_total.computed_block_count, 2)
        self.assertNotIn("block count", parsed.control_total.failed_checks)

    def test_a_wrong_file_debit_total_fails_only_the_debit_check(self) -> None:
        # The mirror of the credit case above.  Asserting one side and assuming
        # the other would leave half of NACHA's distinguishing feature untested.
        text = joined(
            [
                file_header(),
                batch_header(service_class="225"),
                entry(code="27", cents=150000),
                batch_control(service_class="225", debits=150000, credits=0),
                file_control(debits=150001, credits=0),
            ]
        )
        control = parse_nacha(text).control_total
        self.assertEqual(control.failed_checks, ("total debits",))
        self.assertEqual(control.debit_delta, Money.from_minor_units(-1, "USD"))
        self.assertEqual(control.credit_delta, Money.from_minor_units(0, "USD"))

    def test_a_wrong_file_entry_count_fails_only_the_count_check(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(),
                batch_control(),
                file_control(count=2),
            ]
        )
        control = parse_nacha(text).control_total
        self.assertEqual(control.failed_checks, ("entry and addenda count",))
        self.assertEqual(control.computed_entry_addenda_count, 1)

    def test_addenda_count_toward_the_entry_addenda_count(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(addenda_indicator="1"),
                addenda(),
                batch_control(count=2),
                file_control(count=2),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(len(parsed.entries), 1)
        self.assertEqual(len(parsed.addenda), 1)
        self.assertEqual(
            parsed.batches[0].control_total.computed_entry_addenda_count, 2
        )
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)

    def test_addenda_do_not_enter_the_entry_hash(self) -> None:
        # The hash is over entries.  An addendum has no receiving institution.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(addenda_indicator="1"),
                addenda(),
                batch_control(count=2),
                file_control(count=2),
            ]
        )
        control = parse_nacha(text).batches[0].control_total
        self.assertEqual(control.computed_entry_hash, 2100002)

    def test_a_wrong_block_count_fails_at_file_level_only(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(),
                batch_control(),
                file_control(blocks=7),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(parsed.control_total.failed_checks, ("block count",))
        self.assertEqual(parsed.control_total.computed_block_count, 1)
        self.assertIs(
            parsed.batches[0].reconciliation_status, ReconciliationStatus.balanced
        )

    def test_a_wrong_batch_count_fails_at_file_level(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(),
                batch_control(),
                file_control(batches=3),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(parsed.control_total.failed_checks, ("batch count",))
        self.assertEqual(parsed.control_total.computed_batch_count, 1)

    def test_block_count_counts_filler(self) -> None:
        # Eleven content records occupy two ten-record blocks, and the filler
        # that pads the second is part of the carriage the count describes.
        entries = [
            entry(trace=f"09100001000000{i}", cents=10000) for i in range(1, 8)
        ]
        text = joined(
            [
                file_header(),
                batch_header(batch="0000001"),
                *entries[:4],
                batch_control(
                    count=4, entry_hash=2100002 * 4, credits=40000, batch="0000001"
                ),
                batch_header(batch="0000002"),
                *entries[4:],
                batch_control(
                    count=3, entry_hash=2100002 * 3, credits=30000, batch="0000002"
                ),
                file_control(
                    batches=2,
                    blocks=2,
                    count=7,
                    entry_hash=2100002 * 7,
                    credits=70000,
                ),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(parsed.physical_record_count, 20)
        self.assertEqual(parsed.control_total.computed_block_count, 2)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(parsed.proof_class, ProofClass.p0)


class SeparateSidesTests(NachaTestCase):
    """Why NACHA is stronger than a format that states a net."""

    def test_direction_error_fails_both_money_totals(self) -> None:
        # The claim the module docstring makes.  A debit read as a credit moves
        # the amount out of one declared figure and into the other, so the two
        # halves fail in opposite directions by the same amount.  Under a
        # single net total — camt.053, BAI2, MT940 — the same error cancels and
        # nothing fails at all.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(code="27", cents=150000),  # a debit
                batch_control(debits=0, credits=150000),  # declared as a credit
                file_control(debits=0, credits=150000),
            ]
        )
        control = parse_nacha(text).batches[0].control_total
        self.assertEqual(control.failed_checks, ("total debits", "total credits"))
        self.assertEqual(control.debit_delta, Money.from_minor_units(150000, "USD"))
        self.assertEqual(control.credit_delta, Money.from_minor_units(-150000, "USD"))
        # Equal and opposite: the error names its own size.
        self.assertEqual(
            control.debit_delta.minor_units, -control.credit_delta.minor_units
        )

    def test_a_compensating_pair_does_not_cancel(self) -> None:
        # Two entries, one on each side, both misdeclared by the same amount.
        # A net total would be satisfied; two separate totals are not.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(code="22", cents=100000, trace="091000010000001"),
                entry(code="27", cents=100000, trace="091000010000002"),
                batch_control(
                    count=2, entry_hash=2100002 * 2, debits=90000, credits=110000
                ),
                file_control(
                    count=2, entry_hash=2100002 * 2, debits=90000, credits=110000
                ),
            ]
        )
        control = parse_nacha(text).batches[0].control_total
        self.assertEqual(control.failed_checks, ("total debits", "total credits"))


class EntryHashTests(NachaTestCase):
    """The one check that is not about money."""

    def test_retargeted_entry_fails_only_the_hash(self) -> None:
        # The entry is readdressed to a different institution and its amount is
        # untouched.  Both money totals still agree; only the hash notices.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(rdfi="01100001", check_digit="5"),
                batch_control(entry_hash=2100002),  # the original institution
                file_control(entry_hash=2100002),
            ]
        )
        control = parse_nacha(text).batches[0].control_total
        self.assertEqual(control.failed_checks, ("entry hash",))
        self.assertEqual(control.computed_entry_hash, 1100001)
        self.assertEqual(control.declared_entry_hash, 2100002)
        self.assertEqual(control.debit_delta, Money.from_minor_units(0, "USD"))
        self.assertEqual(control.credit_delta, Money.from_minor_units(0, "USD"))

    def test_hash_sums_the_eight_digit_prefix_not_the_routing_number(self) -> None:
        # Including the check digit would multiply every contribution by ten
        # and add the digit itself, producing a number that is stable,
        # plausible, and disagrees with every originator's.
        parsed = parse_nacha(simple())
        item = parsed.entries[0]
        self.assertEqual(item.routing_number, "021000021")
        self.assertEqual(
            parsed.batches[0].control_total.computed_entry_hash, 2100002
        )
        self.assertNotEqual(
            parsed.batches[0].control_total.computed_entry_hash, 21000021
        )

    def test_hash_is_truncated_to_ten_digits(self) -> None:
        self.assertEqual(_truncate_hash(12345678901234), 5678901234)
        self.assertEqual(_truncate_hash(9999999999), 9999999999)
        self.assertEqual(_truncate_hash(10000000000), 0)

    def test_hash_of_no_entries_is_zero(self) -> None:
        self.assertEqual(_entry_hash([]), 0)


class RoutingCheckDigitTests(NachaTestCase):
    """The only assertion in any of the four suites checked against the world.

    These six routing numbers exist and their ninth digits were not chosen
    here.  If the weights or the modulus were wrong, they would fail.

    The last of the six earns its place separately.  Its check digit is zero,
    and zero is the one value the *outer* modulus exists to produce:
    ``(10 - total % 10)`` on its own yields ten wherever the weighted sum lands
    on a multiple of ten, and ten is not a digit.  Five routing numbers with
    non-zero check digits cannot tell the two formulas apart.  Only a zero can,
    so one is here deliberately.
    """

    KNOWN = [
        ("021000021", 1),  # JPMorgan Chase, New York
        ("011000015", 5),  # Federal Reserve Bank of Boston
        ("091000019", 9),  # Wells Fargo, Minneapolis
        ("121000248", 8),  # Wells Fargo, San Francisco
        ("026009593", 3),  # Bank of America, New York
        ("054001220", 0),  # Bank of America, Virginia — check digit zero
    ]

    def test_known_routing_numbers_verify(self) -> None:
        for number, expected in self.KNOWN:
            with self.subTest(number=number):
                self.assertEqual(_aba_check_digit(number[:8]), expected)

    def test_a_prefix_that_is_not_eight_digits_yields_none(self) -> None:
        self.assertIsNone(_aba_check_digit("0210000"))
        self.assertIsNone(_aba_check_digit("021000021"))
        self.assertIsNone(_aba_check_digit("0210000A"))
        self.assertIsNone(_aba_check_digit(""))

    def test_a_failing_check_digit_is_reported_not_refused(self) -> None:
        # Refusing the whole file over one corrupt record would discard the
        # other entries and the control totals that vouch for them.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(check_digit="7"),  # 021000027 is not a routing number
                batch_control(),
                file_control(),
            ]
        )
        parsed = parse_nacha(text)
        self.assertIs(parsed.entries[0].check_digit_agrees, False)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)
        self.assertIn(
            "fails its own check digit", " ".join(parsed.admissibility_reservations)
        )

    def test_a_check_digit_that_agrees_raises_nothing(self) -> None:
        parsed = parse_nacha(simple())
        self.assertIs(parsed.entries[0].check_digit_agrees, True)
        self.assertEqual(parsed.admissibility_reservations, ())

    def test_a_non_numeric_check_digit_yields_none_rather_than_false(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(check_digit="X"),
                batch_control(),
                file_control(),
            ]
        )
        parsed = parse_nacha(text)
        self.assertIsNone(parsed.entries[0].check_digit_agrees)
        # ``None`` is not ``False``, so it raises no reservation: the digit was
        # not checked rather than checked and failed.
        self.assertEqual(parsed.admissibility_reservations, ())


class TransactionCodeTests(NachaTestCase):
    """Directions are enumerated, not derived from the decade pattern."""

    def test_the_loan_decade_breaks_the_pattern(self) -> None:
        # In the 2x, 3x and 4x decades ``x5`` is unused and ``x1``-``x4``
        # credit.  In the 5x decade ``55`` is an automated loan account
        # *debit*, because a loan account is the originator's asset and the
        # customer's liability, so the sign convention inverts.  A parser that
        # inferred the offsets would put it on the credit side.
        self.assertIs(
            NACHA_TRANSACTION_CODE_DIRECTIONS["55"], TransactionDirection.debit
        )
        self.assertIs(
            NACHA_TRANSACTION_CODE_DIRECTIONS["53"], TransactionDirection.credit
        )
        self.assertNotIn("25", NACHA_TRANSACTION_CODE_DIRECTIONS)
        self.assertNotIn("35", NACHA_TRANSACTION_CODE_DIRECTIONS)
        self.assertNotIn("45", NACHA_TRANSACTION_CODE_DIRECTIONS)

    def test_checking_decade(self) -> None:
        for code in ("21", "22", "23", "24"):
            with self.subTest(code=code):
                self.assertIs(
                    NACHA_TRANSACTION_CODE_DIRECTIONS[code],
                    TransactionDirection.credit,
                )
        for code in ("26", "27", "28", "29"):
            with self.subTest(code=code):
                self.assertIs(
                    NACHA_TRANSACTION_CODE_DIRECTIONS[code],
                    TransactionDirection.debit,
                )

    def test_an_unknown_code_with_a_non_zero_amount_blocks_the_money_totals(
        self,
    ) -> None:
        # Placing it on either side would make one of the two declared figures
        # agree by construction, and an agreement obtained that way is worse
        # than no agreement at all.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(code="25", cents=150000),
                batch_control(),
                file_control(),
            ]
        )
        parsed = parse_nacha(text)
        control = parsed.batches[0].control_total
        self.assertIsNone(parsed.entries[0].direction)
        self.assertIs(control.status, ReconciliationStatus.unavailable)
        self.assertEqual(control.undirected_count, 1)
        self.assertIsNone(control.computed_debit_total)
        self.assertIsNone(control.computed_credit_total)
        self.assertIn("fixes no direction", control.unavailable_reason or "")
        self.assertIn("1 entry carries", control.unavailable_reason or "")
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_an_unknown_code_with_a_zero_amount_does_not_block(self) -> None:
        # Zero contributes nothing to either side, so not knowing which side it
        # belongs on costs nothing.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(code="25", cents=0),
                batch_control(credits=0),
                file_control(credits=0),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(parsed.batches[0].control_total.undirected_count, 0)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(parsed.proof_class, ProofClass.p0)

    def test_the_plural_is_right_for_more_than_one(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(code="25", cents=150000, trace="091000010000001"),
                entry(code="25", cents=150000, trace="091000010000002"),
                batch_control(count=2, entry_hash=2100002 * 2),
                file_control(count=2, entry_hash=2100002 * 2),
            ]
        )
        reason = parse_nacha(text).batches[0].control_total.unavailable_reason or ""
        self.assertIn("2 entries carry", reason)


class LocalisationTests(NachaTestCase):
    """The file trailer is computed from what the batches declared."""

    def _two_batches(self, *, batch_one_credits: int, file_credits: int) -> str:
        entries = [
            entry(trace=f"09100001000000{i}", cents=10000) for i in range(1, 8)
        ]
        return joined(
            [
                file_header(),
                batch_header(batch="0000001"),
                *entries[:4],
                batch_control(
                    count=4,
                    entry_hash=2100002 * 4,
                    credits=batch_one_credits,
                    batch="0000001",
                ),
                batch_header(batch="0000002"),
                *entries[4:],
                batch_control(
                    count=3, entry_hash=2100002 * 3, credits=30000, batch="0000002"
                ),
                file_control(
                    batches=2,
                    blocks=2,
                    count=7,
                    entry_hash=2100002 * 7,
                    credits=file_credits,
                ),
            ]
        )

    def test_a_batch_that_lies_fails_only_at_batch_level(self) -> None:
        # This pins a real design choice.  The specification defines the file
        # figures as sums of the batch figures, and following that literally
        # localises the failure: a reviewer is shown one failure at the level
        # where the fault is.  Recomputing the file figures from the entries
        # instead would fail both levels for one cause.
        parsed = parse_nacha(
            self._two_batches(batch_one_credits=99999, file_credits=99999 + 30000)
        )
        self.assertIs(parsed.control_total.status, ReconciliationStatus.balanced)
        self.assertEqual(parsed.control_total.failed_checks, ())
        self.assertIs(
            parsed.batches[0].control_total.status, ReconciliationStatus.unbalanced
        )
        self.assertEqual(
            parsed.batches[0].control_total.failed_checks, ("total credits",)
        )
        self.assertIs(
            parsed.batches[1].control_total.status, ReconciliationStatus.balanced
        )
        # The file as a whole is still unbalanced: both levels are consulted.
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_a_batch_that_lies_about_its_hash_fails_only_at_batch_level(self) -> None:
        # The same design choice as above, asserted on the hash rather than on
        # the money.  It needs its own test: the file trailer is six separate
        # sums, and an implementation that took the money from the batch
        # declarations while recomputing the hash from the entries would pass
        # the credit test above and still be wrong here.
        #
        # Batch one holds four entries on one receiving institution, so its
        # true hash is 2100002 x 4; it declares one more than that.  The file
        # trailer sums the *declarations* — the inflated figure plus batch
        # two's honest one — so the file agrees with itself and stays clean.
        entries = [
            entry(trace=f"09100001000000{i}", cents=10000) for i in range(1, 8)
        ]
        text = joined(
            [
                file_header(),
                batch_header(batch="0000001"),
                *entries[:4],
                batch_control(
                    count=4,
                    entry_hash=2100002 * 4 + 1,
                    credits=40000,
                    batch="0000001",
                ),
                batch_header(batch="0000002"),
                *entries[4:],
                batch_control(
                    count=3, entry_hash=2100002 * 3, credits=30000, batch="0000002"
                ),
                file_control(
                    batches=2,
                    blocks=2,
                    count=7,
                    entry_hash=2100002 * 7 + 1,
                    credits=70000,
                ),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(parsed.batches[0].control_total.failed_checks, ("entry hash",))
        self.assertEqual(parsed.batches[1].control_total.failed_checks, ())
        self.assertEqual(parsed.control_total.failed_checks, ())
        self.assertIs(parsed.control_total.status, ReconciliationStatus.balanced)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.unbalanced)

    def test_a_file_trailer_that_disagrees_with_its_batches_fails(self) -> None:
        parsed = parse_nacha(
            self._two_batches(batch_one_credits=40000, file_credits=70001)
        )
        self.assertEqual(parsed.control_total.failed_checks, ("total credits",))
        self.assertIs(
            parsed.batches[0].control_total.status, ReconciliationStatus.balanced
        )

    def test_both_levels_are_consulted_for_the_file_status(self) -> None:
        clean = parse_nacha(
            self._two_batches(batch_one_credits=40000, file_credits=70000)
        )
        self.assertIs(clean.reconciliation_status, ReconciliationStatus.balanced)


class ServiceClassTests(NachaTestCase):
    """A batch's service class constrains which totals may be non-zero."""

    def test_credits_only_batch_with_a_declared_debit_fails_the_check(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(service_class="220"),
                entry(code="27", cents=150000),
                batch_control(service_class="220", debits=150000, credits=0),
                file_control(debits=150000, credits=0),
            ]
        )
        control = parse_nacha(text).batches[0].control_total
        self.assertIs(control.service_class_consistent, False)
        self.assertIn("service class against the totals declared", control.failed_checks)
        self.assertIs(control.status, ReconciliationStatus.unbalanced)

    def test_debits_only_batch_with_a_declared_credit_fails_the_check(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(service_class="225"),
                entry(code="22", cents=150000),
                batch_control(service_class="225", debits=0, credits=150000),
                file_control(debits=0, credits=150000),
            ]
        )
        control = parse_nacha(text).batches[0].control_total
        self.assertIs(control.service_class_consistent, False)

    def test_a_mixed_batch_constrains_nothing(self) -> None:
        # ``None`` rather than ``True``: a statement that constrains nothing
        # has nothing to agree or disagree with.
        control = parse_nacha(simple()).batches[0].control_total
        self.assertIsNone(control.service_class_consistent)

    def test_a_credits_only_batch_with_only_credits_is_consistent(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(service_class="220"),
                entry(),
                batch_control(service_class="220"),
                file_control(),
            ]
        )
        control = parse_nacha(text).batches[0].control_total
        self.assertIs(control.service_class_consistent, True)
        self.assertEqual(control.failed_checks, ())

    def test_header_and_trailer_disagreeing_is_a_refusal(self) -> None:
        # Refused rather than reported, unlike the check above.  That check
        # compares a declaration against arithmetic and can say which is wrong.
        # This one has two declarations of the same quantity and no tie-break,
        # so there is no service class to check the totals against at all.
        text = joined(
            [
                file_header(),
                batch_header(service_class="200"),
                entry(),
                batch_control(service_class="220"),
                file_control(),
            ]
        )
        self.assertRefuses(
            NachaMalformedFileError,
            "a batch whose two records disagree about it cannot be checked",
            parse_nacha,
            text,
        )

    def test_an_unrecognised_service_class_is_refused(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(service_class="999"),
                entry(),
                batch_control(service_class="999"),
                file_control(),
            ]
        )
        self.assertRefuses(
            NachaMalformedFileError,
            "leaves the batch's own trailer uninterpretable",
            parse_nacha,
            text,
        )


class ReservationTests(NachaTestCase):
    """Arithmetic that passes over contents that are not payments."""

    def test_a_prenotification_batch_balances_but_does_not_reach_p0(self) -> None:
        # Zero-dollar tests that an account exists.  They satisfy every control
        # total while contributing nothing to either side — the strongest
        # possible arithmetic agreement about no money at all.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(code="23", cents=0),
                batch_control(credits=0),
                file_control(credits=0),
            ]
        )
        parsed = parse_nacha(text)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(parsed.entries[0].is_prenotification, True)
        self.assertIs(parsed.proof_class, ProofClass.p3)
        self.assertIn("prenotification", parsed.admissibility_reservations[0])

    def test_assign_proof_class_alone_would_have_said_p0(self) -> None:
        # The withholding is this module's decision, not the taxonomy's.  On
        # the evidence ``assign_proof_class`` is given, p0 is correct.
        self.assertIs(
            assign_proof_class(
                SourceShape.native_with_control_totals,
                ReconciliationStatus.balanced,
            ),
            ProofClass.p0,
        )

    def test_a_notification_of_change_raises_a_reservation(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(code="21", cents=0, addenda_indicator="1"),
                addenda(type_code="98", info="C01021000021999999"),
                batch_control(count=2, credits=0),
                file_control(count=2, credits=0),
            ]
        )
        parsed = parse_nacha(text)
        self.assertIs(parsed.entries[0].is_notification_of_change, True)
        self.assertIs(parsed.entries[0].is_return, False)
        self.assertIs(parsed.proof_class, ProofClass.p3)
        self.assertIn("notification", parsed.admissibility_reservations[0])

    def test_a_return_raises_a_reservation(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(code="26", cents=150000, addenda_indicator="1"),
                addenda(type_code="99", info="R01021000021999999"),
                batch_control(count=2, debits=150000, credits=0),
                file_control(count=2, debits=150000, credits=0),
            ]
        )
        parsed = parse_nacha(text)
        self.assertIs(parsed.entries[0].is_return, True)
        self.assertIs(parsed.entries[0].is_notification_of_change, False)
        self.assertIs(parsed.proof_class, ProofClass.p3)
        self.assertIn("counts the same funds twice", parsed.admissibility_reservations[0])

    def test_a_shared_code_without_addenda_is_an_ordinary_payment(self) -> None:
        # ``26`` is used for both a return and an ordinary debit.  What tells
        # them apart is the addenda type, not the code, so an entry carrying
        # neither addendum is a payment.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(code="26", cents=150000),
                batch_control(debits=150000, credits=0),
                file_control(debits=150000, credits=0),
            ]
        )
        parsed = parse_nacha(text)
        self.assertIs(parsed.entries[0].is_return, False)
        self.assertIs(parsed.entries[0].is_notification_of_change, False)
        self.assertEqual(parsed.admissibility_reservations, ())
        self.assertIs(parsed.proof_class, ProofClass.p0)

    def test_an_international_batch_raises_a_reservation(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(sec="IAT"),
                entry(),
                batch_control(),
                file_control(),
            ]
        )
        parsed = parse_nacha(text)
        self.assertIs(parsed.proof_class, ProofClass.p3)
        self.assertIn("settlement leg", parsed.admissibility_reservations[0])

    def test_reservations_gather_from_every_batch(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(batch="0000001", sec="IAT"),
                entry(trace="091000010000001"),
                batch_control(batch="0000001"),
                batch_header(batch="0000002"),
                entry(code="23", cents=0, trace="091000010000002"),
                batch_control(batch="0000002", credits=0),
                file_control(batches=2, count=2, entry_hash=2100002 * 2),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(len(parsed.admissibility_reservations), 2)
        self.assertIn("0000001", parsed.admissibility_reservations[0])
        self.assertIn("0000002", parsed.admissibility_reservations[1])

    def test_a_reservation_does_not_change_the_reconciliation_status(self) -> None:
        # The arithmetic passed and the artefact says so.  What the reservation
        # changes is the class, not the finding.
        text = joined(
            [
                file_header(),
                batch_header(sec="IAT"),
                entry(),
                batch_control(),
                file_control(),
            ]
        )
        parsed = parse_nacha(text)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertIs(parsed.control_total.status, ReconciliationStatus.balanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)

    def test_a_reservation_does_not_demote_an_already_failing_file(self) -> None:
        # p3 is where a failing file already lands; the reservation cannot make
        # it worse, and must not accidentally make it better.
        text = joined(
            [
                file_header(),
                batch_header(sec="IAT"),
                entry(),
                batch_control(credits=1),
                file_control(credits=1),
            ]
        )
        parsed = parse_nacha(text)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.unbalanced)
        self.assertIs(parsed.proof_class, ProofClass.p3)


class CarriageTests(NachaTestCase):
    """Two conformant carriages, and what is done with a malformed one."""

    def test_a_file_with_no_line_terminators_reads(self) -> None:
        parsed = parse_nacha(simple().replace("\n", ""))
        self.assertEqual(len(parsed.entries), 1)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)

    def test_an_unbroken_run_of_the_wrong_length_is_refused(self) -> None:
        self.assertRefuses(
            NachaMalformedFileError,
            "not a multiple of the 94-character record length",
            parse_nacha,
            file_header()[:90],
        )

    def test_crlf_terminators_read(self) -> None:
        parsed = parse_nacha(simple().replace("\n", "\r\n"))
        self.assertEqual(len(parsed.entries), 1)

    def test_records_trimmed_of_trailing_blanks_are_restored(self) -> None:
        # Trailing blanks carry no information in a fixed-width format, so a
        # record shortened by a transport that trimmed them is restored exactly.
        trimmed = "\n".join(line.rstrip() for line in simple().split("\n"))
        parsed = parse_nacha(trimmed)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)
        self.assertEqual(parsed.entries[0].trace_number, "091000010000001")

    def test_a_record_longer_than_the_record_length_is_refused(self) -> None:
        # The asymmetry with padding is deliberate: a surplus character is
        # somewhere unlocatable, so every field boundary after it is wrong.
        self.assertRefuses(
            NachaMalformedFileError,
            "the surplus cannot be located",
            parse_nacha,
            joined([file_header() + "X"]),
        )

    def test_a_record_truncated_mid_field_is_caught_by_the_trace_number(self) -> None:
        # This is what makes padding safe.  The last field of a ``6`` record is
        # mandatory, so a genuinely truncated entry is refused rather than read
        # with the missing characters supplied as blanks.
        text = "\n".join(
            blocked(
                [
                    file_header(),
                    batch_header(),
                    entry()[:70],
                    batch_control(),
                    file_control(),
                ]
            )
        )
        self.assertRefuses(
            NachaMissingFieldError,
            "the trace number is mandatory and is blank",
            parse_nacha,
            text,
        )

    def test_blank_lines_between_records_do_not_consume_a_record_number(
        self,
    ) -> None:
        # The numbers a reader is given have to match the records.  A blank
        # that consumed a number would make every message after it point one
        # record short.
        text = simple().replace("\n", "\n\n")
        parsed = parse_nacha(text)
        self.assertEqual(parsed.entries[0].line_number, 3)
        self.assertEqual(parsed.physical_record_count, 10)

    def test_split_records_numbers_records_from_one(self) -> None:
        records = _split_records(simple())
        self.assertEqual(records[0].line_number, 1)
        self.assertEqual(records[0].code, "1")
        self.assertEqual(records[-1].line_number, 10)

    def test_filler_is_recognised(self) -> None:
        records = _split_records(simple())
        self.assertIs(records[5].is_filler, True)
        self.assertIs(records[0].is_filler, False)


class EnvelopeTests(NachaTestCase):
    """The header and the trailer, and what may sit outside them."""

    def test_a_file_that_does_not_open_with_a_header_is_refused(self) -> None:
        self.assertRefuses(
            NotANachaError,
            "a NACHA file opens with a 1 file header",
            parse_nacha,
            joined([batch_header()]),
        )

    def test_an_empty_file_is_refused(self) -> None:
        self.assertRefuses(NotANachaError, "the file is empty", parse_nacha, "   \n  ")

    def test_a_declared_record_size_that_is_not_094_is_refused(self) -> None:
        # A different record size states that every offset in the module is
        # wrong, and the fields read at those offsets would still parse.
        self.assertRefuses(
            NachaMalformedFileError,
            "would parse cleanly and mean something else",
            parse_nacha,
            joined([file_header(record_size="080")]),
        )

    def test_a_declared_blocking_factor_that_is_not_ten_is_refused(self) -> None:
        self.assertRefuses(
            NachaMalformedFileError,
            "a different factor would make the file trailer's block count "
            "disagree",
            parse_nacha,
            joined([file_header(blocking_factor="20")]),
        )

    def test_a_declared_format_code_that_is_not_one_is_refused(self) -> None:
        self.assertRefuses(
            NachaMalformedFileError,
            "a different format code is a different record layout",
            parse_nacha,
            joined([file_header(format_code="2")]),
        )

    def test_a_file_never_closed_by_a_control_is_refused(self) -> None:
        self.assertRefuses(
            NachaMalformedFileError,
            "the file is never closed by a 9 file control record",
            parse_nacha,
            joined([file_header(), batch_header(), entry(), batch_control()]),
        )

    def test_filler_standing_where_the_control_should_be_is_not_read_as_one(
        self,
    ) -> None:
        # A filler opens with ``9`` too.  Read as a control it parses — every
        # field is digits — and the file would report ``unbalanced``, naming an
        # arithmetic failure when the fault is a trailer that is not there.  A
        # conformant control ends in thirty-nine blank reserved positions, so
        # no control is ever ninety-four ``9`` characters.
        exception = self.assertRefuses(
            NachaMalformedFileError,
            "the record standing where one should be is filler",
            parse_nacha,
            joined([file_header(), batch_header(), entry(), batch_control()]),
        )
        self.assertNotIn("unbalanced", str(exception))

    def test_content_after_the_file_control_is_refused(self) -> None:
        text = "\n".join(
            [
                file_header(),
                batch_header(),
                entry(),
                batch_control(),
                file_control(),
                entry(),
            ]
            + [FILLER] * 4
        )
        self.assertRefuses(
            NachaMalformedFileError,
            "would enter the ledger uncounted",
            parse_nacha,
            text,
        )

    def test_filler_after_the_file_control_is_permitted(self) -> None:
        # Unlike its siblings this is a shape test rather than a flat refusal,
        # because records legitimately follow a NACHA trailer.
        parsed = parse_nacha(simple())
        self.assertEqual(parsed.physical_record_count, 10)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)

    def test_a_stray_record_code_where_a_batch_header_belongs_is_refused(
        self,
    ) -> None:
        self.assertRefuses(
            NachaMalformedFileError,
            "expected a 5 batch header or the 9 file control",
            parse_nacha,
            joined([file_header(), entry(), file_control()]),
        )


class BatchStructureTests(NachaTestCase):
    """A batch is a header, its entries, and the trailer that closes it."""

    def test_a_batch_never_closed_is_refused(self) -> None:
        # Deliberately not ``joined``.  Padding a short run out to a block puts
        # filler after the last entry, and the walk then finds a record where
        # the trailer belongs rather than finding nothing at all — which is the
        # stray-record refusal below, not this one.  Reaching the exhaustion
        # branch takes a run that ends mid-batch and is *already* a multiple of
        # ten, so the blocking-factor check passes and the batch walk is what
        # runs off the end: a header, a batch header, and eight entries.
        text = "\n".join([file_header(), batch_header()] + [entry()] * 8)
        self.assertRefuses(
            NachaMalformedFileError,
            "the batch is never closed by an 8 batch control record",
            parse_nacha,
            text,
        )

    def test_a_stray_record_inside_a_batch_is_refused(self) -> None:
        self.assertRefuses(
            NachaMalformedFileError,
            "expected a 6 entry detail or the 8 batch control",
            parse_nacha,
            joined([file_header(), batch_header(), entry(), file_control()]),
        )

    def test_an_empty_batch_reads(self) -> None:
        # Unusual but not malformed: a batch with no entries and zero totals.
        text = joined(
            [
                file_header(),
                batch_header(),
                batch_control(count=0, entry_hash=0, credits=0),
                file_control(count=0, entry_hash=0, credits=0),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(parsed.entries, ())
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)

    def test_batches_are_returned_in_file_order(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(batch="0000001"),
                entry(trace="091000010000001"),
                batch_control(batch="0000001"),
                batch_header(batch="0000002"),
                entry(trace="091000010000002"),
                batch_control(batch="0000002"),
                file_control(batches=2, count=2, entry_hash=2100002 * 2, credits=300000),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(
            [b.batch_number for b in parsed.batches], ["0000001", "0000002"]
        )

    def test_a_missing_transaction_code_is_refused(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(code="  "),
                batch_control(),
                file_control(),
            ]
        )
        self.assertRefuses(
            NachaMissingFieldError,
            "the transaction code is mandatory and is blank",
            parse_nacha,
            text,
        )

    def test_a_missing_receiving_dfi_is_refused(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(rdfi=" " * 8),
                batch_control(),
                file_control(),
            ]
        )
        self.assertRefuses(
            NachaMissingFieldError,
            "the receiving DFI identification is mandatory and is blank",
            parse_nacha,
            text,
        )

    def test_a_missing_standard_entry_class_is_refused(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(sec="   "),
                entry(),
                batch_control(),
                file_control(),
            ]
        )
        self.assertRefuses(
            NachaMissingFieldError,
            "the standard entry class code is mandatory and is blank",
            parse_nacha,
            text,
        )


class AddendaTests(NachaTestCase):
    """``7`` records, and the one thing read out of them."""

    def test_addenda_attach_to_the_entry_above(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(addenda_indicator="1", trace="091000010000001"),
                addenda(info="INVOICE 4471", entry_sequence="0000001"),
                entry(trace="091000010000002"),
                batch_control(count=3, entry_hash=2100002 * 2, credits=300000),
                file_control(count=3, entry_hash=2100002 * 2, credits=300000),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(len(parsed.entries[0].addenda), 1)
        self.assertEqual(parsed.entries[1].addenda, ())
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)

    def test_payment_information_is_verbatim_and_unparsed(self) -> None:
        # A field read into fields is a field a reader can no longer see as it
        # was sent, and the return reason in particular is the sort of thing an
        # opposing expert will want to read in the original.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(addenda_indicator="1"),
                addenda(info="R01  INSUFFICIENT   FUNDS"),
                batch_control(count=2),
                file_control(count=2),
            ]
        )
        payload = parse_nacha(text).addenda[0].payment_information
        self.assertEqual(len(payload), 80)
        self.assertTrue(payload.startswith("R01  INSUFFICIENT   FUNDS"))

    def test_the_addenda_type_code_is_mandatory(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(addenda_indicator="1"),
                addenda(type_code="  "),
                batch_control(count=2),
                file_control(count=2),
            ]
        )
        self.assertRefuses(
            NachaMissingFieldError,
            "the addenda type code is mandatory and is blank",
            parse_nacha,
            text,
        )

    def test_addenda_are_read_even_when_the_indicator_says_none(self) -> None:
        # The indicator is a declaration and the records are the fact.  An
        # indicator of ``0`` on an entry followed by a ``7`` would otherwise
        # make that record vanish from the entry count and take the batch
        # trailer's count check down with it.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(addenda_indicator="0"),
                addenda(),
                batch_control(count=2),
                file_control(count=2),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(len(parsed.addenda), 1)
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)

    def test_an_indicator_of_one_with_no_addenda_is_refused(self) -> None:
        # The reverse direction, where reading past it would report an
        # arithmetic failure whose real cause is a truncated file.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(addenda_indicator="1"),
                batch_control(),
                file_control(),
            ]
        )
        self.assertRefuses(
            NachaMalformedFileError,
            "declares that addenda follow, and none do",
            parse_nacha,
            text,
        )

    def test_the_addenda_sequence_number_is_read_when_present(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(addenda_indicator="1"),
                addenda(seq=3, entry_sequence="0000001"),
                batch_control(count=2),
                file_control(count=2),
            ]
        )
        addendum = parse_nacha(text).addenda[0]
        self.assertEqual(addendum.sequence_number, 3)
        self.assertEqual(addendum.entry_detail_sequence, "0000001")


class TraceNumberTests(NachaTestCase):
    """The join between an addendum and the entry it hangs from."""

    def test_entry_detail_sequence_is_the_last_seven_digits(self) -> None:
        parsed = parse_nacha(simple())
        self.assertEqual(parsed.entries[0].trace_number, "091000010000001")
        self.assertEqual(parsed.entries[0].entry_detail_sequence, "0000001")

    def test_it_is_derived_rather_than_stored(self) -> None:
        # Storing it separately would allow the two to disagree.
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(trace="091000019999999"),
                batch_control(),
                file_control(),
            ]
        )
        self.assertEqual(parse_nacha(text).entries[0].entry_detail_sequence, "9999999")


class AmountTests(NachaTestCase):
    """Ten digits, two implied decimals, no sign and no separator."""

    def test_a_zero_amount_is_zero_dollars_not_an_absent_amount(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(cents=0),
                batch_control(credits=0),
                file_control(credits=0),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(parsed.entries[0].amount, Money.from_minor_units(0, "USD"))
        self.assertIs(parsed.entries[0].amount.is_zero, True)

    def test_the_largest_representable_amount(self) -> None:
        text = joined(
            [
                file_header(),
                batch_header(),
                entry(cents=9999999999),
                batch_control(credits=9999999999),
                file_control(credits=9999999999),
            ]
        )
        parsed = parse_nacha(text)
        self.assertEqual(
            parsed.entries[0].amount, Money.from_minor_units(9999999999, "USD")
        )
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)

    def test_a_non_numeric_amount_is_refused(self) -> None:
        broken = pad(
            "6" "22" "02100002" "1" + "111111".ljust(17) + "15000.000"
            + " " + " " * 15 + "ALICE".ljust(22) + "  " + "0" + "091000010000001"
        )
        text = joined(
            [file_header(), batch_header(), broken, batch_control(), file_control()]
        )
        self.assertRefuses(
            NachaAmountError,
            "amounts are written as an unsigned run of digits in cents",
            parse_nacha,
            text,
        )

    def test_a_signed_amount_is_refused(self) -> None:
        # ``int`` would forgive a leading sign; a fixed-width field carrying
        # one means the boundaries are wrong.
        broken = pad(
            "6" "22" "02100002" "1" + "111111".ljust(17) + "-000150000"
            + " " * 15 + "ALICE".ljust(22) + "  " + "0" + "091000010000001"
        )
        text = joined(
            [file_header(), batch_header(), broken, batch_control(), file_control()]
        )
        self.assertRefuses(NachaAmountError, "no sign", parse_nacha, text)

    def test_a_non_numeric_declared_total_is_refused(self) -> None:
        broken = pad(
            "8" "200" "000001" "0002100002" + "00000000000A" + f"{150000:012d}"
            + "1234567890" + " " * 25 + "09100001" + "0000001"
        )
        text = joined(
            [file_header(), batch_header(), entry(), broken, file_control()]
        )
        self.assertRefuses(
            NachaAmountError,
            "the total debit entry dollar amount",
            parse_nacha,
            text,
        )

    def test_a_non_numeric_declared_count_is_refused(self) -> None:
        broken = pad(
            "8" "200" "00000A" "0002100002" + f"{0:012d}" + f"{150000:012d}"
            + "1234567890" + " " * 25 + "09100001" + "0000001"
        )
        text = joined(
            [file_header(), batch_header(), entry(), broken, file_control()]
        )
        self.assertRefuses(
            NachaMalformedFileError,
            "a NACHA count is a right-justified zero-filled run of digits",
            parse_nacha,
            text,
        )


class CurrencyTests(NachaTestCase):
    """Fixed USD, with no parameter to reinterpret it."""

    def test_every_amount_is_usd(self) -> None:
        parsed = parse_nacha(simple())
        self.assertEqual(parsed.entries[0].amount.currency, "USD")
        self.assertEqual(
            parsed.control_total.declared_credit_total.currency, "USD"
        )

    def test_parse_nacha_takes_no_currency_parameter(self) -> None:
        # A parameter would let a caller reinterpret a count of cents as some
        # other currency's minor unit, which is a way of being wrong the format
        # itself forecloses.
        import inspect

        parameters = inspect.signature(parse_nacha).parameters
        self.assertEqual(list(parameters), ["data"])


class DecodeTests(NachaTestCase):
    """Bytes in, text out, or a refusal."""

    def test_bytes_are_decoded_as_utf8(self) -> None:
        parsed = parse_nacha(simple().encode("utf-8"))
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)

    def test_bytearray_is_accepted(self) -> None:
        parsed = parse_nacha(bytearray(simple().encode("utf-8")))
        self.assertIs(parsed.reconciliation_status, ReconciliationStatus.balanced)

    def test_a_wrong_type_is_refused_by_name(self) -> None:
        self.assertRefuses(
            NachaMalformedFileError,
            "parse_nacha takes bytes or str, got int",
            parse_nacha,
            42,
        )
        self.assertRefuses(
            NachaMalformedFileError,
            "parse_nacha takes bytes or str, got list",
            parse_nacha,
            [],
        )

    def test_invalid_utf8_is_refused_rather_than_decoded_with_a_fallback(
        self,
    ) -> None:
        # A fallback succeeds on every input and turns unreadable bytes into
        # plausible-looking text that nothing downstream can tell from what the
        # originator sent.
        self.assertRefuses(
            NachaMalformedFileError,
            "refused rather than decoded with a fallback",
            parse_nacha,
            b"\xff\xfe" + b"x" * 92,
        )

    def test_a_file_over_the_ceiling_is_refused(self) -> None:
        self.assertEqual(NACHA_MAX_FILE_BYTES, 64 * 1024 * 1024)
        oversized = b"1" * (NACHA_MAX_FILE_BYTES + 1)
        self.assertRefuses(
            NachaMalformedFileError,
            "over the 67108864-byte ceiling for an ACH file",
            parse_nacha,
            oversized,
        )


class WeakestTests(NachaTestCase):
    """The fold that stops one clean batch from covering for a broken one."""

    def test_unbalanced_outranks_everything(self) -> None:
        self.assertIs(
            _weakest(
                [
                    ReconciliationStatus.balanced,
                    ReconciliationStatus.unbalanced,
                    ReconciliationStatus.unavailable,
                ]
            ),
            ReconciliationStatus.unbalanced,
        )

    def test_unavailable_outranks_not_attempted(self) -> None:
        self.assertIs(
            _weakest(
                [
                    ReconciliationStatus.unavailable,
                    ReconciliationStatus.not_attempted,
                    ReconciliationStatus.balanced,
                ]
            ),
            ReconciliationStatus.unavailable,
        )

    def test_not_attempted_outranks_balanced(self) -> None:
        self.assertIs(
            _weakest(
                [ReconciliationStatus.not_attempted, ReconciliationStatus.balanced]
            ),
            ReconciliationStatus.not_attempted,
        )

    def test_all_balanced_is_balanced(self) -> None:
        self.assertIs(
            _weakest([ReconciliationStatus.balanced] * 3),
            ReconciliationStatus.balanced,
        )

    def test_an_empty_run_is_not_attempted_rather_than_balanced(self) -> None:
        # Nothing checked is not the same as everything passing.
        self.assertIs(_weakest([]), ReconciliationStatus.not_attempted)


class OffsetTableTests(NachaTestCase):
    """The one guard available against a silently wrong field boundary."""

    def test_verify_offsets_passes_on_the_table_as_written(self) -> None:
        _verify_offsets()  # raises on failure

    def test_it_is_run_at_import(self) -> None:
        # A test can be skipped; an import cannot.  The module under test has
        # already executed this by the time this file is collected.
        import services.financial.nacha as module

        self.assertTrue(hasattr(module, "_verify_offsets"))

    def test_every_span_is_inside_the_record(self) -> None:
        import re

        import services.financial.nacha as module

        spans = {
            name: value
            for name, value in vars(module).items()
            if re.match(r"^_(FH|BH|ED|AD|BC|FC)_", name)
        }
        self.assertGreater(len(spans), 40)
        for name, (start, stop) in spans.items():
            with self.subTest(name=name):
                self.assertGreaterEqual(start, 0)
                self.assertLess(start, stop)
                self.assertLessEqual(stop, 94)

    def test_a_bad_span_would_be_caught(self) -> None:
        import services.financial.nacha as module

        original = module._FH_PRIORITY
        try:
            module._FH_PRIORITY = (1, 200)
            with self.assertRaises(AssertionError):
                module._verify_offsets()
        finally:
            module._FH_PRIORITY = original
        module._verify_offsets()


class ErrorHierarchyTests(NachaTestCase):
    """One base a caller can catch."""

    def test_every_refusal_derives_from_the_base(self) -> None:
        for exception in (
            NotANachaError,
            NachaMalformedFileError,
            NachaMissingFieldError,
            NachaAmountError,
        ):
            with self.subTest(exception=exception.__name__):
                self.assertTrue(issubclass(exception, NachaError))

    def test_the_base_is_an_exception(self) -> None:
        self.assertTrue(issubclass(NachaError, Exception))


class StatusCoherenceTests(NachaTestCase):
    """``status`` and ``failed_checks`` must never contradict each other.

    These are two independent computations of the same thing.  ``status`` is
    folded at construction from a list of per-comparison outcomes;
    ``failed_checks`` is derived afterwards from the ``*_agrees`` properties.
    Nothing in the type forces them to agree, so an edit to one and not the
    other produces the worst artefact this module could emit: a control total
    reporting ``balanced`` while listing, underneath, the checks that failed.
    A reviewer reading the top line would be told the file reconciles when it
    does not.

    The two cannot simply be merged — ``status`` carries ``unavailable``, for
    which ``failed_checks`` has no vocabulary — so the invariant is asserted
    here instead, over a fixture for every comparison at both levels.  One
    fixture would not do: each comparison is written out separately in both
    places, so each can drift on its own.
    """

    def _cases(self):
        """(label, control) for one deliberate single-point failure each."""
        yield "clean file", parse_nacha(simple()).control_total
        yield "clean batch", parse_nacha(simple()).batches[0].control_total

        for label, trailer in {
            "file batch count": file_control(batches=2),
            "file block count": file_control(blocks=2),
            "file entry count": file_control(count=2),
            "file entry hash": file_control(entry_hash=1),
            "file debit total": file_control(debits=1),
            "file credit total": file_control(credits=150001),
        }.items():
            text = joined(
                [file_header(), batch_header(), entry(), batch_control(), trailer]
            )
            yield label, parse_nacha(text).control_total

        for label, trailer in {
            "batch entry count": batch_control(count=2),
            "batch entry hash": batch_control(entry_hash=1),
            "batch debit total": batch_control(debits=1),
            "batch credit total": batch_control(credits=150001),
        }.items():
            text = joined(
                [file_header(), batch_header(), entry(), trailer, file_control()]
            )
            yield label, parse_nacha(text).batches[0].control_total

    def test_a_named_failure_always_makes_the_status_unbalanced(self) -> None:
        for label, control in self._cases():
            with self.subTest(case=label):
                if control.failed_checks:
                    self.assertIs(
                        control.status,
                        ReconciliationStatus.unbalanced,
                        f"{label}: named {control.failed_checks} as failed but "
                        f"reported status {control.status}",
                    )

    def test_an_unbalanced_status_always_names_what_failed(self) -> None:
        for label, control in self._cases():
            with self.subTest(case=label):
                if control.status is ReconciliationStatus.unbalanced:
                    self.assertNotEqual(
                        control.failed_checks,
                        (),
                        f"{label}: reported unbalanced without naming a check",
                    )

    def test_each_fixture_breaks_exactly_the_check_it_is_named_for(self) -> None:
        # Guards the two tests above against decaying into tautologies.  Both
        # are written as implications, so a fixture that quietly stopped
        # breaking anything would satisfy them vacuously and the invariant
        # would go untested while still reporting green.
        self.assertEqual(
            {label: control.failed_checks for label, control in self._cases()},
            {
                "clean file": (),
                "clean batch": (),
                "file batch count": ("batch count",),
                "file block count": ("block count",),
                "file entry count": ("entry and addenda count",),
                "file entry hash": ("entry hash",),
                "file debit total": ("total debits",),
                "file credit total": ("total credits",),
                "batch entry count": ("entry and addenda count",),
                "batch entry hash": ("entry hash",),
                "batch debit total": ("total debits",),
                "batch credit total": ("total credits",),
            },
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
