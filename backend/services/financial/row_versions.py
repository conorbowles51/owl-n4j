"""Values read from large JSON metadata, reused per row while its PostgreSQL row version is unchanged.

Several checks of one import read a few keys from every saved period of a file
(its statement id, source pages, source regions). A JSON path select still
makes PostgreSQL detoast each row's whole metadata, and every saved period of a
multi-statement file carries large values (the file's statement catalogue,
until it is stored once), so each check cost seconds on a 217-period production
and grew with every import. A row's values are reused while PostgreSQL reports
the same row version (xmin), which every committed update of the row changes;
only the ids and versions are read for the rest. Without row versions (SQLite)
every value is read, as before.
"""
from collections import OrderedDict
from threading import Lock
from types import SimpleNamespace

from sqlalchemy import literal_column, select, text

from services.financial.request_timing import count


def own_write_floor(session):
    """Row versions at or above this number were written by this session's own transaction, which may still change
    them again before it commits (both versions then carry the same xmin), so they are never memoised.

    None: the transaction has written nothing, so every row it sees is a committed version (another transaction's
    uncommitted rows are invisible; its own subtransactions have later ids than the transaction itself). 0: the
    transaction counter has passed 2**32, where a 32-bit xmin no longer orders, so nothing is memoised. Databases
    without transaction ids (SQLite, whose callers stand a row's content in for its version, so every write is a
    new version) get None, as before."""
    if session.get_bind().dialect.name != 'postgresql':
        return None
    own = session.execute(text('SELECT pg_current_xact_id_if_assigned()::text')).scalar()
    if own is None:
        return None
    own = int(own)
    return own if own < 2 ** 32 else 0


def memoisable(row_version, floor):
    """A row version (xmin as text) that is final for every reader: see own_write_floor."""
    return floor is None or (floor > 0 and int(row_version) < floor)


class RowValues:
    """Per process: primary key -> (row version, {name: value}) for one table and one set of keys."""

    def __init__(self, model, kept=20_000):
        self.model, self.kept = model, kept
        self._values, self._lock = OrderedDict(), Lock()

    def rows(self, session, columns, keys, conditions, order_by=None, transform=None):
        """[SimpleNamespace] matching ``conditions``: ``columns`` (plain columns, the primary key first) read
        every time, ``keys`` (labelled expressions) reused per row version. ``transform`` ({name: value} ->
        {name: value}) reduces what is kept per row; whatever it keeps is shared between reads, so it must
        keep only values no caller changes (strings, numbers, frozen sets)."""
        identifier = columns[0]
        column_names = [column.key for column in columns]
        names = [key.name for key in keys]
        transform = transform or (lambda values: values)
        if session.get_bind().dialect.name != 'postgresql':
            query = select(*columns, *keys).where(*conditions)
            count('row_reads_unversioned')
            return [SimpleNamespace(**dict(zip(column_names, row[:len(columns)])),
                                    **transform(dict(zip(names, row[len(columns):]))))
                    for row in session.execute(query.order_by(order_by) if order_by is not None else query)]
        version = literal_column(f'{self.model.__tablename__}.xmin::text').label('row_version')
        query = select(*columns, version).where(*conditions)
        current = session.execute(query.order_by(order_by) if order_by is not None else query).all()
        with self._lock:
            known = {row[0]: self._values.get(row[0]) for row in current}
        stale = [row[0] for row in current if (known[row[0]] or (None,))[0] != row.row_version]
        # For the import timing line: rows whose values were reused, and read again.
        count('rows_reused', len(current) - len(stale))
        count('rows_reread', len(stale))
        for start in range(0, len(stale), 500):
            for row in session.execute(select(identifier, version, *keys).where(identifier.in_(stale[start:start + 500]))):
                # Stored under the version read with the values: a row changed between the two reads is
                # compared again on the next read.
                known[row[0]] = (row.row_version, transform({name: getattr(row, name) for name in names}))
        if stale:
            floor = own_write_floor(session)
            with self._lock:
                for key in stale:
                    if known.get(key) is not None and memoisable(known[key][0], floor):
                        self._values[key] = known[key]
                        self._values.move_to_end(key)
                while len(self._values) > self.kept:
                    self._values.popitem(last=False)
        # A row deleted between the two reads is left out, as a fresh read would.
        return [SimpleNamespace(**dict(zip(column_names, row[:len(columns)])), **known[row[0]][1])
                for row in current if known.get(row[0]) is not None]

    def clear(self):
        with self._lock:
            self._values.clear()
