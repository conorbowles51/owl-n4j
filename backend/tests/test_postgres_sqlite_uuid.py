import unittest
from uuid import UUID as Value
from sqlalchemy import Column, MetaData, Table, create_engine, insert, select, text
from sqlalchemy.dialects.postgresql import UUID, dialect
import postgres.base  # Register the SQLite-only compatibility compilation.


class SqliteUuidTests(unittest.TestCase):
    def test_numeric_looking_uuid_round_trips_exactly_in_bulk_returning(self):
        metadata = MetaData()
        table = Table('uuid_regression', metadata, Column('id', UUID(as_uuid=True), primary_key=True))
        engine = create_engine('sqlite://')
        values = [Value('00000000-0000-4000-8000-000000000001'), Value('00000000-0000-4000-8000-000000000002')]
        try:
            metadata.create_all(engine)
            with engine.begin() as connection:
                result = list(connection.scalars(insert(table).returning(table.c.id, sort_by_parameter_order=True), [{'id':value} for value in values]))
                self.assertEqual(result, values)
                self.assertEqual(set(connection.scalars(select(table.c.id))), set(values))
                self.assertEqual(set(connection.scalars(text('SELECT typeof(id) FROM uuid_regression'))), {'text'})
        finally:
            engine.dispose()

    def test_postgresql_keeps_native_uuid_type(self):
        self.assertEqual(UUID().compile(dialect=dialect()), 'UUID')
