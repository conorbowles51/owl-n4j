"""Tests for reading a native bank file without storing it.

The corpus caveat from ``test_financial_native`` and
``test_financial_native_subjects`` applies once more and compounds again: these
fixtures are the four parser suites' builders, read through the row adapter,
described by the subject adapter, and described once more here.  Nothing below
is independent evidence that any parser is right.

What it is evidence for is the seam this module owns, which is a promise about
*what a screen may say*.  The precheck exists so a person can be shown what
would land before anything lands, and every failure mode of that promise is a
person deciding to store a file on the strength of a description that was not
true of it.  So the tests are organised around the ways the description could
lie rather than around the functions.

:class:`OutcomeTests` pins the verdicts.  Each one exists because the caller's
next move differs: widening a window, reading at a layer above zero, and
finding the rest of a document are three different actions, and collapsing any
two of them into one outcome would send someone to do the wrong one.

:class:`FactsSurviveFailureTests` is the one most easily deleted by someone
tidying.  A file that parsed forty rows and then could not have its accounts
described still parsed forty rows, and a description that reported only the
refusal would leave a person unable to tell a nearly-right bank file from a
photograph.  The assertion is that the parse facts are present on a *failing*
outcome, which is exactly the case a naive implementation returns bare.

:class:`AttributionTests` pins the failure that ingestion would raise and this
is meant to predict.  Rows carry an account key; subjects carry account keys;
a row whose key matches no subject cannot be stored without either inventing an
account or putting one account's money on another.  The precheck has to say so
*before* the write, which is the whole reason it re-derives through the real
``describe_subjects`` instead of trusting the reading alone.

:class:`IdentifiedFlagTests` guards a distinction that reads like a detail and
is not.  ``identified`` false does not mean the file printed no account number.
A number with no institution beside it does not identify an account, because
the same digits belong to a different account at every other bank -- so a BAI2
statement lands with its number visible and ``identified`` false, and the
consequence is that those movements cannot be joined to the same account in
another document.  A test that only checked "unidentified means no identifier
printed" would pass against an implementation that had thrown the number away.

:class:`CaseScopeTests` pins the two properties that are security-shaped: a
file in another case is reported exactly as one that does not exist, and the
distinguisher is taken from the evidence row's own hash rather than computed a
second way.  The second is what makes the account keys shown here the keys that
would actually be written.
"""

from __future__ import annotations

import datetime
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from services.financial import native_precheck
from services.financial.native import (
    AmbiguousFormatError,
    CenturyWindow,
    NativeFormat,
    read_native,
)
from services.financial.native_precheck import (
    MAX_PRECHECK_BYTES,
    FilePrecheck,
    PrecheckOutcome,
    precheck_bytes,
    precheck_case_file,
    precheck_path,
    precheck_reading,
)

# The same builders every layer below this one imports, for the same reason: a
# copy of any of these fixtures here would drift from its origin silently.
from tests.test_financial_camt053 import build as camt_build, stmt
from tests.test_financial_native import (
    WINDOW,
    NACHA_SIMPLE,
    bai2_bytes,
    camt_bytes,
    mt940_bytes,
    nacha_bytes,
)
from tests.test_financial_native_subjects import NO_IDENTIFIER, OTHER_ACCOUNT

D = datetime.date

#: Sixty-four hex characters, the shape of the value the evidence row carries.
SHA = "a" * 64


def check(data: bytes, **kw) -> FilePrecheck:
    """Precheck bytes with the shared window and hash unless overridden."""
    kw.setdefault("window", WINDOW)
    kw.setdefault("distinguisher", SHA)
    kw.setdefault("file_id", "file-1")
    return precheck_bytes(data, **kw)


