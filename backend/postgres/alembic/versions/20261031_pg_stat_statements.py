"""Query statistics for Postgres (pg_stat_statements): additive, no table or row changes.

The live server preloads the library (docker-compose.yml postgres command); this creates the view in owl_db so
the top statements by time, temp spill and cache misses can be read. A role that may not create extensions (a
test database run by a non-superuser) gets a printed notice and no view; nothing else depends on it.
"""
from alembic import op
import sqlalchemy as sa

revision = "20261031_pg_stat_statements"
down_revision = "20261031_lx_measure"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    available = bind.execute(sa.text(
        "SELECT count(*) FROM pg_available_extensions WHERE name = 'pg_stat_statements'")).scalar()
    superuser = bind.execute(sa.text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar()
    if not available or not superuser:
        print('pg_stat_statements not created: %s' % ('not installed on this server' if not available
                                                       else 'the migration role is not a superuser'))
        return
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_stat_statements')


def downgrade():
    op.execute('DROP EXTENSION IF EXISTS pg_stat_statements')
