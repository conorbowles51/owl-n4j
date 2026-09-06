"""Generate a synthetic ledger/PDF fixture and check its source navigation.

Uses only the isolated local stack. Run with the backend venv and
PYTHON_DOTENV_DISABLED=1. Leaves a labelled case for browser inspection.
"""
import hashlib
import argparse
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


def main(correct_held_out=False):
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
            fixture.case = Case(id=uuid4(), title="LOCAL TEST — ledger PDF source navigation", created_by_user_id=fixture.user.id, owner_user_id=fixture.user.id)
            fixture.db.add(fixture.case)
            fixture.db.commit()
            fixture.account = fixture._account(fixture.case.id)
            fixture.db.add(fixture.account)
            fixture.db.commit()
            fixture.run = open_ingestion_run(case_id=fixture.case.id, actor=fixture.user, session_factory=fixture.SessionLocal)
            fixture._file_index = fixture._row_index = 0
            directory = ROOT / "data/local-runtime/files" / str(fixture.case.id)
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / "synthetic-ledger-source.pdf"
            with pymupdf.open() as pdf:
                page = pdf.new_page(width=612, height=792)
                page.insert_text((72, 72), "SYNTHETIC LOCAL TEST - not evidence", fontsize=16)
                page.insert_text((72, 130), "Credit 400.00 GBP", fontsize=14)
                page.insert_text((72, 170), "Credit 20.00 GBP - held out for this test", fontsize=14)
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
                    "kind": "page_rectangle", "page": 1, "rect": [68000, top, 350000, top + 23000],
                    "page_size": [612000, 792000], "units": "millipoints", "space": "pdf_displayed"}}
            rows[1].ledger_status, rows[1].quarantine_reason = "quarantined", "adjudicated"
            case_id, file_id = str(fixture.case.id), str(evidence.id)
            row_ids = [str(row.id) for row in rows]
            fixture.db.commit()
            for row_id in row_ids:
                answer = client.get(f"/api/financial/ledger/{row_id}/source", params={"case_id": case_id})
                answer.raise_for_status()
                assert answer.json()["evidence_file_id"] == file_id
                assert answer.json()["locator_state"] == "stored"
            image = client.get(f"/api/evidence/{file_id}/page/1/image")
            image.raise_for_status()
            assert image.headers["content-type"].startswith("image/png")
            assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
            original = client.get(f"/api/evidence/{file_id}/file")
            original.raise_for_status()
            assert hashlib.sha256(original.content).hexdigest() == digest
            source_path = f"/api/financial/source-files/{file_id}"
            text = client.get(source_path + "/text", params={"case_id": case_id})
            text.raise_for_status()
            assert text.json()["content"] == content
            start = content.index("400.00")
            assessment = client.post(source_path + "/amount-assessment", params={"case_id": case_id}, json={
                "start_char": start, "end_char": start + 6, "expected_text": "400.00",
                "content_sha256": text_digest, "currency": "GBP"})
            assessment.raise_for_status()
            assert assessment.json()["assessment"]["minor_units"] == "40000"
            assert assessment.json()["applied"] is False
            summary = {"case_id": case_id, "evidence_file_id": file_id, "admitted_row": row_ids[0], "held_out_row": row_ids[1]}
            if correct_held_out:
                route = f"/api/financial/transactions/{row_ids[1]}"
                proposal = {"amount_minor": "2100", "direction": "credit"}
                preview = client.post(route + "/correction-preview", params={"case_id": case_id}, json=proposal)
                preview.raise_for_status()
                assert preview.json()["verification"]["can_record"] is True
                correction = client.post(route + "/correction", params={"case_id": case_id}, json={
                    **proposal, "expected_revision": preview.json()["document_revision"],
                    "reason": "Synthetic history navigation test: intentionally edit 20.00 to 21.00; not evidence."})
                correction.raise_for_status()
                new_id = correction.json()["replacement_id"]
                assert correction.json()["ledger_status"] == "quarantined"
                old_source = client.get(f"/api/financial/ledger/{row_ids[1]}/source", params={"case_id": case_id})
                new_source = client.get(f"/api/financial/ledger/{new_id}/source", params={"case_id": case_id})
                old_source.raise_for_status()
                new_source.raise_for_status()
                assert old_source.json()["ledger_status"] == "superseded"
                assert old_source.json()["superseded_by_id"] == new_id
                assert old_source.json()["locator"] == new_source.json()["locator"]
                assert old_source.json()["evidence_file_id"] == new_source.json()["evidence_file_id"] == file_id
                summary["corrected_row"] = new_id
            (ROOT / "data/local-runtime/ledger-source-check.json").write_text(json.dumps(summary, indent=2))
            print("PASS: both ledger source citations, rendered PNG, original PDF bytes and canonical-text assessment.")
            print(json.dumps(summary, indent=2))
    finally:
        fixture.db.close()
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--correct-held-out", action="store_true", help="Also record a synthetic correction for historical source navigation")
    main(correct_held_out=parser.parse_args().correct_held_out)
