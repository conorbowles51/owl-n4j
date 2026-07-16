"""Fixture-based acceptance tests for the citation / AI-limitation contract.

DKT-418, under story DKT-413. These tests run the real RAG pipeline over the
static corpus in ``tests/fixtures/citation_case`` with a scripted LLM, so they
are deterministic and need no Neo4j, ChromaDB or LLM provider.

This module is the executable statement of the contract the sibling tickets
(DKT-414..417) have to satisfy. Behaviour that exists today is asserted
normally. Behaviour that does not exist yet is marked ``xfail(strict=True)``:
the suite stays green while the gap is open, and turns **red the moment a
sibling makes an assertion pass without removing its marker**. It gates
forwards rather than breaking the build for unrelated tickets.

The contract these tests encode, on the dict returned by
``rag_service.answer_question`` and mirrored on ``POST /api/chat``:

``sources[i]``
    ``filename``, ``chunk_id``, ``doc_key``, ``page`` (``None`` when the
    document is unpaginated — never invented), ``quote``, ``resolved``.
``claims``
    ``{text, kind: evidence|reasoning|assertion, supported: bool,
    citations: [chunk_id, ...]}`` — a material claim is either cited or
    explicitly marked unsupported.
``review_warning``
    ``{text, dismissible: False}`` — present on every answer.
``citation_snapshot``
    ``{snapshot_id, chunk_ids, ...}`` — what was cited, as it was at answer time.
"""

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from services.case_service import CaseAccessDenied
from services.llm_service import LLMExecutionContext
from services.rag_service import rag_service

pytestmark = pytest.mark.acceptance

CITATION_LINK_RE = re.compile(r"\[([^\]]+?),\s*p\.?\s*(\d+)\]\(doc://([^/]+)/(\d+)\)")


def _source_filenames(result) -> set[str]:
    return {source["filename"] for source in result["sources"]}


def _rendered_links(answer: str) -> set[tuple[str, int]]:
    """The (filename, page) pairs rendered as openable doc:// links."""
    return {(m.group(3), int(m.group(4))) for m in CITATION_LINK_RE.finditer(answer)}


# Questions whose scripted answer cites the corpus honestly. q-fabricated-citation
# is excluded: it deliberately cites a document that was never retrieved, and is
# exercised on its own below.
HONESTLY_CITED = ["q-transfer-amount", "q-doyle-denial", "q-invoice-amount"]


# ---------------------------------------------------------------------------
# Successful path — behaviour that exists today and must not regress
# ---------------------------------------------------------------------------


def test_fixture_quotes_are_verbatim(citation_corpus):
    """Guards the fixture itself: every expected quote must really be in its chunk.

    Without this, a typo in expected_answers.json would silently weaken the
    quote-level assertions rather than failing.
    """
    chunk_text = {chunk["id"]: chunk["text"] for chunk in citation_corpus["chunks"]}
    for question in citation_corpus["questions"].values():
        for citation in question["required_citations"]:
            assert citation["quote"] in chunk_text[citation["chunk_id"]], (
                f"{question['id']}: quote is not verbatim in {citation['chunk_id']}"
            )


@pytest.mark.parametrize("question_id", HONESTLY_CITED)
def test_supported_question_is_answered_from_the_fixture_corpus(
    question_id, answer_for, citation_corpus
):
    result = answer_for(question_id)

    assert result["sources"], "a supported answer must carry at least one source"

    # Bare [file, p.N] citations are rewritten into openable doc:// links. Only
    # paginated citations can be rendered as a link today; the unpaginated case
    # is asserted separately below.
    expected = {
        (citation["filename"], citation["page"])
        for citation in citation_corpus["questions"][question_id]["required_citations"]
        if citation["page"] is not None
    }
    assert _rendered_links(result["answer"]) == expected


def test_retrieved_passages_reach_the_prompt_with_their_page_numbers(answer_for, fake_llm):
    answer_for("q-transfer-amount")

    prompt = fake_llm.last_prompt
    assert "USA-ET-000021.pdf (page 3)" in prompt
    assert "EUR 48,500.00" in prompt


def test_sources_only_name_documents_that_were_actually_retrieved(answer_for, citation_corpus):
    result = answer_for("q-transfer-amount")

    retrieved = {chunk["metadata"]["filename"] for chunk in citation_corpus["chunks"]}
    assert _source_filenames(result) <= retrieved


