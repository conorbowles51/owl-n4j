"""Verify human-reading constraints on isolated PostgreSQL; roll test changes back."""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[1]


def main():
    engine = create_engine(
        "postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local"
    )
    path = ROOT / "backend/postgres/alembic/versions/20260907_investigator_reading.py"
    spec = importlib.util.spec_from_file_location("reading_method_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == module.revision
            row = connection.execute(text(
                "SELECT id, source_document_id FROM financial_transactions LIMIT 1"
            )).one_or_none()
            if row is None:
                raise RuntimeError("Run the synthetic local ledger check first.")
            connection.execute(text(
                "UPDATE financial_source_documents SET extraction_layer = 4 WHERE id = :id"
            ), {"id": row.source_document_id})
            connection.execute(text(
                "UPDATE financial_transactions SET extraction_layer = 4 WHERE id = :id"
            ), {"id": row.id})
            for table, identifier in (("financial_transactions", row.id),
                                      ("financial_source_documents", row.source_document_id)):
                try:
                    with connection.begin_nested():
                        connection.execute(text(
                            f"UPDATE {table} SET extraction_layer = 5 WHERE id = :id"
                        ), {"id": identifier})
                except IntegrityError:
                    pass
                else:
                    raise AssertionError("Unknown reading method was accepted.")
            with Operations.context(MigrationContext.configure(connection)):
                try:
                    module.downgrade()
                except RuntimeError as exc:
                    assert "investigator-reviewed readings exist" in str(exc)
                else:
                    raise AssertionError("Downgrade would discard human-reading provenance.")
            print("PASS: document/row method 4 accepted; method 5 refused; downgrade protected.")
        finally:
            transaction.rollback()
    engine.dispose()
    print("All synthetic test row changes rolled back.")


if __name__ == "__main__":
    main()
