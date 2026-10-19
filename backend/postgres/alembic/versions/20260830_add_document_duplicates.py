"""fingerprint source documents so in-matter duplicates can be found

Revision ID: 20260830_document_duplicates
Revises: 20260830_period_provenance
Create Date: 2026-08-30

Evidence arrives with duplicates.  The same statement is disclosed twice, or
scanned once and re-exported, or supplied by two parties who each obtained it
from the bank.  Nothing downstream notices: each copy becomes its own document,
its own statement period and its own transactions, and each of those periods
reconciles perfectly well on its own, because each is a faithful reading of the
same page.  The balance identity is per period and so it stays green.

What breaks is everything that adds periods together.  Account totals, the
money flow view, and the cross-period continuity check all see March twice and
have no way to tell that from March happening twice.  A defect that inflates
every aggregate while leaving every individual check passing is the worst shape
available, because nothing announces it.

So documents are fingerprinted twice, at different coarseness.

``content_fingerprint`` covers the reading: the accounts, the period bounds and
the transaction rows.  Two documents sharing it were read to say exactly the
same thing.  This is the fingerprint that earns its place, because it is the
one that survives a re-scan — different bytes, identical content — which is the
case that plain file hashing misses and the case that actually occurs.

``duplicate_group_key`` covers only the accounts and their period bounds.  It
is deliberately coarser, and it is what gathers candidates into a group.  Two
documents agreeing on the content fingerprint necessarily agree on this one, so
one group key is enough to hold every copy regardless of how strongly each
matched; ``duplicate_match_rung`` then records, per document, which rung
actually held.

Neither fingerprint includes the case.  A statement filed in two matters
produces the same key in both, and that is intended: seeing it is useful and
sometimes important.  Acting on it is not permitted.  Every query that changes
a status filters on case_id, so nothing outside the case is ever superseded,
and the two indexes below encode that split — one keyed on (case_id, group) for
the resolution path, one on the group alone for the cross-matter question.

This migration does not require an empty table, unlike the one below it.  There
the new columns were assertions about provenance, and defaulting them would
have meant claiming a date was printed when nobody had checked.  Here a null
fingerprint means "not yet computed" and false means "no review outstanding",
both of which are true of every existing row.  Backfilling is honest because
the defaults are not claims.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260830_document_duplicates"
down_revision: Union[str, None] = "20260830_period_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "financial_source_documents"


def upgrade() -> None:
    op.add_column(
        TABLE, sa.Column("content_fingerprint", sa.String(length=64), nullable=True)
    )
    op.add_column(
        TABLE, sa.Column("duplicate_group_key", sa.String(length=64), nullable=True)
    )
    op.add_column(
        TABLE, sa.Column("duplicate_match_rung", sa.Integer(), nullable=True)
    )
    op.add_column(
        TABLE,
        sa.Column(
            "duplicate_review_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.create_check_constraint(
        "ck_financial_source_documents_duplicate_rung",
        TABLE,
        "duplicate_match_rung IS NULL OR duplicate_match_rung BETWEEN 0 AND 2",
    )
    # A rung says how a document matched its group, so it cannot stand without
    # one.  Otherwise a row could claim it had been shown to duplicate
    # something without recording what.
    op.create_check_constraint(
        "ck_financial_source_documents_rung_needs_group",
        TABLE,
        "duplicate_match_rung IS NULL OR duplicate_group_key IS NOT NULL",
    )

    op.create_index(
        "ix_financial_source_documents_case_duplicate_group",
        TABLE,
        ["case_id", "duplicate_group_key"],
    )
    op.create_index(
        "ix_financial_source_documents_duplicate_group",
        TABLE,
        ["duplicate_group_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_financial_source_documents_duplicate_group", table_name=TABLE)
    op.drop_index(
        "ix_financial_source_documents_case_duplicate_group", table_name=TABLE
    )

    for name in (
        "ck_financial_source_documents_rung_needs_group",
        "ck_financial_source_documents_duplicate_rung",
    ):
        op.drop_constraint(name, TABLE, type_="check")

    op.drop_column(TABLE, "duplicate_review_required")
    op.drop_column(TABLE, "duplicate_match_rung")
    op.drop_column(TABLE, "content_fingerprint")
    op.drop_column(TABLE, "duplicate_group_key")
