"""What a document *is* cannot be read off what it *says*.

`_infer_evidence_source_type` decides `evidence_source_type`, which decides
`evidence_strength`, which is one of the three conditions for
`is_evidence_backed_transaction`. It used to search the extracted entity's
`specific_type`, `name` and `source_quote` alongside the filename, so a
witness statement quoting "he sent a wire to Petrov" classified `wire` — a
documentary source — and hearsay was promoted to an exhibit.

An earlier fix required keywords to match as words. That removed the
accidental collisions ("wired" no longer matched "wire", "CITIBANK" no longer
matched "iban") but not the category error: it only stopped the past tense.
The witness had to say "wired" rather than "a wire" for the system to stay
honest. These tests pin the actual repair — the three content fields are not
parameters any more — and the two things it had to preserve.

Measured over 35,192 rows in 357 extraction files:

  * 51 of 306 documents were assigned two or more source types by their own
    rows, and 18 were graded both documentary and narrative. A property of the
    document was being computed per row, so a document could disagree with
    itself. Classifying from the artifact takes both counts to zero by
    construction.
  * 1,457 rows move narrative -> documentary. In 17 of the 18 affected
    documents those rows sit beside rows already graded documentary, so no
    document changes character; they had been demoted by an "@" in a Cash App
    handle, a Zelle payee's email address, or "620 gallons @ $2.75".
  * Exactly one extraction file flips in full: all 391 rows of
    `USA-ET-026407.pdf`, an Ameris Bank monthly statement carrying an account
    holder, account number, statement period and header totals. Its section
    header reads "Ameris monthly statement", and `statement` is an interview
    keyword while neither "bank statement" nor "account statement" is
    adjacent, so a genuine bank statement was labelled hearsay in full.

The separate precision/recall split this file used to describe still holds and
is still pinned at the bottom. `_infer_evidence_source_type` CLASSIFIES, so it
matches keywords as words; `_is_financial_candidate` and
`_looks_like_transaction_event` ADMIT, where a false negative silently drops a
real transaction, so they stay substring-matched. On the corpus the word rule
would reject 912 correct matches on the admission lists. The inconsistency
between the two halves is deliberate.
"""

from __future__ import annotations

import inspect

import pytest

from app.pipeline.extract_entities import (
    DOCUMENTARY_SOURCE_TYPES,
    NARRATIVE_SOURCE_TYPES,
    _SOURCE_TYPE_KEYWORDS,
    _SOURCE_TYPE_PATTERNS,
    _build_financial_provenance,
    _infer_evidence_source_type,
    _infer_evidence_strength,
    _is_financial_candidate,
    _looks_like_transaction_event,
    _word_pattern,
)


def classify(
    file_name: str = "", file_type: str | None = None, is_table: bool = False
) -> str:
    return _infer_evidence_source_type(
        file_name=file_name, file_type=file_type, is_table=is_table
    )


# --- the defect this change exists to remove --------------------------------


def test_the_function_cannot_see_what_the_document_says() -> None:
    """The structural guarantee. Removing the parameters is the repair.

    Ignoring the content inside the body would leave it one edit away from
    being consulted again. Taking it away means a reader has to change this
    signature, and read the docstring, to reintroduce the defect.
    """
    parameters = inspect.signature(_infer_evidence_source_type).parameters
    for forbidden in ("specific_type", "name", "source_quote"):
        assert forbidden not in parameters, forbidden
    assert set(parameters) == {"file_name", "file_type", "is_table"}
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in parameters.values()
    )


def test_a_witness_describing_a_wire_is_not_a_wire_document() -> None:
    """The motivating case, in the present tense the old fix left working.

    "wired" was stopped by the word-boundary rule. "a wire" was not: it is a
    real mention of the keyword, in a sentence that is unambiguously hearsay.
    """
    provenance = _build_financial_provenance(
        None,
        category="Transaction",
        specific_type="Payment",
        name="Alleged transfer to Petrov",
        source_quote="She told me he sent a wire to Dubai last spring.",
        properties={"amount": "3000", "currency": "USD"},
        file_name="witness_interview_marta.txt",
        file_type="txt",
        source_document_id="DOC-1",
        source_page=2,
        confidence=0.5,
        is_table=False,
    )

    assert provenance is not None
    assert provenance["evidence_source_type"] == "interview"
    assert provenance["evidence_strength"] == "narrative"
    assert provenance["is_evidence_backed_transaction"] is False


