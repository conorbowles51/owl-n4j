"""Tests for the financial ledger schema.

These assert the guarantees the schema is supposed to give, not that rows
insert.  A schema test that only inserts a valid row proves nothing: the value
of a constraint is what it *refuses*, so most of what follows is an attempt to
write something wrong and a check that the database says no.

Two of the tests are structural rather than behavioural, and are the ones most
likely to catch a future regression: one walks every check constraint on the
six tables and refuses to let a vocabulary drift from its Python enum, and one
refuses to let a float column appear anywhere in the ledger.

SQLite is used in memory, as everywhere else in this suite.  It enforces check
constraints natively and enforces foreign keys once ``PRAGMA foreign_keys`` is
on, which ``setUp`` turns on, so cascade and reference behaviour is genuinely
exercised here rather than merely assumed to match Postgres.
"""

from __future__ import annotations

import re
import unittest
from datetime import date, timezone
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Float, Numeric, create_engine, delete, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.case import Case
from postgres.models.enums import (
    AdjudicationSubject,
    BalanceSource,
    DateSource,
    DocumentStatus,
    ExtractionLayer,
    GlobalRole,
    IngestionRunStatus,
    LedgerStatus,
    PeriodBoundsSource,
    ProofClass,
    ReconciliationStatus,
    TransactionDirection,
)
from postgres.models.evidence import EvidenceFile, EvidenceFolder
from postgres.models.financial import (
    FinancialAccount,
    FinancialAdjudication,
    FinancialIngestionRun,
    FinancialSourceDocument,
    FinancialStatementPeriod,
    FinancialTransaction,
)
from postgres.models.user import User


FINANCIAL_MODELS = [
    FinancialIngestionRun,
    FinancialSourceDocument,
    FinancialAccount,
    FinancialStatementPeriod,
    FinancialTransaction,
    FinancialAdjudication,
]

# Creation order.  The financial tables depend on cases, users and evidence
# files, and on each other in the order listed above.  ``evidence_folders`` is
# present because ``evidence_files`` references it and SQLite, once foreign key
# enforcement is on, requires the parent table to exist even where every child
# value is null.
TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
] + [model.__table__ for model in FINANCIAL_MODELS]


# Every check constraint that pins a column to a fixed vocabulary, mapped to
# the enum that owns that vocabulary.  A new IN-list constraint that is not
# registered here fails test_every_vocabulary_constraint_is_registered, which
# is deliberate: the point is that the mapping cannot be quietly skipped.
VOCABULARY_CONSTRAINTS = {
    "ck_financial_ingestion_runs_status": IngestionRunStatus,
    "ck_financial_source_documents_proof_class": ProofClass,
    "ck_financial_source_documents_status": DocumentStatus,
    "ck_financial_statement_periods_reconciliation_status": ReconciliationStatus,
    "ck_financial_statement_periods_opening_source": BalanceSource,
    "ck_financial_statement_periods_closing_source": BalanceSource,
    "ck_financial_statement_periods_start_source": PeriodBoundsSource,
    "ck_financial_statement_periods_end_source": PeriodBoundsSource,
    "ck_financial_transactions_direction": TransactionDirection,
    "ck_financial_transactions_proof_class": ProofClass,
    "ck_financial_transactions_ledger_status": LedgerStatus,
    "ck_financial_transactions_ordering_date_source": DateSource,
    "ck_financial_adjudications_subject_type": AdjudicationSubject,
}

_IN_LIST = re.compile(r"\bIN\s*\(([^)]*)\)", re.IGNORECASE)
_QUOTED = re.compile(r"'([^']*)'")


def _bound_source(value) -> str:
    """The bounds source a fixture date implies, so the two cannot disagree."""
    if value is None:
        return PeriodBoundsSource.absent.value
    return PeriodBoundsSource.printed.value


def _in_list_values(sqltext: str) -> set[str] | None:
    """Pull the quoted members out of an ``IN (...)`` clause, if there is one."""
    match = _IN_LIST.search(sqltext)
    if match is None:
        return None
    return set(_QUOTED.findall(match.group(1)))


