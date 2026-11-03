"""The phone test template must be at this checkout's alembic head; a stale one fails with words that say so
(followups m11031250014627: one migration behind read as UndefinedColumn dossier_assessments.derived_text_id)."""
import uuid

import pytest

from tests import phone_pg
from tests.phone_pg import alembic_heads, needs_template, sa_url, template_behind_reason


def test_at_head_has_no_reason():
    assert template_behind_reason({"b"}, {"b"}) is None


def test_behind_names_both_revisions_and_the_upgrade():
    reason = template_behind_reason({"a"}, {"b"})
    assert "at a" in reason and "head is b" in reason and "alembic upgrade head" in reason


def test_heads_read_from_this_checkout():
    assert len(alembic_heads()) == 1


@needs_template
def test_a_template_one_migration_behind_fails_with_the_reason():
    from sqlalchemy import create_engine, text
    base, template = phone_pg._split(sa_url(phone_pg.TEMPLATE_URL))
    name = "phone_stale_%s" % uuid.uuid4().hex[:12]
    admin = create_engine(base + "/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text('CREATE DATABASE "%s" TEMPLATE "%s"' % (name, template)))
    try:
        eng = create_engine(base + "/" + name)
        with eng.begin() as c:
            c.execute(text("UPDATE alembic_version SET version_num = 'an_older_revision'"))
        eng.dispose()
        with pytest.raises(pytest.fail.Exception) as e:
            phone_pg.check_template_at_head(base + "/" + name)
        assert "an_older_revision" in str(e.value)
        phone_pg.check_template_at_head()  # the real template is at the head
    finally:
        with admin.connect() as c:
            c.execute(text('DROP DATABASE IF EXISTS "%s" WITH (FORCE)' % name))
        admin.dispose()