class OutcomeTests(unittest.TestCase):
    """One verdict per thing the person asking has to do next."""

    def test_all_four_native_formats_are_readable(self) -> None:
        for name, data in (
            ("camt053", camt_bytes()),
            ("bai2", bai2_bytes()),
            ("mt940", mt940_bytes()),
            ("nacha", nacha_bytes(NACHA_SIMPLE)),
        ):
            with self.subTest(format=name):
                result = check(data)
                self.assertIs(result.outcome, PrecheckOutcome.readable)
                self.assertTrue(result.would_ingest)
                self.assertEqual(result.detected_format, name)
                self.assertIsNone(result.reason)

    def test_a_file_no_parser_claims_is_unrecognised(self) -> None:
        result = check(b"this is not a bank file")
        self.assertIs(result.outcome, PrecheckOutcome.unrecognised)
        self.assertFalse(result.would_ingest)
        self.assertIsNotNone(result.reason)

    def test_a_file_two_parsers_claim_is_ambiguous_not_unrecognised(self) -> None:
        """The two are separated because the remedies differ.

        An unrecognised file is read at a layer above zero.  An ambiguous one is
        a detector problem, and reading it at another layer would silently pick
        one of the two formats.
        """
        with patch.object(
            native_precheck,
            "read_native",
            side_effect=AmbiguousFormatError("two parsers claim this"),
        ):
            result = check(camt_bytes())
        self.assertIs(result.outcome, PrecheckOutcome.ambiguous)
        self.assertIn("two parsers claim this", result.reason)

    def test_a_row_year_outside_the_window_is_out_of_window(self) -> None:
        """Reported as its own outcome because widening the window fixes it."""
        narrow = CenturyWindow(D(2001, 1, 1), D(2002, 12, 31))
        result = check(mt940_bytes(), window=narrow)
        self.assertIs(result.outcome, PrecheckOutcome.out_of_window)
        self.assertIn("window", result.reason)

    def test_a_parser_that_raises_is_unreadable_not_a_crash(self) -> None:
        """A malformed file is an answer, not a failed request.

        The traceback is still logged.  The person asking gets a verdict they
        can act on, and the engineer keeps the stack that says which parser
        fell over -- swallowing it quietly would trade one for the other.
        """
        with patch.object(
            native_precheck, "read_native", side_effect=ValueError("ragged record")
        ):
            with self.assertLogs(native_precheck.logger, level="ERROR") as logged:
                result = check(camt_bytes())
        self.assertIs(result.outcome, PrecheckOutcome.unreadable)
        self.assertIn("ValueError", result.reason)
        self.assertIn("ragged record", result.reason)
        self.assertIn("ragged record", "\n".join(logged.output))

    def test_two_unnamed_accounts_in_one_file_are_unattributable(self) -> None:
        """The refusal ``describe_subjects`` makes, reported rather than raised."""
        data = camt_build(
            statements=stmt(identification="S1", account=NO_IDENTIFIER)
            + stmt(identification="S2", account=NO_IDENTIFIER)
        )
        result = check(data)
        self.assertIs(result.outcome, PrecheckOutcome.unattributable)
        self.assertFalse(result.would_ingest)
        self.assertIn("print no identifier", result.reason)

    def test_the_dead_window_branch_stays_dead(self) -> None:
        """An unresolvable *balance* date must not become ``out_of_window``.

        ``native_subjects._yymmdd`` swallows ``DateResolutionError`` on purpose
        and records the bound as absent, because raising would discard a whole
        statement -- its rows, amounts and balances -- over its bounds alone.
        This asserts the precheck does not reintroduce the discard by catching
        an error that cannot arrive, which is the shape the module had first.
        """
        reading = read_native(mt940_bytes(), window=WINDOW)
        with patch.object(
            native_precheck,
            "describe_subjects",
            side_effect=native_precheck.DateResolutionError("balance date"),
        ):
            with self.assertRaises(native_precheck.DateResolutionError):
                precheck_reading(
                    reading,
                    window=WINDOW,
                    distinguisher=SHA,
                    file_id="file-1",
                )


class FactsSurviveFailureTests(unittest.TestCase):
    """What the parse established is true whether or not describing worked."""

    def setUp(self) -> None:
        self.result = check(
            camt_build(
                statements=stmt(identification="S1", account=NO_IDENTIFIER)
                + stmt(identification="S2", account=NO_IDENTIFIER)
            )
        )

    def test_the_outcome_is_still_a_failure(self) -> None:
        self.assertIs(self.result.outcome, PrecheckOutcome.unattributable)

    def test_the_format_and_parser_are_reported_anyway(self) -> None:
        self.assertEqual(self.result.detected_format, NativeFormat.camt053.value)
        self.assertIsNotNone(self.result.parser_name)
        self.assertIsNotNone(self.result.parser_version)

    def test_the_row_counts_are_reported_anyway(self) -> None:
        """A file that parsed rows parsed them, and the person needs to know."""
        self.assertIsNotNone(self.result.row_count)
        self.assertGreater(self.result.row_count, 0)
        self.assertIsNotNone(self.result.parsed_row_count)

    def test_the_date_range_is_reported_anyway(self) -> None:
        self.assertIsNotNone(self.result.earliest_ordering_date)
        self.assertIsNotNone(self.result.latest_ordering_date)
        self.assertLessEqual(
            self.result.earliest_ordering_date, self.result.latest_ordering_date
        )


