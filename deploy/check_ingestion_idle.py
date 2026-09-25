"""Read-only release gate. No restart is safe when an older worker owns work.

Run with the backend's configured database. Failure to inspect is a failure to
release; this script never pauses, retries, clears or changes ingestion records.
"""
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
# Deployment retains this program in memory before changing the checkout. Its
# explicit backend path also lets rollback use the current gate with old code.
backend_path = Path(sys.argv[1]) if __name__ == '__main__' and len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(backend_path))
from sqlalchemy import inspect, text
from postgres.session import _get_engine


SAMPLE_LIMIT = 10  # At most 60 references across the six blocking categories.
KNOWN_STATUSES = frozenset({
    'pending', 'processing', 'extracting_text', 'chunking', 'extracting_entities',
    'resolving_entities', 'resolving_relationships', 'generating_summaries',
    'merging_properties', 'writing_graph', 'completed', 'failed',
    'pending_import', 'preparing', 'pausing', 'paused', 'review', 'running',
    'waiting', 'reading', 'uploading', 'staged', 'dispatching',
})


def _safe_reference(record):
    """Legacy VARCHAR columns must not turn this diagnostic into a data export."""
    safe = {}
    for field, value in record.items():
        if value is None:
            safe[field] = None
        elif field.endswith('_id'):
            try:
                safe[field] = str(UUID(str(value)))
            except (ValueError, TypeError, AttributeError):
                safe[field] = 'unrecognized'
        elif field in ('status', 'run_status'):
            safe[field] = value if isinstance(value, str) and value in KNOWN_STATUSES else 'unrecognized'
        else:  # Only allow-listed timestamp projections reach this branch.
            try:
                safe[field] = datetime.fromisoformat(str(value).replace('Z', '+00:00')).isoformat()
            except (ValueError, TypeError):
                safe[field] = 'unrecognized'
    return safe


def _active_queries(inspector):
    """Share the existing safety predicates between counts and diagnostics.

    Diagnostic columns are optional on older installations. Missing safety
    columns still fail their SQL query; they are never treated as idle.
    """
    def columns(table):
        return {column['name'] for column in inspector.get_columns(table)}

    def fields(names, alias='work'):
        return {label: f'{alias}.{column}' if column in names else 'NULL'
                for label, column in (
                    ('record_id', 'id'), ('case_id', 'case_id'), ('status', 'status'),
                    ('created_at', 'created_at'), ('updated_at', 'updated_at'))}

    if inspector.has_table('jobs'):
        names = columns('jobs')
        paused = " AND COALESCE(work.paused, false) = false" if 'paused' in names else ''
        selected = fields(names)
        if 'batch_id' in names:
            selected['batch_id'] = 'work.batch_id'
        yield ('engine_jobs', 'jobs work',
               "work.status NOT IN ('completed','failed')" + paused, selected)

    # Accepted financial imports and live review leases are separate API work.
    batches = inspector.has_table('financial_import_batches')
    batch_columns = columns('financial_import_batches') if batches else set()
    if inspector.has_table('financial_import_batch_items'):
        names = columns('financial_import_batch_items')
        selected = fields(names)
        if 'batch_id' in names:
            selected['batch_id'] = 'work.batch_id'
            if {'id', 'case_id'} <= batch_columns:
                # Lookup enriches only the sample; it cannot drop an orphaned
                # pending item from the unchanged blocking count.
                selected['case_id'] = '(SELECT parent.case_id FROM financial_import_batches parent WHERE parent.id = work.batch_id LIMIT 1)'
        yield ('pending_financial_imports', 'financial_import_batch_items work',
               "work.status = 'pending_import'", selected)
    if batches:
        selected = fields(batch_columns)
        selected['lease_until'] = 'work.lease_until'
        yield ('financial_batch_leases', 'financial_import_batches work',
               'work.worker_token IS NOT NULL AND work.lease_until > CURRENT_TIMESTAMP', selected)

    # Paused/completed recovery campaigns and results awaiting review are idle.
    recovery_runs = inspector.has_table('financial_recovery_runs')
    recovery_items = inspector.has_table('financial_recovery_items')
    if recovery_runs != recovery_items:
        raise RuntimeError('Incomplete financial recovery schema')
    if recovery_runs:
        selected = fields(columns('financial_recovery_items'), 'item')
        run_columns = columns('financial_recovery_runs')
        selected.update(run_id='item.run_id', run_status='run.status',
                        case_id='run.case_id' if 'case_id' in run_columns else 'NULL',
                        run_updated_at='run.updated_at' if 'updated_at' in run_columns else 'NULL')
        yield ('recovery_items', 'financial_recovery_items item JOIN financial_recovery_runs run ON run.id = item.run_id',
               "run.status = 'running' AND item.status IN ('pending', 'waiting', 'reading')", selected)

    # Folder/archive members count once at group level, preserving legacy
    # handling when groups or group_id do not exist. No unfinished row expires.
    upload_groups = inspector.has_table('evidence_upload_groups')
    if upload_groups:
        yield ('upload_groups', 'evidence_upload_groups work',
               "work.status NOT IN ('paused', 'completed')", fields(columns('evidence_upload_groups')))
    if inspector.has_table('evidence_upload_sessions'):
        names = columns('evidence_upload_sessions')
        standalone = ' AND work.group_id IS NULL' if upload_groups and 'group_id' in names else ''
        selected = fields(names)
        if 'group_id' in names:
            selected['group_id'] = 'work.group_id'
        yield ('upload_sessions', 'evidence_upload_sessions work',
               "work.status NOT IN ('paused', 'completed')" + standalone, selected)


