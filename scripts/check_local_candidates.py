"""Synthetic PostgreSQL check for atomic, immutable candidate originals.

Uses only the hardcoded isolated local database. Leaves a labelled synthetic case.
Run with data/local-runtime/backend-venv/bin/python and PYTHON_DOTENV_DISABLED=1.
"""
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
from postgres.models.financial import FinancialTransaction
from postgres.models.financial_candidates import FinancialCandidateMapping, FinancialExtractionCandidate
from services.financial.candidate_store import read_candidate_mapping, store_pdf_candidates
from services.financial.decisions import Actor
from services.financial.pdf_geometry_candidates import pdf_grid_source_revision
from services.financial.pdf_tables import read_tables


def main():
    import pymupdf
    application = "loupe-candidate-check-" + uuid4().hex[:12]
    engine = create_engine("postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local",
                           connect_args={"application_name": application})
    case_id, file_id, job = uuid4(), uuid4(), uuid4()
    directory = ROOT / "data/local-runtime/files" / str(case_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "synthetic-candidates.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=600, height=800)
        for x in (50, 200, 350):
            page.draw_line((x, 50), (x, 130))
        for y in (50, 90, 130):
            page.draw_line((50, y), (350, y))
        for row, date in enumerate(("01/02", "03/02")):
            page.insert_text((60, 75 + row * 40), date)
            page.insert_text((210, 75 + row * 40), "1234")
        content = page.get_text()
        geometry = [t.to_json() for t in read_tables(page, 1)]
        pdf.save(path)
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.email == "loupe-local@example.com"))
        if user is None:
            raise RuntimeError("Initialize the local synthetic user first.")
        actor = Actor(user.name, user.email, user.id)
        session.add(Case(id=case_id, title="LOCAL TEST — pending PDF candidate originals",
                         created_by_user_id=user.id, owner_user_id=user.id))
        session.commit()
        session.add(EvidenceFile(id=file_id, case_id=case_id, original_filename=path.name,
            stored_path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            size=path.stat().st_size, status="processed"))
        session.commit()
        session.add(EvidenceDocumentText(evidence_file_id=file_id, engine_job_id=job, content=content,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(), character_count=len(content),
            source_locations=[dict(kind="page", page_number=1, start_char=0, end_char=len(content),
                                   text_origin="digital_text_layer")]))
        session.add(EvidenceTableGeometry(evidence_file_id=file_id, page_number=1, engine_job_id=job, payload=geometry))
        session.commit()
        revision = pdf_grid_source_revision(session, case_id=case_id, evidence_file_id=file_id, page_number=1)
    proposal = dict(schema_version="pdf-grid-mapping-v1", case_id=str(case_id), evidence_file_id=str(file_id),
        source_revision=revision, page_number=1, table_index=0,
        columns=[dict(column_index=0, meaning="booking_date"), dict(column_index=1, meaning="amount")],
        rows=[dict(row_index=row, cells=[dict(column_index=0, expected_text=date),
              dict(column_index=1, expected_text="1234")]) for row, date in enumerate(("01/02", "03/02"))])

    def save():
        with Session(engine) as session:
            return store_pdf_candidates(session, case_id=case_id, proposal=proposal, actor=actor)

    # Prove actual contention, rather than relying on threads happening to race.
    with Session(engine) as blocker, ThreadPoolExecutor(max_workers=2) as pool:
        blocker.execute(select(EvidenceFile.id).where(EvidenceFile.id == file_id).with_for_update()).all()
        futures = [pool.submit(save) for _ in range(2)]
        try:
            deadline = time.monotonic() + 10
            waiting = 0
            while waiting < 2 and time.monotonic() < deadline:
                with engine.connect() as observer:
                    waiting = observer.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE application_name=:app AND wait_event_type='Lock'"), {"app": application})
                if waiting < 2:
                    time.sleep(0.05)
            if waiting != 2:
                raise AssertionError("Both candidate saves did not reach the source lock.")
        finally:
            blocker.rollback()
        results = [future.result(timeout=30) for future in futures]
    assert sorted(r["created"] for r in results) == [False, True]
    assert results[0]["id"] == results[1]["id"]
    mapping_id = UUID(results[0]["id"])
    with Session(engine) as session:
        loaded = read_candidate_mapping(session, case_id=case_id, mapping_id=mapping_id)
        assert len(loaded["candidates"]) == 2
        assert session.scalar(select(func.count()).select_from(FinancialCandidateMapping).where(FinancialCandidateMapping.case_id == case_id)) == 1
        assert session.scalar(select(func.count()).select_from(FinancialTransaction).where(FinancialTransaction.case_id == case_id)) == 0
    for model, identifier in ((FinancialCandidateMapping, mapping_id),
                              (FinancialExtractionCandidate, UUID(loaded["candidates"][0]["id"]))):
        try:
            with engine.begin() as connection:
                connection.execute(update(model).where(model.id == identifier).values(snapshot={"changed": True}))
        except DBAPIError as exc:
            assert "Extraction originals are immutable" in str(exc.orig)
        else:
            raise AssertionError("PostgreSQL allowed an original snapshot to change.")
    summary = dict(case_id=str(case_id), mapping_id=str(mapping_id), competing_writers=2,
        observed_lock_waiters=waiting, mappings=1, candidates=2, ledger_transactions=0,
        immutable_update_triggers="passed")
    (ROOT / "data/local-runtime/candidate-check.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    engine.dispose()


if __name__ == "__main__":
    main()
