"""Deleted items (lx-casebin): a deleted case or evidence file is hidden everywhere, can be restored exactly, and is
purged with the old delete after 30 days.

Opt-in like the other PostgreSQL tests: ``LOUPE_TEST_PHONE_PG_TEMPLATE_URL`` (a database at the alembic head; each
test gets a throwaway copy). The graph tests also need ``LOUPE_TEST_NEO4J_URI`` (+ ``LOUPE_TEST_NEO4J_PASSWORD``), a
scratch Neo4j 5.26+ with APOC, which they empty. ChromaDB is replaced by an in-memory collection with the same
get/update/delete calls.
"""
from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tests import phone_pg

NEO4J_URI = os.getenv("LOUPE_TEST_NEO4J_URI")
needs_graph = pytest.mark.skipif(not (phone_pg.TEMPLATE_URL and NEO4J_URI),
                                 reason="Requires LOUPE_TEST_PHONE_PG_TEMPLATE_URL and LOUPE_TEST_NEO4J_URI "
                                        "(scratch Neo4j 5.26+ with APOC)")

COUNTED = ("case_memberships", "evidence_files", "financial_accounts", "financial_statement_periods",
           "financial_transactions", "adjudications", "financial_judgements", "phone_extractions",
           "phone_comm_events", "workspace_entries")


# ------------------------------------------------------------------------------------------------------- fixtures


def _seed(engine):
    """A case with an owner, two evidence files, an account with three ledger rows and one phone report."""
    from sqlalchemy import text
    from tests.test_pattern_u10_money import ledger, txn
    with engine.begin() as c:
        case = phone_pg.make_case(c)
        ids = ledger(c, case)
        for row in range(3):
            txn(c, case, ids, row, tdate="2026-01-0%d" % (row + 1))
        c.execute(text("INSERT INTO evidence_files (id, case_id, original_filename, stored_path, sha256) "
                       "VALUES (:i, :c, 'notes.pdf', '/nowhere/notes.pdf', :h)"),
                  {"i": uuid.uuid4(), "c": case, "h": "b" * 64})
        phone_pg.make_extraction(c, case, [])
        owner = c.execute(text("SELECT owner_user_id FROM cases WHERE id = :c"), {"c": case}).scalar_one()
    return case, owner, ids


def _user(engine, user_id, *, admin=False):
    from sqlalchemy.orm import Session
    from postgres.models.enums import GlobalRole
    from postgres.models.user import User
    with Session(engine) as s:
        user = s.get(User, user_id)
        s.expunge(user)
    if admin:
        user.global_role = GlobalRole.super_admin
    return user


def _admin(engine):
    from sqlalchemy import text
    uid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO users (id,email,name,password_hash,global_role,is_active,created_at,updated_at) "
                       "VALUES (:u, :e, 'admin', 'x', 'super_admin', true, now(), now())"),
                  {"u": uid, "e": "a%s@x.test" % uid.hex[:8]})
    return _user(engine, uid)


def _orm_counts(session, case_id):
    """What every screen sees: the counted tables read through the ORM (the deleted-items filter applies)."""
    from sqlalchemy import func, select
    from postgres.base import Base
    import postgres.models  # noqa: F401 - every mapper
    by_table = {m.local_table.name: m.class_ for m in Base.registry.mappers}
    out = {}
    for name in COUNTED:
        cls = by_table.get(name)
        if cls is None:  # phone_comm_events has no ORM model: read by hand-written SQL behind the case check
            continue
        out[name] = session.scalar(select(func.count()).select_from(cls).where(cls.case_id == case_id))
    return out


def _core_counts(engine, case_id):
    """What the database holds, read past the filter."""
    from sqlalchemy import text
    with engine.connect() as c:
        return {name: c.execute(text(f"SELECT count(*) FROM {name} WHERE case_id = :c"), {"c": case_id}).scalar()
                for name in COUNTED}