class ReadingFactsTests(unittest.TestCase):
    """The description matches the reading it came from, field by field."""

    def setUp(self) -> None:
        self.reading = read_native(camt_bytes(), window=WINDOW)
        self.result = precheck_reading(
            self.reading, window=WINDOW, distinguisher=SHA, file_id="file-1"
        )

    def test_counts_come_from_the_reading(self) -> None:
        self.assertEqual(self.result.row_count, self.reading.row_count)
        self.assertEqual(
            self.result.parsed_row_count, self.reading.parsed_row_count
        )

    def test_the_provenance_fields_come_from_the_reading(self) -> None:
        self.assertEqual(
            self.result.proof_class, self.reading.proof_class.value
        )
        self.assertEqual(
            self.result.reconciliation_status,
            self.reading.reconciliation_status.value,
        )
        self.assertEqual(
            self.result.extraction_layer, int(self.reading.extraction_layer.value)
        )

    def test_stored_and_skipped_rows_are_both_reported(self) -> None:
        """Reporting one without the other is how a total covers a subset."""
        self.assertEqual(len(self.result.skipped), len(self.reading.unmapped))
        self.assertEqual(
            self.result.parsed_row_count,
            self.result.row_count + len(self.result.skipped),
        )

    def test_the_whole_description_is_json_serialisable(self) -> None:
        """It is returned by an API, so a date that is not a string is a 500."""
        json.dumps(self.result.as_dict())


class PeriodClaimTests(unittest.TestCase):
    """A period is reported only where the document claims one."""

    def test_a_statement_carries_a_period(self) -> None:
        result = check(camt_bytes())
        self.assertIsNotNone(result.accounts[0].period)

    def test_nacha_carries_no_period_for_anybody(self) -> None:
        """A batch of payment instructions makes no claim to cover a span.

        Inventing one here would put a coverage claim on the record that no
        document made, which is the tempting change because it makes the shapes
        uniform.
        """
        result = check(nacha_bytes(NACHA_SIMPLE))
        self.assertTrue(result.accounts)
        for account in result.accounts:
            self.assertIsNone(account.period)

    def test_an_absent_balance_is_not_a_zero_balance(self) -> None:
        """Flattening the two would let a total be computed from a gap."""
        result = check(bai2_bytes())
        period = result.accounts[0].period
        self.assertIsNotNone(period)
        for balance in (period.opening, period.closing):
            if balance.source == "absent":
                self.assertIsNone(balance.amount_minor)


class IdentifiedFlagTests(unittest.TestCase):
    """What ``identified`` means, and what it does not mean."""

    def test_a_file_printing_an_iban_is_identified(self) -> None:
        result = check(camt_bytes())
        self.assertTrue(result.accounts[0].identified)

    def test_a_number_with_no_institution_is_not_an_identity(self) -> None:
        """The same digits are a different account at every other bank."""
        result = check(bai2_bytes())
        self.assertFalse(result.accounts[0].identified)

    def test_the_printed_number_is_still_reported(self) -> None:
        """Unidentified is not the same as nothing printed.

        This is the assertion that fails against an implementation which threw
        the number away on deciding it did not identify anything.
        """
        result = check(bai2_bytes())
        account = result.accounts[0]
        self.assertFalse(account.identified)
        self.assertIsNotNone(account.identifier_as_printed)

    def test_rows_are_counted_against_the_account_they_name(self) -> None:
        result = check(
            camt_build(
                statements=stmt(identification="S1", account=NO_IDENTIFIER)
                + stmt(identification="S2", account=OTHER_ACCOUNT)
            )
        )
        self.assertIs(result.outcome, PrecheckOutcome.readable)
        self.assertEqual(
            sum(account.row_count for account in result.accounts),
            result.row_count,
        )


class AttributionTests(unittest.TestCase):
    """The ingestion failure this exists to predict."""

    def test_a_row_naming_no_described_account_is_unattributable(self) -> None:
        reading = read_native(camt_bytes(), window=WINDOW)
        with patch.object(native_precheck, "describe_subjects", return_value=()):
            result = precheck_reading(
                reading, window=WINDOW, distinguisher=SHA, file_id="file-1"
            )
        self.assertIs(result.outcome, PrecheckOutcome.unattributable)
        self.assertEqual(result.unattributed_row_count, reading.row_count)
        self.assertTrue(result.unattributed_keys)

    def test_the_reason_says_what_storing_them_would_do(self) -> None:
        """A reason naming the consequence, not the internal condition."""
        reading = read_native(camt_bytes(), window=WINDOW)
        with patch.object(native_precheck, "describe_subjects", return_value=()):
            result = precheck_reading(
                reading, window=WINDOW, distinguisher=SHA, file_id="file-1"
            )
        self.assertIn("does not describe", result.reason)

    def test_a_fully_attributed_file_reports_none_outstanding(self) -> None:
        result = check(camt_bytes())
        self.assertEqual(result.unattributed_keys, ())
        self.assertEqual(result.unattributed_row_count, 0)


