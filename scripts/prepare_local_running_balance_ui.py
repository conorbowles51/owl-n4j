"""Generate a synthetic ledger/PDF fixture and check its source navigation.

Uses only the isolated local stack. Run with the backend venv and
PYTHON_DOTENV_DISABLED=1. Leaves a labelled case for browser inspection.
"""
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from tests.test_financial_duplicates import DuplicateTestCase, printed
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText
from postgres.models.financial import FinancialTransaction
from services.financial.runs import open_ingestion_run
from services.financial.transactions import LOCATOR_PROVENANCE_KEY


def main():
    engine = create_engine("postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local")
    fixture = DuplicateTestCase()
    fixture.SessionLocal = sessionmaker(bind=engine, autoflush=False)
    fixture.db = fixture.SessionLocal()
    try:
        with httpx.Client(base_url="http://127.0.0.1:58002", timeout=30) as client:
            login = client.post("/api/auth/login", json={"username": "loupe-local@example.com", "password": "Loupe-local-test-2026"})
            login.raise_for_status()
            client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
            fixture.user = fixture.db.scalar(select(User).where(User.email == "loupe-local@example.com"))
            fixture.case = Case(id=uuid4(), title="LOCAL TEST — running balance correction", created_by_user_id=fixture.user.id, owner_user_id=fixture.user.id)
            fixture.db.add(fixture.case)
            fixture.db.commit()
            fixture.account = fixture._account(fixture.case.id)
            fixture.db.add(fixture.account)
            fixture.db.commit()
            fixture.run = open_ingestion_run(case_id=fixture.case.id, actor=fixture.user, session_factory=fixture.SessionLocal)
            fixture._file_index = fixture._row_index = 0
            directory = ROOT / "data/local-runtime/files" / str(fixture.case.id)
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "synthetic-running-balances.pdf"
            with pymupdf.open() as pdf:
                page = pdf.new_page(width=612, height=792)
                page.insert_text((72, 72), "SYNTHETIC LOCAL TEST - not evidence", fontsize=16)
                page.insert_text((72, 98), "Opening balance 0.00 GBP", fontsize=14)
                page.insert_text((72, 130), "Credit 400.00 GBP | balance 400.00 GBP", fontsize=14)
                page.insert_text((72, 170), "Credit 20.00 GBP | balance 420.00 GBP", fontsize=14)
                pdf.save(path)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            document = fixture.make_copy(sha256=digest, opening=printed(0), closing=printed(42000))
            document.page_count = 1
            document.metadata_ = {**(document.metadata_ or {}), "source_shape": "statement_document"}
            evidence = fixture.db.get(EvidenceFile, document.evidence_file_id)
            evidence.stored_path, evidence.original_filename = str(path), path.name
            evidence.sha256, evidence.size, evidence.status = digest, path.stat().st_size, "processed"
            with pymupdf.open(path) as pdf:
                content = pdf[0].get_text()
            text_digest = hashlib.sha256(content.encode()).hexdigest()
            fixture.db.add(EvidenceDocumentText(evidence_file_id=evidence.id, content=content,
                content_sha256=text_digest, character_count=len(content), source_locations=[{
                    "kind": "page", "page_number": 1, "start_char": 0, "end_char": len(content),
                    "text_origin": "digital_text_layer"}]))
            rows = list(fixture.db.scalars(select(FinancialTransaction).where(FinancialTransaction.source_document_id == document.id).order_by(FinancialTransaction.amount_minor.desc())))
            for row, top in zip(rows, (112000, 152000)):
                row.provenance = {**(row.provenance or {}), LOCATOR_PROVENANCE_KEY: {
                    "kind": "page_rectangle", "page": 1, "rect": [68000, top, 530000, top + 23000],
                    "page_size": [612000, 792000], "units": "millipoints", "space": "pdf_displayed"}}
            rows[0].running_balance_minor, rows[1].running_balance_minor = 40000, 42000
            case_id, file_id = str(fixture.case.id), str(evidence.id)
            row_ids = [str(row.id) for row in rows]
            fixture.db.commit()
            summary = dict(case_id=case_id, evidence_file_id=file_id, transaction_id=row_ids[0], ref_id=rows[0].ref_id)
            (ROOT / "data/local-runtime/running-balance-check.json").write_text(json.dumps(summary, indent=2))
            print(json.dumps(summary))
    finally:
        fixture.db.close()
        engine.dispose()

if __name__ == "__main__":
    main()
