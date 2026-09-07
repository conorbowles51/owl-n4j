"""Create a fresh isolated synthetic PDF with printed headers; no candidate writes."""
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText, EvidenceTableGeometry
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
    path = directory / "synthetic-headers.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=600, height=800)
        for x in (50, 200, 350):
            page.draw_line((x, 50), (x, 170))
        for y in (50, 90, 130, 170):
            page.draw_line((50, y), (350, y))
        for row, (date, amount) in enumerate((("Transaction Date", "Amount"), ("01/02", "1234"), ("03/02", "1234"))):
            page.insert_text((60, 75 + row * 40), date)
            page.insert_text((210, 75 + row * 40), amount)
        content = page.get_text()
        geometry = [t.to_json() for t in read_tables(page, 1)]
        pdf.save(path)
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.email == "loupe-local@example.com"))
        if user is None:
            raise RuntimeError("Initialize the local synthetic user first.")
        session.add(Case(id=case_id, title="LOCAL TEST — printed header suggestions",
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
    report = dict(case_id=str(case_id), evidence_file_id=str(file_id), source_revision=revision)
    (ROOT / "data/local-runtime/header-check.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))
    engine.dispose()

if __name__ == "__main__":
    main()
