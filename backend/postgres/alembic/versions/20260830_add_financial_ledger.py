"""add the financial ledger: runs, documents, accounts, periods, transactions, adjudications

Revision ID: 20260830_financial_ledger
Revises: 20260807_deepseek
Create Date: 2026-08-30

Creates the relational system of record for financial evidence.  Monetary
values are BigInteger counts of minor units beside an ISO 4217 code; there is
no float column anywhere in this migration, and there must never be one.

The choice of parent is deliberate and is explained at ``down_revision`` below.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260830_financial_ledger"
# Chained onto 20260807_deepseek rather than 20260725_speaker_merges.  Origin
# had already branched 20260803_loupes off speaker_merges, so hanging the
# ledger off the same parent would leave two alembic heads the moment this
# branch met origin, and `alembic upgrade head` refuses to run with two.  The
# ledger depends on nothing either of those revisions touches; this edge
# exists to keep the graph linear.
#
# Verified after rebasing onto origin: 50 revisions, one head, base to head
# walks as a single line.  No merge migration is wanted; adding one would
# invent a branch point where there is none.
down_revision: Union[str, None] = "20260807_deepseek"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PROOF_CLASSES = "('p0', 'p1', 'p2', 'p3', 'p4')"
LEDGER_STATUSES = "('admitted', 'quarantined', 'superseded', 'rejected')"
RUN_STATUSES = "('pending', 'running', 'completed', 'failed', 'aborted')"
RECONCILIATION_STATUSES = "('not_attempted', 'balanced', 'unbalanced', 'unavailable')"
DIRECTIONS = "('credit', 'debit')"
DATE_SOURCES = "('transaction', 'posted', 'value', 'effective')"
BALANCE_SOURCES = "('printed', 'carried_forward', 'absent')"
ADJUDICATION_SUBJECTS = (
    "('transaction', 'statement_period', 'source_document', 'account')"
)

# Nested replace() rather than trim(reason): in both Postgres and SQLite,
# single-argument trim strips spaces only, so a reason made of a tab and a
# newline would satisfy a naive blank check.  The literals hold real control
# characters — written as Python escapes for readability, but they must reach
# the SQL as the characters themselves, because Postgres runs with
# standard_conforming_strings on.  Kept identical to the model definition in
# postgres/models/financial.py.
REASON_NOT_BLANK = (
    "length(trim(replace(replace(replace("
    "reason, '\t', ' '), '\r', ' '), '\n', ' '))) > 0"
)

_JSONB = postgresql.JSONB(astext_type=sa.Text())
_EMPTY_OBJECT = sa.text("'{}'::jsonb")


def _timestamps():
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def upgrade() -> None:
    # -- runs ---------------------------------------------------------------
    op.create_table(
        "financial_ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="pending", nullable=False
        ),
        sa.Column("code_version", sa.String(length=64), nullable=True),
        sa.Column("ruleset_version", sa.String(length=64), nullable=True),
        sa.Column("config", _JSONB, server_default=_EMPTY_OBJECT, nullable=False),
        sa.Column("started_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("started_by_email", sa.String(length=255), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("documents_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "transactions_admitted", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "transactions_quarantined", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            f"status IN {RUN_STATUSES}", name="ck_financial_ingestion_runs_status"
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["started_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_financial_ingestion_runs_case",
        "financial_ingestion_runs",
        ["case_id", "started_at"],
        unique=False,
    )

    # -- source documents ---------------------------------------------------
    op.create_table(
        "financial_source_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sha256_at_ingestion", sa.String(length=64), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("proof_class", sa.String(length=2), nullable=False),
        sa.Column("extraction_layer", sa.Integer(), nullable=False),
        sa.Column("parser_name", sa.String(length=64), nullable=False),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.Column("institution_name", sa.String(length=255), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default="admitted", nullable=False
        ),
        sa.Column("quarantine_reason", sa.String(length=64), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", _JSONB, server_default=_EMPTY_OBJECT, nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            f"proof_class IN {PROOF_CLASSES}",
            name="ck_financial_source_documents_proof_class",
        ),
        sa.CheckConstraint(
            f"status IN {LEDGER_STATUSES}",
            name="ck_financial_source_documents_status",
        ),
        sa.CheckConstraint(
            "extraction_layer BETWEEN 0 AND 3",
            name="ck_financial_source_documents_extraction_layer",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["evidence_file_id"], ["evidence_files.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["financial_ingestion_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"],
            ["financial_source_documents.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ingestion_run_id",
            "evidence_file_id",
            name="uq_financial_source_documents_run_file",
        ),
    )
    op.create_index(
        "ix_financial_source_documents_case",
        "financial_source_documents",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_source_documents_evidence_file",
        "financial_source_documents",
        ["evidence_file_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_source_documents_case_status",
        "financial_source_documents",
        ["case_id", "status"],
        unique=False,
    )

    # -- accounts -----------------------------------------------------------
    op.create_table(
        "financial_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("identity_key", sa.String(length=512), nullable=False),
        sa.Column("institution_name", sa.String(length=255), nullable=True),
        sa.Column("identifier_as_printed", sa.String(length=128), nullable=True),
        sa.Column("identifier_normalised", sa.String(length=128), nullable=True),
        sa.Column("account_type", sa.String(length=32), nullable=True),
        sa.Column("holder_name", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("iban", sa.String(length=34), nullable=True),
        sa.Column("bic", sa.String(length=11), nullable=True),
        sa.Column("routing_number", sa.String(length=9), nullable=True),
        sa.Column("first_seen_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", _JSONB, server_default=_EMPTY_OBJECT, nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["first_seen_run_id"],
            ["financial_ingestion_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_id", "identity_key", name="uq_financial_accounts_case_identity"
        ),
    )
    op.create_index(
        "ix_financial_accounts_case", "financial_accounts", ["case_id"], unique=False
    )
    op.create_index(
        "ix_financial_accounts_normalised",
        "financial_accounts",
        ["case_id", "identifier_normalised"],
        unique=False,
    )

    # -- statement periods --------------------------------------------------
    op.create_table(
        "financial_statement_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("opening_balance_minor", sa.BigInteger(), nullable=True),
        sa.Column("closing_balance_minor", sa.BigInteger(), nullable=True),
        sa.Column(
            "opening_balance_source",
            sa.String(length=16),
            server_default="absent",
            nullable=False,
        ),
        sa.Column(
            "closing_balance_source",
            sa.String(length=16),
            server_default="absent",
            nullable=False,
        ),
        sa.Column(
            "reconciliation_status",
            sa.String(length=16),
            server_default="not_attempted",
            nullable=False,
        ),
        sa.Column("computed_closing_minor", sa.BigInteger(), nullable=True),
        sa.Column("delta_minor", sa.BigInteger(), nullable=True),
        sa.Column("credit_total_minor", sa.BigInteger(), nullable=True),
        sa.Column("debit_total_minor", sa.BigInteger(), nullable=True),
        sa.Column("transaction_count", sa.Integer(), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delta_explanation", _JSONB, nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            f"reconciliation_status IN {RECONCILIATION_STATUSES}",
            name="ck_financial_statement_periods_reconciliation_status",
        ),
        sa.CheckConstraint(
            f"opening_balance_source IN {BALANCE_SOURCES}",
            name="ck_financial_statement_periods_opening_source",
        ),
        sa.CheckConstraint(
            f"closing_balance_source IN {BALANCE_SOURCES}",
            name="ck_financial_statement_periods_closing_source",
        ),
        sa.CheckConstraint(
            "period_start IS NULL OR period_end IS NULL OR period_start <= period_end",
            name="ck_financial_statement_periods_ordered",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["financial_source_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["financial_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["financial_ingestion_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_document_id",
            "account_id",
            "period_start",
            "period_end",
            name="uq_financial_statement_periods_document_account_period",
        ),
    )
    op.create_index(
        "ix_financial_statement_periods_case",
        "financial_statement_periods",
        ["case_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_statement_periods_account_span",
        "financial_statement_periods",
        ["account_id", "period_start", "period_end"],
        unique=False,
    )
    op.create_index(
        "ix_financial_statement_periods_status",
        "financial_statement_periods",
        ["case_id", "reconciliation_status"],
        unique=False,
    )

    # -- transactions -------------------------------------------------------
    op.create_table(
        "financial_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement_period_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ref_id", sa.String(length=64), nullable=False),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("direction", sa.String(length=6), nullable=False),
        sa.Column("running_balance_minor", sa.BigInteger(), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("posted_date", sa.Date(), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("ordering_date", sa.Date(), nullable=False),
        sa.Column("ordering_date_source", sa.String(length=16), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("counterparty_raw", sa.String(length=512), nullable=True),
        sa.Column("transaction_type", sa.String(length=64), nullable=True),
        sa.Column("bank_reference", sa.String(length=128), nullable=True),
        sa.Column("proof_class", sa.String(length=2), nullable=False),
        sa.Column("extraction_layer", sa.Integer(), nullable=False),
        sa.Column(
            "ledger_status",
            sa.String(length=16),
            server_default="admitted",
            nullable=False,
        ),
        sa.Column("quarantine_reason", sa.String(length=64), nullable=True),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("provenance", _JSONB, server_default=_EMPTY_OBJECT, nullable=False),
        sa.Column("metadata", _JSONB, server_default=_EMPTY_OBJECT, nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "amount_minor >= 0", name="ck_financial_transactions_amount_non_negative"
        ),
        sa.CheckConstraint(
            f"direction IN {DIRECTIONS}", name="ck_financial_transactions_direction"
        ),
        sa.CheckConstraint(
            f"proof_class IN {PROOF_CLASSES}",
            name="ck_financial_transactions_proof_class",
        ),
        sa.CheckConstraint(
            "proof_class <> 'p4'", name="ck_financial_transactions_no_p4"
        ),
        sa.CheckConstraint(
            f"ledger_status IN {LEDGER_STATUSES}",
            name="ck_financial_transactions_ledger_status",
        ),
        sa.CheckConstraint(
            f"ordering_date_source IN {DATE_SOURCES}",
            name="ck_financial_transactions_ordering_date_source",
        ),
        sa.CheckConstraint(
            "transaction_date IS NOT NULL OR posted_date IS NOT NULL "
            "OR value_date IS NOT NULL OR effective_date IS NOT NULL",
            name="ck_financial_transactions_has_a_date",
        ),
        sa.CheckConstraint(
            "extraction_layer BETWEEN 0 AND 3",
            name="ck_financial_transactions_extraction_layer",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["financial_accounts.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_document_id"],
            ["financial_source_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["financial_ingestion_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["statement_period_id"],
            ["financial_statement_periods.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id"], ["financial_transactions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_id", "ref_id", name="uq_financial_transactions_case_ref"
        ),
        sa.UniqueConstraint(
            "source_document_id",
            "content_hash",
            name="uq_financial_transactions_document_content",
        ),
    )
    op.create_index(
        "ix_financial_transactions_period_order",
        "financial_transactions",
        ["statement_period_id", "ordering_date", "row_index"],
        unique=False,
    )
    op.create_index(
        "ix_financial_transactions_account_date",
        "financial_transactions",
        ["account_id", "ordering_date"],
        unique=False,
    )
    op.create_index(
        "ix_financial_transactions_case_status",
        "financial_transactions",
        ["case_id", "ledger_status"],
        unique=False,
    )
    op.create_index(
        "ix_financial_transactions_run",
        "financial_transactions",
        ["ingestion_run_id"],
        unique=False,
    )

    # -- adjudications ------------------------------------------------------
    op.create_table(
        "financial_adjudications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject_type", sa.String(length=24), nullable=False),
        sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(length=48), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("before", _JSONB, nullable=True),
        sa.Column("after", _JSONB, nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_name", sa.String(length=255), nullable=False),
        sa.Column("actor_email", sa.String(length=255), nullable=False),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            f"subject_type IN {ADJUDICATION_SUBJECTS}",
            name="ck_financial_adjudications_subject_type",
        ),
        sa.CheckConstraint(
            REASON_NOT_BLANK,
            name="ck_financial_adjudications_reason_not_blank",
        ),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["financial_ingestion_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_financial_adjudications_subject",
        "financial_adjudications",
        ["subject_type", "subject_id"],
        unique=False,
    )
    op.create_index(
        "ix_financial_adjudications_case",
        "financial_adjudications",
        ["case_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_financial_adjudications_case", table_name="financial_adjudications"
    )
    op.drop_index(
        "ix_financial_adjudications_subject", table_name="financial_adjudications"
    )
    op.drop_table("financial_adjudications")

    op.drop_index("ix_financial_transactions_run", table_name="financial_transactions")
    op.drop_index(
        "ix_financial_transactions_case_status", table_name="financial_transactions"
    )
    op.drop_index(
        "ix_financial_transactions_account_date", table_name="financial_transactions"
    )
    op.drop_index(
        "ix_financial_transactions_period_order", table_name="financial_transactions"
    )
    op.drop_table("financial_transactions")

    op.drop_index(
        "ix_financial_statement_periods_status",
        table_name="financial_statement_periods",
    )
    op.drop_index(
        "ix_financial_statement_periods_account_span",
        table_name="financial_statement_periods",
    )
    op.drop_index(
        "ix_financial_statement_periods_case", table_name="financial_statement_periods"
    )
    op.drop_table("financial_statement_periods")

    op.drop_index("ix_financial_accounts_normalised", table_name="financial_accounts")
    op.drop_index("ix_financial_accounts_case", table_name="financial_accounts")
    op.drop_table("financial_accounts")

    op.drop_index(
        "ix_financial_source_documents_case_status",
        table_name="financial_source_documents",
    )
    op.drop_index(
        "ix_financial_source_documents_evidence_file",
        table_name="financial_source_documents",
    )
    op.drop_index(
        "ix_financial_source_documents_case", table_name="financial_source_documents"
    )
    op.drop_table("financial_source_documents")

    op.drop_index(
        "ix_financial_ingestion_runs_case", table_name="financial_ingestion_runs"
    )
    op.drop_table("financial_ingestion_runs")
