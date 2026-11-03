"""Money between two parties: the one answer (agent-ledger B; report "Money between two people is computed three
ways today").

Built on the ledger reading the Graph pair edge already used (``services.phone.link_edges.payments``), so there is
one implementation: admitted, current rows (a corrected amount is the one used) whose reviewed payment identity
(``payment_counterparty_link.resolved_link``) is the other side, on an account the first side holds (or the account
itself). A payment seen on both sides' statements is one payment (the ledger's mirror rule). Sums are exact integer
minor units per currency, never across currencies. p0 to p2 are summed; p3 is stated beside them, never added in;
p4 (a phone's reading of money) is counted, never summed.

A side is one of:
- ``{"kind": "party", "id": <party id>}``: a reviewed person or business, with the accounts it holds through the
  ledger's one holder resolver (``account_selection.holder_account_ids``, the same accounts the ledger table, totals
  and the agent ledger tool select for that holder);
- ``{"kind": "account", "id": <account id>}``: one account with its consolidated aliases;
- ``{"kind": "entity", "id": <canonical entity key>}``: a dossier, through the parties its accounts' reviewed entity
  links name (``link_edges.financial_sides``).
A printed or labelled name is never a side: grouping by name is the ledger table's view, not an identity.

The graph's ``TRANSFERRED_TO`` relationships are navigation, not a total, and are never summed here.
"""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

SCHEMA = "loupe.financial.money_between/1"
KINDS = ("party", "account", "entity")
BASIS = ("Reviewed identity: payments on one side's accounts whose reviewed payment link names the other side "
         "(a party, or an account), from both sides' statements, a payment seen on both counted once. Admitted, "
         "current rows only; a corrected amount is the one used. p0 to p2 are summed per currency; p3 is stated "
         "beside them and not added in; phone readings of money (p4) are counted, never summed. Payments whose "
         "other side is only a printed name are not between these two parties.")
GRAPH_NOT_A_TOTAL = ("Graph money relationships (TRANSFERRED_TO) are navigation, not a total: they draw every "
                     "admitted class, including p3, and know no reviewed identity. Never sum them as money between "
                     "two parties; use get_money_between.")


class MoneyBetweenError(ValueError):
    """An invalid side (answered without a partial result)."""


class NotInCase(LookupError):
    """A side that is not in this case. The same words whether or not it exists in another case."""


def _uuid(value):
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise MoneyBetweenError("Use a valid party or account identifier.") from exc


def parse_side(value) -> dict:
    """``"party:<id>"``, ``"account:<id>"``, ``"entity:<key>"`` or a dict ``{"kind", "id"}``."""
    if isinstance(value, dict):
        kind, ident = value.get("kind"), value.get("id")
    elif isinstance(value, str) and ":" in value:
        kind, ident = value.split(":", 1)
    else:
        raise MoneyBetweenError("Name each side as party:<id>, account:<id> or entity:<key>.")
    if kind not in KINDS or not ident:
        raise MoneyBetweenError("Name each side as party:<id>, account:<id> or entity:<key>.")
    return {"kind": kind, "id": str(ident) if kind == "entity" else str(_uuid(ident))}


def _parties(session, case_id):
    from services.financial.account_parties import _account_party_state
    from services.financial.counterparty_parties import payment_party_choices
    known = _account_party_state(session, case_id=case_id)["parties"]
    return {p["id"]: p for p in payment_party_choices(session, case_id=case_id, known_parties=known).values()}


def _linked_party(session, case_id, party_id):
    """A party named by a current row's reviewed payment link in this case (``{"id", "name"}``), or None."""
    from sqlalchemy import or_, select
    from postgres.models.financial import FinancialTransaction as T
    labelled = T.metadata_['investigation_labels']['counterparty_link']
    reviewed = T.provenance['reviewed_counterparty']
    row = session.execute(select(labelled, reviewed).where(
        T.case_id == case_id, T.superseded_by_id.is_(None),
        or_(labelled['id'].as_string() == party_id, reviewed['id'].as_string() == party_id)).limit(1)).first()
    if row is None:
        return None
    link = next((x for x in row if isinstance(x, dict) and x.get('id') == party_id and x.get('kind') == 'party'), None)
    return None if link is None else {"id": party_id, "name": link.get("label") or "Party " + party_id[:8]}


