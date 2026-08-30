"""Tests for the reference a reviewer cites, and the hash beneath it.

The property this module exists to defend is regenerability, and it is the one
V1 did not have: ``uuid.uuid4().hex[:8]`` assigned on first read produced a
reference that was different in every database and depended on the order rows
came back in.  So the tests that matter most here are the boring-looking ones
-- that the same reading produces the same reference in a *separate process*
under a *different hash seed*, and that shuffling a document does not move a
reference off the row it names.  A test that computed a reference twice in one
interpreter would have passed against V1's implementation too, on a case whose
ids were already assigned.

The second cluster is about what a reference is allowed to survive.  A parser
upgrade that changes only spacing must not rename every row it touched, and a
re-extraction that recovers a row missed earlier must not rename the rows
below it.  The first is why text is normalised; the second is why occurrence
is counted over identical readings instead of taken from ``row_index``.  Both
are asserted directly, because both are silent failures: the references simply
stop matching, and the notes keyed to them stop finding anything.

No case material appears here.  Every amount is round and invented and every
digest is a literal or built in the test.
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import unittest
from dataclasses import replace
from datetime import date

from postgres.models.enums import TransactionDirection
from services.financial.references import (
    REFERENCE_LENGTH,
    REFERENCE_PREFIX,
    MalformedReadingError,
    MalformedReferenceError,
    RowReading,
    canonical_form,
    content_hash,
    document_content_hashes,
    document_ref_ids,
    is_reference,
    normalise,
    ref_id,
)

DOCUMENT = "3b" * 32
OTHER_DOCUMENT = "c7" * 32

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def reading(**overrides) -> RowReading:
    """A plausible row.  Every field is invented."""
    fields = {
        "currency": "USD",
        "amount_minor": 2500_00,
        "direction": TransactionDirection.debit,
        "transaction_date": date(2026, 3, 14),
        "description": "WIRE TO MEYER LLC",
        "counterparty_raw": "MEYER LLC",
    }
    fields.update(overrides)
    return RowReading(**fields)


class RegenerabilityTests(unittest.TestCase):
    """The property the column comment promises and V1 could not keep."""

    def test_the_same_reading_gives_the_same_reference(self):
        first = ref_id(DOCUMENT, content_hash(reading()))
        second = ref_id(DOCUMENT, content_hash(reading()))
        self.assertEqual(first, second)

    def test_the_reference_survives_a_separate_process_and_hash_seed(self):
        """The test V1's implementation would have failed.

        Randomised hashing and a fresh interpreter are exactly the conditions
        under which an id that came from ``uuid4`` or from ``hash()`` stops
        agreeing with itself, and neither shows up when a value is computed
        twice inside one run.
        """
        script = (
            "from datetime import date\n"
            "from postgres.models.enums import TransactionDirection\n"
            "from services.financial.references import RowReading, content_hash, ref_id\n"
            "r = RowReading(currency='USD', amount_minor=250000,\n"
            "               direction=TransactionDirection.debit,\n"
            "               transaction_date=date(2026, 3, 14),\n"
            "               description='WIRE TO MEYER LLC',\n"
            "               counterparty_raw='MEYER LLC')\n"
            f"print(ref_id({DOCUMENT!r}, content_hash(r)))\n"
        )
        environment = dict(os.environ, PYTHONHASHSEED="0", PYTHONPYCACHEPREFIX="/tmp/pyc_ref_sub")
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=os.getcwd(),
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout.strip(), ref_id(DOCUMENT, content_hash(reading()))
        )

    def test_the_reference_does_not_depend_on_the_order_rows_arrive_in(self):
        """V1's ids were handed out in whatever order the database returned.

        Here a reference belongs to a reading, so shuffling the document has
        to leave every row holding the reference it had.
        """
        rows = [reading(amount_minor=n * 100) for n in range(1, 21)]
        forward = dict(zip(rows, document_ref_ids(DOCUMENT, rows)))

        shuffled = list(rows)
        random.Random(20260830).shuffle(shuffled)
        backward = dict(zip(shuffled, document_ref_ids(DOCUMENT, shuffled)))

        self.assertEqual(forward, backward)
        self.assertEqual(len(set(forward.values())), len(rows))


class WhatChangesTheReferenceTests(unittest.TestCase):
    """A reference names a reading, so it moves when the reading does."""

    def test_every_asserted_field_changes_the_reference(self):
        base = reading()
        altered = {
            "currency": "EUR",
            "amount_minor": 2500_01,
            "direction": TransactionDirection.credit,
            "transaction_date": date(2026, 3, 15),
            "posted_date": date(2026, 3, 16),
            "value_date": date(2026, 3, 17),
            "effective_date": date(2026, 3, 18),
            "running_balance_minor": 1,
            "description": "WIRE TO MEYER LLP",
            "counterparty_raw": "MEYER LLP",
            "transaction_type": "wire",
            "bank_reference": "REF-1",
        }
        self.assertEqual(
            set(altered), {f for f in base.__slots__},
            "a field was added to RowReading without deciding whether it is "
            "part of the reading",
        )

        original = ref_id(DOCUMENT, content_hash(base))
        for field, value in altered.items():
            with self.subTest(field=field):
                changed = ref_id(DOCUMENT, content_hash(replace(base, **{field: value})))
                self.assertNotEqual(original, changed)

    def test_the_document_is_part_of_the_reference(self):
        row = content_hash(reading())
        self.assertNotEqual(ref_id(DOCUMENT, row), ref_id(OTHER_DOCUMENT, row))

    def test_collapsing_whitespace_does_not_rename_a_row(self):
        """A parser that only changes spacing must not orphan every note."""
        spaced = reading(description="  WIRE   TO\tMEYER\nLLC ")
        self.assertEqual(content_hash(spaced), content_hash(reading()))

    def test_two_encodings_of_one_character_are_one_reading(self):
        composed = reading(counterparty_raw="M\u00dcLLER GMBH")
        decomposed = reading(counterparty_raw="MU\u0308LLER GMBH")
        self.assertNotEqual(
            composed.counterparty_raw, decomposed.counterparty_raw
        )
        self.assertEqual(content_hash(composed), content_hash(decomposed))

    def test_case_is_not_folded(self):
        """What is printed on the page is evidence, including its case."""
        self.assertNotEqual(
            content_hash(reading(description="wire to meyer llc")),
            content_hash(reading()),
        )

    def test_an_absent_text_field_reads_as_an_empty_one(self):
        """Which of the two a parser emits is an artefact, not a reading."""
        self.assertEqual(
            content_hash(reading(bank_reference=None)),
            content_hash(reading(bank_reference="")),
        )

    def test_absent_fields_cannot_be_confused_with_each_other(self):
        """Fixed positions, so a missing posted date is not a missing value date."""
        posted = reading(transaction_date=None, posted_date=date(2026, 3, 14))
        value = reading(transaction_date=None, value_date=date(2026, 3, 14))
        self.assertNotEqual(content_hash(posted), content_hash(value))

    def test_a_running_balance_of_zero_is_not_an_absent_one(self):
        """Zero is a figure printed beside the row; absent is no figure at all."""
        self.assertNotEqual(
            content_hash(reading(running_balance_minor=0)),
            content_hash(reading(running_balance_minor=None)),
        )


class OccurrenceTests(unittest.TestCase):
    """Identical rows happen, and must not collide in the unique constraint."""

    def test_two_identical_rows_get_different_hashes(self):
        rows = [reading(), reading()]
        hashes = document_content_hashes(rows)
        self.assertEqual(len(set(hashes)), 2)
        self.assertEqual(hashes[0], content_hash(reading(), occurrence=0))
        self.assertEqual(hashes[1], content_hash(reading(), occurrence=1))

    def test_occurrence_counts_only_identical_readings(self):
        rows = [reading(), reading(amount_minor=99_00), reading()]
        hashes = document_content_hashes(rows)
        self.assertEqual(hashes[0], content_hash(reading(), occurrence=0))
        self.assertEqual(hashes[2], content_hash(reading(), occurrence=1))
        self.assertEqual(
            hashes[1], content_hash(reading(amount_minor=99_00), occurrence=0)
        )

    def test_inserting_a_row_does_not_rename_the_rows_below_it(self):
        """The whole reason occurrence is not ``row_index``.

        A re-extraction that recovers a row missed earlier shifts every row
        number beneath it.  If the reference were positional, every one of
        those rows would be renamed although nobody re-read them, and every
        note keyed to them would orphan.
        """
        before = [reading(amount_minor=n * 100) for n in (1, 2, 3)]
        after = [
            reading(amount_minor=100),
            reading(amount_minor=150),  # recovered on a second pass
            reading(amount_minor=200),
            reading(amount_minor=300),
        ]
        first = document_ref_ids(DOCUMENT, before)
        second = document_ref_ids(DOCUMENT, after)
        self.assertEqual([first[0], first[1], first[2]], [second[0], second[2], second[3]])

    def test_removing_one_of_two_identical_rows_is_the_admitted_exception(self):
        """Occurrence can only move where the rows were never distinguishable.

        Documented rather than defended: there is no field left to tell two
        identical readings apart, so the second one's reference is the one
        that has to give.
        """
        pair = document_content_hashes([reading(), reading()])
        single = document_content_hashes([reading()])
        self.assertEqual(pair[0], single[0])
        self.assertNotIn(pair[1], single)

    def test_hashes_are_returned_in_document_order(self):
        rows = [reading(amount_minor=n * 100) for n in range(1, 6)]
        self.assertEqual(
            document_content_hashes(rows), [content_hash(row) for row in rows]
        )

    def test_an_empty_document_yields_nothing(self):
        self.assertEqual(document_content_hashes([]), [])
        self.assertEqual(document_ref_ids(DOCUMENT, []), [])


class ReferenceFormTests(unittest.TestCase):
    """It has to be readable aloud and typable from a printed page."""

    def test_the_printed_form(self):
        value = ref_id(DOCUMENT, content_hash(reading()))
        prefix, *groups = value.split("-")
        self.assertEqual(prefix, REFERENCE_PREFIX)
        self.assertEqual([len(g) for g in groups], [4, 4, 4])
        self.assertEqual(sum(len(g) for g in groups), REFERENCE_LENGTH)

    def test_the_ambiguous_letters_are_never_printed(self):
        """I, L, O and U are absent by construction, over a wide sample."""
        seen = set()
        for n in range(3000):
            value = ref_id(DOCUMENT, content_hash(reading(amount_minor=n)))
            seen.update(value.split("-", 1)[1].replace("-", ""))
        self.assertTrue(seen)
        self.assertEqual(seen - set(ALPHABET), set())
        self.assertEqual(seen & set("ILOU"), set())

    def test_distinct_rows_get_distinct_references(self):
        values = {
            ref_id(DOCUMENT, content_hash(reading(amount_minor=n)))
            for n in range(5000)
        }
        self.assertEqual(len(values), 5000)

    def test_the_whole_sixty_bit_range_is_reachable(self):
        """Twelve base-32 characters is exactly 2**60, so encoding is a bijection.

        Asserted at both ends because an off-by-one in the encoder would show
        up nowhere else: it would still produce plausible references.
        """
        from services.financial.references import _encode

        self.assertEqual(_encode(0), "0" * REFERENCE_LENGTH)
        self.assertEqual(_encode(2**60 - 1), "Z" * REFERENCE_LENGTH)
        self.assertEqual(len({_encode(v) for v in range(4096)}), 4096)


class NormaliseTests(unittest.TestCase):
    """Reading a reference back in from a spreadsheet a person typed."""

    def setUp(self):
        self.value = ref_id(DOCUMENT, content_hash(reading()))

    def test_the_canonical_form_round_trips(self):
        self.assertEqual(normalise(self.value), self.value)

    def test_hyphens_and_case_and_spacing_are_ornament(self):
        bare = self.value.split("-", 1)[1].replace("-", "")
        for variant in (bare, bare.lower(), f"  {self.value.lower()} ", f"{REFERENCE_PREFIX}{bare}"):
            with self.subTest(variant=variant):
                self.assertEqual(normalise(variant), self.value)

    def test_the_confusable_letters_fold(self):
        """Asserted on a reference that actually contains the digit.

        Only about a third of references contain any given digit, so folding
        ``0`` into a reference that has no ``0`` in it substitutes nothing and
        the assertion passes without touching the fold.  Each case here is
        therefore run against a reference chosen for containing the character,
        and the substitution is asserted to have changed the string before the
        fold is asserted to have undone it.
        """
        for typed, meant in (("O", "0"), ("I", "1"), ("L", "1")):
            printed = self._a_reference_containing(meant)
            with self.subTest(typed=typed, printed=printed):
                mistyped = printed.replace(meant, typed)
                self.assertNotEqual(mistyped, printed, "the case did not exercise the fold")
                self.assertEqual(normalise(mistyped), printed)

    def _a_reference_containing(self, character: str) -> str:
        """The first reference in a deterministic series that carries it.

        The series is over the amount, so it is reproducible and independent of
        which reading ``setUp`` happens to build.
        """
        for minor_units in range(1, 500):
            value = ref_id(DOCUMENT, content_hash(reading(amount_minor=minor_units)))
            if character in value.split("-", 1)[1]:
                return value
        raise AssertionError(f"no reference in 500 carried {character!r}")

    def test_a_letter_that_was_never_printed_is_reported(self):
        """U is not in the alphabet, so a U is a mistake and not a fold."""
        bare = self.value.split("-", 1)[1].replace("-", "")
        with self.assertRaises(MalformedReferenceError) as caught:
            normalise(f"{REFERENCE_PREFIX}-{'U' + bare[1:]}")
        self.assertIn("U", str(caught.exception))

    def test_the_wrong_length_is_reported_with_both_numbers(self):
        with self.assertRaises(MalformedReferenceError) as caught:
            normalise("TX-ABCD-EFGH")
        self.assertIn(str(REFERENCE_LENGTH), str(caught.exception))
        self.assertIn("8", str(caught.exception))

    def test_something_that_is_not_text_is_reported(self):
        with self.assertRaises(MalformedReferenceError):
            normalise(None)

    def test_is_reference_sorts_a_column_without_raising(self):
        rows = [self.value, self.value.lower(), "", "n/a", "TX-ABCD-EFGH", None]
        self.assertEqual(
            [is_reference(r) for r in rows], [True, True, False, False, False, False]
        )


class ValidationTests(unittest.TestCase):
    """A reading that could never be stored must not be hashable either."""

    def test_a_negative_amount_is_refused(self):
        with self.assertRaises(MalformedReadingError) as caught:
            reading(amount_minor=-1)
        self.assertIn("sign lives in the direction", str(caught.exception))

    def test_a_float_amount_is_refused(self):
        with self.assertRaises(MalformedReadingError):
            reading(amount_minor=2500.00)

    def test_a_bool_amount_is_refused(self):
        """``True`` is an ``int`` in Python and would hash as ``1``."""
        with self.assertRaises(MalformedReadingError):
            reading(amount_minor=True)

    def test_a_float_running_balance_is_refused(self):
        with self.assertRaises(MalformedReadingError):
            reading(running_balance_minor=10.5)

    def test_a_direction_that_is_not_the_enum_is_refused(self):
        with self.assertRaises(MalformedReadingError):
            reading(direction="debit")

    def test_a_currency_that_is_not_a_three_letter_code_is_refused(self):
        for bad in ("usd", "US", "USDD", "US$", "", None):
            with self.subTest(currency=bad):
                with self.assertRaises(MalformedReadingError):
                    reading(currency=bad)

    def test_a_negative_occurrence_is_refused(self):
        with self.assertRaises(MalformedReadingError):
            canonical_form(reading(), occurrence=-1)

    def test_a_float_occurrence_is_refused(self):
        with self.assertRaises(MalformedReadingError):
            canonical_form(reading(), occurrence=1.0)

    def test_a_bool_occurrence_is_refused(self):
        """``True`` is an ``int``, but it does not render as ``"1"``.

        ``str(True)`` is ``"True"``, so a caller who passed a flag where a count
        belongs would not collide with occurrence 1 -- they would get a hash in
        a namespace of their own, for a row indistinguishable from one already
        stored.  Silent and unrecoverable, so it is refused at the door.
        """
        for flag in (True, False):
            with self.subTest(flag=flag), self.assertRaises(MalformedReadingError):
                canonical_form(reading(), occurrence=flag)

    def test_a_digest_that_is_not_a_digest_is_refused(self):
        row = content_hash(reading())
        for bad in ("", "zz" * 32, "3b" * 31, None, 7):
            with self.subTest(value=bad):
                with self.assertRaises(MalformedReferenceError):
                    ref_id(bad, row)
                with self.assertRaises(MalformedReferenceError):
                    ref_id(DOCUMENT, bad)

    def test_a_digest_is_read_case_insensitively(self):
        """sha256 hex arrives upper-cased from some tools and is the same digest."""
        row = content_hash(reading())
        self.assertEqual(
            ref_id(DOCUMENT.upper(), row.upper()), ref_id(DOCUMENT, row)
        )


class ShapeTests(unittest.TestCase):
    """What the values have to fit into."""

    def test_both_values_fit_their_columns(self):
        row = content_hash(reading())
        self.assertEqual(len(row), 64)  # String(64) on content_hash
        self.assertLessEqual(
            len(ref_id(DOCUMENT, row)), 64
        )  # String(64) on ref_id

    def test_the_canonical_form_is_separated_by_a_character_text_cannot_hold(self):
        """The separator must not be producible by a PDF reader."""
        form = canonical_form(reading(description="a|b,c;d\te"), occurrence=0)
        self.assertEqual(form.count("\x1f"), 12)


class GoldenVectorTests(unittest.TestCase):
    """One reading, written out in full, with the values it must always give.

    Every other test here is differential: it asserts that two things agree, or
    that changing something changes the answer.  Differential tests are the
    right shape for almost everything in this module, but they share a blind
    spot -- they all still pass if the derivation moves wholesale.  Widen the
    digest slice, flip the byte order, reorder the fields: references stay
    unique, stay stable within a release, stay order-independent, and every
    property asserted elsewhere still holds.  What breaks is the only promise
    that matters, which is that a reference printed in a report resolves to the
    same row years later, in a later release, on a different machine.

    Mutation testing is what surfaced this: narrowing the digest to four bytes
    and reversing its byte order were both survived by the whole suite.  So the
    values below are written out as literals.  They are not derived from the
    code at test time, because a value derived from the code cannot contradict
    it.

    If one of these fails, the derivation changed.  That is not necessarily
    wrong -- but it means every reference ever printed is now dangling, so it is
    a migration and an exhibit re-issue, not a patch.  Changing the literal to
    match the new output is the one repair that must not be made silently.
    """

    DOCUMENT = "3b" * 32
    CONTENT_HASH = "38c89cfb67ff904eb406e383f2bc06086ddfebeeecf646be290a53e3cfd60e3e"
    REF_ID = "TX-QE1S-SWW7-AQ41"

    def _reading(self) -> RowReading:
        """Every field populated, including ones a simpler fixture leaves out.

        The description carries a doubled space so that the vector pins
        whitespace collapsing too, and the running balance is negative because
        an overdrawn account is where the sign discipline is easiest to get
        wrong.
        """
        return RowReading(
            currency="GBP",
            amount_minor=125000,
            direction=TransactionDirection.debit,
            transaction_date=date(2024, 3, 11),
            posted_date=date(2024, 3, 12),
            value_date=None,
            effective_date=None,
            running_balance_minor=-4250,
            description="CARD PAYMENT TO  ACME  LTD",
            counterparty_raw="ACME LTD",
            transaction_type="DEB",
            bank_reference="REF/00919",
        )

    def test_the_canonical_form_is_what_it_has_always_been(self):
        self.assertEqual(
            canonical_form(self._reading(), occurrence=0),
            "GBP\x1f125000\x1fdebit\x1f2024-03-11\x1f2024-03-12\x1f\x1f\x1f-4250"
            "\x1fCARD PAYMENT TO ACME LTD\x1fACME LTD\x1fDEB\x1fREF/00919\x1f0",
        )

    def test_the_content_hash_is_what_it_has_always_been(self):
        self.assertEqual(content_hash(self._reading()), self.CONTENT_HASH)

    def test_the_reference_is_what_it_has_always_been(self):
        """Pins the slice, the shift, the byte order and the alphabet at once."""
        self.assertEqual(ref_id(self.DOCUMENT, self.CONTENT_HASH), self.REF_ID)

    def test_the_vector_is_self_consistent(self):
        """The two literals above describe one row, not two unrelated ones."""
        self.assertEqual(
            ref_id(self.DOCUMENT, content_hash(self._reading())), self.REF_ID
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
