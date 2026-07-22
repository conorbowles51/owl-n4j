from importlib import import_module
from unittest.mock import patch


def test_geocoding_cache_status_migration_allows_ambiguous_results() -> None:
    migration = import_module(
        "postgres.alembic.versions.20260722_expand_geocoding_cache_status"
    )

    with patch.object(migration.op, "execute") as execute:
        migration.upgrade()

    statements = [call.args[0] for call in execute.call_args_list]
    assert statements == [
        "ALTER TABLE geocoding_cache DROP CONSTRAINT IF EXISTS ck_geocoding_cache_status",
        "ALTER TABLE geocoding_cache ADD CONSTRAINT ck_geocoding_cache_status "
        "CHECK (status IN ('success', 'failed', 'ambiguous'))",
    ]