@pytest.mark.parametrize(
    "quote",
    [
        "She told me he sent a wire to Dubai last spring.",
        "He said the invoice was paid in cash.",
        "I saw the bank statement on his desk.",
        "There was a receipt in the glovebox.",
        "The ledger, he claimed, was destroyed.",
    ],
)
def test_no_quoted_mention_of_a_document_can_promote_hearsay(quote: str) -> None:
    """Naming a document is not producing one, whichever document is named."""
    provenance = _build_financial_provenance(
        None,
        category="Transaction",
        specific_type="Payment",
        name="Alleged payment",
        source_quote=quote,
        properties={"amount": "3000"},
        file_name="witness_interview_marta.txt",
        file_type="txt",
        source_document_id="DOC-1",
        source_page=2,
        confidence=0.5,
        is_table=False,
    )

    assert provenance is not None
    assert provenance["evidence_source_type"] in NARRATIVE_SOURCE_TYPES
    assert provenance["evidence_strength"] == "narrative"


def test_every_row_of_one_document_gets_the_same_class() -> None:
    """51 of 306 corpus documents used to disagree with themselves.

    The rows below are real shapes from the corpus: a merchant whose name
    contains "wire", a Cash App handle containing "@", and a statement's own
    boilerplate containing "statement". Under the old probe these three rows
    of one bank statement classified three different ways.
    """
    rows = (
        "CHECKCARD 0510 SPRINT *WIRELESS 800-639-6111 KS",
        "CASH APP*@BECKISH",
        "days in statement cycle 30",
        "#Zelle Acct Debit ZELLE DERICA KAMERON AMERIS BANK",
        "WIRE TRANSFER OUT NEXUS TRADING LTD 48,200.00",
    )
    provenances = [
        _build_financial_provenance(
            None,
            category="Transaction",
            specific_type="Payment",
            name=row,
            source_quote=row,
            properties={"amount": "100", "currency": "USD"},
            file_name="chase_bank_statement_apr2024.pdf",
            file_type="pdf",
            source_document_id="DOC-2",
            source_page=7,
            confidence=0.9,
            is_table=True,
        )
        for row in rows
    ]

    assert all(p is not None for p in provenances)
    assert {p["evidence_source_type"] for p in provenances} == {"bank_statement"}
    assert {p["evidence_strength"] for p in provenances} == {"documentary"}


# --- separator-joined filenames ---------------------------------------------


@pytest.mark.parametrize(
    ("expected", "file_name"),
    [
        ("bank_statement", "bank_statement.pdf"),
        ("bank_statement", "bank-statement.pdf"),
        ("bank_statement", "bank statement.pdf"),
        ("bank_statement", "BANK_STATEMENT_APR2024.PDF"),
        ("bank_statement", "2024/04/bank.statement.pdf"),
        ("bank_statement", "account_statement_q3.pdf"),
        ("card_statement", "card_statement.pdf"),
        ("card_statement", "credit_card_summary.pdf"),
        ("invoice", "purchase_order_88.pdf"),
        ("ledger", "general_ledger_extract.pdf"),
        ("official_report", "official_report.pdf"),
        ("wire", "transfer_confirmation.pdf"),
    ],
)
def test_a_multi_word_keyword_matches_a_filename_that_joins_its_words(
    expected: str, file_name: str
) -> None:
    """`bank_statement.pdf` contains no "bank statement".

    Before the separators were relaxed this fell through to the interview
    keyword "statement" and a bank statement was classified as a witness
    interview. That is an affirmative mislabel, not a near miss: it graded the
    document narrative and took its rows out of the transaction view.
    """
    assert classify(file_name=file_name, file_type="pdf") == expected


def test_the_filename_that_used_to_become_an_interview() -> None:
    source_type = classify(file_name="bank_statement.pdf", file_type="pdf")
    assert source_type != "interview"
    assert source_type in DOCUMENTARY_SOURCE_TYPES
    assert (
        _infer_evidence_strength(
            evidence_source_type=source_type, file_type="pdf", is_table=False
        )
        == "documentary"
    )


