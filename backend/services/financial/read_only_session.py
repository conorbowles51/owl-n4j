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
tries that file again later, and nothing is written. Measured on the test suites: 486 statement readings and 24
held-statement judgements, no flush with a pending change.

Switch: ``FINANCIAL_SWEEP_READS_OUTSIDE_TRANSACTION=0`` keeps the old open transaction.
"""
import os

from sqlalchemy import event

ENABLED = os.environ.get('FINANCIAL_SWEEP_READS_OUTSIDE_TRANSACTION', '1').strip().lower() not in (
    '0', 'false', 'off', 'no')


class WriteInReadOnlyComparison(RuntimeError):
    """A read-only comparison tried to write; refused, because under autocommit it would be committed at once."""


def _refuse_writes(session, flush_context, instances):
    if session.new or session.dirty or session.deleted:
        raise WriteInReadOnlyComparison(
            'A read-only comparison tried to write (new %d, changed %d, deleted %d); nothing was written'
            % (len(session.new), len(session.dirty), len(session.deleted)))


def reads_outside_transaction(session):
    """Call before the session's first statement. Its reads then run each in its own transaction, and a write is
    refused. Does nothing when the switch is off."""
    if not ENABLED:
        return session
    event.listen(session, 'before_flush', _refuse_writes)
    session.connection(execution_options={'isolation_level': 'AUTOCOMMIT'})
    return session
