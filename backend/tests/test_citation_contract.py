import unittest
from unittest.mock import patch

from services.llm_service import LLMExecutionContext
from services.rag_service import RAGService


class CitationContractTests(unittest.TestCase):
    def setUp(self):
        self.rag = RAGService.__new__(RAGService)

    def test_sources_are_emitted_per_retrieved_chunk(self):
        chunks = [
            {
                "id": "doc-1_chunk_0",
                "text": "First material claim appears here.",
                "metadata": {
                    "doc_id": "doc-1",
                    "filename": "evidence.pdf",
                    "chunk_index": 0,
                    "page_start": 2,
                },
            },
            {
                "id": "doc-1_chunk_1",
                "text": "Second material claim appears elsewhere.",
                "metadata": {
                    "doc_id": "doc-1",
                    "filename": "evidence.pdf",
                    "chunk_index": 1,
                    "page_start": 5,
                },
            },
        ]

        sources = self.rag._build_sources(chunks)

        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0]["filename"], "evidence.pdf")
        self.assertEqual(sources[0]["chunk_id"], "doc-1:0")
        self.assertEqual(sources[1]["chunk_id"], "doc-1:1")
        self.assertEqual(sources[0]["page"], 2)
        self.assertEqual(sources[1]["page"], 5)

    def test_source_quote_is_verbatim_and_unpaginated_sources_do_not_invent_page(self):
        chunk_text = "  The verified amount was EUR 125,000 in the invoice attachment.\n\nExtra context.  "
        chunks = [
            {
                "id": "invoice_chunk_7",
                "text": chunk_text,
                "metadata": {
                    "filename": "invoice.txt",
                    "chunk_index": 7,
                    "page_start": None,
                },
            }
        ]

        source = self.rag._build_sources(chunks)[0]

        self.assertIsNone(source["page"])
        self.assertEqual(
            source["quote"],
            "The verified amount was EUR 125,000 in the invoice attachment.\n\nExtra context.",
        )
        self.assertIn(source["quote"], chunk_text)
        self.assertTrue(source["resolved"])

    def test_plain_citation_links_only_when_document_page_was_retrieved(self):
        chunks = [
            {
                "text": "Retrieved context",
                "metadata": {"filename": "retrieved.pdf", "page_start": 3},
            }
        ]
        targets = self.rag._build_citation_target_map(chunks)
        answer = "Use [retrieved.pdf, p.3] but not [missing.pdf, p.4]."

        linked = self.rag._link_retrieved_plain_citations(answer, targets)

        self.assertIn("[retrieved.pdf, p.3](doc://retrieved.pdf/3)", linked)
        self.assertIn("[missing.pdf, p.4]", linked)
        self.assertNotIn("doc://missing.pdf/4", linked)

    def test_doc_links_to_unretrieved_documents_are_downgraded_to_plain_text(self):
        targets = self.rag._build_citation_target_map(
            [{"text": "Retrieved context", "metadata": {"filename": "retrieved.pdf", "page_start": 3}}]
        )
        answer = (
            "Valid [retrieved.pdf, p.3](doc://retrieved.pdf/3). "
            "Invalid [missing.pdf, p.4](doc://missing.pdf/4)."
        )

        sanitized = self.rag._sanitize_doc_links(answer, targets)

        self.assertIn("[retrieved.pdf, p.3](doc://retrieved.pdf/3)", sanitized)
        self.assertIn("Invalid missing.pdf, p.4.", sanitized)
        self.assertNotIn("doc://missing.pdf/4", sanitized)

    def test_prompt_does_not_instruct_model_to_invent_page_one(self):
        context = LLMExecutionContext(provider="openai", model_id="test-model")

        def fake_call(prompt, **_kwargs):
            context.last_prompt = prompt
            return "Unsupported by the provided sources."

        with patch.object(context, "call", side_effect=fake_call):
            _answer, prompt = context.answer_question_with_prompt(
                "Question?",
                "No relevant context found.",
            )

        self.assertIs(context.last_prompt, prompt)
        self.assertNotIn("use page 1", prompt.lower())
        self.assertIn("without inventing a page", prompt.lower())
        self.assertIn("Unsupported by the provided sources", prompt)


if __name__ == "__main__":
    unittest.main()