class FakeCollection:
    """The ChromaDB collection calls the services use: get (ids / where with $and of equalities), update, delete."""

    def __init__(self):
        self.rows = {}

    def add(self, id, metadata):
        self.rows[id] = dict(metadata)

    def _match(self, metadata, where):
        if "$and" in where:
            return all(self._match(metadata, w) for w in where["$and"])
        return all(metadata.get(k) == v for k, v in where.items())

    def get(self, ids=None, where=None, include=None):
        keys = [i for i in (ids if ids is not None else self.rows) if i in self.rows
                and (where is None or self._match(self.rows[i], where))]
        return {"ids": keys, "metadatas": [dict(self.rows[k]) for k in keys]}

    def update(self, ids, metadatas):
        for i, m in zip(ids, metadatas):
            self.rows[i] = dict(m)

    def delete(self, ids):
        for i in ids:
            self.rows.pop(i, None)

    def count(self):
        return len(self.rows)


class FakeVectorDB:
    def __init__(self):
        self.chunk_collection = FakeCollection()
        self.entity_collection = FakeCollection()
        self.calls = []

    def delete_chunks_by_case(self, case_id):
        ids = self.chunk_collection.get(where={"case_id": case_id})["ids"]
        self.chunk_collection.delete(ids)
        self.calls.append(("delete_chunks_by_case", case_id))
        return len(ids)

    def delete_entities_by_case(self, case_id):
        ids = self.entity_collection.get(where={"case_id": case_id})["ids"]
        self.entity_collection.delete(ids)
        self.calls.append(("delete_entities_by_case", case_id))
        return len(ids)

    def delete_chunks_for_document(self, *, case_id, evidence_file_id, doc_key=None, file_name=None):
        from services.evidence_casebin import _document_chunk_ids
        ids = _document_chunk_ids(self, case_id=case_id, file_id=evidence_file_id, doc_key=doc_key,
                                  file_name=file_name)
        self.chunk_collection.delete(ids)
        return len(ids)

    def delete_entity(self, key):
        self.entity_collection.delete([key])

    def searchable_chunks(self, case_id):
        """The chunks search_chunks would return for the case (it skips every state but none, "" and active)."""
        return sorted(i for i, m in self.chunk_collection.rows.items()
                      if m.get("case_id") == case_id and m.get("ingestion_state") in (None, "", "active"))


@contextmanager
def _api(engine, user, *routers):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from postgres.session import get_db
    from routers.auth import get_current_user
    from routers.users import get_current_db_user
    Session = sessionmaker(bind=engine)
    app = FastAPI()
    for router in routers:
        app.include_router(router)

    def db():
        s = Session()
        try:
            yield s
            s.commit()
        finally:
            s.close()
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_db_user] = lambda: user
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user.id), "email": user.email,
                                                          "username": user.email, "name": user.name}
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def _fresh_filter():
    from postgres import soft_delete
    soft_delete.forget()
    yield
    soft_delete.forget()


# ------------------------------------------------------------------------------------------------------ the cases


@phone_pg.needs_template
def test_a_deleted_case_is_hidden_then_restored_with_every_count_identical():
    from sqlalchemy.orm import Session
    from services import case_service
    with phone_pg.fresh_engine() as engine:
        case, owner_id, _ = _seed(engine)
        owner = _user(engine, owner_id)
        with Session(engine) as s:
            before = _orm_counts(s, case)
        held = _core_counts(engine, case)
        assert before == {k: v for k, v in held.items() if k != "phone_comm_events"} and before["financial_transactions"] == 3 and before["evidence_files"] == 2
        assert before["phone_extractions"] == 1 and before["case_memberships"] == 1

        with Session(engine) as s:
            case_service.delete_case(s, case, owner)
        with Session(engine) as s:
            assert _orm_counts(s, case) == {name: 0 for name in COUNTED if name != "phone_comm_events"}
            for who in (owner, _admin(engine)):
                with pytest.raises(case_service.CaseNotFound):
                    case_service.check_case_access(s, case, who, required_permission=("case", "view"))
            assert case_service.list_cases_for_user(s, owner) == []
            [listed] = case_service.list_deleted_cases(s, owner)
            # The listing counts what the delete records (_case_record_counts: mapped tables only).
            assert (listed["id"], listed["days_left"]) == (str(case), 29)
            assert listed["holds"] == {k: v for k, v in held.items() if k != "phone_comm_events"}
        assert _core_counts(engine, case) == held  # nothing removed

        with Session(engine) as s:
            case_service.restore_case(s, case, owner)
        with Session(engine) as s:
            assert _orm_counts(s, case) == before
            assert [c.id for c, _, _ in case_service.list_cases_for_user(s, owner)] == [case]
            assert case_service.list_deleted_cases(s, owner) == []
        assert _core_counts(engine, case) == held

        from sqlalchemy import text
        with engine.connect() as c:
            actions = [r[0] for r in c.execute(text(
                "SELECT action FROM activity_events WHERE case_id = :c ORDER BY at"), {"c": case})]
        assert actions == ["case_deleted", "case_restored"]