def active_work_report(engine, *, sample_limit=SAMPLE_LIMIT):
    """Read bounded, allow-listed references; never fetch filenames or payloads."""
    if isinstance(sample_limit, bool) or not isinstance(sample_limit, int) or not 0 <= sample_limit <= SAMPLE_LIMIT:
        raise ValueError('Invalid diagnostic sample limit')
    categories = []
    with engine.connect() as connection:
        for category, source, predicate, fields in _active_queries(inspect(engine)):
            count = connection.scalar(text(f'SELECT count(*) FROM {source} WHERE {predicate}'))
            records = []
            if count and sample_limit:
                selected = ', '.join(f'{expression} AS {name}' for name, expression in fields.items())
                records = [_safe_reference(dict(row)) for row in connection.execute(text(
                    f'SELECT {selected} FROM {source} WHERE {predicate} '
                    'ORDER BY updated_at ASC, record_id ASC LIMIT :sample_limit'),
                    {'sample_limit': sample_limit}).mappings()]
            categories.append(dict(category=category, count=count, records=records,
                                   omitted=max(0, count - len(records))))
    return dict(observed_at=datetime.now(timezone.utc).isoformat(),
                total=sum(category['count'] for category in categories),
                sample_limit=sample_limit, categories=categories)


def active_work(engine):
    """Keep the original count-only API for existing release checks/tests."""
    return active_work_report(engine, sample_limit=0)['total']


def main():
    try:
        report = active_work_report(_get_engine())
        if report['total']:
            print(f"Release deferred: {report['total']} ingestion, recovery or upload records are queued or running. No further services will be replaced by this release attempt.", file=sys.stderr)
            print(f"Ingestion gate diagnostics at {report['observed_at']}: at most {report['sample_limit']} references per category; counts and samples may change while work runs.", file=sys.stderr)
            for category in report['categories']:
                if not category['count']:
                    continue
                print(f"  {category['category']}: {category['count']} blocking records; {len(category['records'])} shown; {category['omitted']} not shown.", file=sys.stderr)
                for record in category['records']:
                    print('    ' + json.dumps(record, default=str, sort_keys=True), file=sys.stderr)
            return 75
        print('Ingestion gate: no queued or running ingestion, recovery or uploads.')
        return 0
    except Exception as error:
        # Database errors can contain connection URLs, SQL parameters or other
        # private values. Keep diagnostics fail-closed and print only the type.
        print(f'Release deferred: ingestion state could not be verified ({type(error).__name__}).',file=sys.stderr)
        return 75


if __name__=='__main__':
    sys.exit(main())
