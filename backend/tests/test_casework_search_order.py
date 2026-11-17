"""The agent's casework read with words: entries come best match first, in the case search's order.

Before, the found entries were sorted newest first, so on the demo case a check theory written at 19:13 on
17 Nov 2026 took rank 1 for "when did the glovebox phone enter the truck" and the judged note fell from 3 to 4
(casework mrr 0.71 to 0.61 with no search code changed). Without words, newest first stays.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tests.test_workspace_entry_service import ENTRY_TABLES


@pytest.fixture()
def casework_db(monkeypatch):
    from postgres.base import Base
    from postgres.models.case import Case
    from postgres.models.user import User
    from postgres.models.workspace_entry import WorkspaceEntry
    from services.agent import casework_tools
    from services.phone import link_states

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine, tables=ENTRY_TABLES)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    user, case = uuid4(), uuid4()
    t0 = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)
    ids = {}
    with Session() as db:
        db.add(User(id=user, email="s@x.test", name="Synthetic", password_hash="h"))
        db.add(Case(id=case, title="Synthetic case", created_by_user_id=user, owner_user_id=user))
        db.flush()
        for n, (name, kind) in enumerate((("answer", "note"), ("second", "theory"), ("newest", "theory"))):
            ids[name] = uuid4()
            db.add(WorkspaceEntry(id=ids[name], case_id=case, entry_type=kind, title=name, body=name,
                                  author_user_id=user, created_at=t0 + timedelta(days=n),
                                  updated_at=t0 + timedelta(days=n)))
        db.commit()
    # the search's order: the answer first, the newest entry last
    order = [ids["answer"], ids["second"], ids["newest"]]
    monkeypatch.setattr(casework_tools, "case_search_entry_ids", lambda conn, case_id, words: list(order))
    monkeypatch.setattr(link_states, "entry_links", lambda conn, case_id, entry_id: [])
    monkeypatch.setattr(link_states, "for_readers", lambda conn, case_id, links: {})
    return Session, case, ids


def _titles(out):
    return [i["title"] for i in out["items"]]


def test_a_search_lists_casework_best_match_first_not_newest_first(casework_db):
    from services.agent import casework_tools
    Session, case, _ = casework_db
    with Session() as db:
        out = casework_tools.casework(db, case, search="when did the phone enter the truck")
    assert _titles(out) == ["answer", "second", "newest"]
    assert out["total_matching"] == 3 and "best match first" in out["coverage"]


def test_search_pages_keep_the_search_order(casework_db):
    from services.agent import casework_tools
    Session, case, _ = casework_db
    with Session() as db:
        first = casework_tools.casework(db, case, search="phone", limit=2)
        rest = casework_tools.casework(db, case, search="phone", offset=first["next_offset"], limit=2)
    assert _titles(first) == ["answer", "second"] and first["next_offset"] == 2
    assert _titles(rest) == ["newest"] and rest["next_offset"] is None


def test_a_kind_filter_keeps_the_search_order(casework_db):
    from services.agent import casework_tools
    Session, case, _ = casework_db
    with Session() as db:
        out = casework_tools.casework(db, case, kinds=("theory",), search="phone")
    assert _titles(out) == ["second", "newest"]


def test_without_words_casework_stays_newest_first(casework_db):
    from services.agent import casework_tools
    Session, case, _ = casework_db
    with Session() as db:
        out = casework_tools.casework(db, case)
    assert _titles(out) == ["newest", "second", "answer"]