@phone_pg.needs_template
def test_only_the_owner_or_an_admin_restores_and_a_member_cannot():
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from services import case_service
    with phone_pg.fresh_engine() as engine:
        case, owner_id, _ = _seed(engine)
        other = uuid.uuid4()
        with engine.begin() as c:
            c.execute(text("INSERT INTO users (id,email,name,password_hash,global_role,is_active,created_at,"
                           "updated_at) VALUES (:u, :e, 'member', 'x', 'user', true, now(), now())"),
                      {"u": other, "e": "m%s@x.test" % other.hex[:8]})
        with Session(engine) as s:
            case_service.delete_case(s, case, _user(engine, owner_id))
        with Session(engine) as s:
            assert case_service.list_deleted_cases(s, _user(engine, other)) == []
            with pytest.raises(case_service.CaseAccessDenied):
                case_service.restore_case(s, case, _user(engine, other))
        with Session(engine) as s:
            case_service.restore_case(s, case, _admin(engine))
            with pytest.raises(case_service.CaseNotDeleted):
                case_service.restore_case(s, case, _admin(engine))


@phone_pg.needs_template
def test_a_deleted_case_is_refused_by_every_surface_and_back_after_restore():
    """Cases list and page, evidence list, search, financial ledger and export, phone reports, agent messages."""
    from routers.agent import router as agent_router
    from routers.cases import router as cases_router
    from routers.evidence import router as evidence_router
    from routers.financial_ledger import router as ledger_router
    from routers.phone_extractions import router as phones_router
    from routers.search import router as search_router
    with phone_pg.fresh_engine() as engine:
        case, owner_id, _ = _seed(engine)
        owner = _user(engine, owner_id)
        title = "synthetic phone test"
        surfaces = [f"/api/cases/{case}", f"/api/evidence?case_id={case}", f"/api/search?case_id={case}&q=notes",
                    f"/api/financial/ledger-accounts?case_id={case}", f"/api/financial/ledger-export?case_id={case}",
                    f"/api/phone-extractions?case_id={case}"]
        with _api(engine, owner, cases_router, evidence_router, search_router, ledger_router, phones_router,
                  agent_router) as api:
            assert [r["id"] for r in api.get("/api/cases").json()["cases"]] == [str(case)]
            ok = {path: api.get(path).status_code for path in surfaces}
            assert ok == {path: 200 for path in surfaces}, ok
            assert api.delete(f"/api/cases/{case}?confirm_title=wrong").status_code == 400
            assert api.get(f"/api/cases/{case}/delete-preview").json()["holds"]["financial_transactions"] == 3
            assert api.delete(f"/api/cases/{case}?confirm_title={title}").status_code == 204

            assert api.get("/api/cases").json()["cases"] == []
            gone = {path: api.get(path).status_code for path in surfaces}
            assert set(gone.values()) <= {403, 404}, gone
            agent = api.post("/api/agent/messages", json={"case_id": str(case), "message": "list the accounts"})
            assert agent.status_code in (403, 404, 422) and agent.status_code != 200
            [row] = api.get("/api/cases/deleted").json()["cases"]
            assert row["title"] == title and row["deleted_by"]["id"] == str(owner_id)

            assert api.post(f"/api/cases/{case}/restore").status_code == 200
            back = {path: api.get(path).status_code for path in surfaces}
            assert back == ok, back