def test_page_numbers_are_not_invented_for_unpaginated_documents(answer_for, stub_rag, citation_corpus):
    # chunk-0005 is an unpaginated spreadsheet; its page_start is the -1 sentinel.
    stub_rag.retrieved_chunks = [
        chunk for chunk in citation_corpus["chunks"] if chunk["id"] == "chunk-0005"
    ]

    result = answer_for("q-invoice-amount")

    assert len(result["sources"]) == 1
    source = result["sources"][0]
    assert source["filename"] == "Vendor_Invoice_Meridian.xlsx"
    assert source.get("page") is None, "the -1 sentinel must not surface as a page number"


# ---------------------------------------------------------------------------
# Empty / permission / failure boundaries
# ---------------------------------------------------------------------------


def test_empty_retrieval_yields_no_sources(answer_for, stub_rag):
    stub_rag.retrieved_chunks = []
    stub_rag.retrieved_entities = []

    result = answer_for("q-tax-number")

    assert result["sources"] == []
    assert result["context_description"] == "No relevant context found"


def test_case_access_is_checked_before_any_retrieval(chat_client, citation_corpus, monkeypatch):
    client, calls = chat_client
    calls["access_error"] = CaseAccessDenied("denied")

    retrievals = []
    monkeypatch.setattr(
        rag_service,
        "answer_question",
        lambda **kwargs: retrievals.append(kwargs),
    )

    response = client.post(
        "/api/chat",
        json={
            "question": "How much did Fintan Doyle transfer to Meridian Holdings?",
            "case_id": citation_corpus["case_id"],
            "persist": False,
        },
    )

    assert response.status_code != 200
    assert calls["case_access"], "the permission gate must run"
    assert retrievals == [], "no evidence may be retrieved for a denied case"


def test_blank_question_is_rejected(chat_client, citation_corpus):
    client, _ = chat_client

    response = client.post(
        "/api/chat",
        json={"question": "   ", "case_id": citation_corpus["case_id"], "persist": False},
    )

    assert response.status_code == 400


def test_chat_endpoint_returns_the_cited_sources(chat_client, citation_corpus):
    client, _ = chat_client

    response = client.post(
        "/api/chat",
        json={
            "question": "How much did Fintan Doyle transfer to Meridian Holdings?",
            "case_id": citation_corpus["case_id"],
            "persist": False,
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sources"], "a supported answer must carry at least one source"
    assert body["provenance"]["case_id"] == citation_corpus["case_id"]


# ---------------------------------------------------------------------------
# DKT-414 — exact file/page/chunk/quote citations
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="DKT-414: sources drop the chunk id, so a citation cannot open an exact location")
@pytest.mark.parametrize("question_id", HONESTLY_CITED)
def test_each_source_identifies_the_exact_chunk_it_came_from(
    question_id, answer_for, citation_corpus
):
    result = answer_for(question_id)

    for source in result["sources"]:
        assert source.get("chunk_id"), f"no chunk_id on {source}"
        assert source.get("doc_key"), f"no doc_key on {source}"

    # The chunks the fixture says are needed must each be cited by id.
    expected_chunk_ids = {
        citation["chunk_id"]
        for citation in citation_corpus["questions"][question_id]["required_citations"]
    }
    assert expected_chunk_ids <= {source["chunk_id"] for source in result["sources"]}


@pytest.mark.xfail(strict=True, reason="DKT-414: sources carry a truncated excerpt, not a verbatim quote")
def test_each_source_carries_a_verbatim_quote_from_the_document(answer_for, citation_corpus):
    result = answer_for("q-transfer-amount")

    chunk_text = {chunk["id"]: chunk["text"] for chunk in citation_corpus["chunks"]}
    for source in result["sources"]:
        quote = source.get("quote")
        assert quote, f"no quote on {source}"
        assert quote in chunk_text[source["chunk_id"]], "quote must be verbatim"

    # The specific supporting quotes the fixture pins must survive to the source.
    quotes = {source["chunk_id"]: source["quote"] for source in result["sources"]}
    for citation in citation_corpus["questions"]["q-transfer-amount"]["required_citations"]:
        assert citation["quote"] in quotes[citation["chunk_id"]]


@pytest.mark.xfail(strict=True, reason="DKT-414: _build_sources dedupes by filename, collapsing distinct passages")
def test_distinct_passages_from_one_document_are_cited_separately(answer_for):
    # chunks 1, 2 and 6 are three different pages of USA-ET-000021.pdf.
    result = answer_for("q-transfer-amount")

    pages = sorted(
        source["page"]
        for source in result["sources"]
        if source["filename"] == "USA-ET-000021.pdf"
    )
    assert pages == [1, 3, 4]


@pytest.mark.xfail(strict=True, reason="DKT-414: the doc:// rewrite never checks the cited file was retrieved")
def test_a_citation_to_a_document_that_was_never_retrieved_is_not_linked(answer_for, citation_corpus):
    question = citation_corpus["questions"]["q-fabricated-citation"]
    result = answer_for("q-fabricated-citation")

    linked_files = {match.group(3) for match in CITATION_LINK_RE.finditer(result["answer"])}
    assert question["fabricated_filename"] not in linked_files, (
        "a fabricated filename must not be rendered as a working source link"
    )


@pytest.mark.xfail(strict=True, reason="DKT-414: the prompt tells the model to default to page 1 when no page is known")
def test_the_prompt_never_instructs_the_model_to_invent_a_page_number():
    context = LLMExecutionContext(provider="openai", model_id="gpt-5-mini")

    with patch.object(LLMExecutionContext, "call", return_value="answer"):
        _, prompt = context.answer_question_with_prompt(
            question="How much was transferred?",
            context="=== RELEVANT TEXT PASSAGES ===",
        )

    assert "use page 1" not in prompt.lower()


# ---------------------------------------------------------------------------
# DKT-415 — separate evidence, model reasoning and investigator assertions
# ---------------------------------------------------------------------------


def test_claims_are_labelled_as_evidence_reasoning_or_assertion(answer_for):
    result = answer_for("q-transfer-amount")

    claims = result["claims"]
    assert claims
    assert {claim["kind"] for claim in claims} <= {"evidence", "reasoning", "assertion"}
    assert any(claim["kind"] == "evidence" for claim in claims)


def test_every_supported_claim_cites_a_retrieved_chunk(answer_for, citation_corpus):
    result = answer_for("q-transfer-amount")

    retrieved_ids = {chunk["id"] for chunk in citation_corpus["chunks"]}
    for claim in result["claims"]:
        if claim["kind"] == "evidence" and claim["supported"]:
            assert claim["citations"], f"uncited evidence claim: {claim['text']!r}"
            assert set(claim["citations"]) <= retrieved_ids


# ---------------------------------------------------------------------------
# DKT-416 — persistent review warning, unsupported questions, absence of evidence
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="DKT-416: no human-review warning is attached to answers")
def test_every_answer_carries_a_non_dismissible_human_review_warning(answer_for):
    result = answer_for("q-transfer-amount")

    warning = result["review_warning"]
    assert warning["text"]
    assert warning["dismissible"] is False


