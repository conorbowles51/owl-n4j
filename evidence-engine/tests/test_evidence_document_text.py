import hashlib
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy.dialects import postgresql

from app.pipeline.extract_text import ExtractedDocument
from app.services.evidence_document_text import (
    build_canonical_document_text,
    upsert_evidence_document_text,
)


def test_pdf_uses_body_once_and_retains_page_locations() -> None:
    doc = ExtractedDocument(
        text="first page\n\nsecond page",
        metadata={
            "file_type": "pdf",
            "page_spans": [
                {"page": 1, "start_char": 0, "end_char": 10},
                {"page": 2, "start_char": 12, "end_char": 23},
            ],
        },
        tables=["first page table duplicate"],
    )

    result = build_canonical_document_text(doc)

    assert result.content == doc.text
    assert "table duplicate" not in result.content
    assert result.source_locations[1]["page_number"] == 2
    assert result.source_locations[1]["start_char"] == 12


def test_docx_appends_tables_with_exact_ranges() -> None:
    result = build_canonical_document_text(
        ExtractedDocument(
            text="Body text",
            metadata={"file_type": "docx"},
            tables=["A | B", "C | D"],
        )
    )

    assert result.content == "Body text\n\nA | B\n\nC | D"
    for location in result.source_locations:
        assert result.content[location["start_char"] : location["end_char"]]
    assert result.source_locations[-1]["label"] == "Table 2"


def test_xlsx_records_sheet_ranges_and_hash() -> None:
    result = build_canonical_document_text(
        ExtractedDocument(
            text="",
            metadata={"file_type": "xlsx"},
            tables=["[Sheet: Accounts]\nName | Number"],
        )
    )

    assert result.source_locations == [
        {
            "kind": "sheet",
            "label": "Sheet Accounts",
            "start_char": 0,
            "end_char": len(result.content),
            "table_number": 1,
            "sheet_name": "Accounts",
        }
    ]
    assert result.content_sha256 == hashlib.sha256(result.content.encode("utf-8")).hexdigest()


async def test_reextraction_upserts_the_same_evidence_row_with_new_content() -> None:
    db = AsyncMock()
    evidence_id = uuid4()
    job_id = uuid4()

    await upsert_evidence_document_text(
        db,
        evidence_file_id=evidence_id,
        engine_job_id=job_id,
        doc=ExtractedDocument(text="old text", metadata={"file_type": "text"}),
    )
    await upsert_evidence_document_text(
        db,
        evidence_file_id=evidence_id,
        engine_job_id=job_id,
        doc=ExtractedDocument(text="replacement text", metadata={"file_type": "text"}),
    )

    statement = db.execute.await_args_list[-1].args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "ON CONFLICT (evidence_file_id) DO UPDATE" in str(compiled)
    assert compiled.params["content"] == "replacement text"
    assert compiled.params["evidence_file_id"] == evidence_id
    assert db.commit.await_count == 2
