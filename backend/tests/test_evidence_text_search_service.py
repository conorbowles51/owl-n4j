from __future__ import annotations

import unittest
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from postgres.base import Base
from postgres.models.evidence import EvidenceDocumentText, EvidenceFile, EvidenceFolder
from services.evidence_text_search_service import search_case_text, search_document_text


TABLES = [
    EvidenceFolder.__table__,
    EvidenceFile.__table__,
    EvidenceDocumentText.__table__,
]


class EvidenceTextSearchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.case_id = uuid4()
        self.other_case_id = uuid4()

    def tearDown(self) -> None:
        self.engine.dispose()

    def _add_document(
        self,
        db,
        *,
        case_id,
        name: str,
        content: str,
        locations: list[dict] | None = None,
        folder_id=None,
    ) -> EvidenceFile:
        evidence = EvidenceFile(
            id=uuid4(),
            case_id=case_id,
            folder_id=folder_id,
            original_filename=name,
            stored_path=f"/tmp/{name}",
            size=len(content),
            sha256="a" * 64,
            status="processed",
        )
        db.add(evidence)
        db.add(
            EvidenceDocumentText(
                evidence_file_id=evidence.id,
                content=content,
                content_sha256="b" * 64,
                character_count=len(content),
                source_locations=locations or [],
            )
        )
        return evidence

    def test_phrase_returns_every_case_document_with_highlighted_previews(self) -> None:
        with self.Session() as db:
            folder = EvidenceFolder(id=uuid4(), case_id=self.case_id, name="Statements")
            db.add(folder)
            for index in range(3):
                self._add_document(
                    db,
                    case_id=self.case_id,
                    name=f"statement-{index}.pdf",
                    content="Before ACME Account 12_34% after.",
                    folder_id=folder.id,
                )
            self._add_document(
                db,
                case_id=self.other_case_id,
                name="secret.pdf",
                content="ACME Account 12_34%",
            )
            db.commit()

            result = search_case_text(
                db,
                case_id=self.case_id,
                query="acme account 12_34%",
                document_limit=25,
                document_offset=0,
            )

        self.assertEqual(result["total_documents"], 3)
        self.assertEqual(result["total_matches"], 3)
        self.assertEqual(result["case_documents"], 3)
        self.assertEqual(result["searchable_documents"], 3)
        self.assertEqual(result["documents"][0]["folder_path"], "Root / Statements")
        for document in result["documents"]:
            hit = document["matches"][0]
            highlighted = hit["snippet"][hit["highlight_start"] : hit["highlight_end"]]
            self.assertEqual(highlighted, "ACME Account 12_34%")

    def test_repeated_matches_are_distinct_and_pagination_totals_are_exact(self) -> None:
        with self.Session() as db:
            evidence = self._add_document(
                db,
                case_id=self.case_id,
                name="ledger.txt",
                content="AB-123 then ab-123 then AB-123",
            )
            db.commit()

            result = search_document_text(
                db,
                evidence_id=evidence.id,
                query="AB-123",
                limit=2,
                offset=0,
            )

        self.assertEqual(result["total_matches"], 3)
        self.assertEqual(result["returned_matches"], 2)
        self.assertTrue(result["has_more"])
        self.assertLess(result["matches"][0]["start_char"], result["matches"][1]["start_char"])

    def test_match_resolves_to_pdf_page(self) -> None:
        with self.Session() as db:
            evidence = self._add_document(
                db,
                case_id=self.case_id,
                name="report.pdf",
                content="first page\n\nneedle on second page",
                locations=[
                    {"kind": "page", "label": "Page 1", "page_number": 1, "start_char": 0, "end_char": 10},
                    {"kind": "page", "label": "Page 2", "page_number": 2, "start_char": 12, "end_char": 33},
                ],
            )
            db.commit()

            result = search_document_text(
                db,
                evidence_id=evidence.id,
                query="needle",
                limit=50,
                offset=0,
            )

        self.assertEqual(result["matches"][0]["page_number"], 2)
        self.assertEqual(result["matches"][0]["location_label"], "Page 2")


if __name__ == "__main__":
    unittest.main()