@phone_pg.needs_template
def test_the_purge_waits_30_days_then_removes_exactly_what_the_old_delete_removed():
    from sqlalchemy import text
    from sqlalchemy.orm import Session, sessionmaker
    from services import case_service, casebin_purge
    with phone_pg.fresh_engine() as engine:
        case, owner_id, _ = _seed(engine)
        keep, _, _ = _seed(engine)  # another case, untouched
        kept = _core_counts(engine, keep)
        with Session(engine) as s:
            case_service.delete_case(s, case, _user(engine, owner_id))
        with engine.connect() as c:
            deleted_at = c.execute(text("SELECT deleted_at FROM cases WHERE id = :c"), {"c": case}).scalar()
        fake = FakeVectorDB()
        factory = sessionmaker(bind=engine)
        with patch("services.vector_db_service.vector_db_service", fake):
            early = casebin_purge.purge_due(factory, now=deleted_at + timedelta(days=29, hours=23))
            assert early["cases"] == [] and _core_counts(engine, case)["financial_transactions"] == 3
            done = casebin_purge.purge_due(factory, now=deleted_at + timedelta(days=30, minutes=1))
        assert [c["case_id"] for c in done["cases"]] == [str(case)]
        assert fake.calls == [("delete_chunks_by_case", str(case)), ("delete_entities_by_case", str(case))]
        # The old delete: the case row and its cascade. No row of any table pointing at the case is left.
        with engine.connect() as c:
            tables = [r[0] for r in c.execute(text(
                "SELECT DISTINCT conrelid::regclass::text FROM pg_constraint WHERE contype = 'f' "
                "AND confrelid = 'cases'::regclass"))]
            left = {t: c.execute(text(f'SELECT count(*) FROM {t} WHERE case_id = :c'), {"c": case}).scalar()
                    for t in tables if t != "cases"}
            assert c.execute(text("SELECT count(*) FROM cases WHERE id = :c"), {"c": case}).scalar() == 0
            purged = c.execute(text("SELECT details FROM activity_events WHERE action = 'case_purged' "
                                    "AND case_id = :c"), {"c": case}).scalar()
        assert {t: n for t, n in left.items() if n} == {}
        assert purged["records_removed"]["financial_transactions"] == 3
        assert _core_counts(engine, keep) == kept


@phone_pg.needs_template
def test_the_filter_reads_deleted_ids_once_and_adds_nothing_when_nothing_is_deleted():
    from sqlalchemy import event, select
    from sqlalchemy.orm import Session
    from postgres.models.financial import FinancialTransaction as T
    with phone_pg.fresh_engine() as engine:
        case, _, _ = _seed(engine)
        seen = []
        event.listen(engine, "before_cursor_execute", lambda *a: seen.append(a[2]))
        with Session(engine) as s:
            for _ in range(3):
                s.execute(select(T.id).where(T.case_id == case)).all()
        lookups = [q for q in seen if "deleted_at IS NOT NULL" in q]
        ledger = [q for q in seen if "FROM financial_transactions" in q]
        assert len(lookups) == 1 and len(ledger) == 3
        assert all("NOT IN" not in q and "deleted_case" not in q for q in ledger)


# ------------------------------------------------------------------------------------------------ evidence files


@contextmanager
def _graph():
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(NEO4J_URI, auth=("neo4j", os.getenv("LOUPE_TEST_NEO4J_PASSWORD", "")))
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
    try:
        with driver.session() as s:
            yield driver, s
    finally:
        with driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")
        driver.close()


def _graph_snapshot(session, case_id):
    """Every node of the case (labels + properties) and every relationship touching it, comparable as sets."""
    nodes = session.run("MATCH (n {case_id: $c}) RETURN n.key AS key, labels(n) AS labels, properties(n) AS props",
                        c=case_id).data()
    rels = session.run("MATCH (a {case_id: $c})-[r]->(b) RETURN a.key AS a, type(r) AS t, b.key AS b, "
                       "properties(r) AS props", c=case_id).data()
    return (sorted((n["key"], tuple(sorted(n["labels"])), tuple(sorted(n["props"].items()))) for n in nodes),
            sorted((r["a"], r["t"], r["b"], tuple(sorted(r["props"].items()))) for r in rels))


def _seed_graph(session, case_id, file_name, other_name):
    session.run(
        "CREATE (d:Document {key: $d, name: $dn, case_id: $c}), (o:Document {key: $o, name: $on, case_id: $c}), "
        "(only:Person {key: 'p-only', name: 'Only Here', case_id: $c, born: date('1980-02-03')}), "
        "(shared:Organisation {key: 'o-shared', name: 'Shared Ltd', case_id: $c}), "
        "(only)-[:MENTIONED_IN {case_id: $c, page: 2}]->(d), (shared)-[:MENTIONED_IN {case_id: $c}]->(d), "
        "(shared)-[:MENTIONED_IN {case_id: $c}]->(o), (only)-[:WORKS_FOR {case_id: $c, since: 2019}]->(shared), "
        "(only)-[:WORKS_FOR {case_id: $c, since: 2021}]->(shared)",
        d="doc-" + file_name, dn=file_name, o="doc-" + other_name, on=other_name, c=case_id)


