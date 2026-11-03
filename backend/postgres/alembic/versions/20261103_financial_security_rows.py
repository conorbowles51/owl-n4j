"""Security rows of the ledger: trades and holdings read from brokerage statements (lx-brokerage B).

- ``financial_security_rows``: one row per printed trade line (linked to its cash leg in ``financial_transactions``,
  which is never changed) and per printed holding line, with the instrument and quantity as printed, price, trade
  and settlement dates, the same proof class and extraction layer as the cash leg, the locator, the reading origin,
  corrections (the value as read stays visible) and a confirmation.
- The case decision ledger gains the subject ``security_row`` and the decisions ``correct_security_row`` and
  ``confirm_security_row``.

The constraint lists are read from the database and extended, so values another migration added are kept.
"""
import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261103_financial_security_rows"
down_revision = "20261103_case_briefs"
branch_labels = None
depends_on = None

NEW = {"ck_adjudications_subject_type": ("subject_type", ["security_row"]),
       "ck_adjudications_decision": ("decision", ["correct_security_row", "confirm_security_row"])}


def _values(conn, name):
    d = conn.execute(sa.text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = :n AND "
                             "conrelid = 'adjudications'::regclass"), {"n": name}).scalar()
    return re.findall(r"'([^']+)'::", d or "")


def _replace(conn, name, column, values):
    quoted = ", ".join("'%s'" % v for v in values)
    op.execute("ALTER TABLE adjudications DROP CONSTRAINT IF EXISTS %s" % name)
    op.execute("ALTER TABLE adjudications ADD CONSTRAINT %s CHECK (%s IN (%s))" % (name, column, quoted))


def upgrade():
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "financial_security_rows",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("case_id", uuid, sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_kind", sa.String(16), nullable=False),
        sa.Column("evidence_file_id", uuid, sa.ForeignKey("evidence_files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_document_id", uuid, sa.ForeignKey("financial_source_documents.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("account_id", uuid, sa.ForeignKey("financial_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("statement_period_id", uuid, sa.ForeignKey("financial_statement_periods.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("cash_transaction_id", uuid, sa.ForeignKey("financial_transactions.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("reading_key", sa.String(160), nullable=False),
        sa.Column("reader", sa.String(64), nullable=False),
        sa.Column("ledger_status", sa.String(16), nullable=False, server_default="admitted"),
        sa.Column("superseded_by_id", uuid, nullable=True),
        sa.Column("operation", sa.Text(), nullable=True),
        sa.Column("side", sa.String(16), nullable=True),
        sa.Column("holding_kind", sa.String(16), nullable=True),
        sa.Column("instrument", sa.String(128), nullable=False),
        sa.Column("issuer", sa.String(64), nullable=True),
        sa.Column("series", sa.String(32), nullable=True),
        sa.Column("isin", sa.String(12), nullable=True),
        sa.Column("quantity_printed", sa.String(64), nullable=True),
        sa.Column("quantity", sa.Numeric(28, 8), nullable=True),
        sa.Column("price_printed", sa.String(64), nullable=True),
        sa.Column("price", sa.Numeric(28, 10), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("gross_minor", sa.BigInteger(), nullable=True),
        sa.Column("commission_minor", sa.BigInteger(), nullable=True),
        sa.Column("premium_minor", sa.BigInteger(), nullable=True),
        sa.Column("tax_minor", sa.BigInteger(), nullable=True),
        sa.Column("net_minor", sa.BigInteger(), nullable=True),
        sa.Column("market_value_minor", sa.BigInteger(), nullable=True),
        sa.Column("trade_date", sa.Date(), nullable=True),
        sa.Column("trade_date_source", sa.String(16), nullable=False, server_default="absent"),
        sa.Column("execution_time", sa.String(32), nullable=True),
        sa.Column("settlement_date", sa.Date(), nullable=True),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("term_days", sa.Integer(), nullable=True),
        sa.Column("rate_printed", sa.String(32), nullable=True),
        sa.Column("proof_class", sa.String(2), nullable=False),
        sa.Column("extraction_layer", sa.Integer(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("corrections", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confirmation", postgresql.JSONB(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("row_kind IN ('trade', 'holding')", name="ck_financial_security_rows_kind"),
        sa.CheckConstraint("side IS NULL OR side IN ('buy', 'sell', 'repo', 'repo_start', 'repo_maturity', 'other')",
                           name="ck_financial_security_rows_side"),
        sa.CheckConstraint("holding_kind IS NULL OR holding_kind IN ('security', 'repo')",
                           name="ck_financial_security_rows_holding_kind"),
        sa.CheckConstraint("ledger_status IN ('admitted', 'superseded')", name="ck_financial_security_rows_status"),
        sa.CheckConstraint("proof_class IN ('p0', 'p1', 'p2', 'p3')", name="ck_financial_security_rows_proof_class"),
        sa.CheckConstraint("trade_date_source IN ('printed', 'absent')",
                           name="ck_financial_security_rows_trade_date_source"),
    )
    op.create_index("ix_financial_security_rows_case_kind", "financial_security_rows",
                    ["case_id", "row_kind", "ledger_status"])
    op.create_index("ix_financial_security_rows_document", "financial_security_rows", ["source_document_id"])
    op.create_index("ix_financial_security_rows_cash", "financial_security_rows", ["cash_transaction_id"])
    op.create_index("uq_financial_security_rows_line", "financial_security_rows", ["evidence_file_id", "reading_key"],
                    unique=True, postgresql_where=sa.text("ledger_status = 'admitted'"))
    conn = op.get_bind()
    for name, (column, add) in NEW.items():
        have = _values(conn, name)
        if not have:
            raise RuntimeError("constraint %s not found on adjudications" % name)
        _replace(conn, name, column, have + [v for v in add if v not in have])


def downgrade():
    conn = op.get_bind()
    for name, (column, add) in NEW.items():
        _replace(conn, name, column, [v for v in _values(conn, name) if v not in add])
    op.drop_table("financial_security_rows")
