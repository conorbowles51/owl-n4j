"""The agent's reads of every possible match, graded (Neil 2026-11-04: "If there are any payment matches at all they
should be mentioned. With a signal strength showing the user how well matched something is and how heavily
substantiated. We don't want to miss things based on an arbitrary cutoff.").

Three tools, each returning every candidate the screens list, strongest first, with its strength on the app's one
scale (services.match_strength; set by a stated rule, never by a model) and its reasons in two parts, paged with
exact totals (``total``, ``returned``, ``has_more``, ``next_offset``) and the count per strength:

- ``get_transfer_pairs``: possible transfers between the case's accounts (services.financial.linkage
  .graded_transfer_pairs over the whole case, by the Transfers workbench's rule; a whole case can hold tens of
  thousands of pairs, so each payment keeps its GRADED_PER_ROW strongest and the number left out is returned and
  stated in ``left_out_words``; the workbench's scope of at most 500 payments lists every pair);
- ``get_payment_other_legs``: one payment's possible other legs (payment_party_matches.other_leg_candidates);
- ``get_identity_suggestions``: phone identity suggestions (services.phone.identity_decisions).

Nothing here is a link, a name or a corroboration: a weak or faint candidate is a possibility to check, and no
candidate enters a total.
"""
from __future__ import annotations

import logging
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

MAX_LIMIT = 200
DEFAULT_LIMIT = 100
Level = Literal["strong", "moderate", "weak", "faint"]


class TransferPairArgs(BaseModel):
    strength: Optional[Level] = Field(None, description="Only pairs of this strength.")
    start_date: Optional[str] = Field(None, description="Only pairs whose money-out date is on or after (YYYY-MM-DD).")
    end_date: Optional[str] = Field(None, description="Only pairs whose money-out date is on or before (YYYY-MM-DD).")
    offset: int = Field(0, ge=0)
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class OtherLegArgs(BaseModel):
    payment: str = Field(..., description="The payment's id (the transaction id in its financial_href).")


class IdentitySuggestionArgs(BaseModel):
    strength: Optional[Level] = Field(None, description="Only suggestions of this strength.")
    offset: int = Field(0, ge=0)
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


def _page(items, offset, limit):
    total = len(items)
    page = items[offset:offset + limit]
    end = offset + len(page)
    return dict(total=total, returned=len(page), offset=offset, has_more=end < total,
                next_offset=end if end < total else None, items=page)


def _href(case_id, txn):
    return "/cases/%s/financial?view=transactions&payment=%s" % (case_id, txn)


def transfer_pairs(db, case_id, *, strength=None, start_date=None, end_date=None, offset=0, limit=DEFAULT_LIMIT):
    from dataclasses import replace
    from services.financial import payment_party_matches as P
    from services.financial.linkage import graded_left_out_words, graded_transfer_pairs
    from services.match_strength import LEVELS, SCALE_WORDS, counts
    rows = [r for r in P.case_rows(db, case_id) if r.get('ordering_date')]
    by_id = {r['id']: r for r in rows}
    obs = [replace(P._observation(r), counterparty_raw=r.get('name') or None, holder_name=r.get('holder') or None)
           for r in rows]
    g = graded_transfer_pairs(obs, same_holder=lambda d, c: P._related_holders(
        by_id[str(d.transaction_id)]['holder'], by_id[str(c.transaction_id)]['holder']))
    pairs = g['pairs']
    if start_date:
        pairs = [p for p in pairs if str(by_id[p['debit_id']]['ordering_date']) >= start_date]
    if end_date:
        pairs = [p for p in pairs if str(by_id[p['debit_id']]['ordering_date']) <= end_date]
    in_scope = counts(pairs)
    if strength:
        pairs = [p for p in pairs if p['level'] == strength]
    items = []
    for p in pairs:
        d, c = by_id[p['debit_id']], by_id[p['credit_id']]
        side = lambda r: dict(payment_id=r['id'], financial_href=_href(case_id, r['id']), date=str(r['ordering_date']),
                              account_holder=r['holder'], institution=r['institution'], account=r['identifier'],
                              description=r['description'], other_side_shown=r.get('name'))
        items.append(dict(strength=p['level'], amount_minor=p['amount_minor'], currency=p['currency'],
                          days_apart=p['gap_days'], money_out=side(d), money_in=side(c),
                          how_well_matched=p['reasons']['match'], how_substantiated=p['reasons']['substantiation']))
    out = _page(items, offset, limit)
    out.update(available=True, by_strength=in_scope, levels=list(LEVELS), rule=g['rule'], scale=SCALE_WORDS,
               left_out=g['left_out'], left_out_words=graded_left_out_words(g['left_out']),
               coverage="Every current admitted payment with a date in the case was compared (%d payments)." % len(rows),
               limitation=("A pair is a possibility to check, never a link, and never enters a total. Weak and faint "
                           "pairs are listed as weak and faint."))
    return out


