"""The phone PostgreSQL helpers skip with their reason when no test database is set.

Two tests reached ``fresh_engine`` through a fixture without the ``needs_template`` mark and crashed with
AttributeError in ``sa_url(None)`` instead of skipping (2026-11-04). The helpers themselves now skip.
"""
import pytest

from tests import phone_pg


def test_fresh_engine_skips_with_the_reason_when_no_template_is_set(monkeypatch):
    monkeypatch.setattr(phone_pg, "TEMPLATE_URL", None)
    with pytest.raises(pytest.skip.Exception, match="LOUPE_TEST_PHONE_PG_TEMPLATE_URL"):
        with phone_pg.fresh_engine():
            pass


def test_corpus_connection_skips_with_the_reason_when_no_corpus_is_set(monkeypatch):
    monkeypatch.setattr(phone_pg, "CORPUS_URL", None)
    with pytest.raises(pytest.skip.Exception, match="LOUPE_TEST_PHONE_PG_URL"):
        with phone_pg.corpus_connection():
            pass
