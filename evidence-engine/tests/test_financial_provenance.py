"""The extracting model's claims about its own output are recorded, never obeyed.

`is_evidence_backed_transaction` decides whether a figure is presentable as a
documentary transaction rather than as intelligence. It is derived from three
fields. Until this was fixed, all three were taken verbatim from the model
whenever it declared them, so the model could move that flag in either
direction on unchanged source text: promoting hearsay to an exhibit, or
demoting a genuine statement row out of the transaction view.

These tests pin the arbitration: the source decides, the claim is kept beside
it, and disagreement is recorded rather than discarded.
"""

from __future__ import annotations

import inspect
from typing import Any

from app.pipeline.extract_entities import (
    PROVENANCE_POLICY,
    _build_financial_provenance,
    _infer_evidence_source_type,
    _infer_evidence_strength,
    _infer_financial_record_kind,
)
from app.pipeline.property_canonicalization import is_neo4j_primitive_list

# A witness recounting a payment. Narrative on its face: no document, no row.
NARRATIVE_SOURCE: dict[str, Any] = dict(
    category="Transaction",
    specific_type="Payment",
    name="Alleged $3,000 payment to Petrov",
    source_quote="Marta told me she gave him three thousand dollars last spring.",
    properties={"amount": "3000", "currency": "USD", "date": "2024-04-01"},
    file_name="witness_interview_marta.txt",
    file_type="txt",
    source_document_id="DOC-1",
    source_page=2,
    confidence=0.5,
    is_table=False,
)

# A row off a bank statement. Documentary on its face.
DOCUMENTARY_SOURCE: dict[str, Any] = dict(
    category="Transaction",
    specific_type="Payment",
    name="Wire transfer $48,200 to Nexus Trading Ltd",
    source_quote="04/12/2024  WIRE TRANSFER OUT  NEXUS TRADING LTD  48,200.00",
    properties={
        "amount": "48200",
        "currency": "USD",
        "date": "2024-04-12",
        "receiver": "Nexus Trading Ltd",
    },
    file_name="chase_bank_statement_apr2024.pdf",
    file_type="pdf",
    source_document_id="DOC-2",
    source_page=7,
    confidence=0.95,
    is_table=True,
)

DECLARES_DOCUMENTARY = {
    "evidence_source_type": "bank_statement",
    "evidence_strength": "documentary",
    "financial_record_kind": "transaction",
}


def test_a_declaration_cannot_promote_hearsay_to_an_evidence_backed_transaction() -> None:
    silent = _build_financial_provenance(None, **NARRATIVE_SOURCE)
    declared = _build_financial_provenance(DECLARES_DOCUMENTARY, **NARRATIVE_SOURCE)

    assert silent["evidence_strength"] == "narrative"
    assert silent["is_evidence_backed_transaction"] is False

    # Same source text, opposite claim, unchanged verdict.
    assert declared["evidence_source_type"] == silent["evidence_source_type"]
    assert declared["evidence_strength"] == silent["evidence_strength"]
    assert declared["financial_record_kind"] == silent["financial_record_kind"]
    assert declared["is_evidence_backed_transaction"] is False
    assert declared["financial_view_mode"] == "intelligence"


def test_a_declaration_cannot_demote_a_genuine_statement_row_out_of_the_ledger() -> None:
    silent = _build_financial_provenance(None, **DOCUMENTARY_SOURCE)
    declared = _build_financial_provenance(
        {"evidence_strength": "narrative"}, **DOCUMENTARY_SOURCE
    )

    assert silent["is_evidence_backed_transaction"] is True
    assert declared["evidence_strength"] == "documentary"
    assert declared["is_evidence_backed_transaction"] is True
    assert declared["financial_view_mode"] == "transaction"


