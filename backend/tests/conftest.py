"""Shared offline harness for the citation / AI-limitation acceptance tests.

Everything here runs without Neo4j, ChromaDB or an LLM provider: retrieval is
replaced by the static corpus under ``tests/fixtures/citation_case`` and the
LLM by a scripted stub.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.rag_service import rag_service
from tests.fixtures import load_fixture

CORPUS_DIR = "citation_case"


class FakeLLMContext:
    """Stands in for ``LLMExecutionContext``.

    Returns the scripted answer for whichever fixture question it is handed and
    records the prompt it was given, so a test can assert what the citation
    instructions actually told the model to do.
    """

    def __init__(self, scripted_answers: Dict[str, str]):
        self._scripted_answers = scripted_answers
        self.provider = "openai"
        self.model_id = "gpt-5-mini"
        self.prompts: List[str] = []
        self.last_prompt: Optional[str] = None
        self.last_raw_response: Optional[str] = None
        self.last_usage: Optional[Dict[str, int]] = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }

    def set_answer(self, question: str, answer: str) -> None:
        """Re-script one question, for tests that need a specific model output."""
        self._scripted_answers[question] = answer

    def answer_for(self, question: str) -> str:
        for fixture_question, answer in self._scripted_answers.items():
            # answer_question() may append document-focus instructions to the
            # question, so match on prefix rather than equality.
            if question.startswith(fixture_question):
                return answer
        raise AssertionError(f"No scripted answer for question: {question!r}")

    def answer_question_with_prompt(
        self,
        question: str,
        context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> tuple[str, str]:
        prompt = f"CONTEXT:\n{context}\n\nQUESTION:\n{question}"
        self.prompts.append(prompt)
        self.last_prompt = prompt
        answer = self.answer_for(question)
        self.last_raw_response = answer
        return answer, prompt

    def answer_question(
        self,
        question: str,
        context: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        answer, _ = self.answer_question_with_prompt(
            question, context, conversation_history=conversation_history
        )
        return answer

    def classify_question(self, question: str) -> str:
        # "semantic" keeps the pipeline off the Cypher/Neo4j path.
        return "semantic"


@pytest.fixture
def citation_corpus() -> Dict[str, Any]:
    """The fixture case: chunks, entities and per-question expectations."""
    expected = load_fixture(f"{CORPUS_DIR}/expected_answers.json")
    return {
        "case_id": expected["case_id"],
        "chunks": load_fixture(f"{CORPUS_DIR}/chunks.json"),
        "entities": load_fixture(f"{CORPUS_DIR}/entities.json"),
        "questions": {q["id"]: q for q in expected["questions"]},
    }


@pytest.fixture
def fake_llm(citation_corpus) -> FakeLLMContext:
    return FakeLLMContext(
        {q["question"]: q["scripted_answer"] for q in citation_corpus["questions"].values()}
    )


@pytest.fixture
def stub_rag(monkeypatch, citation_corpus):
    """Point rag_service at the fixture corpus instead of the live datastores.

    Yields a control object; set ``retrieved_chunks``/``retrieved_entities`` to
    ``[]`` to exercise the empty-retrieval boundary.
    """

    class RagStub:
        def __init__(self):
            self.retrieved_chunks = [dict(c) for c in citation_corpus["chunks"]]
            self.retrieved_entities = [dict(e) for e in citation_corpus["entities"]]

    stub = RagStub()

    def _retrieve_chunks(
        question, case_id=None, doc_keys=None, confidence_threshold=None, debug_log=None
    ):
        chunks = [dict(c) for c in stub.retrieved_chunks]
        if debug_log is not None:
            # answer_question() reads this back when describing the context.
            debug_log["chunk_search"] = {
                "enabled": True,
                "source": "chunks",
                "chunks_in_db": len(chunks),
                "total_results": len(chunks),
                "filtered_results": len(chunks),
                "results": [],
            }
        return chunks

    def _retrieve_entities(question, case_id=None, top_k=None, debug_log=None):
        entities = [dict(e) for e in stub.retrieved_entities]
        if debug_log is not None:
            debug_log["entity_search"] = {
                "enabled": True,
                "vector_results": len(entities),
                "enriched_entities": len(entities),
                "entity_keys": [e.get("key") for e in entities],
            }
        return entities

    monkeypatch.setattr(rag_service, "_retrieve_chunks", _retrieve_chunks)
    monkeypatch.setattr(rag_service, "_retrieve_entities", _retrieve_entities)
    monkeypatch.setattr(
        rag_service,
        "_traverse_graph",
        lambda entity_keys, case_id=None, debug_log=None: {"selected_entities": []},
    )
    # Identity re-rank: ordering is not what these tests are about.
    monkeypatch.setattr(
        rag_service,
        "_rerank_results",
        lambda question, chunk_results, entity_results, debug_log=None: (
            chunk_results,
            entity_results,
        ),
    )
    monkeypatch.setattr(
        rag_service,
        "_build_result_graph",
        lambda **kwargs: {"nodes": [], "links": []},
    )
    return stub


@pytest.fixture
def answer_for(stub_rag, fake_llm, citation_corpus):
    """Run the real RAG pipeline over the fixture corpus for a fixture question."""

    def _answer(question_id: str, **kwargs) -> Dict[str, Any]:
        question = citation_corpus["questions"][question_id]["question"]
        return rag_service.answer_question(
            question=question,
            case_id=citation_corpus["case_id"],
            llm_context=fake_llm,
            **kwargs,
        )

    return _answer


class FakeUser:
    def __init__(self):
        self.id = uuid.UUID("22222222-2222-4222-8222-222222222222")
        self.email = "investigator@example.com"


@pytest.fixture
def chat_client(monkeypatch, stub_rag, fake_llm):
    """A TestClient over just the chat router.

    Avoids importing main.py, which wires ~40 routers. Yields
    ``(client, calls)``; ``calls`` records case-access checks so a test can
    assert the permission gate ran before any retrieval.
    """
    import routers.chat as chat_router

    app = FastAPI()
    app.include_router(chat_router.router)

    calls: Dict[str, Any] = {"case_access": [], "access_error": None}

    def _require_case_access(db, user, case_id):
        calls["case_access"].append(case_id)
        if calls["access_error"] is not None:
            raise calls["access_error"]
        return object()

    monkeypatch.setattr(chat_router, "require_case_access", _require_case_access)
    monkeypatch.setattr(chat_router.rag_service.llm, "create_context", lambda **kw: fake_llm)

    # Persistence, logging and cost accounting are out of scope here.
    @contextmanager
    def _no_cost_context(**kwargs):
        yield None

    monkeypatch.setattr(chat_router, "ai_cost_context", _no_cost_context)
    monkeypatch.setattr(chat_router, "get_latest_case_revision", lambda db, case_id: None)
    monkeypatch.setattr(chat_router, "record_cost", lambda **kwargs: None)
    monkeypatch.setattr(chat_router.system_log_service, "log", lambda **kwargs: None)
    monkeypatch.setattr(
        chat_router.rag_service, "get_suggested_questions", lambda *args, **kwargs: []
    )

    app.dependency_overrides[chat_router.get_db] = lambda: MagicMock()
    app.dependency_overrides[chat_router.get_current_db_user] = lambda: FakeUser()

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, calls