def _seed_chunks(fake, case_id, file_id, other_id):
    for i in range(3):
        fake.chunk_collection.add(f"{file_id}_chunk_{i}", {"case_id": case_id, "evidence_file_id": str(file_id),
                                                            **({"ingestion_state": "active"} if i else {})})
    fake.chunk_collection.add(f"{other_id}_chunk_0", {"case_id": case_id, "evidence_file_id": str(other_id)})
    fake.entity_collection.add("p-only", {"case_id": case_id})
    fake.entity_collection.add("o-shared", {"case_id": case_id})


@needs_graph
def test_a_deleted_file_is_hidden_everywhere_and_restored_exactly():
    from sqlalchemy import select, text
    from sqlalchemy.orm import Session
    from postgres.models.evidence import EvidenceFile
    from services import evidence_casebin
    with phone_pg.fresh_engine() as engine, _graph() as (_, gs):
        case, owner_id, ids = _seed(engine)
        owner = _user(engine, owner_id)
        with engine.connect() as c:
            other = c.execute(text("SELECT id FROM evidence_files WHERE case_id = :c AND original_filename = "
                                   "'notes.pdf'"), {"c": case}).scalar()
        cid = str(case)
        _seed_graph(gs, cid, "synthetic.pdf", "notes.pdf")
        fake = FakeVectorDB()
        _seed_chunks(fake, cid, ids["file"], other)
        graph_before, chunks_before = _graph_snapshot(gs, cid), dict(fake.chunk_collection.rows)
        counts_before = evidence_casebin.case_graph_counts(gs, cid)

        with Session(engine) as s:
            record = s.get(EvidenceFile, ids["file"])
            out = evidence_casebin.delete_file(s, record, owner, graph_session=gs, vector_db=fake)
        assert (out["hidden_graph_nodes"], out["hidden_chunks"]) == (2, 3)  # the Document and 'Only Here'
        nodes, _ = _graph_snapshot(gs, cid)
        assert sorted(n[0] for n in nodes) == ["doc-notes.pdf", "o-shared"]
        assert gs.run("MATCH (n:Document {case_id: $c}) RETURN count(n) AS k", c=cid).single()["k"] == 1
        assert fake.searchable_chunks(cid) == [f"{other}_chunk_0"]
        with Session(engine) as s:
            assert s.get(EvidenceFile, ids["file"]) is None
            assert [f.original_filename for f in s.scalars(select(EvidenceFile).where(EvidenceFile.case_id == case))] \
                == ["notes.pdf"]
            [listed] = evidence_casebin.list_deleted(s, case)
            assert (listed["filename"], listed["days_left"], listed["holds"]["text_chunks"]) == ("synthetic.pdf", 29, 3)

        from routers.evidence import router as evidence_router
        with _api(engine, owner, evidence_router) as api:
            listed = [f["original_filename"] for f in api.get(f"/api/evidence?case_id={case}").json()["files"]]
            assert listed == ["notes.pdf"]
            assert api.get(f"/api/evidence/{ids['file']}").status_code == 404
            [shown] = api.get(f"/api/evidence/deleted?case_id={case}").json()["files"]
            assert shown["filename"] == "synthetic.pdf"
        with Session(engine) as s:
            back = evidence_casebin.restore_file(s, case, str(ids["file"]), owner, graph_session=gs, vector_db=fake)
        assert back["merged_entities"] == []
        with _api(engine, owner, evidence_router) as api:
            listed = sorted(f["original_filename"] for f in api.get(f"/api/evidence?case_id={case}").json()["files"])
            assert listed == ["notes.pdf", "synthetic.pdf"]
        assert _graph_snapshot(gs, cid) == (graph_before[0], graph_before[1])
        assert evidence_casebin.case_graph_counts(gs, cid) == counts_before
        restored = dict(fake.chunk_collection.rows)
        # A chunk that had no state comes back "active" (search reads both the same way); the rest are identical.
        assert restored.pop(f"{ids['file']}_chunk_0") == dict(chunks_before.pop(f"{ids['file']}_chunk_0"),
                                                              ingestion_state="active")
        assert restored == chunks_before
        with Session(engine) as s:
            assert s.get(EvidenceFile, ids["file"]).deleted_at is None
        assert gs.run("MATCH (n:DeletedItem) RETURN count(n) AS k").single()["k"] == 0
        assert gs.run("MATCH ()-[r]-() WHERE r.casebin_hidden IS NOT NULL RETURN count(r) AS k").single()["k"] == 0


