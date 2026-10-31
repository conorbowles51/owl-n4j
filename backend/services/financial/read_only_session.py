"""Read-only background comparisons without an open database transaction.

The release re-check sweeps (reader_release, held_reprepare) read a prepared file again with the current reader and
compare, read only, then roll the session back. One comparison can take minutes of Python work (measured on live
31 Oct 12:12-12:17: one batch_rounds transaction 256 s old, after the 12:00 release). Postgres here runs READ
COMMITTED, so the open transaction gave the comparison no consistency: each statement reads its own snapshot. It
did hold the vacuum horizon (measured: those sessions carry backend_xmin) and the read tables' locks for the whole
comparison.

``reads_outside_transaction(session)`` runs the session's reads each in its own transaction (AUTOCOMMIT), and
refuses any flush that would write: under autocommit a flush would be committed at once, where before the
comparison's rollback discarded it. A refused flush raises ``WriteInReadOnlyComparison``; the sweep logs it and
tries that file again later, and nothing is written. On PostgreSQL the database refuses too: the comparison's
connection runs with ``default_transaction_read_only`` on, so a raw ``session.execute(insert/update/delete)`` or a
``text()`` write, which never reaches a flush, is refused by Postgres (SQLSTATE 25006) and raised as the same
``WriteInReadOnlyComparison``. The setting is reset before the connection goes back to the pool; if the reset
fails the connection is discarded instead, so no later user of the pool gets a read-only connection. Measured on
the test suites: 486 statement readings and 24 held-statement judgements, no flush with a pending change.

Switch: ``FINANCIAL_SWEEP_READS_OUTSIDE_TRANSACTION=0`` keeps the old open transaction.
"""
import functools
import logging
import os

from sqlalchemy import event
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# Marks the comparison's connection (an execution option lives on that Connection only, never on the pooled one).
_OPTION = 'loupe_read_only_comparison'
READ_ONLY_SQLSTATE = '25006'  # read_only_sql_transaction

ENABLED = os.environ.get('FINANCIAL_SWEEP_READS_OUTSIDE_TRANSACTION', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')


class WriteInReadOnlyComparison(RuntimeError):
    """A read-only comparison tried to write; refused, because under autocommit it would be committed at once."""


def _refuse_writes(session, flush_context, instances):
    if session.new or session.dirty or session.deleted:
        raise WriteInReadOnlyComparison(
            'A read-only comparison tried to write (new %d, changed %d, deleted %d); nothing was written'
            % (len(session.new), len(session.dirty), len(session.deleted)))


def _writable_again(record, dbapi_connection):
    """Runs as the connection goes back to the pool: the next user gets the server's default again."""
    try:
        with dbapi_connection.cursor() as cursor:
            cursor.execute('RESET default_transaction_read_only')
        if not getattr(dbapi_connection, 'autocommit', True):
            dbapi_connection.commit()
    except Exception as error:  # noqa: BLE001 - never hand a read-only connection to the pool
        # Invalidate through the pool record: it closes the connection, drops the remaining resets (they would fail
        # on it too) and still returns the slot; the next checkout opens a fresh connection.
        log.warning('Could not reset a read-only comparison connection; discarding it instead', exc_info=True)
        record.invalidate(e=error)


def _database_refuses_writes(connection):
    if connection.dialect.name != 'postgresql':
        return  # SQLite test databases: the flush refusal alone
    # The reset is registered before the SET, so a connection never leaves read only without it. Finalizers run
    # last-registered first, so this one runs before SQLAlchemy restores the isolation level (still autocommit).
    record = connection.connection._connection_record
    record.finalize_callback.append(functools.partial(_writable_again, record))
    connection.exec_driver_sql('SET default_transaction_read_only = on')


@event.listens_for(Engine, 'handle_error')
def _refused_by_database(context):
    """A write Postgres refused on a comparison's connection is the same refusal as a refused flush."""
    connection = context.connection
    if connection is None or not connection.get_execution_options().get(_OPTION):
        return None
    original = context.original_exception
    if (getattr(original, 'sqlstate', None) or getattr(original, 'pgcode', None)) != READ_ONLY_SQLSTATE:
        return None
    verb = ((context.statement or '').split(None, 1) or ['?'])[0]
    return WriteInReadOnlyComparison(
        'A read-only comparison tried to write (%s); Postgres refused it, nothing was written' % verb)


def reads_outside_transaction(session):
    """Call before the session's first statement. Its reads then run each in its own transaction, and a write is
    refused: by the flush check, and on PostgreSQL by the database itself. Does nothing when the switch is off."""
    if not ENABLED:
        return session
    event.listen(session, 'before_flush', _refuse_writes)
    connection = session.connection(execution_options={'isolation_level': 'AUTOCOMMIT', _OPTION: True})
    _database_refuses_writes(connection)
    return session
