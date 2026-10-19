"""drop the ``financial_`` prefix: the decision ledger was never only financial

Revision ID: 20260901_rename_adjudications
Revises: 20260831_reclassify_decision
Create Date: 2026-09-01

Why the name is wrong, not merely narrow
----------------------------------------

``financial_adjudications`` was built polymorphic and named as though it were
not.  The model says so itself about ``subject_id``: it "carries no foreign key
because the subject may be any of four tables", and the trade is deliberate --
"a decision must outlive the row it was about, and a cascade that deleted the
record of a decision would destroy the audit trail at precisely the moment it
was needed."  A table that deliberately refuses a foreign key so that it can
point at any subject is not a financial table.  It is the decision ledger, and
the four subjects it happens to accept today are a fact about one ``CHECK``
constraint rather than about the structure.

The next subject is an evidence file, which is not a financial row by any
reading.  So the choice is between a table named for a category its contents no
longer sit inside, and one rename.  The prefix is dropped now.

Why now
-------

The rename costs what it will ever cost least: no row anywhere carries the old
name in its meaning yet, because no admission has been recorded.  Every day
after this one, the same rename either drags stored history behind it or gets
skipped, and the name stays wrong permanently.  This is the cheapest this is
going to be.

What Postgres does not do for you
---------------------------------

``ALTER TABLE ... RENAME TO`` renames the table and nothing else.  Constraints
and indexes keep the names they were given, so a table renamed and left alone
ends up as ``adjudications`` covered in objects still called
``ck_financial_adjudications_*`` -- which is worse than not renaming, because
the disagreement is now something a reader has to resolve rather than a
consistent old name.  Every one of the eleven objects on this table is renamed
here.

They divide into two kinds, handled differently on purpose.

Seven were named explicitly when they were created -- four ``CHECK``, one
``UNIQUE``, two indexes -- across three migrations (``20260830_financial_ledger``
created two checks and both indexes, ``20260830_adjudication_sequence`` added
the unique constraint and two more checks).  Those are renamed by exact name.
If one is missing the migration should fail loudly, because a decision ledger
missing a constraint it was built with is a fact worth stopping for.

Four were created *unnamed* -- the primary key and three foreign keys -- and no
``naming_convention`` is configured on the metadata, so they carry names
Postgres generated rather than names anyone chose: ``<table>_pkey`` and
``<table>_<column>_fkey``.  Those are discovered from ``pg_constraint`` and
renamed by prefix substitution rather than asserted by name.  The distinction
is not fussiness.  Naming a constraint we never named would hard-code a guess
about another system's generator into a migration that has to run everywhere;
reading the catalogue renames whatever is actually there, and quietly does
nothing on a database where those names already differ.

Renaming a ``UNIQUE`` or ``PRIMARY KEY`` constraint also renames its backing
index, which is why only the two plain ``ix_`` indexes need
``ALTER INDEX``.

On the downgrade
----------------

Reversible in full, and worth keeping so: this migration changes no data and
admits no value, so unlike ``20260831_reclassify_decision`` there is nothing a
downgrade could strand.  The reversal is the same operation with the
substitution running the other way.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260901_rename_adjudications"
down_revision: Union[str, None] = "20260831_reclassify_decision"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_TABLE = "financial_adjudications"
NEW_TABLE = "adjudications"

# Named when created, so renamed by name.  The suffixes are the part that
# survives; the prefix is what this migration exists to change.
CHECK_SUFFIXES = (
    "subject_type",
    "decision",
    "reason_not_blank",
    "sequence_positive",
)
UNIQUE_SUFFIXES = ("subject_sequence",)
INDEX_SUFFIXES = ("subject", "case")


def _rename_named(table: str, was: str, now: str) -> None:
    """Rename the seven objects whose names were chosen rather than generated.

    ``table`` is what the table is called by the time this runs -- the rename
    happens first -- while ``was`` and ``now`` are the stem inside the object
    names, which the table rename did not touch.  The three are spelled
    separately because on the downgrade ``table`` and ``now`` are the old name
    and ``was`` is the new one, and a single pair of arguments would have to be
    read backwards to see that.
    """
    for suffix in CHECK_SUFFIXES:
        op.execute(
            sa.text(  # noqa: S608 - identifiers are module constants
                f"ALTER TABLE {table} RENAME CONSTRAINT "
                f"ck_{was}_{suffix} TO ck_{now}_{suffix}"
            )
        )
    for suffix in UNIQUE_SUFFIXES:
        # Renames the backing index with it, so no ALTER INDEX is needed here.
        op.execute(
            sa.text(  # noqa: S608 - identifiers are module constants
                f"ALTER TABLE {table} RENAME CONSTRAINT "
                f"uq_{was}_{suffix} TO uq_{now}_{suffix}"
            )
        )
    for suffix in INDEX_SUFFIXES:
        op.execute(
            sa.text(  # noqa: S608 - identifiers are module constants
                f"ALTER INDEX ix_{was}_{suffix} RENAME TO ix_{now}_{suffix}"
            )
        )


def _rename_generated(table: str, was: str, now: str) -> None:
    """Rename the primary key and foreign keys Postgres named for us.

    Read from the catalogue rather than assumed, because these names were never
    chosen here.  Anything already outside the old prefix is left alone: on such
    a database the generator evidently did something different, and inventing a
    name for it would be a worse outcome than leaving it as it is.

    The prefix test is done in Python rather than with ``LIKE`` on purpose --
    ``_`` is a single-character wildcard to ``LIKE``, and every name involved
    here is full of them, so the pattern that looks exact is not.
    """
    old_prefix, new_prefix = f"{was}_", f"{now}_"
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = CAST(:table AS regclass) "
            "AND contype IN ('p', 'f')"
        ),
        {"table": table},
    ).fetchall()

    for (conname,) in rows:
        if not conname.startswith(old_prefix):
            continue
        renamed = f"{new_prefix}{conname[len(old_prefix):]}"
        op.execute(
            sa.text(  # noqa: S608 - names come from pg_constraint
                f"ALTER TABLE {table} RENAME CONSTRAINT "
                f'"{conname}" TO "{renamed}"'
            )
        )


def upgrade() -> None:
    op.rename_table(OLD_TABLE, NEW_TABLE)
    _rename_named(NEW_TABLE, was=OLD_TABLE, now=NEW_TABLE)
    _rename_generated(NEW_TABLE, was=OLD_TABLE, now=NEW_TABLE)


def downgrade() -> None:
    op.rename_table(NEW_TABLE, OLD_TABLE)
    _rename_named(OLD_TABLE, was=NEW_TABLE, now=OLD_TABLE)
    _rename_generated(OLD_TABLE, was=NEW_TABLE, now=OLD_TABLE)
