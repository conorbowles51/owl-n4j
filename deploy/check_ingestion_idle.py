"""Read-only release gate. No restart is safe when an older worker owns work.

Run with the backend's configured database. Failure to inspect is a failure to
release; this script never pauses, retries, clears or changes ingestion records.
"""
import sys
from pathlib import Path
# Deployment retains this program in memory before changing the checkout. Its
# explicit backend path also lets rollback use the current gate with old code.
backend_path = Path(sys.argv[1]) if __name__ == '__main__' and len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(backend_path))
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
        # Recovery can be inside an atomic API unit before it has queued an
        # engine job. Paused/completed campaigns and review results are idle.
        recovery_runs = inspector.has_table('financial_recovery_runs')
        recovery_items = inspector.has_table('financial_recovery_items')
        if recovery_runs != recovery_items:
            raise RuntimeError('Incomplete financial recovery schema')
        if recovery_runs:
            count += connection.scalar(text("""
                SELECT count(*) FROM financial_recovery_items item
                JOIN financial_recovery_runs run ON run.id = item.run_id
                WHERE run.status = 'running' AND item.status IN ('pending', 'waiting', 'reading')
            """))
        # Upload registration/dispatch has durable receipts, but it still must
        # not race a release. Count a folder/archive once, including staged
        # members and pending dispatch. Explicitly paused selections are safe.
        upload_groups = inspector.has_table('evidence_upload_groups')
        if upload_groups:
            count += connection.scalar(text("SELECT count(*) FROM evidence_upload_groups WHERE status NOT IN ('paused', 'completed')"))
        if inspector.has_table('evidence_upload_sessions'):
            columns = {c['name'] for c in inspector.get_columns('evidence_upload_sessions')}
            standalone = ' AND group_id IS NULL' if upload_groups and 'group_id' in columns else ''
            count += connection.scalar(text("SELECT count(*) FROM evidence_upload_sessions WHERE status NOT IN ('paused', 'completed')" + standalone))
    return count


if __name__=='__main__':
    try:
        count=active_work(_get_engine())
        if count:
            print(f'Release deferred: {count} ingestion, recovery or upload records are queued or running. No further services will be replaced by this release attempt.',file=sys.stderr)
            sys.exit(75)
        print('Ingestion gate: no queued or running ingestion, recovery or uploads.')
    except Exception as error:
        print(f'Release deferred: ingestion state could not be verified ({type(error).__name__}).',file=sys.stderr)
        sys.exit(75)