class FinancialLedgerStructureTests(unittest.TestCase):
    """Structural invariants, checked against the metadata rather than a database."""

    def test_no_float_or_numeric_column_anywhere(self):
        """The ledger's central rule, enforced mechanically rather than by docstring.

        A float amount makes the balance identity approximate, and an
        approximate identity detects nothing.  Numeric is excluded too: it is
        exact, but it reopens the question of scale per currency, which minor
        units close.
        """
        offenders = [
            f"{model.__tablename__}.{column.name} ({type(column.type).__name__})"
            for model in FINANCIAL_MODELS
            for column in model.__table__.columns
            if isinstance(column.type, (Float, Numeric))
        ]
        self.assertEqual(
            offenders,
            [],
            "Monetary values must be integer minor units; found approximate "
            f"or scale-bearing columns: {offenders}",
        )

    def test_every_minor_column_is_a_big_integer(self):
        """A 32-bit amount column overflows at about 21 million in major units.

        That is an entirely reachable sum in the kind of case this feature
        exists for, so the width is part of the correctness claim.
        """
        for model in FINANCIAL_MODELS:
            for column in model.__table__.columns:
                if column.name.endswith("_minor"):
                    with self.subTest(column=f"{model.__tablename__}.{column.name}"):
                        self.assertEqual(
                            column.type.__class__.__name__,
                            "BigInteger",
                            f"{column.name} holds money and must be BigInteger",
                        )

    def test_vocabulary_constraints_match_their_enums(self):
        """The check constraint and the Python enum must agree, member for member.

        These are maintained in two files and will drift the first time someone
        adds an enum member without touching the constraint.  When they drift,
        the database rejects a value the application believes is legal, which
        surfaces as a failed ingestion run rather than as anything obviously
        about enums.
        """
        seen = set()
        for model in FINANCIAL_MODELS:
            for constraint in model.__table__.constraints:
                if not isinstance(constraint, CheckConstraint):
                    continue
                values = _in_list_values(str(constraint.sqltext))
                if values is None:
                    continue
                expected_enum = VOCABULARY_CONSTRAINTS.get(constraint.name)
                self.assertIsNotNone(
                    expected_enum,
                    f"Constraint {constraint.name} pins a vocabulary but is not "
                    "registered in VOCABULARY_CONSTRAINTS",
                )
                seen.add(constraint.name)
                self.assertEqual(
                    values,
                    {member.value for member in expected_enum},
                    f"{constraint.name} has drifted from {expected_enum.__name__}",
                )

        self.assertEqual(
            seen,
            set(VOCABULARY_CONSTRAINTS),
            "A registered constraint is no longer present on the schema",
        )

    def test_every_vocabulary_constraint_is_registered(self):
        """No IN-list constraint may exist without a registered enum owner."""
        unregistered = [
            constraint.name
            for model in FINANCIAL_MODELS
            for constraint in model.__table__.constraints
            if isinstance(constraint, CheckConstraint)
            and _in_list_values(str(constraint.sqltext)) is not None
            and constraint.name not in VOCABULARY_CONSTRAINTS
        ]
        self.assertEqual(unregistered, [])

    def test_extraction_layer_bounds_match_the_enum(self):
        """The BETWEEN bounds in SQL and the enum members must describe one range."""
        layers = [member.value for member in ExtractionLayer]
        self.assertEqual(min(layers), 0)
        self.assertEqual(max(layers), 3)
        self.assertEqual(sorted(layers), list(range(4)))

        bounded = [
            str(constraint.sqltext)
            for model in FINANCIAL_MODELS
            for constraint in model.__table__.constraints
            if isinstance(constraint, CheckConstraint)
            and "extraction_layer" in str(constraint.sqltext)
        ]
        self.assertEqual(len(bounded), 2, "documents and transactions each bound it")
        for sqltext in bounded:
            self.assertIn("BETWEEN 0 AND 3", sqltext)

    def test_adjudications_carry_no_updated_at(self):
        """The table records decisions, so it must not invite editing them."""
        columns = set(FinancialAdjudication.__table__.columns.keys())
        self.assertIn("created_at", columns)
        self.assertNotIn("updated_at", columns)

    def test_adjudication_subject_has_no_foreign_key(self):
        """A decision must outlive the row it was about.

        A cascade here would delete the record of a decision at exactly the
        moment it mattered most, so the absence of a foreign key is a design
        choice and is asserted rather than left to be re-added by someone
        tidying up.
        """
        subject_id = FinancialAdjudication.__table__.columns["subject_id"]
        self.assertEqual(len(subject_id.foreign_keys), 0)

    def test_all_models_are_exported_from_the_package(self):
        import postgres.models as models_package

        for model in FINANCIAL_MODELS:
            with self.subTest(model=model.__name__):
                self.assertIn(model.__name__, models_package.__all__)
                self.assertIs(getattr(models_package, model.__name__), model)


