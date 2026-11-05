"""deploy/migration_safety.py: which pending migrations the old backend can stay up beside."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('migration_safety', Path(__file__).resolve().parents[2] / 'deploy' / 'migration_safety.py')
safety = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safety)


def migration(body, extra=''):
    return f'from alembic import op\nimport sqlalchemy as sa\n{extra}\ndef upgrade():\n' + ''.join(
        f'    {line}\n' for line in body.splitlines()) + '\ndef downgrade():\n    op.drop_table("anything")\n'


class Additive(unittest.TestCase):
    def test_what_the_old_code_never_notices(self):
        for body in ('op.create_table("t", sa.Column("id", sa.Integer, primary_key=True))',
                     'op.add_column("t", sa.Column("n", sa.Text(), nullable=True))',
                     'op.add_column("t", sa.Column("n", sa.Text()))',
                     'op.add_column("t", sa.Column("n", sa.Integer, nullable=False, server_default="0"))',
                     'op.create_index("i", "t", ["a"])',
                     'op.create_table("t", sa.Column("id", sa.Integer))\nop.create_index("i", "t", ["id"], unique=True)',
                     'op.create_table("t", sa.Column("id", sa.Integer))\nop.create_check_constraint("c", "t", "id > 0")',
                     'op.execute("CREATE INDEX IF NOT EXISTS i ON t (a)")',
                     'op.execute(sa.text("-- note\\nCREATE TABLE x (id int); COMMENT ON TABLE x IS \'y\'"))',
                     'op.execute("ALTER TABLE t ADD COLUMN IF NOT EXISTS n text")',
                     'op.execute("ALTER TABLE t ADD COLUMN n int NOT NULL DEFAULT 0")',
                     'op.execute("ALTER TABLE t ADD COLUMN a numeric(10,2), ADD COLUMN b text")',
                     'op.create_table("n", sa.Column("id", sa.Integer))\nop.create_foreign_key("f", "n", "existing", ["a"], ["id"])'):
            with self.subTest(body):
                self.assertEqual(safety.problems(migration(body)), [])

    def test_a_module_constant_is_read(self):
        self.assertEqual(safety.problems(migration('op.execute(UP)', 'UP = "CREATE INDEX i ON t (a)"')), [])
        self.assertTrue(safety.problems(migration('op.execute(UP)', 'UP = "DELETE FROM t"')))


class NotAdditive(unittest.TestCase):
    def test_what_can_break_the_old_code(self):
        for body in ('op.drop_column("t", "a")', 'op.drop_table("t")', 'op.drop_index("i")',
                     'op.alter_column("t", "a", nullable=False)',
                     'op.add_column("t", sa.Column("n", sa.Text(), nullable=False))',
                     'op.create_index("i", "t", ["a"], unique=True)',
                     'op.create_check_constraint("c", "t", "a > 0")',
                     'op.create_foreign_key("f", "t", "u", ["a"], ["id"])',
                     'op.create_unique_constraint("c", "t", ["a"])',
                     'op.drop_constraint("c", "t")',
                     'op.get_bind().execute(sa.text("UPDATE t SET a = 1"))',
                     'op.bulk_insert(t, [])',
                     'op.batch_alter_table("t")',
                     'op.execute("UPDATE t SET a = 1")',
                     'op.execute("ALTER TABLE t ALTER COLUMN a SET NOT NULL")',
                     'op.execute("ALTER TABLE t ADD COLUMN n int NOT NULL")',
                     'op.execute("ALTER TABLE t ADD CONSTRAINT c CHECK (a > 0)")',
                     'op.execute("ALTER TABLE t DROP COLUMN a")',
                     'op.execute("CREATE UNIQUE INDEX i ON t (a)")',
                     'op.execute("CREATE INDEX i ON t (a); DELETE FROM t")',
                     'op.execute(f"CREATE INDEX i ON {name} (a)")',
                     'op.execute(build_sql())',
                     'op.create_table("n", sa.Column("id", sa.Integer))\nop.create_foreign_key("f", "existing", "n", ["a"], ["id"])',
                     'op.add_column("t", sa.Column("n", sa.Text(), unique=True, server_default="x"))',
                     'op.execute("ALTER TABLE t ADD PRIMARY KEY (id)")',
                     'op.execute("ALTER TABLE t ADD EXCLUDE USING gist (a WITH =)")',
                     'op.execute("ALTER TABLE t ADD COLUMN a int DEFAULT 0, ALTER COLUMN b SET NOT NULL")',
                     'op.execute("ALTER TABLE t ADD COLUMN a int DEFAULT 0, ADD COLUMN c int NOT NULL")'):
            with self.subTest(body):
                self.assertTrue(safety.problems(migration(body)))

    def test_a_helper_outside_upgrade_counts_and_downgrade_does_not(self):
        self.assertTrue(safety.problems(migration('_helper()', 'def _helper():\n    op.drop_table("t")\n')))
        self.assertEqual(safety.problems(migration('op.create_index("i", "t", ["a"])')), [])


class Verdict(unittest.TestCase):
    def test_lines(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as root:
            good, bad = os.path.join(root, 'g.py'), os.path.join(root, 'b.py')
            open(good, 'w').write(migration('op.create_index("i", "t", ["a"])'))
            open(bad, 'w').write(migration('op.drop_table("t")'))
            self.assertEqual(safety.verdict([]), 'none')
            self.assertEqual(safety.verdict([('r1', good)]), 'additive 1')
            self.assertTrue(safety.verdict([('r1', good), ('r2', bad)]).startswith('unsafe r2'))
