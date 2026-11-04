"""Opt-in real PostgreSQL: AI costs per case (BACKLOG FEAT-007).

The cost routes used to check only that someone was signed in, so an ordinary user read every case's cost records
(on live 4 Nov 2026: 107,338 records, all cases). Now costs need an admin, or the case's manager for that case only.
The case report folds the per-call records into one line per document, batch, conversation or kind of work, names the
case, and its line totals equal the case total exactly.
"""
import os
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.skipif(os.getenv("LOUPE_TEST_LOCAL_POSTGRES") != "1",
                                reason="Requires isolated local PostgreSQL")


@pytest.fixture()
def db():
    from postgres.base import Base
    import postgres.models  # noqa: F401  (every table on the metadata)
    url = make_url(os.environ["LOUPE_TEST_LOCAL_POSTGRES_URL"])
    assert url.host in {"127.0.0.1", "localhost"}, "local PostgreSQL only"
    admin = create_engine(url, future=True)
    schema = f"costs_{uuid4().hex[:8]}"
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, future=True, connect_args={"options": f"-csearch_path={schema}"})
    with engine.begin() as conn:  # the migrations create this type; the model does not (create_type=False)
        conn.execute(text("CREATE TYPE cost_job_type AS ENUM ('ingestion', 'ai_assistant', 'entity_merge')"))
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, future=True)()
    yield session
    session.close()
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()


def _world(db):
    from postgres.models.case import Case
    from postgres.models.cost_record import CostRecord
    from postgres.models.enums import GlobalRole
    from postgres.models.evidence import EvidenceFile
    from postgres.models.user import User
    owner = User(id=uuid4(), email=f"o{uuid4().hex[:6]}@x.invalid", name="Owner", password_hash="x",
                 global_role=GlobalRole.user)
    stranger = User(id=uuid4(), email=f"s{uuid4().hex[:6]}@x.invalid", name="Stranger", password_hash="x",
                    global_role=GlobalRole.user)
    boss = User(id=uuid4(), email=f"a{uuid4().hex[:6]}@x.invalid", name="Admin", password_hash="x",
                global_role=GlobalRole.admin)
    db.add_all([owner, stranger, boss])
    db.flush()
    mine = Case(id=uuid4(), title="Smith v. Jones", created_by_user_id=owner.id, owner_user_id=owner.id)
    other = Case(id=uuid4(), title="Other matter", created_by_user_id=stranger.id, owner_user_id=stranger.id)
    db.add_all([mine, other])
    db.flush()
    from postgres.models.case_membership import CaseMembership
    from postgres.models.enums import CaseMembershipRole
    from postgres.permissions import OWNER_PERMISSIONS, clone_permissions
    for case, user in ((mine, owner), (other, stranger)):
        db.add(CaseMembership(case_id=case.id, user_id=user.id, membership_role=CaseMembershipRole.owner,
                              permissions=clone_permissions(OWNER_PERMISSIONS), added_by_user_id=user.id))
    statement = EvidenceFile(id=uuid4(), case_id=mine.id, original_filename="bank-march.pdf",
                             stored_path="/tmp/x.pdf", size=1, sha256="a" * 64, status="processed")
    db.add(statement)
    db.flush()

    def cost(case, value, **kw):
        db.add(CostRecord(id=uuid4(), case_id=case.id, provider="openai", model_id=kw.pop("model", "gpt-4o"),
                          cost_usd=Decimal(value), total_tokens=100, **kw))
    for value in ("0.010000", "0.020000", "0.003000"):
        cost(mine, value, job_type="ingestion", evidence_file_id=statement.id, operation_kind="chat_completion",
             description="Evidence ingestion: bank-march.pdf")
    for value in ("0.100000", "0.200000"):
        cost(mine, value, job_type="ingestion", operation_kind="chat_completion",
             description="Evidence ingestion: None-named.pdf")
    for value in ("0.050000", "0.050000"):
        cost(mine, value, job_type="ingestion", operation_kind="embedding", description="Evidence ingestion batch b",
             extra_metadata={"batch_id": "1b2c3d4e-0000-0000-0000-000000000000", "batch_size": 3},
             model="text-embedding-3-small")
    cost(mine, "0.400000", job_type="ai_assistant", operation_kind="chat_completion",
         extra_metadata={"conversation_id": "c0ffee00-1111-2222-3333-444455556666"})
    cost(mine, "0.700000", job_type="entity_merge", operation_kind="chat_completion")
    cost(other, "9.000000", job_type="ingestion", operation_kind="chat_completion", description="Evidence ingestion: secret.pdf")
    db.commit()
    return owner, stranger, boss, mine, other