class FinancialLedgerConstraintTests(unittest.TestCase):
    """Behavioural tests against a real, if small, database."""

    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

        @event.listens_for(self.engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        Base.metadata.create_all(self.engine, tables=TABLES)
        self.SessionLocal = sessionmaker(
            bind=self.engine, autoflush=False, autocommit=False
        )
        self.db = self.SessionLocal()

        self.user = User(
            id=uuid4(),
            email="investigator@example.test",
            name="Investigator",
            password_hash="not-used",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.case = Case(
            id=uuid4(),
            title="Ledger Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.evidence_file = EvidenceFile(
            id=uuid4(),
            case_id=self.case.id,
            original_filename="march-statement.pdf",
            stored_path="/evidence/march-statement.pdf",
            sha256="a" * 64,
        )
        self.db.add_all([self.user, self.case, self.evidence_file])
        self.db.commit()

        self.run = self.make_run()
        self.document = self.make_document()
        self.account = self.make_account()
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine, tables=list(reversed(TABLES)))
        self.engine.dispose()

    # ---- fixture builders -------------------------------------------------

    def make_run(self, **overrides):
        run = FinancialIngestionRun(
            id=overrides.pop("id", uuid4()),
            case_id=overrides.pop("case_id", self.case.id),
            status=overrides.pop("status", IngestionRunStatus.completed.value),
            code_version=overrides.pop("code_version", "financial@1.0.0"),
            ruleset_version=overrides.pop("ruleset_version", "rules@2026.08"),
            started_by_user_id=overrides.pop("started_by_user_id", self.user.id),
            started_by_email=overrides.pop("started_by_email", self.user.email),
            **overrides,
        )
        self.db.add(run)
        return run

    def make_document(self, **overrides):
        document = FinancialSourceDocument(
            id=overrides.pop("id", uuid4()),
            case_id=overrides.pop("case_id", self.case.id),
            evidence_file_id=overrides.pop("evidence_file_id", self.evidence_file.id),
            ingestion_run_id=overrides.pop("ingestion_run_id", self.run.id),
            sha256_at_ingestion=overrides.pop("sha256_at_ingestion", "a" * 64),
            document_type=overrides.pop("document_type", "bank_statement"),
            proof_class=overrides.pop("proof_class", ProofClass.p2.value),
            extraction_layer=overrides.pop(
                "extraction_layer", ExtractionLayer.structural.value
            ),
            parser_name=overrides.pop("parser_name", "statement_pdf"),
            parser_version=overrides.pop("parser_version", "1.4.0"),
            **overrides,
        )
        self.db.add(document)
        return document

    def make_account(self, **overrides):
        account = FinancialAccount(
            id=overrides.pop("id", uuid4()),
            case_id=overrides.pop("case_id", self.case.id),
            identity_key=overrides.pop("identity_key", "gb-barclays-20445566"),
            institution_name=overrides.pop("institution_name", "Barclays"),
            identifier_as_printed=overrides.pop("identifier_as_printed", "20-44-55 66"),
            identifier_normalised=overrides.pop("identifier_normalised", "20445566"),
            currency=overrides.pop("currency", "GBP"),
            **overrides,
        )
        self.db.add(account)
        return account

    def make_period(self, **overrides):
        period_start = overrides.pop("period_start", date(2026, 3, 1))
        period_end = overrides.pop("period_end", date(2026, 3, 31))
        # The source columns are derived from the dates rather than defaulted,
        # because the coherence constraints require the two to agree: a bound
        # is 'absent' exactly when the date is null.  Hard-coding 'printed'
        # here would break every test that asks for an open-ended period, and
        # leaving the column to its 'absent' default breaks every test that
        # supplies dates, which is what happened.
        period = FinancialStatementPeriod(
            id=overrides.pop("id", uuid4()),
            case_id=overrides.pop("case_id", self.case.id),
            source_document_id=overrides.pop("source_document_id", self.document.id),
            account_id=overrides.pop("account_id", self.account.id),
            ingestion_run_id=overrides.pop("ingestion_run_id", self.run.id),
            period_start=period_start,
            period_end=period_end,
            period_start_source=overrides.pop(
                "period_start_source", _bound_source(period_start)
            ),
            period_end_source=overrides.pop(
                "period_end_source", _bound_source(period_end)
            ),
            currency=overrides.pop("currency", "GBP"),
            **overrides,
        )
        self.db.add(period)
        return period

    def make_transaction(self, **overrides):
        transaction = FinancialTransaction(
            id=overrides.pop("id", uuid4()),
            case_id=overrides.pop("case_id", self.case.id),
            account_id=overrides.pop("account_id", self.account.id),
            source_document_id=overrides.pop("source_document_id", self.document.id),
            ingestion_run_id=overrides.pop("ingestion_run_id", self.run.id),
            ref_id=overrides.pop("ref_id", f"TXN-{uuid4().hex[:8]}"),
            row_index=overrides.pop("row_index", 0),
            amount_minor=overrides.pop("amount_minor", 125_00),
            currency=overrides.pop("currency", "GBP"),
            direction=overrides.pop("direction", TransactionDirection.debit.value),
            transaction_date=overrides.pop("transaction_date", date(2026, 3, 4)),
            ordering_date=overrides.pop("ordering_date", date(2026, 3, 4)),
            ordering_date_source=overrides.pop(
                "ordering_date_source", DateSource.transaction.value
            ),
            proof_class=overrides.pop("proof_class", ProofClass.p2.value),
            extraction_layer=overrides.pop(
                "extraction_layer", ExtractionLayer.structural.value
            ),
            content_hash=overrides.pop("content_hash", uuid4().hex),
            **overrides,
        )
        self.db.add(transaction)
        return transaction

    def make_adjudication(self, **overrides):
        adjudication = FinancialAdjudication(
            id=overrides.pop("id", uuid4()),
            case_id=overrides.pop("case_id", self.case.id),
            subject_type=overrides.pop(
                "subject_type", AdjudicationSubject.transaction.value
            ),
            subject_id=overrides.pop("subject_id", uuid4()),
            decision=overrides.pop("decision", "admit"),
            reason=overrides.pop("reason", "Verified against the printed page."),
            actor_user_id=overrides.pop("actor_user_id", self.user.id),
            actor_name=overrides.pop("actor_name", self.user.name),
            actor_email=overrides.pop("actor_email", self.user.email),
            **overrides,
        )
        self.db.add(adjudication)
        return adjudication

    def assertRejected(self, build):
        """Assert that building and committing a row is refused by the database."""
        build()
        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()

    # ---- the happy path ---------------------------------------------------

    def test_a_full_chain_persists(self):
        period = self.make_period(
            opening_balance_minor=100_000_00,
            closing_balance_minor=99_875_00,
            opening_balance_source=BalanceSource.printed.value,
            closing_balance_source=BalanceSource.printed.value,
            reconciliation_status=ReconciliationStatus.balanced.value,
            computed_closing_minor=99_875_00,
            delta_minor=0,
            credit_total_minor=0,
            debit_total_minor=125_00,
            transaction_count=1,
        )
        self.db.flush()
        self.make_transaction(statement_period_id=period.id)
        self.db.commit()

        stored = self.db.execute(select(FinancialTransaction)).scalar_one()
        self.assertEqual(stored.amount_minor, 125_00)
        self.assertEqual(stored.ledger_status, LedgerStatus.admitted.value)
        self.assertEqual(stored.provenance, {})

        reloaded = self.db.execute(select(FinancialStatementPeriod)).scalar_one()
        self.assertEqual(
            reloaded.opening_balance_minor
            + reloaded.credit_total_minor
            - reloaded.debit_total_minor,
            reloaded.closing_balance_minor,
        )

    def test_amounts_survive_beyond_thirty_two_bits(self):
        """Nine hundred million in major units, stored and read back exactly."""
        big = 900_000_000_00
        self.make_transaction(amount_minor=big)
        self.db.commit()
        stored = self.db.execute(select(FinancialTransaction)).scalar_one()
        self.assertEqual(stored.amount_minor, big)

    # ---- what the ledger refuses -----------------------------------------

    def test_negative_amount_is_rejected(self):
        """Sign lives in ``direction``; a negative magnitude is a category error."""
        self.assertRejected(lambda: self.make_transaction(amount_minor=-1))

    def test_unknown_direction_is_rejected(self):
        self.assertRejected(lambda: self.make_transaction(direction="DEBIT"))
        self.assertRejected(lambda: self.make_transaction(direction="out"))

    def test_p4_never_reaches_the_ledger(self):
        """The processor boundary, enforced by the database rather than by intent.

        A p4 assertion is something someone said about money.  It may be
        corroborated, displayed and correlated, but it may never be counted,
        and the only way to guarantee that is to make it unstorable here.
        """
        self.assertRejected(
            lambda: self.make_transaction(proof_class=ProofClass.p4.value)
        )

    def test_p4_is_allowed_on_a_source_document(self):
        """The asymmetry is deliberate and is the point of the boundary.

        A chat log making a financial claim is a legitimate p4 source document.
        What it may not do is produce ledger rows.
        """
        second_file = EvidenceFile(
            id=uuid4(),
            case_id=self.case.id,
            original_filename="whatsapp-export.txt",
            stored_path="/evidence/whatsapp-export.txt",
            sha256="b" * 64,
        )
        self.db.add(second_file)
        self.db.flush()
        self.make_document(
            evidence_file_id=second_file.id,
            document_type="chat_export",
            proof_class=ProofClass.p4.value,
            extraction_layer=ExtractionLayer.grounded_model.value,
        )
        self.db.commit()
        self.assertEqual(
            len(self.db.execute(select(FinancialSourceDocument)).scalars().all()), 2
        )

    def test_a_transaction_must_carry_at_least_one_date(self):
        """All four date columns are nullable; all four being null is not a row."""
        self.assertRejected(
            lambda: self.make_transaction(
                transaction_date=None,
                posted_date=None,
                value_date=None,
                effective_date=None,
            )
        )

    def test_a_transaction_with_only_a_posted_date_is_accepted(self):
        self.make_transaction(
            transaction_date=None,
            posted_date=date(2026, 3, 6),
            ordering_date=date(2026, 3, 6),
            ordering_date_source=DateSource.posted.value,
        )
        self.db.commit()
        stored = self.db.execute(select(FinancialTransaction)).scalar_one()
        self.assertIsNone(stored.transaction_date)
        self.assertEqual(stored.ordering_date_source, DateSource.posted.value)

    def test_extraction_layer_is_bounded(self):
        self.assertRejected(lambda: self.make_transaction(extraction_layer=4))
        self.assertRejected(lambda: self.make_transaction(extraction_layer=-1))

    def test_unknown_ledger_status_is_rejected(self):
        self.assertRejected(lambda: self.make_transaction(ledger_status="maybe"))

    def test_unknown_reconciliation_status_is_rejected(self):
        self.assertRejected(
            lambda: self.make_period(reconciliation_status="probably_fine")
        )

    def test_a_period_may_not_end_before_it_starts(self):
        self.assertRejected(
            lambda: self.make_period(
                period_start=date(2026, 3, 31), period_end=date(2026, 3, 1)
            )
        )

    def test_an_open_ended_period_is_allowed(self):
        """A statement with no printed end date is still a statement."""
        self.make_period(period_end=None)
        self.db.commit()
        stored = self.db.execute(select(FinancialStatementPeriod)).scalar_one()
        self.assertIsNone(stored.period_end)

    def test_an_adjudication_requires_a_stated_reason(self):
        """An adjudication without a reason is not an adjudication.

        Whitespace is checked as well as emptiness, because an unexplained edit
        with a space in the reason field is still an unexplained edit.
        """
        self.assertRejected(lambda: self.make_adjudication(reason=""))
        self.assertRejected(lambda: self.make_adjudication(reason="   "))
        self.assertRejected(lambda: self.make_adjudication(reason="\t\n "))

    def test_unknown_adjudication_subject_is_rejected(self):
        self.assertRejected(lambda: self.make_adjudication(subject_type="hunch"))

    # ---- idempotency and identity ----------------------------------------

    def test_re_reading_a_document_cannot_duplicate_a_row(self):
        """``(source_document_id, content_hash)`` is what makes re-ingestion safe.

        Without it, running the pipeline twice over the same statement doubles
        every total, which is the failure mode that is hardest to notice
        because nothing errors.
        """
        shared_hash = "c" * 32
        self.make_transaction(content_hash=shared_hash)
        self.db.commit()
        self.assertRejected(
            lambda: self.make_transaction(content_hash=shared_hash, row_index=1)
        )

    def test_the_same_row_in_a_different_document_is_a_different_fact(self):
        """Two statements can legitimately both report one movement."""
        shared_hash = "c" * 32
        self.make_transaction(content_hash=shared_hash)
        second_file = EvidenceFile(
            id=uuid4(),
            case_id=self.case.id,
            original_filename="april-statement.pdf",
            stored_path="/evidence/april-statement.pdf",
            sha256="d" * 64,
        )
        self.db.add(second_file)
        self.db.flush()
        second_document = self.make_document(evidence_file_id=second_file.id)
        self.db.flush()
        self.make_transaction(
            source_document_id=second_document.id, content_hash=shared_hash
        )
        self.db.commit()
        self.assertEqual(
            len(self.db.execute(select(FinancialTransaction)).scalars().all()), 2
        )

    def test_ref_id_is_unique_within_a_case(self):
        """Exhibit references are cited in reports; two rows cannot share one."""
        self.make_transaction(ref_id="TXN-0001")
        self.db.commit()
        self.assertRejected(lambda: self.make_transaction(ref_id="TXN-0001"))

    def test_the_same_ref_id_may_exist_in_another_case(self):
        """Numbering restarts per case, so uniqueness is scoped, not global."""
        self.make_transaction(ref_id="TXN-0001")
        self.db.commit()

        other_case = Case(
            id=uuid4(),
            title="Unrelated Matter",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        other_file = EvidenceFile(
            id=uuid4(),
            case_id=other_case.id,
            original_filename="other.pdf",
            stored_path="/evidence/other.pdf",
            sha256="e" * 64,
        )
        self.db.add_all([other_case, other_file])
        self.db.flush()
        other_run = self.make_run(case_id=other_case.id)
        self.db.flush()
        other_document = self.make_document(
            case_id=other_case.id,
            evidence_file_id=other_file.id,
            ingestion_run_id=other_run.id,
        )
        other_account = self.make_account(
            case_id=other_case.id, identity_key="us-chase-99887766"
        )
        self.db.flush()
        self.make_transaction(
            case_id=other_case.id,
            account_id=other_account.id,
            source_document_id=other_document.id,
            ingestion_run_id=other_run.id,
            ref_id="TXN-0001",
        )
        self.db.commit()
        self.assertEqual(
            len(self.db.execute(select(FinancialTransaction)).scalars().all()), 2
        )

    def test_account_identity_is_unique_within_a_case(self):
        self.assertRejected(
            lambda: self.make_account(identity_key="gb-barclays-20445566")
        )

    def test_a_document_is_read_once_per_run(self):
        self.assertRejected(lambda: self.make_document())

    def test_a_document_may_be_re_read_by_a_later_run(self):
        """Reprocessing under a new parser version is a new run, not a duplicate."""
        later_run = self.make_run(code_version="financial@1.1.0")
        self.db.flush()
        self.make_document(ingestion_run_id=later_run.id, parser_version="1.5.0")
        self.db.commit()
        self.assertEqual(
            len(self.db.execute(select(FinancialSourceDocument)).scalars().all()), 2
        )

    # ---- supersession and audit ------------------------------------------

    def test_a_wrong_row_is_superseded_rather_than_edited(self):
        """The correction keeps both rows and the link between them."""
        wrong = self.make_transaction(ref_id="TXN-0001", amount_minor=125_00)
        self.db.commit()

        correction = self.make_transaction(ref_id="TXN-0002", amount_minor=152_00)
        self.db.flush()
        wrong.ledger_status = LedgerStatus.superseded.value
        wrong.superseded_by_id = correction.id
        self.make_adjudication(
            subject_type=AdjudicationSubject.transaction.value,
            subject_id=wrong.id,
            decision="supersede",
            reason="Transposed digits; the page reads 152.00.",
            before={"amount_minor": 125_00},
            after={"amount_minor": 152_00},
        )
        self.db.commit()

        self.db.refresh(wrong)
        self.assertEqual(wrong.ledger_status, LedgerStatus.superseded.value)
        self.assertEqual(wrong.superseded_by_id, correction.id)
        self.assertEqual(wrong.superseded_by.amount_minor, 152_00)

        admitted = (
            self.db.execute(
                select(FinancialTransaction).where(
                    FinancialTransaction.ledger_status
                    == LedgerStatus.admitted.value
                )
            )
            .scalars()
            .all()
        )
        self.assertEqual(len(admitted), 1)
        self.assertEqual(admitted[0].amount_minor, 152_00)

    def test_an_adjudication_outlives_its_subject(self):
        """Deleting the row a decision was about must not delete the decision.

        This is the behavioural half of the missing foreign key on
        ``subject_id``: the audit trail has to survive the thing it audits.
        """
        transaction = self.make_transaction()
        self.db.commit()
        subject_id = transaction.id

        self.make_adjudication(
            subject_id=subject_id,
            decision="quarantine",
            reason="Amount unreadable in the scan.",
        )
        self.db.commit()

        self.db.execute(
            delete(FinancialTransaction).where(FinancialTransaction.id == subject_id)
        )
        self.db.commit()

        self.assertEqual(
            len(self.db.execute(select(FinancialTransaction)).scalars().all()), 0
        )
        surviving = self.db.execute(select(FinancialAdjudication)).scalar_one()
        self.assertEqual(surviving.subject_id, subject_id)
        self.assertEqual(surviving.reason, "Amount unreadable in the scan.")

    def test_the_actor_survives_deletion_of_the_user(self):
        """Who decided what must not become unknowable when an account is removed.

        The foreign key on ``actor_user_id`` sets null so the row is not
        destroyed, and the copied name and email are what carry the answer
        afterwards.  Both halves are asserted: the link goes, the identity
        stays.
        """
        analyst = User(
            id=uuid4(),
            email="analyst@example.test",
            name="Second Analyst",
            password_hash="not-used",
            global_role=GlobalRole.user,
            is_active=True,
        )
        self.db.add(analyst)
        self.db.flush()
        self.make_adjudication(
            actor_user_id=analyst.id,
            actor_name=analyst.name,
            actor_email=analyst.email,
        )
        self.db.commit()

        # The identifier is taken before the identity map is cleared: after
        # ``expunge_all`` the instance is detached and reading a column off it
        # would raise rather than test anything.
        analyst_id = analyst.id
        self.db.expunge_all()
        self.db.execute(delete(User).where(User.id == analyst_id))
        self.db.commit()

        adjudication = self.db.execute(select(FinancialAdjudication)).scalar_one()
        self.assertIsNone(adjudication.actor_user_id)
        self.assertEqual(adjudication.actor_email, "analyst@example.test")
        self.assertEqual(adjudication.actor_name, "Second Analyst")

    def test_run_provenance_is_recorded_not_inferred(self):
        run = self.db.execute(
            select(FinancialIngestionRun).where(
                FinancialIngestionRun.id == self.run.id
            )
        ).scalar_one()
        self.assertEqual(run.code_version, "financial@1.0.0")
        self.assertEqual(run.ruleset_version, "rules@2026.08")
        self.assertEqual(run.started_by_email, self.user.email)
        self.assertIsNotNone(run.started_at)

    def test_unknown_run_status_is_rejected(self):
        self.assertRejected(lambda: self.make_run(status="finished"))

    # ---- deletion semantics ----------------------------------------------

    def test_deleting_a_case_removes_its_ledger(self):
        """A case deletion that half succeeded would leave orphaned money."""
        period = self.make_period()
        self.db.flush()
        self.make_transaction(statement_period_id=period.id)
        self.make_adjudication()
        self.db.commit()

        case_id = self.case.id
        self.db.expunge_all()
        self.db.execute(delete(Case).where(Case.id == case_id))
        self.db.commit()

        for model in FINANCIAL_MODELS:
            with self.subTest(table=model.__tablename__):
                remaining = self.db.execute(select(model)).scalars().all()
                self.assertEqual(
                    len(remaining),
                    0,
                    f"{model.__tablename__} still holds rows for a deleted case",
                )

    def test_a_transaction_cannot_reference_a_missing_account(self):
        """Foreign keys are on; a dangling reference is not storable."""
        self.assertRejected(lambda: self.make_transaction(account_id=uuid4()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
