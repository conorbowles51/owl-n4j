"""Run the complete migration chain in a disposable local database, then remove it.

The fixed local endpoint and generated database name cannot target an existing case DB.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
LOCAL = 'postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/'


def main():
    name = 'loupe_migration_check_' + uuid4().hex
    admin = create_engine(LOCAL + 'postgres', isolation_level='AUTOCOMMIT')
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        env = {**os.environ, 'DATABASE_URL':LOCAL + name, 'PYTHON_DOTENV_DISABLED':'1'}
        result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
            cwd=ROOT / 'backend', env=env, capture_output=True, text=True, timeout=180)
        if result.returncode:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            raise RuntimeError('Fresh migration chain failed.')
        engine = create_engine(LOCAL + name)
        try:
            with engine.connect() as connection:
                revision = connection.scalar(text('SELECT version_num FROM alembic_version'))
                tables = connection.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname='public'"))
                audit_triggers = connection.scalar(text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname IN ('capture_financial_audit','capture_financial_audit_delete','capture_graph_processing_audit')"))
                assert connection.scalar(text("SELECT count(*) FROM financial_audit_events")) == 0
                assert connection.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_name='evidence_document_texts' AND column_name='processing_manifest'")) == 1
                assert audit_triggers >= 18
            # An already-current deployment must also safely rerun upgrade head.
            repeated = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'],
                cwd=ROOT / 'backend', env=env, capture_output=True, text=True, timeout=180)
            if repeated.returncode:
                raise RuntimeError('Repeated upgrade failed: ' + repeated.stderr)
            print(json.dumps(dict(revision=revision, tables=tables, audit_triggers=audit_triggers,
                fresh_upgrade=True, repeated_upgrade=True, existing_case_databases_untouched=True)))
        finally:
            engine.dispose()
    finally:
        if created:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
            print('Disposable migration database removed.')
        admin.dispose()


if __name__ == '__main__':
    main()