def test_relaxing_separators_does_not_break_the_literal_prefix_probe() -> None:
    """The raw form is searched as well as the relaxed one, and must be.

    "inv-" is written as a prefix, so it is matched literally rather than as a
    word. Relaxing the hyphen turns `INV-4471.pdf` into "inv 4471", which
    matches nothing. Had the relaxed form replaced the raw one instead of
    joining it, every invoice named this way would have been lost.
    """
    assert _word_pattern("inv-") is None
    assert classify(file_name="INV-4471.pdf", file_type="pdf") == "invoice"
    assert classify(file_name="inv-4471.pdf", file_type="pdf") == "invoice"


# --- what must keep working -------------------------------------------------


@pytest.mark.parametrize(
    ("expected", "file_name"),
    [
        ("wire", "wire_confirmation_0412.pdf"),
        ("wire", "swift_advice.pdf"),
        ("bank_statement", "chase_bank_statement_apr2024.pdf"),
        ("invoice", "invoice_4471.pdf"),
        ("receipt", "receipt_0412.pdf"),
        ("ledger", "general_ledger.pdf"),
        ("official_report", "receiver_report.pdf"),
        ("interview", "transcript_smith.pdf"),
        ("interview", "witness_statement_marta.pdf"),
    ],
)
def test_a_real_mention_in_the_filename_still_classifies(
    expected: str, file_name: str
) -> None:
    assert classify(file_name=file_name, file_type="pdf") == expected


@pytest.mark.parametrize(
    ("expected", "file_name"),
    [
        ("invoice", "invoices_q2.pdf"),
        ("receipt", "receipts_attached.pdf"),
        ("official_report", "quarterly_reports.pdf"),
        ("bank_statement", "bank_statements_2024.pdf"),
        ("wire", "wires_sent_tuesday.pdf"),
    ],
)
def test_plurals_still_classify(expected: str, file_name: str) -> None:
    assert classify(file_name=file_name, file_type="pdf") == expected


def test_a_keyword_against_a_digit_still_classifies() -> None:
    """A letter boundary, not a word boundary: names run words into digits."""
    assert classify(file_name="21INVOICE.pdf", file_type="pdf") == "invoice"
    assert classify(file_name="WIRE0412.pdf", file_type="pdf") == "wire"


@pytest.mark.parametrize(
    ("file_name", "collision"),
    [
        ("sprint_wireless_bill.pdf", "wire in wireless"),
        ("citibank_letter.pdf", "iban in citibank"),
        ("mbicam_and_co.pdf", "bic in mbicam"),
        ("kenilworth_properties.pdf", "worth in kenilworth"),
        ("wirecard_ag_payment.pdf", "wire in wirecard"),
    ],
)
def test_a_keyword_buried_in_a_longer_word_does_not_classify(
    file_name: str, collision: str
) -> None:
    """The word rule from the previous fix, still in force on the filename."""
    assert classify(file_name=file_name, file_type="pdf") == "other", collision


def test_a_letter_in_another_alphabet_still_blocks_a_match() -> None:
    """The boundary is a letter in any alphabet, not just a-z."""
    assert classify(file_name="Wirén Holdings.pdf", file_type="pdf") != "wire"
    assert classify(file_name="Bicüm SARL.pdf", file_type="pdf") != "wire"


def test_a_mail_container_is_an_email_whatever_its_filename_claims() -> None:
    """The file type is checked before the keywords, on purpose.

    Content used to supply this through the "@" in a header. With content gone
    the extension has to carry it, and it has to outrank the filename: the
    filename of an email is chosen by its author, so letting "wire" win would
    promote a narrative artifact on the strength of the sender's own claim.
    """
    assert classify(file_name="c.eml", file_type="eml") == "email"
    assert classify(file_name="wire_confirmation.eml", file_type="eml") == "email"
    assert classify(file_name="bank_statement.msg", file_type="msg") == "email"
    assert "email" in NARRATIVE_SOURCE_TYPES


