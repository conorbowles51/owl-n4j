"""Case-agnostic, read-only database readiness for the deployed code revision."""
from functools import lru_cache
from pathlib import Path
from sqlalchemy import text


@lru_cache(maxsize=1)
def expected_database_heads():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    return tuple(sorted(ScriptDirectory.from_config(config).get_heads()))


def database_readiness(*, engine=None, expected_heads=None):
    try:
        if engine is None:
            from postgres.session import _get_engine
            engine = _get_engine()
        expected = tuple(sorted(expected_heads if expected_heads is not None else expected_database_heads()))
        if not expected:
            return dict(status='unavailable', schema='unknown')
        with engine.connect() as connection:
            with connection.begin():
                connection.execute(text('SET TRANSACTION READ ONLY'))
                connection.execute(text("SET LOCAL statement_timeout = '2000ms'"))
                connection.execute(text('SELECT 1'))
                recorded = tuple(sorted(connection.execute(text('SELECT version_num FROM alembic_version')).scalars()))
        return dict(status='connected', schema='current' if recorded == expected else 'outdated')
    except Exception:
        # The health endpoint is public. Connection strings, hosts, usernames and
        # driver error details must not be copied into its response.
        return dict(status='unavailable', schema='unknown')


def overall_readiness(neo4j_status, evidence_engine_status, database):
    return ('ok' if neo4j_status == 'connected' and evidence_engine_status == 'ok'
            and database == {'status':'connected', 'schema':'current'} else 'degraded')
