"""Exercise finalization guards on isolated PostgreSQL, rolling all data back."""
import importlib.util
import sys
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from postgres.base import Base
from postgres.models.financial_candidates import (
    FinancialCandidateFinalization as Finalization, FinancialCandidateTransaction as Link,
    FinancialCandidateMapping as Mapping, FinancialExtractionCandidate as Candidate,
    FinancialCandidateReview as Review,
)
from tests.test_financial_candidate_finalizations import FinalizationFixture, LEDGER_TABLES, CANDIDATE_TABLES


def main():
    fixture = FinalizationFixture()
    fixture.setUp()
    engine = create_engine("postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local")
    checks = []
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                tables = set(LEDGER_TABLES + CANDIDATE_TABLES)
                for table in Base.metadata.sorted_tables:
                    if table in tables:
                        rows = [dict(row) for row in fixture.db.execute(select(table)).mappings()]
                        if rows:
                            connection.execute(table.insert(), rows)

                def refused(label, statement, values=None):
                    try:
                        with connection.begin_nested():
                            connection.execute(statement, values or {})
                    except DBAPIError:
                        checks.append(label)
                    else:
                        raise AssertionError(f"Guard failed: {label}")

                refused("cross-case receipt", Finalization.__table__.insert(),
                        fixture.receipt_values(case_id=fixture.other_case.id))
                receipt = fixture.receipt_values()
                connection.execute(Finalization.__table__.insert(), receipt)
                refused("duplicate whole-file receipt", Finalization.__table__.insert(), fixture.receipt_values())
                refused("changed original digest", Link.__table__.insert(),
                        fixture.link_values(receipt["id"], original_sha256="e" * 64))
                link = fixture.link_values(receipt["id"])
                connection.execute(Link.__table__.insert(), link)
                refused("duplicate candidate transaction", Link.__table__.insert(), fixture.link_values(receipt["id"]))
                refused("receipt rewrite", text("UPDATE financial_candidate_finalizations SET reason = 'rewrite' WHERE id = :id"), {"id": receipt["id"]})
                refused("link rewrite", text("UPDATE financial_candidate_transactions SET review_revision = :digest WHERE id = :id"), {"id": link["id"], "digest": "d" * 64})
                mapping = dict(fixture.db.execute(select(Mapping.__table__)).mappings().one())
                mapping.update(id=uuid4(), mapping_revision="f" * 64)
                refused("new mapping after seal", Mapping.__table__.insert(), mapping)
                candidate = dict(fixture.db.execute(select(Candidate.__table__)).mappings().one())
                candidate.update(id=uuid4(), candidate_key="e" * 64, row_index=1)
                refused("new candidate after seal", Candidate.__table__.insert(), candidate)
                review = dict(fixture.db.execute(select(Review.__table__)).mappings().one())
                review.update(id=uuid4(), sequence=2, reason="Try reopening", status="pending", reading=None)
                refused("review after seal", Review.__table__.insert(), review)
                path = ROOT / "backend/postgres/alembic/versions/20260907_candidate_finalizations.py"
                spec = importlib.util.spec_from_file_location("finalization_migration", path)
                migration = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(migration)
                with Operations.context(MigrationContext.configure(connection)):
                    try:
                        migration.downgrade()
                    except RuntimeError:
                        checks.append("downgrade with history")
                    else:
                        raise AssertionError("Downgrade discarded finalization history")
                print("PASS: " + "; ".join(checks))
            finally:
                transaction.rollback()
        print("All synthetic fixture rows rolled back; existing cases unchanged.")
    finally:
        fixture.tearDown()
        engine.dispose()


if __name__ == "__main__":
    main()
