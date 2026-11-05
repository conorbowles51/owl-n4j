"""Agent evaluation of exact words across the case (lx-textbench E), through search_exact_words, the tool the model calls.

Known answers are written by hand from the synthetic case below, not computed by the code under test: which documents
hold the words, how many times, and on which page. Scored as questions right / total, with every hit's citation opening
the page named. Set LOUPE_CITATION_EVAL_OUT to a file path to write one JSON line per question.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

from postgres.models.evidence import EvidenceDocumentText
from tests.test_meaning_search_fallback import Fixture


class ExactWordsEvaluation(Fixture):
    def setUp(self):
        super().setUp()
        with self.Session() as db:
            text = db.get(EvidenceDocumentText, self.tender.id)
            text.source_locations = [
                dict(kind="page", label="Page 1", page_number=1, start_char=0, end_char=43,
                     extraction_method="tesseract_ocr", text_origin="recognised_glyphs"),
                dict(kind="page", label="Page 2", page_number=2, start_char=43, end_char=len(text.content),
                     extraction_method="native", text_origin="digital_text_layer")]
            db.commit()

    def tool(self):
        from services.agent.tools import AgentToolContext, make_agent_tools
        context = AgentToolContext(case_id=str(self.case_id), ledger_session_factory=self.session)
        return {tool.name: tool for tool in make_agent_tools(context)}["search_exact_words"]

    def test_questions(self):
        tender, receipt = str(self.tender.id), str(self.receipt.id)
        # question, the exact words, documents and occurrences across the case, then (file, page, read by) of each hit
        questions = [
            ("Where does the exact name Northgate Ltd appear?", "Northgate Ltd", 1, 1, [(tender, 2, "own text layer")]),
            ("Which documents print Northgate?", "Northgate", 2, 2, [(receipt, None, None), (tender, 2, "own text layer")]),
            ("Where is the amount 412.50?", "412.50", 1, 1, [(receipt, None, None)]),
            ("Which page gives the 3 May closing?", "closed on 3 May", 1, 1, [(tender, 1, "OCR")]),
            ("Is the depot's sale price stated?", "sale price", 0, 0, []),
            ("A name of another case stays out", "other-case", 0, 0, []),
        ]
        tool, right, lines = self.tool(), 0, []
        with patch("services.vector_db_service.get_vector_db_health", side_effect=AssertionError("meaning search ran")):
            for question, words, documents, occurrences, hits in questions:
                data = tool.invoke({"words": words})["data"]
                got = [(hit["evidence_file_id"], hit.get("page")) for hit in data["results"]]
                ok = (data["total_documents"] == documents and data["total_occurrences"] == occurrences
                      and sorted(got, key=str) == sorted(((f, p) for f, p, _ in hits), key=str))
                for hit in data["results"]:
                    page = hit.get("page")
                    expected = f"doc://{hit['evidence_file_id']}/{page}" if page else f"doc://{hit['evidence_file_id']}"
                    ok = ok and hit["cite"] == expected
                    want = next(read for f, p, read in hits if (f, p) == (hit["evidence_file_id"], page))
                    ok = ok and (want is None or want in hit.get("read_by", ""))
                right += ok
                lines.append(dict(question=question, words=words, right=bool(ok), hits=len(got)))
        if os.environ.get("LOUPE_CITATION_EVAL_OUT"):
            with open(os.environ["LOUPE_CITATION_EVAL_OUT"], "a") as out:
                out.writelines(json.dumps(line) + "\n" for line in lines)
        self.assertEqual((right, len(questions)), (len(questions), len(questions)), lines)

    def test_the_answer_says_what_was_not_searched_and_keeps_true_totals(self):
        data = self.tool().invoke({"words": "Northgate", "limit": 1})
        self.assertEqual(data["data"]["total_documents"], 2)
        self.assertEqual(data["data"]["returned_documents"], 1)
        self.assertEqual(data["data"]["next_offset"], 1)
        self.assertEqual(data["data"]["documents_without_text"], 1)  # scan-no-text.jpg
        self.assertIn("not searched", data["summary"])
        self.assertIn("next page", data["summary"])

    def test_inside_the_significant_layer_it_is_refused(self):
        from services.agent.tools import AgentToolContext, make_agent_tools
        context = AgentToolContext(case_id=str(self.case_id), ledger_session_factory=self.session,
                                   allowed_entity_keys=set())
        tool = {t.name: t for t in make_agent_tools(context)}["search_exact_words"]
        self.assertFalse(tool.invoke({"words": "Northgate"})["data"].get("results"))