def test_the_rejected_declaration_is_recorded_beside_the_inferred_value() -> None:
    result = _build_financial_provenance(DECLARES_DOCUMENTARY, **NARRATIVE_SOURCE)

    assert result["evidence_source_type"] == "interview"
    assert result["evidence_source_type_declared"] == "bank_statement"
    assert result["evidence_strength"] == "narrative"
    assert result["evidence_strength_declared"] == "documentary"
    assert result["financial_record_kind"] == "allegation"
    assert result["financial_record_kind_declared"] == "transaction"
    assert result["provenance_declaration_conflicts"] == [
        "evidence_source_type",
        "evidence_strength",
        "financial_record_kind",
    ]
    assert result["provenance_decided_by"] == PROVENANCE_POLICY


def test_only_the_fields_that_actually_disagree_are_listed_as_conflicts() -> None:
    # The model gets record_kind right and strength wrong.
    result = _build_financial_provenance(
        {"financial_record_kind": "transaction", "evidence_strength": "narrative"},
        **DOCUMENTARY_SOURCE,
    )

    assert result["financial_record_kind"] == "transaction"
    assert result["financial_record_kind_declared"] == "transaction"
    assert result["provenance_declaration_conflicts"] == ["evidence_strength"]


def test_silence_is_distinguishable_from_agreement() -> None:
    silent = _build_financial_provenance(None, **DOCUMENTARY_SOURCE)
    agreeing = _build_financial_provenance(
        {"evidence_strength": "documentary"}, **DOCUMENTARY_SOURCE
    )

    assert silent["evidence_strength_declared"] == ""
    assert agreeing["evidence_strength_declared"] == "documentary"
    # Neither is a conflict, but the records differ.
    assert silent["provenance_declaration_conflicts"] == []
    assert agreeing["provenance_declaration_conflicts"] == []


def test_a_declaration_outside_the_vocabulary_is_discarded_not_recorded() -> None:
    result = _build_financial_provenance(
        {
            "evidence_strength": "extremely documentary",
            "financial_record_kind": "",
            "evidence_source_type": "notarised_affidavit",
        },
        **DOCUMENTARY_SOURCE,
    )

    assert result["evidence_strength_declared"] == ""
    assert result["financial_record_kind_declared"] == ""
    assert result["evidence_source_type_declared"] == ""
    assert result["provenance_declaration_conflicts"] == []


def test_declared_values_are_normalised_before_comparison() -> None:
    # Casing and padding must not manufacture a phantom conflict.
    result = _build_financial_provenance(
        {"evidence_strength": "  DOCUMENTARY  "}, **DOCUMENTARY_SOURCE
    )

    assert result["evidence_strength_declared"] == "documentary"
    assert result["provenance_declaration_conflicts"] == []


def test_every_recorded_provenance_field_survives_the_neo4j_property_writer() -> None:
    """`_write_entities` silently drops values that are not scalars or flat lists.

    A nested dict here would vanish from the graph without raising, so the
    audit record would be missing exactly when someone went looking for it.
    """
    result = _build_financial_provenance(DECLARES_DOCUMENTARY, **NARRATIVE_SOURCE)

    for key, value in result.items():
        assert isinstance(value, (str, int, float, bool)) or is_neo4j_primitive_list(
            value
        ), f"{key!r} would be dropped when writing the node: {value!r}"


def test_the_inference_functions_cannot_see_the_models_declaration_at_all() -> None:
    """The structural guarantee: the short-circuit cannot be reintroduced quietly.

    Each inference used to begin by returning the model's declaration when it
    was present and valid. Removing the parameter is what stops that returning.
    """
    for func in (
        _infer_evidence_source_type,
        _infer_evidence_strength,
        _infer_financial_record_kind,
    ):
        parameters = inspect.signature(func).parameters
        assert "financial_provenance" not in parameters, func.__name__
        assert all(
            parameter.kind is inspect.Parameter.KEYWORD_ONLY
            for parameter in parameters.values()
        ), f"{func.__name__} takes positional arguments, which invites the old call shape"