def payment_other_legs(db, case_id, *, payment):
    from services.financial.payment_party_matches import other_leg_candidates
    from services.match_strength import SCALE_WORDS
    try:
        txn = uuid.UUID(str(payment).rsplit('payment=', 1)[-1].strip().split('&')[0].replace('txn://', ''))
    except ValueError:
        raise ValueError("Name the payment by its id.")
    found = other_leg_candidates(db, case_id, txn)
    if found is None:
        return dict(available=False, reason="Not in this case.")
    items = [dict(strength=c['level'], payment_id=c['transaction_id'], financial_href=_href(case_id, c['transaction_id']),
                  date=c['date'], days_apart=c['gap_days'], account_holder=c['holder'], institution=c['institution'],
                  account=c['identifier'], description=c['description'], is_the_leg_the_name_comes_from=c['is_the_named_leg'],
                  how_well_matched=c['reasons']['match'], how_substantiated=c['reasons']['substantiation'],
                  against=c['reasons']['against']) for c in found['candidates']]
    out = _page(items, 0, len(items) or 1)
    out.update(available=True, payment_id=str(txn), financial_href=_href(case_id, txn),
               named_from=found['named_from'], by_strength=found['by_level'], rule=found['rule'], scale=SCALE_WORDS,
               left_out=found['left_out'], coverage="Every payment of the same currency and amount in the case was read.",
               limitation=("A possible other leg is never used as the payment's name; the name shown comes only from a "
                           "single matching payment the deterministic rule resolves."))
    if found.get('reason'):
        out['reason'] = found['reason']
    return out


def identity_suggestions(db, case_id, *, strength=None, offset=0, limit=DEFAULT_LIMIT):
    from sqlalchemy import text
    from services.match_strength import LEVELS, SCALE_WORDS, counts
    from services.phone import identity_decisions as idd
    conn = db.connection()
    rows = idd.candidate_rows(conn, str(case_id))
    decided = {(tuple(sorted(str(x) for x in r[0])), str(r[1]) if r[1] else None) for r in conn.execute(text(
        "SELECT identity_ids, dossier_id FROM phone_identity_suggestions WHERE case_id = :c AND state <> 'open'"),
        {"c": str(case_id)})}
    rows = [r for r in rows if (tuple(sorted(r["ids"])), r["dossier"]) not in decided]
    ids = sorted({i for r in rows for i in r["ids"]})
    shown = {str(i): (k, v) for i, k, v in conn.execute(text(
        "SELECT id::text, identity_key, value_display FROM phone_identities WHERE id = ANY(CAST(:i AS uuid[]))"),
        {"i": ids})} if ids else {}
    names = {str(d): n for d, n in conn.execute(text(
        "SELECT id, display_name FROM case_profiles WHERE case_id = :c"), {"c": str(case_id)})}
    items = []
    for r in rows:
        lv, words = idd.strength(r["score"], r["reasons"])
        items.append(dict(strength=lv, score=r["score"],
                          identities=[dict(identity_key=shown.get(i, (i, i))[0], shown_as=shown.get(i, (i, i))[1])
                                      for i in r["ids"]],
                          person=names.get(r["dossier"]) if r["dossier"] else None,
                          how_well_matched=words["match"], how_substantiated=words["substantiation"],
                          reasons=[x["reason"] for x in r["reasons"]]))
    in_case = counts(items, key="strength")
    if strength:
        items = [x for x in items if x["strength"] == strength]
    out = _page(items, offset, limit)
    out.update(available=True, by_strength=in_case, levels=list(LEVELS), scale=SCALE_WORDS,
               coverage="Every identity seen on the case's phones was compared.",
               limitation=("A suggestion links nothing: a person decides on People suggestions. A name alone is "
                           "always faint."))
    return out


TOOLS = [
    ("get_transfer_pairs", transfer_pairs, TransferPairArgs,
     "Every possible transfer between the case's accounts (same currency and amount, one money out and one money in, "
     "different accounts, within 365 days), strongest first, each with its strength (strong, moderate, weak, faint) "
     "set by a stated rule and its reasons (how well matched, how substantiated), paged with exact totals and the "
     "count per strength. A pair is a possibility, never a link or a total."),
    ("get_payment_other_legs", payment_other_legs, OtherLegArgs,
     "Every possible other leg of one payment in another account of the case, strongest first, with its strength "
     "and reasons, the reasons against, and which leg (if any) the payment's shown name comes from."),
    ("get_identity_suggestions", identity_suggestions, IdentitySuggestionArgs,
     "Every phone identity suggestion (two identities that may be one person, or an identity that may be a dossier's "
     "person), strongest first, with its strength and reasons, paged with exact totals. A name alone is faint."),
]


def make_match_tools(context):
    from langchain_core.tools import StructuredTool
    from services.agent.tools import _financial_session

    def runner(name, func):
        def run(**kwargs):
            if getattr(context, "significant_scope", None):
                return context.result(name, {"available": False, "reason": "Not available in this scope."},
                                      summary="Not available in this scope.", status="error",
                                      error="Not available in this scope.")
            try:
                with (context.ledger_session_factory or _financial_session)() as db:
                    data = func(db, uuid.UUID(context.case_id), **kwargs)
            except ValueError as exc:
                return context.result(name, {"available": False, "reason": str(exc)}, summary=str(exc),
                                      status="error", error=str(exc))
            except Exception:
                log.exception("Agent match read %s failed for case %s", name, context.case_id)
                return context.result(name, {"available": False, "reason": "The matches could not be read just now. "
                                      "Retry; nothing partial was returned."},
                                      summary="Unavailable; nothing partial was returned.", status="error",
                                      error="The matches could not be read.")
            if not data.get("available"):
                return context.result(name, data, summary=str(data.get("reason")))
            from services.match_strength import counts_words
            summary = "Read %d of %d (%s)." % (data["returned"], data["total"], counts_words(data["by_strength"]))
            if data.get("left_out_words"):
                summary += " " + data["left_out_words"]
            return context.result(name, data, summary=summary)
        return run

    return [StructuredTool.from_function(func=runner(name, func), name=name, description=description,
                                         args_schema=args) for name, func, args, description in TOOLS]
