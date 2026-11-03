"""Whether a case holds financial evidence, and the one wording for when it does not (docs/cellebrite/07 section 8).

The first real phone case holds only phones. Every money part beside the phones (the graph edge's money, counterparty
suggestions, the Day view money lane, approach 1, "Open these payments") says what is absent and never shows
"0 payments"; the Financial page and the agent's financial tools say there is no financial evidence.

A case holds financial evidence when it has a financial source document (a statement or other financial file
registered for reading) or a ledger row of any status. Statements uploaded and not yet read are financial evidence:
the sentence would be false for them, so they count.
"""
from __future__ import annotations

NO_FINANCIAL_RECORDS = "No financial records in this case. Add bank statements to see payments beside the phones."
NO_FINANCIAL_EVIDENCE = "No financial evidence in this case. Add bank statements from Evidence."


def _count(conn, model, case_id) -> int:
    """Rows of ``model`` in the case, through the model's own column type (so a UUID compares as the database stores
    it)."""
    from sqlalchemy import func, select
    return int(conn.execute(select(func.count()).select_from(model).where(model.case_id == case_id)).scalar() or 0)


def _phone_count(conn, case_id) -> int:
    """Phones in the case. A database without the phone tables (a test schema built for the ledger alone) counts 0;
    the read runs in a savepoint so a missing table never aborts the caller's transaction."""
    from sqlalchemy.exc import DBAPIError
    from postgres.models.phone_extraction import PhoneExtraction
    try:
        with conn.begin_nested():
            return _count(conn, PhoneExtraction, case_id)
    except DBAPIError:
        return 0


def presence(conn, case_id) -> dict:
    """``{has_financial_evidence, source_documents, ledger_rows, phones, phone_sentence, financial_sentence}``.
    The two sentences are ``None`` when the case holds financial evidence; ``phones`` is counted only then (it feeds
    the sentence), and is ``None`` otherwise. Reads only; the ledger rows are counted first."""
    import uuid
    from postgres.models.financial import FinancialSourceDocument, FinancialTransaction
    c = case_id if isinstance(case_id, uuid.UUID) else uuid.UUID(str(case_id))
    rows = _count(conn, FinancialTransaction, c)
    docs = rows and None
    if not rows:
        docs = _count(conn, FinancialSourceDocument, c)
    has = bool(rows or docs)
    return {"has_financial_evidence": has, "source_documents": docs, "ledger_rows": rows,
            "phones": None if has else _phone_count(conn, c),
            "phone_sentence": None if has else NO_FINANCIAL_RECORDS,
            "financial_sentence": None if has else NO_FINANCIAL_EVIDENCE}


def has_financial_evidence(conn, case_id) -> bool:
    return presence(conn, case_id)["has_financial_evidence"]