def test_the_report_has_one_line_per_document_names_the_case_and_adds_up(db):
    from services.case_cost_report import case_cost_report, cost_report_html
    owner, stranger, boss, mine, other = _world(db)
    report = case_cost_report(db, mine.id)
    lines = {line["label"]: line for line in report["lines"]}
    assert report["case_title"] == "Smith v. Jones"
    assert report["line_count"] == 5 and report["call_count"] == 9
    assert lines["bank-march.pdf"]["calls"] == 3 and lines["bank-march.pdf"]["cost_exact"] == "0.033000"
    assert lines["None-named.pdf"]["calls"] == 2
    batch = next(line for label, line in lines.items() if label.startswith("Documents read together"))
    assert batch["calls"] == 2 and batch["models"] == ["text-embedding-3-small"]
    assert lines["Entity merges"]["cost_exact"] == "0.700000"
    assert Decimal(report["total_cost_exact"]) == sum(Decimal(line["cost_exact"]) for line in report["lines"])
    assert Decimal(report["total_cost_exact"]) == Decimal("1.533")
    assert "secret.pdf" not in str(report)
    page = cost_report_html(report)
    assert page.count("<td>Smith v. Jones</td>") == 5 and "$1.53" in page


def test_costs_are_refused_to_anyone_who_does_not_manage_the_case(db):
    from routers.cost_ledger import get_case_cost_report, get_cost_ledger, get_cost_summary
    owner, stranger, boss, mine, other = _world(db)
    plain = dict(job_type=None, model_id=None, time_period=None, start_date=None, end_date=None)
    # Old code answered this with every case's records, the other case's 9.00 included.
    with pytest.raises(HTTPException) as refused:
        get_cost_ledger(case_id=None, limit=100, offset=0, db=db, user=owner, **plain)
    assert refused.value.status_code == 403
    with pytest.raises(HTTPException) as refused:
        get_cost_summary(case_id=None, db=db, user=owner, **plain)
    assert refused.value.status_code == 403
    with pytest.raises(HTTPException) as refused:
        get_cost_ledger(case_id=str(other.id), limit=100, offset=0, db=db, user=owner, **plain)
    assert refused.value.status_code == 403
    own = get_cost_ledger(case_id=str(mine.id), limit=100, offset=0, db=db, user=owner, **plain)
    assert own.total == 9 and {r.case_id for r in own.records} == {str(mine.id)}
    assert get_cost_ledger(case_id=None, limit=100, offset=0, db=db, user=boss, **plain).total == 10
    with pytest.raises(HTTPException) as refused:
        get_case_cost_report(case_id=mine.id, start_date=None, end_date=None, db=db, user=stranger)
    assert refused.value.status_code == 403
    assert get_case_cost_report(case_id=mine.id, start_date=None, end_date=None, db=db, user=owner)["line_count"] == 5


def test_the_pdf_is_a_pdf_and_too_long_a_report_is_refused_not_cut(db, monkeypatch):
    pytest.importorskip("weasyprint")
    import services.case_cost_report as costs
    owner, stranger, boss, mine, other = _world(db)
    report = costs.case_cost_report(db, mine.id)
    assert costs.cost_report_pdf(report).startswith(b"%PDF")
    monkeypatch.setattr(costs, "MAX_PDF_LINES", 4)
    with pytest.raises(costs.CostReportError, match="no partial PDF"):
        costs.cost_report_pdf(report)