def resolve_side(session, case_id, spec, *, parties=None) -> dict:
    """``{"subject", "label", "parties": set, "accounts": set}``; ``NotInCase`` when the side is not in this case."""
    from postgres.models.financial import FinancialAccount
    from services.financial.account_consolidation import expand_account_ids
    spec = parse_side(spec)
    if spec["kind"] == "party":
        parties = _parties(session, case_id) if parties is None else parties
        party = parties.get(spec["id"]) or _linked_party(session, case_id, spec["id"])
        if party is None:
            raise NotInCase("That person or business is not in this case.")
        from services.financial.account_selection import holder_account_ids
        accounts = {str(a) for a in holder_account_ids(session, case_id, ["party:%s" % spec["id"]])}
        return {"subject": spec, "label": party["name"], "parties": {spec["id"]}, "accounts": accounts}
    if spec["kind"] == "account":
        account = session.get(FinancialAccount, UUID(spec["id"]))
        if account is None or account.case_id != case_id:
            raise NotInCase("That account is not in this case.")
        canonical = (account.metadata_ or {}).get("canonical_account_id") or str(account.id)
        root = session.get(FinancialAccount, UUID(canonical)) or account
        label = " · ".join(v for v in (root.holder_name, root.institution_name, root.identifier_as_printed,
                                       root.currency) if v) or "Account " + canonical[:8]
        accounts = {str(a) for a in expand_account_ids(session, case_id, [account.id])}
        return {"subject": {"kind": "account", "id": canonical}, "label": label, "parties": set(),
                "accounts": accounts}
    from services.phone.link_edges import financial_sides
    side = financial_sides(session, case_id, [spec["id"]]).get(spec["id"])
    return {"subject": spec, "label": spec["id"], "parties": set(side["parties"]), "accounts": set(side["accounts"])}


def money_between(session, case_id, party_a, party_b, *, from_date=None, to_date=None, sides=None,
                  phone_mentions=None) -> dict:
    """The money between two sides, A to B and B to A. ``sides`` (already resolved ``{"parties", "accounts"}``)
    lets a caller that resolved many sides at once pass them; ``phone_mentions`` is the p4 count, or None when no
    phone reading exists.

    Returns ``{schema, a, b, totals, rows, payments, shared_accounts, p4, basis, revision, limits}``; ``totals``
    per currency is ``{currency, classes: "p0-p2", paid_ab_minor, payments_ab, paid_ba_minor, payments_ba, p3:
    {...}}`` (``link_edges.money_totals``)."""
    from services.phone.link_edges import money_totals, payments
    case_id = _uuid(case_id)
    if sides is None:
        parties = _parties(session, case_id) if "party" in {parse_side(s)["kind"] for s in (party_a, party_b)} else None
        sides = (resolve_side(session, case_id, party_a, parties=parties),
                 resolve_side(session, case_id, party_b, parties=parties))
    a, b = sides
    pay = payments(session, case_id, {"parties": set(a["parties"]), "accounts": set(a["accounts"])},
                   {"parties": set(b["parties"]), "accounts": set(b["accounts"])}, from_date=from_date, to_date=to_date)
    rows = pay["rows"]
    totals = money_totals(rows)
    limits = []
    if pay["shared_accounts"]:
        limits.append({"code": "shared_account", "count": pay["shared_accounts"],
                       "message": "%d account%s held by both sides %s left out of the money between them."
                                  % (pay["shared_accounts"], "" if pay["shared_accounts"] == 1 else "s",
                                     "is" if pay["shared_accounts"] == 1 else "are")})
    if not a.get("accounts") and not b.get("accounts"):
        limits.append({"code": "no_accounts", "message": "Neither side holds an account in this case (no reviewed "
                       "holder), so no statement can show a payment between them."})
    revision = hashlib.sha256(json.dumps([[r["id"], r["amount_minor"], r["currency"], r["proof_class"],
                                           r["direction"]] for r in rows], separators=(",", ":")).encode()).hexdigest()
    return {"schema": SCHEMA, "case_id": str(case_id),
            "a": {**a.get("subject", {}), "label": a.get("label"), "accounts": len(a["accounts"]),
                  "parties": len(a["parties"])},
            "b": {**b.get("subject", {}), "label": b.get("label"), "accounts": len(b["accounts"]),
                  "parties": len(b["parties"])},
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
            "totals": totals, "rows": rows, "payments": len(rows),
            "payments_by_class": {c: sum(r["proof_class"] == c for r in rows) for c in ("p0", "p1", "p2", "p3")},
            "shared_accounts": pay["shared_accounts"],
            "p4": {"money_mentioned_on_phones": phone_mentions, "summed": False,
                   "available": phone_mentions is not None},
            "date_basis": "ledger ordering date", "basis": BASIS, "graph": GRAPH_NOT_A_TOTAL,
            "revision": revision, "limits": limits}
