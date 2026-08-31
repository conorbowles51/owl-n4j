"""Tests for account identity: what the writer refuses, and why.

Most of these assert a refusal rather than an insert.  That is the shape the
module calls for.  An account writer that inserts rows is easy; one that
declines to turn ``see statement`` into an identity is the whole point, because
the failure it prevents is silent.  Thirty-six documents in the working corpus
print that string in the account-number field, and anything that treats it as a
value concludes they describe one account — which then makes them one duplicate
group as well, since a period's signature is built from its account's identity
key.  Nothing downstream can detect either error.  The balance identity still
runs, continuity still looks contiguous, and the total is simply wrong.

So the tests are organised around the two directions of failure, which are not
symmetric.  A false merge combines two people's money and is invisible.  A
false split is two rows in a list a human reads, and ``AdjudicationSubject``
already has a member for correcting it.  Where a judgement could go either way,
the assertion is that the module splits.

The database-backed tests use a file on disk rather than ``:memory:``, matching
``test_financial_periods`` and ``test_financial_runs``: the run service opens
sessions of its own, and a test where the caller and the bookkeeping share one
connection cannot see what production sees.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
import uuid
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import GlobalRole
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.financial import (
    FinancialAccount,
    FinancialIngestionRun,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from postgres.models.user import User
from services.financial.accounts import (
    NON_VALUES,
    TIER_IBAN,
    TIER_INSTITUTION_ACCOUNT,
    TIER_INSTITUTION_MASKED,
    TIER_ROUTING_ACCOUNT,
    TIER_UNIDENTIFIED,
    AccountCurrencyError,
    AccountDraft,
    AccountError,
    AccountFieldError,
    AccountIdentityError,
    PlaceholderIdentifierError,
    digits_only,
    is_masked,
    is_non_value,
    read_identity_tier,
    record_account,
)
from services.financial.runs import RunScopeError, open_ingestion_run

TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    FinancialIngestionRun.__table__,
    FinancialSourceDocument.__table__,
    FinancialAccount.__table__,
    FinancialStatementPeriod.__table__,
    FinancialTransaction.__table__,
]

GBP = "GBP"
USD = "USD"

#: A valid IBAN and a valid ABA routing number, used where the tier under test
#: depends on a check digit passing rather than on the particular institution.
GOOD_IBAN = "GB82WEST12345698765432"
GOOD_ROUTING = "021000021"


# ---------------------------------------------------------------------------
# The guard.  No database: these are about what may become identity at all.
# ---------------------------------------------------------------------------


class NonValueTests(unittest.TestCase):
    def test_the_string_the_corpus_actually_contains(self):
        """Thirty-six documents print this where an account number belongs."""
        self.assertTrue(is_non_value("see statement"))

    def test_recognised_regardless_of_case_spacing_or_punctuation(self):
        """One placeholder typed six ways is still one placeholder."""
        for spelling in (
            "See Statement",
            "SEE STATEMENT",
            "  see   statement  ",
            "See statement.",
            "[see statement]",
            "'see statement'",
        ):
            with self.subTest(spelling=spelling):
                self.assertTrue(is_non_value(spelling))

    def test_the_other_two_the_corpus_contains(self):
        self.assertTrue(is_non_value("varies"))
        self.assertTrue(is_non_value("various"))

    def test_a_value_made_only_of_mask_characters_identifies_nothing(self):
        """Not vocabulary but a rule: no digit of the original survives."""
        for masked in ("****", "xxxx", "XXXX", "####", "**-****", "•••••"):
            with self.subTest(masked=masked):
                self.assertTrue(is_non_value(masked))

    def test_a_mask_with_a_visible_tail_is_a_value(self):
        """It identifies weakly, which is not the same as identifying nothing."""
        self.assertFalse(is_non_value("****7890"))
        self.assertFalse(is_non_value("XXXX-XXXX-XXXX-1234"))

    def test_real_identifiers_survive_the_guard(self):
        for real in ("0", "00000000", "20-44-55 66", GOOD_IBAN, GOOD_ROUTING):
            with self.subTest(real=real):
                self.assertFalse(is_non_value(real))

    def test_absent_is_a_non_value(self):
        self.assertTrue(is_non_value(None))
        self.assertTrue(is_non_value(""))
        self.assertTrue(is_non_value("   "))

    def test_the_vocabulary_is_stored_folded(self):
        """Otherwise an entry with a capital in it could never match."""
        for entry in NON_VALUES:
            with self.subTest(entry=entry):
                self.assertEqual(entry, entry.casefold())
                self.assertEqual(entry, entry.strip())


class MaskDetectionTests(unittest.TestCase):
    def test_common_mask_characters(self):
        for masked in ("****7890", "••••7890", "####7890", "xxxx7890", "XXXX7890"):
            with self.subTest(masked=masked):
                self.assertTrue(is_masked(masked))

    def test_a_single_x_does_not_mask(self):
        """One x can appear in a real identifier; two in a row cannot."""
        self.assertFalse(is_masked("GB82WEST1234x698765432"))

    def test_a_plain_number_is_not_masked(self):
        self.assertFalse(is_masked("1234567890"))
        self.assertFalse(is_masked("20-44-55 66"))

    def test_digits_only_keeps_order_and_drops_everything_else(self):
        self.assertEqual(digits_only("20-44-55 66"), "20445566")
        self.assertEqual(digits_only("****7890"), "7890")
        self.assertEqual(digits_only("no digits here"), "")


class PlaceholderRefusalTests(unittest.TestCase):
    """The guard applies to identifying fields and to nothing else."""

    def test_placeholder_account_number_is_refused(self):
        with self.assertRaises(PlaceholderIdentifierError) as caught:
            AccountDraft.observed(
                institution_name="Capital One", identifier_as_printed="see statement"
            )
        self.assertIn("identifies nothing", str(caught.exception))

    def test_the_refusal_names_the_way_out(self):
        """A caller that hits this needs to know unidentified() exists."""
        with self.assertRaises(PlaceholderIdentifierError) as caught:
            AccountDraft.observed(identifier_as_printed="n/a")
        self.assertIn("unidentified", str(caught.exception))

    def test_placeholder_iban_is_refused(self):
        with self.assertRaises(PlaceholderIdentifierError):
            AccountDraft.observed(iban="not provided", identifier_as_printed="1234")

    def test_placeholder_routing_number_is_refused(self):
        with self.assertRaises(PlaceholderIdentifierError):
            AccountDraft.observed(
                routing_number="unknown", identifier_as_printed="1234"
            )

    def test_a_placeholder_institution_name_is_carried_not_refused(self):
        """It is what the page said, and the page is the evidence.

        ``corpus.INSTITUTION_FIELD`` makes the same argument: these values are
        raw extractor output, and mapping them onto a controlled vocabulary
        would manufacture a fact rather than read one.
        """
        draft = AccountDraft.observed(institution_name="see statement", iban=GOOD_IBAN)
        self.assertEqual(draft.institution_name, "see statement")
        self.assertEqual(draft.identity().tier, TIER_IBAN)

    def test_an_iban_in_the_account_number_field_is_not_sniffed_out(self):
        """The module reads named fields; it does not detect what a value is.

        ``IdentifierKind`` sets the rule this follows: the vocabulary is
        deliberately not a detector, because the caller read the value out of a
        named field and therefore already knows which it is.  A draft offering
        an IBAN as ``identifier_as_printed`` under a placeholder institution
        has nothing this module will treat as identity, and the refusal sends
        the caller to ``unidentified()`` -- one account per document, which is
        the splitting direction.
        """
        with self.assertRaises(AccountIdentityError):
            AccountDraft.observed(
                institution_name="see statement", identifier_as_printed=GOOD_IBAN
            )

    def test_a_placeholder_institution_name_cannot_join(self):
        """Carried, but it takes no part in the key.

        Without this, every document printing 'see statement' as its bank and a
        different number would still be fine -- but two printing it with the
        same masked tail would merge across institutions.
        """
        with self.assertRaises(AccountIdentityError):
            AccountDraft.observed(
                institution_name="see statement", identifier_as_printed="****7890"
            )

    def test_a_placeholder_holder_name_is_carried(self):
        draft = AccountDraft.observed(
            institution_name="Barclays",
            identifier_as_printed="20445566",
            holder_name="unknown",
        )
        self.assertEqual(draft.holder_name, "unknown")

    def test_nothing_identifying_at_all_is_refused(self):
        with self.assertRaises(AccountIdentityError) as caught:
            AccountDraft.observed(holder_name="J Smith", currency=GBP)
        self.assertIn("unidentified", str(caught.exception))


# ---------------------------------------------------------------------------
# Identity tiers
# ---------------------------------------------------------------------------


class IdentityTierTests(unittest.TestCase):
    def test_iban_beats_everything_and_stands_alone(self):
        identity = AccountDraft.observed(iban=GOOD_IBAN).identity()
        self.assertEqual(identity.tier, TIER_IBAN)
        self.assertFalse(identity.is_provisional)

    def test_iban_spacing_does_not_change_the_key(self):
        spaced = AccountDraft.observed(iban="GB82 WEST 1234 5698 7654 32").identity()
        tight = AccountDraft.observed(iban=GOOD_IBAN).identity()
        self.assertEqual(spaced.key, tight.key)

    def test_a_failed_iban_check_demotes_rather_than_raising(self):
        """A failed check digit is usually a real error in the document.

        Dropping the document would discard evidence over a transcription the
        bank itself got wrong, so the identifier is set aside, the verdict is
        recorded, and the next tier is tried.
        """
        identity = AccountDraft.observed(
            iban="GB82WEST12345698765433",
            institution_name="NatWest",
            identifier_as_printed="98765433",
        ).identity()

        self.assertEqual(identity.tier, TIER_INSTITUTION_ACCOUNT)
        self.assertEqual(identity.verdicts["iban"], "failed")

    def test_routing_plus_full_number_outranks_institution_name(self):
        """A verified routing number names the bank; a string only describes it."""
        identity = AccountDraft.observed(
            institution_name="Chase",
            routing_number=GOOD_ROUTING,
            identifier_as_printed="1234567890",
        ).identity()
        self.assertEqual(identity.tier, TIER_ROUTING_ACCOUNT)

    def test_a_failed_routing_check_demotes_to_the_institution_tier(self):
        identity = AccountDraft.observed(
            institution_name="Chase",
            routing_number="021000022",
            identifier_as_printed="1234567890",
        ).identity()
        self.assertEqual(identity.tier, TIER_INSTITUTION_ACCOUNT)
        self.assertEqual(identity.verdicts["routing_number"], "failed")

    def test_routing_with_a_masked_number_does_not_reach_the_routing_tier(self):
        """The tier claims a full account number.  Four digits is not one."""
        identity = AccountDraft.observed(
            institution_name="Chase",
            routing_number=GOOD_ROUTING,
            identifier_as_printed="****7890",
        ).identity()
        self.assertEqual(identity.tier, TIER_INSTITUTION_MASKED)

    def test_a_bic_alone_never_identifies_an_account(self):
        """It names an institution.  Treating it as identity would merge every
        account at that bank into one."""
        with self.assertRaises(AccountIdentityError):
            AccountDraft.observed(bic="DEUTDEFF")

    def test_the_masked_tier_is_marked_provisional(self):
        identity = AccountDraft.observed(
            institution_name="Chase", identifier_as_printed="****7890"
        ).identity()
        self.assertEqual(identity.tier, TIER_INSTITUTION_MASKED)
        self.assertTrue(identity.is_provisional)

    def test_a_full_number_is_not_the_same_key_as_a_masked_one(self):
        """The tier prefix is what guarantees it, not luck about digit counts."""
        full = AccountDraft.observed(
            institution_name="Chase", identifier_as_printed="7890"
        ).identity()
        masked = AccountDraft.observed(
            institution_name="Chase", identifier_as_printed="****7890"
        ).identity()
        self.assertNotEqual(full.key, masked.key)


class IdentityStabilityTests(unittest.TestCase):
    """Two documents describing one account must reach one key."""

    def test_institution_case_and_spacing_do_not_split_an_account(self):
        first = AccountDraft.observed(
            institution_name="CHASE BANK", identifier_as_printed="1234567890"
        ).identity()
        second = AccountDraft.observed(
            institution_name="  Chase   Bank ", identifier_as_printed="1234567890"
        ).identity()
        self.assertEqual(first.key, second.key)

    def test_identifier_punctuation_does_not_split_an_account(self):
        first = AccountDraft.observed(
            institution_name="Barclays", identifier_as_printed="20-44-55 66"
        ).identity()
        second = AccountDraft.observed(
            institution_name="Barclays", identifier_as_printed="20445566"
        ).identity()
        self.assertEqual(first.key, second.key)

    def test_descriptive_fields_do_not_change_the_key(self):
        """Holder name and account type vary in print between documents."""
        bare = AccountDraft.observed(
            institution_name="Barclays", identifier_as_printed="20445566"
        ).identity()
        described = AccountDraft.observed(
            institution_name="Barclays",
            identifier_as_printed="20445566",
            holder_name="MR J SMITH",
            account_type="current",
            currency=GBP,
        ).identity()
        self.assertEqual(bare.key, described.key)

    def test_different_institutions_are_different_accounts(self):
        first = AccountDraft.observed(
            institution_name="Barclays", identifier_as_printed="20445566"
        ).identity()
        second = AccountDraft.observed(
            institution_name="HSBC", identifier_as_printed="20445566"
        ).identity()
        self.assertNotEqual(first.key, second.key)


class UnidentifiedAccountTests(unittest.TestCase):
    """The constructor that stops thirty-six documents becoming one account."""

    def test_two_unidentified_documents_do_not_share_an_account(self):
        """The central anti-merge assertion of the module."""
        first = AccountDraft.unidentified(
            distinguisher="sha256:aaa",
            institution_name="see statement",
            identifier_as_printed="see statement",
        ).identity()
        second = AccountDraft.unidentified(
            distinguisher="sha256:bbb",
            institution_name="see statement",
            identifier_as_printed="see statement",
        ).identity()

        self.assertEqual(first.tier, TIER_UNIDENTIFIED)
        self.assertNotEqual(first.key, second.key)

    def test_re_reading_one_document_reaches_the_same_account(self):
        """Stable distinguisher, stable key: a re-extraction must not fork."""
        first = AccountDraft.unidentified(distinguisher="sha256:aaa").identity()
        second = AccountDraft.unidentified(distinguisher="sha256:aaa").identity()
        self.assertEqual(first.key, second.key)

    def test_the_placeholder_is_still_stored_as_printed(self):
        """It took no part in the key, but it is what the document said."""
        draft = AccountDraft.unidentified(
            distinguisher="sha256:aaa", identifier_as_printed="see statement"
        )
        self.assertEqual(draft.identifier_as_printed, "see statement")
        self.assertIsNone(draft.identifier_normalised)

    def test_a_distinguisher_is_required(self):
        with self.assertRaises(AccountIdentityError) as caught:
            AccountDraft.unidentified(distinguisher="")
        self.assertIn("distinguisher", str(caught.exception))

    def test_a_whitespace_distinguisher_is_not_a_distinguisher(self):
        with self.assertRaises(AccountIdentityError):
            AccountDraft.unidentified(distinguisher="   ")

    def test_unidentified_is_provisional(self):
        self.assertTrue(
            AccountDraft.unidentified(distinguisher="sha256:aaa")
            .identity()
            .is_provisional
        )


class DraftValidationTests(unittest.TestCase):
    def test_an_unknown_currency_is_refused(self):
        with self.assertRaises(AccountCurrencyError):
            AccountDraft.observed(
                institution_name="Barclays",
                identifier_as_printed="20445566",
                currency="ZZZ",
            )

    def test_an_overlong_field_is_refused_rather_than_truncated(self):
        """SQLite ignores column widths and Postgres does not.

        Without this the value passes every test and fails in production
        against real evidence -- or worse, is silently shortened into a
        different identifier.
        """
        with self.assertRaises(AccountFieldError) as caught:
            AccountDraft.observed(
                institution_name="Barclays", identifier_as_printed="1" * 129
            )
        self.assertIn("128", str(caught.exception))

    def test_a_crafted_institution_name_cannot_move_the_field_boundaries(self):
        """A separator in a folded field is neutralised, not carried into the key.

        The attack this guards against is a name chosen so that its separator
        shifts the field boundaries and makes one account's key equal another's.
        It fails at the folding step rather than at the key-building step:
        ``\\x1f`` is a control character, Python's ``\\s`` matches it, and
        ``_fold`` collapses it to a space along with any other whitespace.

        Asserted here as the property that matters -- the crafted name does not
        collide with the account it was crafted to impersonate -- rather than as
        a particular exception, because which layer stops it is an
        implementation detail and the non-collision is not.
        """
        from services.financial.accounts import _SEP, _fold

        crafted = AccountDraft.observed(
            institution_name="Barclays\x1f9999", identifier_as_printed="20445566"
        )
        honest = AccountDraft.observed(
            institution_name="Barclays", identifier_as_printed="9999 20445566"
        )

        self.assertNotIn(_SEP, _fold("Barclays\x1f9999"))
        self.assertNotEqual(crafted.identity().key, honest.identity().key)
        self.assertEqual(crafted.identity().key.count(_SEP), 2)

    def test_the_field_separator_may_not_appear_in_a_component(self):
        """The key builder's own guard, reached by a component that skips folding.

        ``distinguisher`` is passed through to the key as given -- it is a
        content hash, not a value read off a page, so there is nothing to fold
        -- which makes it the path where the guard has to hold.
        """
        draft = AccountDraft.unidentified(distinguisher="sha256:aaa\x1fbbb")
        with self.assertRaises(AccountIdentityError) as caught:
            draft.identity()
        self.assertIn("separator", str(caught.exception))

    def test_a_non_string_identifier_is_a_caller_error(self):
        with self.assertRaises(PlaceholderIdentifierError):
            AccountDraft.observed(identifier_as_printed=20445566)


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------


class AccountPersistenceTestCase(unittest.TestCase):
    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-accounts-")
        self.engine = create_engine(
            f"sqlite+pysqlite:///{Path(self._directory) / 'ledger.db'}",
            future=True,
        )

        @event.listens_for(self.engine, "connect")
        def _configure(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA synchronous=OFF")
            cursor.close()

        Base.metadata.create_all(self.engine, tables=TABLES)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False
        )
        self.db = self.SessionLocal()

        self.user = User(
            id=uuid.uuid4(),
            email="investigator@example.test",
            name="Investigator",
            password_hash="not-used",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.case = Case(
            id=uuid.uuid4(),
            title="Account Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.other_case = Case(
            id=uuid.uuid4(),
            title="A Different Matter",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.db.add_all([self.user, self.case, self.other_case])
        self.db.commit()

        self.run = open_ingestion_run(
            case_id=self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def second_run(self, case_id=None):
        # Committed first, for two reasons that happen to want the same call.
        # SQLAlchemy expires objects on commit, so a test that reads an
        # attribute afterwards issues a SELECT that leaves a read transaction
        # open on this connection; the run service writes from an independent
        # session, and against file-backed SQLite that stale read blocks it
        # ('database is locked').  And a caller with writes still pending has
        # to keep them: rolling back here would discard the very account the
        # test is about to look for under a second run.  Production reaches a
        # second run the same way -- the first run's work is already committed.
        self.db.commit()
        return open_ingestion_run(
            case_id=case_id or self.case.id,
            actor=self.user,
            session_factory=self.SessionLocal,
        )

    def barclays(self, **overrides):
        overrides.setdefault("institution_name", "Barclays")
        overrides.setdefault("identifier_as_printed", "20-44-55 66")
        return AccountDraft.observed(**overrides)


class RecordAccountTests(AccountPersistenceTestCase):
    def test_writes_the_account_with_its_case_and_first_run(self):
        account = record_account(self.db, self.run, self.barclays())
        self.db.commit()

        self.assertEqual(account.case_id, self.case.id)
        self.assertEqual(account.first_seen_run_id, self.run.run_id)
        self.assertEqual(account.identifier_as_printed, "20-44-55 66")
        self.assertEqual(account.identifier_normalised, "20445566")

    def test_the_identity_tier_is_recorded_on_the_row(self):
        """A reviewer looking at a weak match has to be able to see it is weak."""
        account = record_account(self.db, self.run, self.barclays())
        self.db.commit()

        self.assertEqual(account.metadata_["identity_tier"], TIER_INSTITUTION_ACCOUNT)
        self.assertFalse(account.metadata_["identity_provisional"])
        self.assertEqual(read_identity_tier(account), TIER_INSTITUTION_ACCOUNT)

    def test_a_masked_account_is_marked_provisional_on_the_row(self):
        account = record_account(
            self.db,
            self.run,
            AccountDraft.observed(
                institution_name="Chase", identifier_as_printed="****7890"
            ),
        )
        self.db.commit()

        self.assertTrue(account.metadata_["identity_provisional"])

    def test_check_digit_verdicts_are_recorded_including_failures(self):
        account = record_account(
            self.db,
            self.run,
            AccountDraft.observed(
                institution_name="NatWest",
                iban="GB82WEST12345698765433",
                identifier_as_printed="98765433",
            ),
        )
        self.db.commit()

        self.assertEqual(account.metadata_["check_digits"]["iban"], "failed")
        self.assertEqual(account.metadata_["identity_tier"], TIER_INSTITUTION_ACCOUNT)

    def test_a_second_document_reaches_the_same_account(self):
        """The reason this is get-or-create and not insert."""
        first = record_account(self.db, self.run, self.barclays())
        self.db.commit()
        second = record_account(
            self.db,
            self.run,
            self.barclays(identifier_as_printed="20445566", holder_name="MR J SMITH"),
        )
        self.db.commit()

        self.assertEqual(first.id, second.id)
        self.assertEqual(self.db.query(FinancialAccount).count(), 1)

    def test_a_later_run_does_not_rewrite_first_seen(self):
        """Otherwise provenance names the most recent ingestion, not the first."""
        first = record_account(self.db, self.run, self.barclays())
        self.db.commit()
        later = self.second_run()
        record_account(self.db, later, self.barclays())
        self.db.commit()

        self.assertEqual(first.first_seen_run_id, self.run.run_id)

    def test_a_later_document_fills_fields_the_first_left_empty(self):
        account = record_account(self.db, self.run, self.barclays())
        self.db.commit()
        self.assertIsNone(account.holder_name)

        later = self.second_run()
        record_account(self.db, later, self.barclays(holder_name="MR J SMITH"))
        self.db.commit()

        self.assertEqual(account.holder_name, "MR J SMITH")
        self.assertIn(
            "holder_name", account.metadata_["enriched_by_runs"][str(later.run_id)]
        )

    def test_a_contradiction_is_recorded_and_not_applied(self):
        """Overwriting would make the row describe the newest document.

        Raising would stop an ingestion over a holder name printed two ways.
        Recording is the only option that keeps both readings.
        """
        account = record_account(
            self.db, self.run, self.barclays(holder_name="MR J SMITH")
        )
        self.db.commit()

        later = self.second_run()
        record_account(self.db, later, self.barclays(holder_name="JOHN SMITH"))
        self.db.commit()

        self.assertEqual(account.holder_name, "MR J SMITH")
        conflicts = account.metadata_["identity_conflicts"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["field"], "holder_name")
        self.assertEqual(conflicts[0]["stored"], "MR J SMITH")
        self.assertEqual(conflicts[0]["offered"], "JOHN SMITH")

    def test_a_currency_contradiction_is_recorded_not_adopted(self):
        """An account seen in two currencies is a finding, not a preference."""
        account = record_account(self.db, self.run, self.barclays(currency=GBP))
        self.db.commit()

        later = self.second_run()
        record_account(self.db, later, self.barclays(currency=USD))
        self.db.commit()

        self.assertEqual(account.currency, GBP)
        fields = [c["field"] for c in account.metadata_["identity_conflicts"]]
        self.assertIn("currency", fields)

    def test_different_accounts_stay_different(self):
        record_account(self.db, self.run, self.barclays())
        record_account(
            self.db,
            self.run,
            AccountDraft.observed(
                institution_name="HSBC", identifier_as_printed="40-11-22 33"
            ),
        )
        self.db.commit()

        self.assertEqual(self.db.query(FinancialAccount).count(), 2)

    def test_the_same_account_in_two_cases_is_two_rows(self):
        """Case isolation is not negotiable, whatever the identity key says."""
        record_account(self.db, self.run, self.barclays())
        other_run = self.second_run(case_id=self.other_case.id)
        record_account(self.db, other_run, self.barclays())
        self.db.commit()

        rows = self.db.query(FinancialAccount).all()
        self.assertEqual(len(rows), 2)
        self.assertEqual({row.case_id for row in rows}, {self.case.id, self.other_case.id})
        self.assertEqual(len({row.identity_key for row in rows}), 1)

    def test_placeholder_documents_do_not_collapse_into_one_account(self):
        """The corpus regression, written out.

        Thirty-six documents printing 'see statement' where an account number
        belongs must produce thirty-six accounts, not one.  Sharing a key would
        also make them one duplicate group, because a period's signature is
        built from its account's identity key.
        """
        for index in range(36):
            record_account(
                self.db,
                self.run,
                AccountDraft.unidentified(
                    distinguisher=f"sha256:{index:064d}",
                    institution_name="see statement",
                    identifier_as_printed="see statement",
                ),
            )
        self.db.commit()

        rows = self.db.query(FinancialAccount).all()
        self.assertEqual(len(rows), 36)
        self.assertEqual(len({row.identity_key for row in rows}), 36)
        self.assertTrue(all(row.metadata_["identity_provisional"] for row in rows))

    def test_the_placeholder_is_stored_on_the_row_as_printed(self):
        account = record_account(
            self.db,
            self.run,
            AccountDraft.unidentified(
                distinguisher="sha256:aaa", identifier_as_printed="see statement"
            ),
        )
        self.db.commit()

        self.assertEqual(account.identifier_as_printed, "see statement")
        self.assertIsNone(account.identifier_normalised)
        self.assertEqual(account.metadata_["identity_distinguisher"], "sha256:aaa")

    def test_a_draft_of_the_wrong_type_is_refused(self):
        with self.assertRaises(AccountError):
            record_account(self.db, self.run, {"institution_name": "Barclays"})

    def test_an_account_cannot_be_stamped_with_a_run(self):
        """Documents the schema this writer works around.

        ``FinancialAccount`` carries ``first_seen_run_id`` and not
        ``ingestion_run_id``, because an account outlives the run that first saw
        it.  ``stamp`` refuses it, which is why ``record_account`` sets the case
        and the run itself.
        """
        account = record_account(self.db, self.run, self.barclays())
        self.db.commit()

        with self.assertRaises(RunScopeError) as caught:
            self.run.stamp(account)
        self.assertIn("ingestion_run_id", str(caught.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
