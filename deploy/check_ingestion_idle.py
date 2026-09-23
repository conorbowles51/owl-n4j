"""Read-only release gate. No restart is safe when an older worker owns work.

Run with the backend's configured database. Failure to inspect is a failure to
release; this script never pauses, retries, clears or changes ingestion records.
"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from sqlalchemy import inspect, text
from postgres.session import _get_engine


def active_work(engine):
    inspector=inspect(engine)
    count = 0
    with engine.connect() as connection:
        if inspector.has_table('jobs'):
            columns={c['name'] for c in inspector.get_columns('jobs')}
            paused=" AND COALESCE(paused, false) = false" if 'paused' in columns else ''
            count += connection.scalar(text("SELECT count(*) FROM jobs WHERE status NOT IN ('completed','failed')"+paused))
        # Financial import execution runs in the API process, separately from
        # PDF/AI engine jobs. Protect accepted imports and active review leases.
        if inspector.has_table('financial_import_batch_items'):
            count += connection.scalar(text("SELECT count(*) FROM financial_import_batch_items WHERE status = 'pending_import'"))
        if inspector.has_table('financial_import_batches'):
            count += connection.scalar(text("SELECT count(*) FROM financial_import_batches WHERE worker_token IS NOT NULL AND lease_until > CURRENT_TIMESTAMP"))
    return count


if __name__=='__main__':
    try:
        count=active_work(_get_engine())
        if count:
            print(f'Release deferred: {count} ingestion records are queued or running. Their services have not been restarted.',file=sys.stderr)
            sys.exit(75)
        print('Ingestion gate: no queued or running jobs.')
    except Exception as error:
        print(f'Release deferred: ingestion state could not be verified ({type(error).__name__}).',file=sys.stderr)
        sys.exit(75)
