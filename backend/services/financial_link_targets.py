"""Financial link targets (postgres/link_types.FINANCIAL_TYPES) checked against the case, with a label to show.

``financial_transaction`` is a ledger row (its citation is ``txn://<id>``), ``financial_account`` an account of the
case, ``financial_party`` a person or business the case's accounts name (services/financial/account_parties).
A target of another case, or one that does not exist, is refused in the same words.
"""
from __future__ import annotations

import uuid
from typing import Any


class FinancialTargetError(ValueError):
    pass


def _id(target_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(target_id))
    except (TypeError, ValueError) as exc:
        raise FinancialTargetError(f"{target_id} is not in this case") from exc


def financial_target_label(db, case_id, target_type: str, target_id: str) -> str:
    """The target's label in this case, or FinancialTargetError when it is not in this case."""
    from postgres.models.financial import FinancialAccount, FinancialTransaction
    case_uuid = case_id if isinstance(case_id, uuid.UUID) else uuid.UUID(str(case_id))
    if target_type == "financial_transaction":
        row = db.get(FinancialTransaction, _id(target_id))
        if row is None or row.case_id != case_uuid:
            raise FinancialTargetError(f"The payment {target_id} is not in this case")
        from services.financial.money import get_currency
        try:
            exponent = get_currency(row.currency).exponent
            minor = str(row.amount_minor).zfill(exponent + 1)
            amount = minor if not exponent else f"{minor[:-exponent]}.{minor[-exponent:]}"
        except Exception:  # noqa: BLE001 - the label is shown, never computed with
            amount = str(row.amount_minor)
        date = row.ordering_date.isoformat() if row.ordering_date else "no date"
        return " · ".join(v for v in (date, f"{row.currency} {amount} {row.direction}", row.description) if v)[:512]
    if target_type == "financial_account":
        account = db.get(FinancialAccount, _id(target_id))
        if account is None or account.case_id != case_uuid:
            raise FinancialTargetError(f"The account {target_id} is not in this case")
        return " · ".join(v for v in (account.holder_name, account.institution_name, account.identifier_as_printed,
                                      account.currency) if v)[:512] or f"Account {str(account.id)[:8]}"
    if target_type == "financial_party":
        from services.financial.account_parties import account_parties
        wanted = str(_id(target_id))
        party = next((p for p in account_parties(db, case_id=case_uuid)["parties"] if p["id"] == wanted), None)
        if party is None:
            raise FinancialTargetError(f"The person or business {target_id} is not in this case")
        return str(party.get("name") or "Person or business")[:512]
    raise FinancialTargetError(f"{target_type} is not a financial link type")


def financial_anchor(target_type: str, target_id: str, source_anchor: dict[str, Any] | None) -> dict[str, Any]:
    """A payment link's anchor carries its citation, so a bundle names each object by its own scheme."""
    anchor = dict(source_anchor or {})
    if target_type == "financial_transaction":
        anchor["cite"] = f"txn://{str(target_id).lower()}"
    return anchor
