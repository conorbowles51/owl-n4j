"""Check source amount assessment through HTTP against synthetic local data only.

Run with PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python.
Leaves a labelled case and three generated text files for browser inspection.
Neither the database nor HTTP target is configurable.
"""
import hashlib
import json
import sys
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from postgres.models.case import Case
from postgres.models.user import User
from postgres.models.evidence import EvidenceFile, EvidenceDocumentText
from postgres.models.financial import FinancialTransaction, AdjudicationEvent


def main():
    engine = create_engine("postgresql+psycopg://loupe_local:loupe_local_dev@127.0.0.1:55434/loupe_local")
    try:
        with httpx.Client(base_url="http://127.0.0.1:58002", timeout=30) as client, Session(engine) as db:
            login = client.post("/api/auth/login", json={"username": "loupe-local@example.com", "password": "Loupe-local-test-2026"})
            login.raise_for_status()
            client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
            user = db.scalar(select(User).where(User.email == "loupe-local@example.com"))
            case = Case(id=uuid4(), title="LOCAL TEST — source amount assessment", created_by_user_id=user.id, owner_user_id=user.id)
            other = Case(id=uuid4(), title="LOCAL TEST — source isolation", created_by_user_id=user.id, owner_user_id=user.id)
            db.add_all([case, other])
            db.flush()
            ids = {}
            content = "😀\r\nSynthetic amount review\r\nAmount 1234 end\r\n"
            digest = hashlib.sha256(content.encode()).hexdigest()
            directory = ROOT / "data/local-runtime/files" / str(case.id)
            directory.mkdir(parents=True, exist_ok=True)
            for origin in ("digital_text_layer", "recognised_glyphs", "unknown"):
                file_id = uuid4()
                source_path = directory / f"synthetic-{origin}.txt"
                source_path.write_bytes(content.encode())
                db.add(EvidenceFile(id=file_id, case_id=case.id, original_filename=source_path.name,
                                   stored_path=str(source_path), sha256=digest, size=len(content.encode()), status="processed"))
                db.flush()
                locations = [] if origin == "unknown" else [{"kind": "page", "page_number": 1, "start_char": 0, "end_char": len(content), "text_origin": origin}]
                db.add(EvidenceDocumentText(evidence_file_id=file_id, content=content, content_sha256=digest,
                                           character_count=len(content), source_locations=locations))
                ids[origin] = str(file_id)
            case_id, other_id = str(case.id), str(other.id)
            db.commit()
            start = content.index("1234")
            payload = dict(start_char=start, end_char=start + 4, expected_text="1234", content_sha256=digest, currency="USD")
            for origin, file_id in ids.items():
                path = f"/api/financial/source-files/{file_id}"
                window = client.get(path + "/text", params={"case_id": case_id, "start_char": start, "limit": 4})
                window.raise_for_status()
                assert window.json()["content"] == "1234" and window.json()["content_sha256"] == digest
                answer = client.post(path + "/amount-assessment", params={"case_id": case_id}, json=payload)
                answer.raise_for_status()
                result = answer.json()
                assert result["applied"] is False and result["assessment"]["origin"] == origin
                if origin == "digital_text_layer":
                    assert result["assessment"]["minor_units"] == "123400"
                else:
                    assert "minor_units" not in result["assessment"]
                    assert {p["minor_units"] for p in result["assessment"]["proposals"]} == {"1234", "123400"}
                assert client.get(path + "/text", params={"case_id": other_id}).status_code == 404
                assert client.post(path + "/amount-assessment", params={"case_id": other_id}, json=payload).status_code == 404
                assert client.post(path + "/amount-assessment", params={"case_id": case_id}, json={**payload, "content_sha256": "b" * 64}).status_code == 409
                assert client.post(path + "/amount-assessment", params={"case_id": case_id}, json={**payload, "expected_text": "1235"}).status_code == 409
            for model in (FinancialTransaction, AdjudicationEvent):
                assert db.scalar(select(func.count()).select_from(model).where(model.case_id == case.id)) == 0
            for source in db.scalars(select(EvidenceDocumentText).where(EvidenceDocumentText.evidence_file_id.in_([UUID(i) for i in ids.values()]))):
                assert source.content == content and source.content_sha256 == digest
            summary = {"case_id": case_id, "files": ids, "selection": payload}
            (ROOT / "data/local-runtime/source-amount-check.json").write_text(json.dumps(summary, indent=2))
            print("PASS: three origins, exact proposals, wrong-case and stale-source refusal; no ledger writes.")
            print(json.dumps(summary, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