@needs_graph
def test_an_entity_made_again_while_hidden_is_merged_on_restore():
    from sqlalchemy.orm import Session
    from postgres.models.evidence import EvidenceFile
    from services import evidence_casebin
    with phone_pg.fresh_engine() as engine, _graph() as (_, gs):
        case, owner_id, ids = _seed(engine)
        owner = _user(engine, owner_id)
        cid = str(case)
        _seed_graph(gs, cid, "synthetic.pdf", "notes.pdf")
        with Session(engine) as s:
            evidence_casebin.delete_file(s, s.get(EvidenceFile, ids["file"]), owner, graph_session=gs,
                                         vector_db=FakeVectorDB())
        gs.run("CREATE (:Person {key: 'p-only', name: 'Only Here (new)', case_id: $c})", c=cid)
        with Session(engine) as s:
            back = evidence_casebin.restore_file(s, case, str(ids["file"]), owner, graph_session=gs,
                                                 vector_db=FakeVectorDB())
        assert back["merged_entities"] == ["p-only"]
        row = gs.run("MATCH (p {case_id: $c, key: 'p-only'}) OPTIONAL MATCH (p)-[r]-() "
                     "RETURN count(DISTINCT p) AS n, count(DISTINCT r) AS rels, collect(DISTINCT p.name) AS names",
                     c=cid).single()
        assert (row["n"], row["rels"], row["names"]) == (1, 3, ["Only Here (new)"])


@needs_graph
def test_a_file_purge_after_30_days_does_what_the_old_delete_did(tmp_path):
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from postgres.models.evidence import EvidenceFile
    from postgres.models.graph_recycle_bin import GraphRecycleBinItem
    from services import casebin_purge, evidence_casebin
    with phone_pg.fresh_engine() as engine, _graph() as (driver, gs):
        case, owner_id, ids = _seed(engine)
        owner = _user(engine, owner_id)
        cid = str(case)
        stored = tmp_path / "synthetic.pdf"
        stored.write_bytes(b"%PDF-1.4 synthetic")
        with engine.begin() as c:
            c.execute(text("UPDATE evidence_files SET stored_path = :p WHERE id = :i"), {"p": str(stored), "i": ids["file"]})
        _seed_graph(gs, cid, "synthetic.pdf", "notes.pdf")
        fake = FakeVectorDB()
        _seed_chunks(fake, cid, ids["file"], uuid.uuid4())
        with Session(engine) as s:
            evidence_casebin.delete_file(s, s.get(EvidenceFile, ids["file"]), owner, graph_session=gs, vector_db=fake)
        assert stored.exists()
        with patch("services.neo4j.entity_service.driver", driver), \
                patch("services.neo4j.document_service.driver", driver), \
                patch("services.evidence_casebin._vector_db", lambda: fake), \
                patch("routers.evidence._resolve_stored_path", lambda p: None):
            with Session(engine) as s:
                details = casebin_purge.purge_file(s, ids["file"], graph_session=gs, vector_db=fake,
                                                   engine_delete=lambda *a: None)
        assert details["document_deleted"] and details["file_deleted"] and not stored.exists()
        assert [e["key"] for e in details["exclusive_entities_recycled"]] == ["p-only"]
        nodes, _ = _graph_snapshot(gs, cid)
        assert sorted(n[0] for n in nodes) == ["doc-notes.pdf", "o-shared"]
        assert "p-only" not in fake.entity_collection.rows
        assert [i for i in fake.chunk_collection.rows if i.startswith(str(ids["file"]))] == []
        with Session(engine) as s:
            assert s.query(GraphRecycleBinItem).filter_by(original_key="p-only", status="active").count() == 1
        with engine.connect() as c:
            assert c.execute(text("SELECT count(*) FROM evidence_files WHERE id = :i"), {"i": ids["file"]}).scalar() == 0
            assert c.execute(text("SELECT count(*) FROM activity_events WHERE action = 'evidence_purged'")).scalar() == 1


