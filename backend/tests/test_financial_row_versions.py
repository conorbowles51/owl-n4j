"""Values reused per PostgreSQL row version (row_versions.RowValues)."""
from types import SimpleNamespace
from unittest import TestCase

from sqlalchemy import Column, Integer, JSON, String
from sqlalchemy.orm import declarative_base

from services.financial.row_versions import RowValues

Base = declarative_base()


class Record(Base):
    __tablename__ = 'row_version_records'
    id = Column(Integer, primary_key=True)
    owner = Column(String)
    metadata_ = Column('metadata', JSON)


class Row(tuple):
    """A result row: positional values plus named attributes."""

    def __new__(cls, values, **names):
        row = super().__new__(cls, values)
        row.__dict__.update(names)
        return row


class FakePostgres:
    """Answers the two reads RowValues makes: (id, owner, version) for every row, then (id, version, keys) for
    the ids asked. ``table`` is {id: (owner, version, value)}; every keyed read is recorded."""

    def __init__(self, table):
        self.table, self.keyed = table, []

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name='postgresql'))

    def execute(self, query):
        names = [column.name for column in query.selected_columns]
        if 'value' not in names:
            return SimpleNamespace(all=lambda: [Row((key, owner, version), row_version=version)
                                                for key, (owner, version, _) in sorted(self.table.items())])
        asked = sorted(query.whereclause.right.value)
        self.keyed.append(asked)
        return [Row((key, self.table[key][1], self.table[key][2]), row_version=self.table[key][1], value=self.table[key][2])
                for key in asked if key in self.table]


class RowValuesTests(TestCase):
    def read(self, cache, session, transform=None):
        rows = cache.rows(session, (Record.id, Record.owner), (Record.metadata_['value'].label('value'),),
                          (Record.owner == 'a',), order_by=Record.id, transform=transform)
        return [(row.id, row.owner, row.value) for row in rows]

    def test_values_are_read_again_only_for_new_or_changed_rows(self):
        session, cache = FakePostgres({1: ('a', '10', 'one'), 2: ('a', '11', 'two')}), RowValues(Record)
        self.assertEqual(self.read(cache, session), [(1, 'a', 'one'), (2, 'a', 'two')])
        self.assertEqual(session.keyed, [[1, 2]])
        # Unchanged: only ids and versions are read.
        self.assertEqual(self.read(cache, session), [(1, 'a', 'one'), (2, 'a', 'two')])
        self.assertEqual(session.keyed, [[1, 2]])
        # A committed update changes the row version: that row alone is read again; a new row is read.
        session.table[2] = ('a', '15', 'two, edited')
        session.table[3] = ('a', '16', 'three')
        self.assertEqual(self.read(cache, session), [(1, 'a', 'one'), (2, 'a', 'two, edited'), (3, 'a', 'three')])
        self.assertEqual(session.keyed[-1], [2, 3])
        # A deleted row is left out.
        del session.table[1]
        self.assertEqual(self.read(cache, session), [(2, 'a', 'two, edited'), (3, 'a', 'three')])

    def test_only_what_the_transform_keeps_is_reused(self):
        session, cache = FakePostgres({1: ('a', '10', 'long value')}), RowValues(Record)
        transform = lambda values: dict(value=len(values['value']))
        self.assertEqual(self.read(cache, session, transform), [(1, 'a', 10)])
        self.assertEqual(self.read(cache, session, transform), [(1, 'a', 10)])
        self.assertEqual(len(session.keyed), 1)

    def test_the_cache_keeps_a_bounded_number_of_rows(self):
        session, cache = FakePostgres({n: ('a', '1', str(n)) for n in range(5)}), RowValues(Record, kept=3)
        self.read(cache, session)
        self.assertEqual(len(cache._values), 3)
        # Evicted rows are read again, the rest reused.
        self.read(cache, session)
        self.assertTrue(set(session.keyed[-1]) <= {0, 1, 2, 3, 4} and len(session.keyed[-1]) < 5)
