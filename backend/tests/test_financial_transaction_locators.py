"""Tests for joining a graph transaction back to its source rectangle.

:mod:`services.financial.transaction_locators` has one honest claim to make:
when it highlights a row, the excerpt the transaction was extracted from
actually describes that row and no other.  The join is textual -- no key from
a transaction to a cell was ever stored -- so the tests are mostly about the
ways a textual join can lie and the ways this one refuses to:

* a tie between two rows must degrade to the page, because highlighting one
  of them would be a guess wearing the interface's authority;
* one matching cell text is one shared word from a coincidence -- dates repeat
  down a statement column -- so a single match is not a candidate;
* a case difference is a real difference, because the excerpt was built from
  these same cell texts;
* every step down the ladder (row union, table rectangle, page, nothing) loses
  precision but never truth, and malformed stored geometry is skipped rather
  than allowed to take the transaction list down.

The loader tests use the ``test_financial_admission`` fixture shape: SQLite on
disk rather than ``:memory:`` so the caller does not share one connection with
the code under test, and ``PRAGMA foreign_keys=ON``.  The join functions are
imported from the package surface so these tests also exercise the exports.
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
from postgres.models.enums import GlobalRole, LocatorKind
from postgres.models.evidence import (
    EvidenceFile,
    EvidenceFolder,
    EvidenceTableGeometry,
)
from postgres.models.user import User
from services.financial import (
    TRANSACTION_MATCH_MINIMUM_CELLS,
    attach_transaction_locators,
    locate_transaction,
)
from services.financial.locators import Locator, SourceRectangle
from services.financial.transactions import LOCATOR_PROVENANCE_KEY

PAGE_WIDTH = 612_000
PAGE_HEIGHT = 792_000

EXCERPT = "01/03/2024 | ACME PAYROLL | 2,500.00"


def rectangle_locator(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    *,
    page: int = 1,
    page_width: int = PAGE_WIDTH,
    page_height: int = PAGE_HEIGHT,
) -> Locator:
    return Locator(
        kind=LocatorKind.page_rectangle,
        rectangle=SourceRectangle(
            page_number=page,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            page_width=page_width,
            page_height=page_height,
        ),
    )


def cell(row: int, column: int, text: str, locator=None) -> dict:
    payload = {"row": row, "column": column, "text": text}
    if locator is not None:
        payload["locator"] = locator
    return payload


def table_entry(cells: list, table_locator=None, page: int = 1) -> dict:
    """One ``per_table`` entry in the shape ``ExtractedTable.to_json`` writes."""
    return {
        "table_source": "camelot-lattice",
        "geometry_source": "camelot",
        "table": {
            "page": page,
            "table": table_locator,
            "values": cells,
            "unlocated_values": 0,
        },
    }


def payroll_row(row: int = 0, *, page: int = 1) -> list:
    """The grid row the excerpt was built from, three clickable cells wide."""
    return [
        cell(
            row,
            0,
            "01/03/2024",
            rectangle_locator(10_000, 20_000, 110_000, 40_000, page=page).to_json(),
        ),
        cell(
            row,
            1,
            "ACME PAYROLL",
            rectangle_locator(120_000, 20_000, 300_000, 40_000, page=page).to_json(),
        ),
        cell(
            row,
            2,
            "2,500.00",
            rectangle_locator(310_000, 20_000, 400_000, 40_000, page=page).to_json(),
        ),
    ]


def payroll_union(*, page: int = 1) -> dict:
    return rectangle_locator(10_000, 20_000, 400_000, 40_000, page=page).to_json()


class ARowTheExcerptUniquelyDescribes(unittest.TestCase):
    """The only situation the join is allowed to draw a rectangle in."""

    def test_wins_the_union_of_its_clickable_cells(self):
        locator = locate_transaction(
            source_excerpt=EXCERPT,
            source_page=1,
            page_payload=[table_entry(payroll_row())],
        )
        self.assertEqual(locator.to_json(), payroll_union())

    def test_beats_a_row_the_excerpt_describes_less_well(self):
        # The rent row shares the date and the amount with the excerpt --
        # exactly the coincidence dates and amounts produce -- but the payroll
        # row also matches the payee, and a strictly higher score wins.
        rent_row = [
            cell(
                1,
                0,
                "01/03/2024",
                rectangle_locator(10_000, 50_000, 110_000, 70_000).to_json(),
            ),
            cell(
                1,
                1,
                "RENT",
                rectangle_locator(120_000, 50_000, 300_000, 70_000).to_json(),
            ),
            cell(
                1,
                2,
                "2,500.00",
                rectangle_locator(310_000, 50_000, 400_000, 70_000).to_json(),
            ),
        ]
        locator = locate_transaction(
            source_excerpt=EXCERPT,
            source_page=1,
            page_payload=[table_entry(payroll_row() + rent_row)],
        )
        self.assertEqual(locator.to_json(), payroll_union())

    def test_whitespace_in_stored_text_is_normalised_before_matching(self):
        padded = [
            cell(
                0,
                0,
                "  01/03/2024\n",
                rectangle_locator(10_000, 20_000, 110_000, 40_000).to_json(),
            ),
            cell(
                0,
                1,
                "ACME\n  PAYROLL",
                rectangle_locator(120_000, 20_000, 300_000, 40_000).to_json(),
            ),
        ]
        locator = locate_transaction(
            source_excerpt=EXCERPT,
            source_page=1,
            page_payload=[table_entry(padded)],
        )
        self.assertEqual(
            locator.to_json(),
            rectangle_locator(10_000, 20_000, 300_000, 40_000).to_json(),
        )

    def test_a_cell_with_an_unparseable_locator_still_matches_by_text(self):
        # The bad locator costs that cell its place in the union, not the row
        # its win: the remaining clickable cell is the rectangle.
        row = [
            cell(0, 0, "01/03/2024", {"kind": "nonsense"}),
            cell(
                0,
                1,
                "ACME PAYROLL",
                rectangle_locator(120_000, 20_000, 300_000, 40_000).to_json(),
            ),
        ]
        locator = locate_transaction(
            source_excerpt=EXCERPT,
            source_page=1,
            page_payload=[table_entry(row)],
        )
        self.assertEqual(
            locator.to_json(),
            rectangle_locator(120_000, 20_000, 300_000, 40_000).to_json(),
        )


class TheJoinRefuses(unittest.TestCase):
    """Every way the excerpt fails to single out one row."""

    def test_a_tie_between_two_rows_degrades_to_the_page(self):
        # Both rows share the date and the amount with the excerpt.  Two rows
        # described equally well is a guess either way, so neither is drawn.
        twin = [
            cell(
                1,
                0,
                "01/03/2024",
                rectangle_locator(10_000, 50_000, 110_000, 70_000).to_json(),
            ),
            cell(
                1,
                2,
                "2,500.00",
                rectangle_locator(310_000, 50_000, 400_000, 70_000).to_json(),
            ),
        ]
        other_twin = [
            cell(
                2,
                0,
                "01/03/2024",
                rectangle_locator(10_000, 80_000, 110_000, 100_000).to_json(),
            ),
            cell(
                2,
                2,
                "2,500.00",
                rectangle_locator(310_000, 80_000, 400_000, 100_000).to_json(),
            ),
        ]
        locator = locate_transaction(
            source_excerpt="01/03/2024 | 2,500.00",
            source_page=1,
            page_payload=[table_entry(twin + other_twin)],
        )
        self.assertEqual(
            locator.to_json(),
            Locator(kind=LocatorKind.page_only, page_number=1).to_json(),
        )

    def test_a_single_matching_cell_is_not_a_candidate(self):
        self.assertEqual(TRANSACTION_MATCH_MINIMUM_CELLS, 2)
        row = [
            cell(
                0,
                0,
                "01/03/2024",
                rectangle_locator(10_000, 20_000, 110_000, 40_000).to_json(),
            ),
            cell(
                0,
                1,
                "SOMETHING ELSE",
                rectangle_locator(120_000, 20_000, 300_000, 40_000).to_json(),
            ),
        ]
        locator = locate_transaction(
            source_excerpt=EXCERPT,
            source_page=1,
            page_payload=[table_entry(row)],
        )
        self.assertEqual(
            locator.to_json(),
            Locator(kind=LocatorKind.page_only, page_number=1).to_json(),
        )

    def test_the_same_text_twice_in_one_row_counts_once(self):
        # Distinct texts, not matching cells: a row reading "100.00 | 100.00"
        # has matched one word of the excerpt, not two.
        row = [
            cell(
                0,
                0,
                "100.00",
                rectangle_locator(10_000, 20_000, 110_000, 40_000).to_json(),
            ),
            cell(
                0,
                1,
                "100.00",
                rectangle_locator(120_000, 20_000, 300_000, 40_000).to_json(),
            ),
        ]
        locator = locate_transaction(
            source_excerpt="01/03/2024 | TRANSFER | 100.00",
            source_page=1,
            page_payload=[table_entry(row)],
        )
        self.assertEqual(
            locator.to_json(),
            Locator(kind=LocatorKind.page_only, page_number=1).to_json(),
        )

    def test_a_case_difference_is_a_real_difference(self):
        # The excerpt was built from these same cell texts, so folding case
        # could only convert a safe fallback into a wrong highlight.
        locator = locate_transaction(
            source_excerpt="01/03/2024 | acme payroll | 2,500.00",
            source_page=1,
            page_payload=[
                table_entry(
                    [
                        cell(
                            0,
                            1,
                            "ACME PAYROLL",
                            rectangle_locator(
                                120_000, 20_000, 300_000, 40_000
                            ).to_json(),
                        ),
                        cell(
                            0,
                            2,
                            "OTHER TEXT",
                            rectangle_locator(
                                310_000, 20_000, 400_000, 40_000
                            ).to_json(),
                        ),
                    ]
                )
            ],
        )
        self.assertEqual(
            locator.to_json(),
            Locator(kind=LocatorKind.page_only, page_number=1).to_json(),
        )


class TheFallbackLadder(unittest.TestCase):
    """Each step down loses precision, never truth."""

    def test_no_stored_geometry_falls_to_the_page(self):
        locator = locate_transaction(
            source_excerpt=EXCERPT, source_page=4, page_payload=None
        )
        self.assertEqual(
            locator.to_json(),
            Locator(kind=LocatorKind.page_only, page_number=4).to_json(),
        )

    def test_no_usable_page_falls_to_unlocated(self):
        unlocated = Locator(kind=LocatorKind.unlocated).to_json()
        for page in (None, 0, -1, True, "3"):
            with self.subTest(page=page):
                locator = locate_transaction(
                    source_excerpt=EXCERPT, source_page=page, page_payload=None
                )
                self.assertEqual(locator.to_json(), unlocated)

    def test_an_empty_excerpt_falls_to_the_page(self):
        for excerpt in (None, "", "   \n\t"):
            with self.subTest(excerpt=excerpt):
                locator = locate_transaction(
                    source_excerpt=excerpt,
                    source_page=2,
                    page_payload=[table_entry(payroll_row())],
                )
                self.assertEqual(
                    locator.to_json(),
                    Locator(kind=LocatorKind.page_only, page_number=2).to_json(),
                )

    def test_a_winner_with_no_clickable_cells_falls_to_the_table_rectangle(self):
        page_only_cell = Locator(kind=LocatorKind.page_only, page_number=1).to_json()
        table_rect = rectangle_locator(5_000, 10_000, 450_000, 500_000)
        row = [
            cell(0, 0, "01/03/2024", page_only_cell),
            cell(0, 1, "ACME PAYROLL", page_only_cell),
        ]
        locator = locate_transaction(
            source_excerpt=EXCERPT,
            source_page=1,
            page_payload=[table_entry(row, table_locator=table_rect.to_json())],
        )
        self.assertEqual(locator.to_json(), table_rect.to_json())

    def test_mixed_page_geometry_falls_to_the_table_rectangle(self):
        # Two cells captured against differing page sizes: a union across two
        # coordinate frames is not a rectangle anywhere.
        table_rect = rectangle_locator(5_000, 10_000, 450_000, 500_000)
        row = [
            cell(
                0,
                0,
                "01/03/2024",
                rectangle_locator(10_000, 20_000, 110_000, 40_000).to_json(),
            ),
            cell(
                0,
                1,
                "ACME PAYROLL",
                rectangle_locator(
                    120_000,
                    20_000,
                    300_000,
                    40_000,
                    page_width=595_000,
                    page_height=842_000,
                ).to_json(),
            ),
        ]
        locator = locate_transaction(
            source_excerpt=EXCERPT,
            source_page=1,
            page_payload=[table_entry(row, table_locator=table_rect.to_json())],
        )
        self.assertEqual(locator.to_json(), table_rect.to_json())

    def test_a_missing_table_rectangle_falls_to_the_page(self):
        page_only_cell = Locator(kind=LocatorKind.page_only, page_number=1).to_json()
        row = [
            cell(0, 0, "01/03/2024", page_only_cell),
            cell(0, 1, "ACME PAYROLL", page_only_cell),
        ]
        locator = locate_transaction(
            source_excerpt=EXCERPT,
            source_page=1,
            page_payload=[table_entry(row, table_locator=None)],
        )
        self.assertEqual(
            locator.to_json(),
            Locator(kind=LocatorKind.page_only, page_number=1).to_json(),
        )

    def test_an_unclickable_table_rectangle_falls_to_the_page(self):
        page_only = Locator(kind=LocatorKind.page_only, page_number=1).to_json()
        row = [
            cell(0, 0, "01/03/2024", page_only),
            cell(0, 1, "ACME PAYROLL", page_only),
        ]
        locator = locate_transaction(
            source_excerpt=EXCERPT,
            source_page=1,
            page_payload=[table_entry(row, table_locator=page_only)],
        )
        self.assertEqual(
            locator.to_json(),
            Locator(kind=LocatorKind.page_only, page_number=1).to_json(),
        )

    def test_malformed_entries_are_skipped_not_raised_on(self):
        locator = locate_transaction(
            source_excerpt=EXCERPT,
            source_page=1,
            page_payload=[
                "not a mapping",
                {"table": "not a mapping either"},
                {"table": {"page": 1, "values": "not a list"}},
                {"table": {"page": 1, "values": [cell(True, 0, "01/03/2024")]}},
                table_entry(payroll_row()),
            ],
        )
        self.assertEqual(locator.to_json(), payroll_union())


TABLES = [
    User.__table__,
    Case.__table__,
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    EvidenceTableGeometry.__table__,
]


class TheAttachedTransactions(unittest.TestCase):
    """The loader against real stored geometry: one file, geometry on page 3."""

    def setUp(self):
        self._directory = tempfile.mkdtemp(prefix="loupe-txn-locators-")
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
            title="Locator Fixture",
            created_by_user_id=self.user.id,
            owner_user_id=self.user.id,
        )
        self.evidence_file = EvidenceFile(
            id=uuid.uuid4(),
            case_id=self.case.id,
            original_filename="january-statement.pdf",
            stored_path="/evidence/january-statement.pdf",
            sha256="a" * 64,
        )
        self.db.add_all([self.user, self.case, self.evidence_file])
        self.db.commit()

        # Committed after its parent file on purpose: there is no ORM
        # relationship between the geometry mapper and the file mapper, so a
        # single flush has no ordering constraint between the two inserts and
        # SQLite's foreign-key check fires on whichever happens to land first.
        self.geometry = EvidenceTableGeometry(
            evidence_file_id=self.evidence_file.id,
            page_number=3,
            engine_job_id=None,
            payload=[table_entry(payroll_row(page=3), page=3)],
        )
        self.db.add(self.geometry)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        shutil.rmtree(self._directory, ignore_errors=True)

    def transaction(self, **overrides) -> dict:
        base = {
            "transaction_id": "txn-1",
            "amount": 2500.00,
            "source_document_id": str(self.evidence_file.id),
            "source_filename": "january-statement.pdf",
            "source_page": 3,
            "source_excerpt": EXCERPT,
        }
        base.update(overrides)
        return base

    def test_a_transaction_with_stored_geometry_gets_the_row_rectangle(self):
        transaction = self.transaction()
        attach_transaction_locators(self.db, [transaction])
        self.assertEqual(
            transaction[LOCATOR_PROVENANCE_KEY], payroll_union(page=3)
        )

    def test_a_filename_document_id_gets_the_honest_page(self):
        # The extraction pipeline falls back to the filename when no evidence
        # file id was known.  There is nothing to look up, and the transaction
        # gets the page rather than nothing.
        transaction = self.transaction(source_document_id="january-statement.pdf")
        attach_transaction_locators(self.db, [transaction])
        self.assertEqual(
            transaction[LOCATOR_PROVENANCE_KEY],
            Locator(kind=LocatorKind.page_only, page_number=3).to_json(),
        )

    def test_no_provenance_at_all_is_unlocated(self):
        transaction = self.transaction(source_document_id=None, source_page=None)
        attach_transaction_locators(self.db, [transaction])
        self.assertEqual(
            transaction[LOCATOR_PROVENANCE_KEY],
            Locator(kind=LocatorKind.unlocated).to_json(),
        )

    def test_an_ingestion_time_locator_is_left_alone(self):
        # A locator written at ingestion time knows more than this join does.
        already = {"kind": "page_only", "page": 99}
        transaction = self.transaction(**{LOCATOR_PROVENANCE_KEY: already})
        attach_transaction_locators(self.db, [transaction])
        self.assertIs(transaction[LOCATOR_PROVENANCE_KEY], already)

    def test_a_page_with_no_stored_row_falls_to_the_page(self):
        transaction = self.transaction(source_page=7)
        attach_transaction_locators(self.db, [transaction])
        self.assertEqual(
            transaction[LOCATOR_PROVENANCE_KEY],
            Locator(kind=LocatorKind.page_only, page_number=7).to_json(),
        )

    def test_a_non_dict_transaction_is_ignored(self):
        transaction = self.transaction()
        rows = [None, "not a transaction", transaction]
        attach_transaction_locators(self.db, rows)
        self.assertEqual(
            transaction[LOCATOR_PROVENANCE_KEY], payroll_union(page=3)
        )


if __name__ == "__main__":
    unittest.main()