@phone_pg.needs_template
def test_a_live_file_linked_to_a_deleted_one_by_a_set_null_key_stays_visible():
    """duplicate_of_id is ON DELETE SET NULL and the upload sets it across cases (same bytes): the old delete left the
    other file in place, so a deleted file must not hide it."""
    from sqlalchemy import select, text
    from sqlalchemy.orm import Session
    from postgres.models.evidence import EvidenceFile
    from services import evidence_casebin
    with phone_pg.fresh_engine() as engine:
        case, owner_id, ids = _seed(engine)
        other_case, _, _ = _seed(engine)
        with engine.begin() as c:
            copy = c.execute(text("SELECT id FROM evidence_files WHERE case_id = :c AND original_filename = "
                                  "'notes.pdf'"), {"c": other_case}).scalar()
            c.execute(text("UPDATE evidence_files SET duplicate_of_id = :d WHERE id = :i"),
                      {"d": ids["file"], "i": copy})
        with Session(engine) as s:
            evidence_casebin.delete_file(s, s.get(EvidenceFile, ids["file"]), _user(engine, owner_id),
                                         graph_session=_NoGraph(), vector_db=FakeVectorDB())
        with Session(engine) as s:
            assert s.get(EvidenceFile, ids["file"]) is None
            assert s.get(EvidenceFile, copy) is not None
            assert sorted(f.original_filename for f in s.scalars(
                select(EvidenceFile).where(EvidenceFile.case_id == other_case))) == ["notes.pdf", "synthetic.pdf"]


class _NoGraph:
    """A graph session for files with no Document node (every query finds nothing)."""

    def close(self):
        pass

    def run(self, *a, **k):
        class _R:
            def single(self):
                return None

            def __iter__(self):
                return iter(())
        return _R()

    def execute_write(self, work):
        class _Tx:
            def run(self, *a, **k):
                class _R:
                    def single(self):
                        return {"c": 0}

                    def __iter__(self):
                        return iter(())
                return _R()
        return work(_Tx())


@phone_pg.needs_template
def test_a_spreadsheet_whose_payments_count_is_refused_and_a_pdf_one_is_held_as_before():
    """Payments hang off the statement source, not the file, and many ledger reads are hand-written SQL: a non-PDF
    file whose payments count cannot go to Deleted items (it has no Remove imports path); the PDF hold is unchanged."""
    from sqlalchemy import text
    from routers.evidence import router as evidence_router
    with phone_pg.fresh_engine() as engine:
        case, owner_id, ids = _seed(engine)
        owner = _user(engine, owner_id)
        with engine.begin() as c:
            c.execute(text("UPDATE evidence_files SET original_filename = 'statement.csv' WHERE id = :i"),
                      {"i": ids["file"]})
        with _api(engine, owner, evidence_router) as api:
            refused = api.delete(f"/api/evidence/{ids['file']}?case_id={case}")
            assert refused.status_code == 409
            assert "3 payments read from it still count" in refused.json()["detail"]
        with engine.connect() as c:
            assert c.execute(text("SELECT deleted_at FROM evidence_files WHERE id = :i"),
                             {"i": ids["file"]}).scalar() is None
        with engine.begin() as c:
            c.execute(text("UPDATE financial_transactions SET ledger_status = 'rejected' WHERE source_document_id = :d"),
                      {"d": ids["doc"]})
        with patch("services.evidence_casebin._graph_session", lambda: _NoGraph()), \
                patch("services.evidence_casebin._vector_db", lambda: FakeVectorDB()), \
                _api(engine, owner, evidence_router) as api:
            done = api.delete(f"/api/evidence/{ids['file']}?case_id={case}")
            assert done.status_code == 200, done.text


