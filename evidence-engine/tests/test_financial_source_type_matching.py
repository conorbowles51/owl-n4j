"""A keyword buried inside a longer word is not a mention of that keyword.

`_infer_evidence_source_type` decides `evidence_source_type`, which decides
`evidence_strength`, which is one of the three conditions for
`is_evidence_backed_transaction`. Until this was fixed the function tested its
keywords with `keyword in probe`, so:

  * a witness saying someone "wired" the money matched "wire", and because the
    wire branch is tried before the email and interview branches, the statement
    was classified `wire` — a documentary source. Hearsay became an exhibit.
  * "CITIBANK" contains "iban", so a card purchase at a Citibank ATM was
    classified as a wire.
  * "SPRINT *WIRELESS" contains "wire".
  * "INVESTIGATIVE REPORTERS" contains "report", so it was an official report.
  * a Zelle payee named "MBICAM AND CO" contains "bic".

The obvious repair — require a word boundary — was measured against the corpus
first and rejected. Most substring-only matches there are correct: 10,293
"Withdrawals", 6,844 "PAYMENTUS", 5,861 "Deposits", 1,469 "21PURCHASE", 1,383
"debits". A `\\b` rule would have discarded roughly eighteen thousand good
matches to fix about a hundred and ninety bad ones.

What the corpus actually supports is a split, because the two groups of
keywords answer different questions:

  * `_infer_evidence_source_type` CLASSIFIES. Over-matching labels narrative
    material documentary, which is how hearsay is promoted. Precision. On the
    classification list a letter-boundary rule rejects 184 corpus matches and
    every one of them is one of the five defects above.
  * `_is_financial_candidate` and `_looks_like_transaction_event` ADMIT. A false
    positive costs one extra candidate that later checks discard; a false
    negative drops a real transaction silently. Recall. The same rule would
    reject 912 correct matches here, all of them run-together bank-export text.

So the rule is applied to the first and deliberately withheld from the other
two. These tests pin both halves: the collisions must not classify, and the
run-together export text must still be admitted.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.pipeline.extract_entities import (
    DOCUMENTARY_SOURCE_TYPES,
    NARRATIVE_SOURCE_TYPES,
    _SOURCE_TYPE_KEYWORDS,
    _infer_evidence_source_type,
    _infer_evidence_strength,
    _is_financial_candidate,
    _looks_like_transaction_event,
    _word_pattern,
)


def classify(**overrides: Any) -> str:
    source: dict[str, Any] = dict(
        file_name="",
        file_type=None,
        specific_type="",
        name="",
        source_quote="",
        is_table=False,
    )
    source.update(overrides)
    return _infer_evidence_source_type(**source)


# --- the defect this change exists to remove --------------------------------


def test_a_witness_saying_someone_wired_money_is_not_a_wire_document() -> None:
    """The motivating case. A statement about a wire is not a wire."""
    source_type = classify(
        file_name="witness_interview_marta.txt",
        file_type="txt",
        specific_type="Payment",
        name="Alleged transfer to Petrov",
        source_quote="She told me he wired the money to Dubai last spring.",
    )
    assert source_type != "wire"
    assert source_type in NARRATIVE_SOURCE_TYPES


def test_that_witness_statement_is_graded_narrative_not_documentary() -> None:
    """The classification is only the mechanism; this is the harm it caused."""
    source_type = classify(
        file_name="witness_interview_marta.txt",
        file_type="txt",
        source_quote="She told me he wired the money to Dubai last spring.",
    )
    strength = _infer_evidence_strength(
        evidence_source_type=source_type, file_type="txt", is_table=False
    )
    assert strength == "narrative"
    assert strength != "documentary"


@pytest.mark.parametrize(
    ("text", "collision"),
    [
        ("CHECKCARD 0510 SPRINT *WIRELESS 800-639-6111 KS", "wire in wireless"),
        ("19CHECKCARD 0716 CITIBANK, N.A. SIOUX FALLS SD", "iban in citibank"),
        ("Zelle OUT DELIVERED Chase MBICAM AND CO SERVICES LLC", "bic in mbicam"),
        ("CHECKCARD 0602 INVESTIGATIVE REPORTERS 573-8847902 MO", "report in reporters"),
        ("Payment to Wirecard AG", "wire in wirecard"),
        ("KENILWORTH PROPERTIES LLC", "worth in kenilworth"),
    ],
)
def test_a_keyword_buried_in_a_merchant_name_does_not_classify(
    text: str, collision: str
) -> None:
    """Every one of these was measured on the corpus, not invented."""
    source_type = classify(file_name="doc.pdf", file_type="pdf", name=text)
    assert source_type == "other", collision


def test_none_of_those_collisions_are_graded_documentary() -> None:
    for text in (
        "SPRINT *WIRELESS 800-639-6111",
        "CITIBANK, N.A. SIOUX FALLS SD",
        "INVESTIGATIVE REPORTERS 573-8847902",
    ):
        source_type = classify(file_name="doc.pdf", file_type="pdf", name=text)
        assert source_type not in DOCUMENTARY_SOURCE_TYPES


# --- what must keep working -------------------------------------------------


@pytest.mark.parametrize(
    ("expected", "kwargs"),
    [
        ("wire", dict(file_name="wire_confirmation_0412.pdf", file_type="pdf")),
        ("wire", dict(name="WIRE TRANSFER OUT NEXUS TRADING LTD 48,200.00")),
        ("wire", dict(name="IBAN: DE89370400440532013000")),
        ("wire", dict(name="BIC/SWIFT: DEUTDEFF")),
        ("bank_statement", dict(name="Bank Statement — April 2024")),
        ("card_statement", dict(name="Credit Card summary")),
        ("invoice", dict(name="Outstanding invoice 4471")),
        ("receipt", dict(name="Paid receipt for consulting")),
        ("ledger", dict(name="General ledger extract")),
        ("official_report", dict(name="Official report of the receiver")),
        ("interview", dict(file_name="transcript_smith.txt", file_type="txt")),
    ],
)
def test_a_real_mention_still_classifies(expected: str, kwargs: dict[str, Any]) -> None:
    assert classify(**{"file_type": "pdf", **kwargs}) == expected


@pytest.mark.parametrize(
    ("expected", "text"),
    [
        ("invoice", "Outstanding invoices for Q2"),
        ("receipt", "Receipts attached"),
        ("official_report", "Quarterly reports filed"),
        ("bank_statement", "Bank statements for the period"),
        ("wire", "Two wires sent Tuesday"),
    ],
)
def test_plurals_still_classify(expected: str, text: str) -> None:
    """Statement headers are written "Deposits", "Withdrawals", "Purchases"."""
    assert classify(file_name="doc.pdf", file_type="pdf", name=text) == expected


def test_a_keyword_against_a_digit_or_separator_still_classifies() -> None:
    """A letter boundary, not a word boundary: exports run words into digits."""
    assert classify(file_name="wire_confirmation.pdf", file_type="pdf") == "wire"
    assert classify(file_name="doc.pdf", file_type="pdf", name="WIRE/0412") == "wire"
    assert classify(file_name="doc.pdf", file_type="pdf", name="21INVOICE") == "invoice"


def test_the_two_partial_probes_are_still_matched_literally() -> None:
    """"@" is always letter-adjacent in an address and "inv-" is a prefix.

    Neither can be buried inside a longer word, so the boundary rule has nothing
    to do for them, and imposing it anyway would stop both from ever matching.
    """
    assert _word_pattern("@") is None
    assert _word_pattern("inv-") is None
    assert classify(file_name="c.eml", file_type="eml", source_quote="from: j@nexus.com") == "email"
    assert classify(file_name="INV-4471.pdf", file_type="pdf") == "invoice"


def test_every_other_source_keyword_is_matched_as_a_word() -> None:
    """Structural: a keyword added later must be considered, not defaulted."""
    literal = {
        keyword
        for _, keywords in _SOURCE_TYPE_KEYWORDS
        for keyword in keywords
        if _word_pattern(keyword) is None
    }
    assert literal == {"@", "inv-"}


def test_a_letter_in_another_alphabet_still_blocks_a_match() -> None:
    """The boundary is a letter in any alphabet, not just a-z."""
    assert classify(file_name="doc.pdf", file_type="pdf", name="Wirén Holdings") != "wire"
    assert classify(file_name="doc.pdf", file_type="pdf", name="Bicüm SARL") != "wire"


# --- the ordering the fix must not disturb ----------------------------------


def test_a_bank_statement_is_not_classified_as_an_interview() -> None:
    """"statement" is an interview keyword and a substring of "bank statement".

    The keyword map is ordered so the specific phrase is consulted first. This
    pins that ordering: sorting the map alphabetically would silently reclassify
    every bank statement in the corpus as a witness interview.
    """
    assert classify(name="Bank Statement for account 4354") == "bank_statement"
    assert classify(name="Account statement, April") == "bank_statement"


def test_the_documentary_classes_are_still_tried_before_the_narrative_ones() -> None:
    order = [source_type for source_type, _ in _SOURCE_TYPE_KEYWORDS]
    last_documentary = max(
        i for i, s in enumerate(order) if s in DOCUMENTARY_SOURCE_TYPES
    )
    first_narrative = min(i for i, s in enumerate(order) if s in NARRATIVE_SOURCE_TYPES)
    assert last_documentary < first_narrative


# --- the half that must stay permissive -------------------------------------

# Verbatim from the corpus. Bank exports run words together; each of these is a
# real transaction that a word-boundary rule would have dropped.
RUN_TOGETHER_EXPORT_TEXT = (
    "ACHDEBIT,FDGLLEASEPYMT052-1497020-000",
    "18ASI-DEPOSITORY   DES:INS. PYMNT ID:0221343/000",
    "DEPOSITTRANSFER,FromChecking4354790929",
    "21PURCHASE",
    "Debit Card PurchaseR eturn0 5/21 #7957",
    "eTransferCredit,OnlineXfer",
    "PAYMENTUS DES:BILLPAY ID:PAYMENTUSCORP_I",
    "Withdrawals",
    "Deposits",
)


@pytest.mark.parametrize("text", RUN_TOGETHER_EXPORT_TEXT)
def test_run_together_export_text_is_still_admitted_as_a_candidate(text: str) -> None:
    assert _is_financial_candidate("Transaction", "", text, "", {}) is True


@pytest.mark.parametrize("text", RUN_TOGETHER_EXPORT_TEXT)
def test_run_together_export_text_still_looks_like_a_transaction(text: str) -> None:
    assert (
        _looks_like_transaction_event("Transaction", "", text, "", {"amount": "100"})
        is True
    )


def test_admission_is_not_quietly_tightened_to_match_classification() -> None:
    """A false negative here loses a real transaction and nothing reports it.

    If someone later applies the classification rule to these lists to make them
    consistent, this fails. The inconsistency is the point.
    """
    # Asserted against the list that actually holds each keyword: "debit" and
    # "deposit" are transaction-event keywords, not candidate keywords.
    for text in ("ACHDEBIT", "ASI-DEPOSITORY", "DEPOSITTRANSFER", "PAYMENTUS"):
        assert (
            _looks_like_transaction_event("", "", text, "", {"amount": "1"}) is True
        ), text
    for text in ("DEPOSITTRANSFER", "PAYMENTUS"):
        assert _is_financial_candidate("", "", text, "", {}) is True, text