def test_a_question_the_corpus_cannot_answer_is_marked_unsupported(answer_for):
    result = answer_for("q-tax-number")

    claims = result["claims"]
    assert claims
    assert all(claim["supported"] is False for claim in claims)
    assert all(claim["citations"] == [] for claim in claims)


def test_an_unqualified_absence_of_evidence_claim_is_flagged(answer_for, fake_llm, citation_corpus):
    question = citation_corpus["questions"]["q-minister-meeting"]
    # Script the model to assert the negative as fact; the pipeline must not
    # let that stand as a supported claim.
    fake_llm.set_answer(question["question"], question["unqualified_absence_answer"])

    result = answer_for("q-minister-meeting")

    assert result["claims"]
    assert all(claim["supported"] is False for claim in result["claims"])


# ---------------------------------------------------------------------------
# DKT-417 — deleted/broken sources and citation snapshots
# ---------------------------------------------------------------------------


@pytest.mark.xfail(strict=True, reason="DKT-417: no snapshot of the citation context is recorded")
def test_the_citation_context_used_for_an_answer_is_snapshotted(answer_for):
    result = answer_for("q-transfer-amount")

    snapshot = result["citation_snapshot"]
    assert snapshot["snapshot_id"]
    assert set(snapshot["chunk_ids"]) == {source["chunk_id"] for source in result["sources"]}


@pytest.mark.xfail(strict=True, reason="DKT-417: a source whose document is gone is still cited as if it resolves")
def test_a_source_whose_document_is_gone_is_marked_unresolved(answer_for, stub_rag, citation_corpus, monkeypatch):
    stub_rag.retrieved_chunks = [
        chunk for chunk in citation_corpus["chunks"] if chunk["id"] == "chunk-0001"
    ]
    # The document was recycled between ingestion and this answer.
    monkeypatch.setattr(
        rag_service, "_get_document_node_by_key", lambda doc_key, case_id: None
    )

    result = answer_for("q-transfer-amount")

    assert len(result["sources"]) == 1
    assert result["sources"][0]["resolved"] is False