class PathTests(unittest.TestCase):
    """Opening the file, and the three ways that does not happen."""

    def test_a_file_with_no_stored_path_is_unreadable(self) -> None:
        result = precheck_path(
            None, window=WINDOW, distinguisher=SHA, file_id="file-1"
        )
        self.assertIs(result.outcome, PrecheckOutcome.unreadable)
        self.assertIn("no stored path", result.reason)

    def test_a_missing_file_is_unreadable_not_an_exception(self) -> None:
        result = precheck_path(
            Path("/nonexistent/definitely/not/here.sta"),
            window=WINDOW,
            distinguisher=SHA,
            file_id="file-1",
        )
        self.assertIs(result.outcome, PrecheckOutcome.unreadable)

    def test_an_oversized_file_is_refused_without_being_read(self) -> None:
        """Route-check calls a file native from a prefix, and a prefix can lie.

        Asserted by refusing on ``stat`` alone: the read is never reached, which
        is the property that keeps an unbounded file out of request memory.
        """

        class HugeStat:
            st_size = MAX_PRECHECK_BYTES + 1

        with patch.object(Path, "stat", return_value=HugeStat()), patch.object(
            Path, "read_bytes", side_effect=AssertionError("must not be read")
        ):
            result = precheck_path(
                Path("/tmp/huge.sta"),
                window=WINDOW,
                distinguisher=SHA,
                file_id="file-1",
            )

        self.assertIs(result.outcome, PrecheckOutcome.unreadable)
        self.assertIn("limit", result.reason)


class _FakeRecord:
    def __init__(self, *, case_id, sha256=SHA, stored_path="/evidence/x.sta"):
        self.id = uuid.uuid4()
        self.case_id = case_id
        self.sha256 = sha256
        self.stored_path = stored_path
        self.original_filename = "statement.sta"


class CaseScopeTests(unittest.TestCase):
    """Which file, whose case, and where the distinguisher comes from."""

    def setUp(self) -> None:
        self.case_id = uuid.uuid4()
        self.file_id = uuid.uuid4()

    def _run(self, record, **kw):
        with patch(
            "services.evidence_db_storage.EvidenceDBStorage.get", return_value=record
        ):
            return precheck_case_file(
                "fake-session",
                case_id=self.case_id,
                file_id=self.file_id,
                resolve_path=kw.pop("resolve_path", lambda p: Path(p)),
                window=WINDOW,
                **kw,
            )

    def test_a_missing_file_is_not_found(self) -> None:
        result = self._run(None)
        self.assertIs(result.outcome, PrecheckOutcome.not_found)

    def test_a_file_in_another_case_is_reported_identically(self) -> None:
        """Otherwise asking becomes a way to learn what another case holds."""
        absent = self._run(None)
        elsewhere = self._run(_FakeRecord(case_id=uuid.uuid4()))
        self.assertIs(elsewhere.outcome, PrecheckOutcome.not_found)
        self.assertEqual(elsewhere.reason, absent.reason)

    def test_a_row_with_no_content_hash_is_refused(self) -> None:
        """Falling back to the file id would produce keys ingestion would not."""
        result = self._run(_FakeRecord(case_id=self.case_id, sha256=""))
        self.assertIs(result.outcome, PrecheckOutcome.unreadable)
        self.assertIn("content hash", result.reason)

    def test_the_distinguisher_is_the_rows_own_hash(self) -> None:
        """This is what makes the keys shown the keys that would be written."""
        record = _FakeRecord(case_id=self.case_id, sha256="b" * 64)
        with patch.object(
            native_precheck, "precheck_path", return_value=FilePrecheck(
                file_id="x", outcome=PrecheckOutcome.readable
            )
        ) as call:
            self._run(record)
        self.assertEqual(call.call_args.kwargs["distinguisher"], "b" * 64)

    def test_the_stored_path_goes_through_the_callers_resolver(self) -> None:
        """The path on the row is not always a path in this process."""
        record = _FakeRecord(case_id=self.case_id, stored_path="evidence-data/x.sta")
        seen = []

        def resolver(path):
            seen.append(path)
            return None

        self._run(record, resolve_path=resolver)
        self.assertEqual(seen, ["evidence-data/x.sta"])

    def test_a_readable_file_reports_the_records_own_name_and_id(self) -> None:
        record = _FakeRecord(case_id=self.case_id)
        with patch.object(
            native_precheck,
            "precheck_path",
            side_effect=lambda p, **kw: FilePrecheck(
                file_id=kw["file_id"],
                file_name=kw["file_name"],
                outcome=PrecheckOutcome.readable,
            ),
        ):
            result = self._run(record)
        self.assertEqual(result.file_id, str(record.id))
        self.assertEqual(result.file_name, "statement.sta")


if __name__ == "__main__":
    unittest.main()