def test_the_structural_fallbacks_still_apply() -> None:
    """Bates-stamped filenames carry no words, so these carry the corpus."""
    bates_csv = "USA-ET-000042.csv"
    bates_pdf = "USA-ET-000042.pdf"
    assert classify(file_name=bates_csv, file_type="csv", is_table=True) == "ledger"
    assert classify(file_name=bates_csv, file_type="csv") == "other"
    assert (
        classify(file_name=bates_pdf, file_type="pdf", is_table=True)
        == "official_report"
    )
    assert classify(file_name=bates_pdf, file_type="pdf") == "other"


# --- the ordering the fix must not disturb ----------------------------------


def test_a_bank_statement_is_not_classified_as_an_interview() -> None:
    """"statement" is an interview keyword and a substring of "bank statement".

    The keyword map is ordered so the specific phrase is consulted first.
    Sorting the map alphabetically would reclassify every bank statement in
    the corpus as a witness interview.
    """
    for file_name in ("bank_statement_apr.pdf", "account_statement.pdf"):
        assert classify(file_name=file_name, file_type="pdf") == "bank_statement"


def test_the_documentary_classes_are_still_tried_before_the_narrative_ones() -> None:
    """Asserted on the derived table, because that is what the function reads.

    This used to assert on `_SOURCE_TYPE_KEYWORDS`. Reordering the derived
    table alone then changed every classification while this test still
    passed, because it was guarding the source tuple rather than the one
    actually consulted.
    """
    order = [source_type for source_type, _ in _SOURCE_TYPE_PATTERNS]
    last_documentary = max(
        i for i, s in enumerate(order) if s in DOCUMENTARY_SOURCE_TYPES
    )
    first_narrative = min(i for i, s in enumerate(order) if s in NARRATIVE_SOURCE_TYPES)
    assert last_documentary < first_narrative


def test_every_other_source_keyword_is_matched_as_a_word() -> None:
    """Structural: a keyword added later must be considered, not defaulted.

    Asserted on the derived table for the same reason as the ordering test —
    it is the compiled patterns the function consults, not the source map.
    """
    literal = {
        keyword
        for _, keywords in _SOURCE_TYPE_PATTERNS
        for keyword, pattern in keywords
        if pattern is None
    }
    assert literal == {"@", "inv-"}
    assert literal == {
        keyword
        for _, keywords in _SOURCE_TYPE_KEYWORDS
        for keyword in keywords
        if _word_pattern(keyword) is None
    }


def test_deriving_the_pattern_table_loses_nothing() -> None:
    """The derived table must be the source map, class for class and word for
    word. Only the ordering test above would notice a reordering, and nothing
    at all would notice a dropped keyword, so both are pinned here.
    """
    assert [source_type for source_type, _ in _SOURCE_TYPE_PATTERNS] == [
        source_type for source_type, _ in _SOURCE_TYPE_KEYWORDS
    ]
    assert [
        tuple(keyword for keyword, _ in keywords)
        for _, keywords in _SOURCE_TYPE_PATTERNS
    ] == [tuple(keywords) for _, keywords in _SOURCE_TYPE_KEYWORDS]


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


def test_admission_still_reads_content_and_classification_does_not() -> None:
    """The two halves answer different questions and must not be unified.

    Admission reads the row, because a false negative there drops a real
    transaction silently and forever. Classification reads the artifact,
    because a false positive there puts hearsay in front of a jury. Anyone
    making these consistent breaks one of them; this records which.
    """
    admitting = (_is_financial_candidate, _looks_like_transaction_event)
    for func in admitting:
        parameters = inspect.signature(func).parameters
        assert "name" in parameters and "source_quote" in parameters, func.__name__
    assert "name" not in inspect.signature(_infer_evidence_source_type).parameters


def test_admission_is_not_quietly_tightened_to_match_classification() -> None:
    """A false negative here loses a real transaction and nothing reports it."""
    for text in ("ACHDEBIT", "ASI-DEPOSITORY", "DEPOSITTRANSFER", "PAYMENTUS"):
        assert (
            _looks_like_transaction_event("", "", text, "", {"amount": "1"}) is True
        ), text
    for text in ("DEPOSITTRANSFER", "PAYMENTUS"):
        assert _is_financial_candidate("", "", text, "", {}) is True, text
