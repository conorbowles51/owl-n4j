"""Verify the actual rating migration against disposable PostgreSQL tables."""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from tests.test_dossier_postgres import pg_engine, pytestmark  # explicit opt-in fixture


def test_migration_preserves_recorded_ratings_and_allows_unrated_findings(pg_engine):
    path = Path(__file__).parents[1] / "postgres/alembic/versions/20261019_workspace_setup.py"
    spec = importlib.util.spec_from_file_location("workspace_setup_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    old_rule = migration.RULE.replace("AND confidence IS NULL) OR\n(entry_type = 'theory'", "AND confidence IS NULL AND (significance IS NOT NULL OR needs_migration_review = true)) OR\n(entry_type = 'theory'")
    with pg_engine.begin() as connection:
        connection.execute(text(f"CREATE TABLE workspace_entries (id text PRIMARY KEY, entry_type text, lifecycle_state text, significance text, confidence int, needs_migration_review boolean NOT NULL DEFAULT false, CONSTRAINT {migration.CONSTRAINT} CHECK ({old_rule}))"))
        connection.execute(text("INSERT INTO workspace_entries (id, entry_type, lifecycle_state, significance) VALUES ('existing', 'finding', 'active', 'medium')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        connection.execute(text("INSERT INTO workspace_entries (id, entry_type, lifecycle_state) VALUES ('unrated', 'finding', 'draft')"))
        assert connection.scalar(text("SELECT significance FROM workspace_entries WHERE id = 'existing'")) == "medium"
        assert connection.scalar(text("SELECT needs_migration_review FROM workspace_entries WHERE id = 'unrated'")) is False
        with Operations.context(MigrationContext.configure(connection)), pytest.raises(RuntimeError, match="Unrated findings"):
            migration.downgrade()
        connection.execute(text("DELETE FROM workspace_entries WHERE id = 'unrated'"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(text("INSERT INTO workspace_entries (id, entry_type, lifecycle_state) VALUES ('blocked', 'finding', 'draft')"))