@needs_graph
def test_a_file_purge_leaves_a_live_file_of_the_same_name_untouched(tmp_path):
    """Deleted 'synthetic.pdf', then a corrected 'synthetic.pdf' uploaded: 30 days later the purge removes only what
    the delete hid. The old delete looked up the Document and chunks by filename and took the live file's too."""
    from sqlalchemy.orm import Session
    from postgres.models.evidence import EvidenceFile
    from services import casebin_purge, evidence_casebin
    with phone_pg.fresh_engine() as engine, _graph() as (driver, gs):
        case, owner_id, ids = _seed(engine)
        owner = _user(engine, owner_id)
        cid = str(case)
        _seed_graph(gs, cid, "synthetic.pdf", "notes.pdf")
        fake = FakeVectorDB()
        _seed_chunks(fake, cid, ids["file"], uuid.uuid4())
        with Session(engine) as s:
            evidence_casebin.delete_file(s, s.get(EvidenceFile, ids["file"]), owner, graph_session=gs, vector_db=fake)
        # The corrected upload: a live Document with the same name and key, its own entity and chunk.
        new_file = uuid.uuid4()
        gs.run("CREATE (d:Document {key: 'doc-synthetic.pdf', name: 'synthetic.pdf', case_id: $c, version: 2}), "
               "(p:Person {key: 'p-only', name: 'Only Here', case_id: $c, version: 2}), "
               "(p)-[:MENTIONED_IN {case_id: $c}]->(d)", c=cid)
        fake.chunk_collection.add(f"{new_file}_chunk_0", {"case_id": cid, "evidence_file_id": str(new_file),
                                                          "file_name": "synthetic.pdf", "doc_id": "synthetic.pdf"})
        with patch("services.neo4j.entity_service.driver", driver), \
                patch("services.neo4j.document_service.driver", driver), \
                patch("services.evidence_casebin._vector_db", lambda: fake), \
                patch("routers.evidence._resolve_stored_path", lambda p: None):
            with Session(engine) as s:
                details = casebin_purge.purge_file(s, ids["file"], graph_session=gs, vector_db=fake,
                                                   engine_delete=lambda *a: None)
        assert details["hidden_copies_removed"] == ["doc-synthetic.pdf", "p-only"]
        live = gs.run("MATCH (n {case_id: $c}) WHERE n.key IN ['doc-synthetic.pdf', 'p-only'] "
                      "RETURN n.key AS key, n.version AS v ORDER BY key", c=cid).data()
        assert live == [{"key": "doc-synthetic.pdf", "v": 2}, {"key": "p-only", "v": 2}]
        assert gs.run("MATCH (:Person {key: 'p-only', case_id: $c})-[r:MENTIONED_IN]->() RETURN count(r) AS k",
                      c=cid).single()["k"] == 1
        assert gs.run("MATCH (n:DeletedItem) RETURN count(n) AS k").single()["k"] == 0
        assert f"{new_file}_chunk_0" in fake.chunk_collection.rows
        assert [i for i in fake.chunk_collection.rows if i.startswith(str(ids["file"]))] == []


@phone_pg.needs_template
def test_the_purge_lock_is_released_so_the_next_run_purges():
    """The advisory lock is per connection; taken through a session that commits, it stayed on a pooled connection
    and every later run was skipped as 'another process is purging'."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session, sessionmaker
    from services import case_service, casebin_purge
    with phone_pg.fresh_engine() as engine:
        first, owner_id, _ = _seed(engine)
        second, second_owner, _ = _seed(engine)
        for case, owner in ((first, owner_id), (second, second_owner)):
            with Session(engine) as s:
                case_service.delete_case(s, case, _user(engine, owner))
        factory = sessionmaker(bind=engine)
        with engine.begin() as c:
            c.execute(text("UPDATE cases SET deleted_at = now() - interval '40 days' WHERE id = :c"), {"c": first})
        # A web worker's pool holds several idle connections; a session takes whichever comes next after a commit.
        warm = [engine.connect() for _ in range(4)]
        for c in warm:
            c.close()
        with patch("services.vector_db_service.vector_db_service", FakeVectorDB()):
            done = casebin_purge.purge_due(factory)
            assert [c["case_id"] for c in done["cases"]] == [str(first)] and done["skipped"] is None
            with engine.connect() as c:
                assert c.execute(text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'")).scalar() == 0
            with engine.begin() as c:
                c.execute(text("UPDATE cases SET deleted_at = now() - interval '40 days' WHERE id = :c"),
                          {"c": second})
            again = casebin_purge.purge_due(factory)
        assert again["skipped"] is None and [c["case_id"] for c in again["cases"]] == [str(second)]
