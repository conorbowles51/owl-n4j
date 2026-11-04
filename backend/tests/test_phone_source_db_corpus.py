"""05 section 17.2 gate on the real captures (stage J items A and B): for each passing report loaded in the restricted
reference cases, the resolver's count of records reaching a present, verified Database file by ``nodeInfo`` id, and of
those files, equals the cb-ground A3 table. Counts only; read-only.

Opt-in: ``LOUPE_STAGEJ_CORPUS_DB_URL`` (a database holding the captures, opened read-only) and
``LOUPE_STAGEJ_EXTRACTIONS`` (JSON ``{"P12": "<extraction id>", ...}``; reports not loaded are left out)."""
from __future__ import annotations

import json
import os

import pytest

A3 = {"P11": (77446, 26), "P13": (42604, 42), "P08": (37052, 55), "P02": (8028, 44), "P03": (6733, 34),
      "P07": (3785, 44), "P12": (1306, 15)}
URL = os.environ.get("LOUPE_STAGEJ_CORPUS_DB_URL")
LOADED = json.loads(os.environ.get("LOUPE_STAGEJ_EXTRACTIONS") or "{}")
pytestmark = pytest.mark.skipif(not (URL and LOADED), reason="set LOUPE_STAGEJ_CORPUS_DB_URL and LOUPE_STAGEJ_EXTRACTIONS")


@pytest.mark.parametrize("label", sorted(A3))
def test_resolver_count_equals_the_a3_table(label):
    if label not in LOADED:
        pytest.skip("%s is not loaded" % label)
    from sqlalchemy import create_engine, text
    from services.phone import source_db
    engine = create_engine(URL)
    try:
        with engine.connect() as c:
            c.execute(text("SET TRANSACTION READ ONLY"))
            c.execute(text("SET LOCAL statement_timeout = '600s'"))
            n = source_db.record_count(c, LOADED[label])
            c.rollback()
    finally:
        engine.dispose()
    assert (n["records_by_extra_info_id"], n["verified_database_files_referenced_by_id"]) == A3[label], n
