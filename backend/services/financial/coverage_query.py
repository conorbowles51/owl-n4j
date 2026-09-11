"""Case-scoped printed-period coverage, not a claim of complete transactions."""
from datetime import date
from sqlalchemy import select
from postgres.models.financial import FinancialAccount, FinancialStatementPeriod, FinancialSourceDocument
from services.financial.continuity import _bounds_are_printed


class CoverageQueryError(ValueError):
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code=status_code


def list_statement_coverage(session, *, case_id, offset=0, limit=25, account_id=None):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 25:
        raise CoverageQueryError("Invalid account coverage page limits.")
    account_query = select(FinancialAccount).where(FinancialAccount.case_id == case_id)
    if account_id is not None:
        account = session.get(FinancialAccount, account_id)
        if account is None or account.case_id != case_id:
            raise CoverageQueryError("Account not found in this case.", 404)
        account_query = account_query.where(FinancialAccount.id == account_id)
    accounts=list(session.scalars(account_query
        .order_by(FinancialAccount.id).offset(offset).limit(limit+1)))
    items=[]
    for account in accounts[:limit]:
        pairs=list(session.execute(select(FinancialStatementPeriod,FinancialSourceDocument)
            .outerjoin(FinancialSourceDocument,FinancialSourceDocument.id==FinancialStatementPeriod.source_document_id)
            .where(FinancialStatementPeriod.case_id==case_id,FinancialStatementPeriod.account_id==account.id)
            .order_by(FinancialStatementPeriod.id).limit(501)))
        item=dict(account_id=str(account.id), label=(account.metadata_ or {}).get("display_label") or
            account.identifier_as_printed or account.holder_name or "Unidentified account",
            available=True, reason=None, periods=[], currencies=[])
        items.append(item)
        if len(pairs)>500:
            item.update(available=False,reason="More than 500 statement periods; this account's coverage was not calculated.")
            continue
        if any(document is None or document.case_id != case_id for _,document in pairs):
            item.update(available=False,reason="Statement source ownership is inconsistent; coverage was not calculated.")
            continue
        groups={}
        for period, document in pairs:
            reason=None
            if document.status != "admitted":reason="source_not_admitted"
            elif period.period_start is None or period.period_end is None:reason="missing_dates"
            elif not _bounds_are_printed(period):reason="dates_not_printed"
            elif period.period_end < period.period_start:reason="invalid_date_range"
            record=dict(period_id=str(period.id),source_document_id=str(document.id),
                evidence_file_id=str(document.evidence_file_id) if document.evidence_file_id else None,
                currency=period.currency, start=period.period_start.isoformat() if period.period_start else None,
                end=period.period_end.isoformat() if period.period_end else None,
                included=reason is None, exclusion_reason=reason)
            item["periods"].append(record)
            if reason is None:groups.setdefault(period.currency,[]).append(record)
        item["currencies"]=[_coverage(currency,periods) for currency,periods in sorted(groups.items())]
    return dict(case_id=str(case_id),account_id=str(account_id) if account_id else None,offset=offset,has_more=len(accounts)>limit,items=items,applied=False,
        limitation="Printed statement bounds only. Covered dates do not prove every transaction was captured. Gaps are dates not covered by eligible printed bounds, not proof that no transactions occurred. Records before the first or after the last known bound are not assessed.")


def _coverage(currency, periods):
    windows=[]
    overlaps=[]
    for period in sorted(periods,key=lambda p:(p["start"],p["end"],p["period_id"])):
        start=date.fromisoformat(period["start"]).toordinal()
        end=date.fromisoformat(period["end"]).toordinal()
        if not windows or start > windows[-1]["end"]+1:
            windows.append(dict(start=start,end=end,period_ids=[period["period_id"]]))
        else:
            window=windows[-1]
            if start <= window["end"]:
                overlaps.append(dict(period_id=period["period_id"],
                    start=date.fromordinal(start).isoformat(),end=date.fromordinal(min(end,window["end"])).isoformat()))
            window["end"]=max(end,window["end"])
            window["period_ids"].append(period["period_id"])
    gaps=[dict(start=date.fromordinal(a["end"]+1).isoformat(),end=date.fromordinal(b["start"]-1).isoformat(),
               days=b["start"]-a["end"]-1) for a,b in zip(windows,windows[1:])]
    return dict(currency=currency,period_count=len(periods),
        covered_days=sum(w["end"]-w["start"]+1 for w in windows),uncovered_days=sum(g["days"] for g in gaps),
        windows=[dict(start=date.fromordinal(w["start"]).isoformat(),end=date.fromordinal(w["end"]).isoformat(),
                      period_ids=w["period_ids"]) for w in windows],gaps=gaps,overlaps=overlaps)


def requested_statement_coverage(session, *, case_id, account_id, start_date, end_date):
    """Printed bounds intersecting an explicit closed search interval; never completeness."""
    if account_id is None:
        raise CoverageQueryError("Select one ledger account for requested date coverage.")
    if type(start_date) is not date or type(end_date) is not date or start_date > end_date:
        raise CoverageQueryError("A valid start date on or before the end date is required.")
    response = list_statement_coverage(session, case_id=case_id, account_id=account_id)
    if not response["items"]:
        raise CoverageQueryError("Ledger account not found in this case.", 404)
    account = response["items"][0]
    groups = []
    if account["available"]:
        for group in account["currencies"]:
            # Intersect the original eligible periods, not a merged window's
            # period_ids: otherwise an outside period becomes a false citation.
            clipped = []
            for period in account["periods"]:
                if not period["included"] or period["currency"] != group["currency"]:
                    continue
                start = max(start_date, date.fromisoformat(period["start"]))
                end = min(end_date, date.fromisoformat(period["end"]))
                if start <= end:
                    clipped.append(dict(period_id=period["period_id"], start=start.isoformat(), end=end.isoformat()))
            covered = _coverage(group["currency"], clipped)
            cursor = start_date.toordinal()
            last = end_date.toordinal()
            gaps = []
            for window in covered["windows"]:
                start, end = date.fromisoformat(window["start"]).toordinal(), date.fromisoformat(window["end"]).toordinal()
                if cursor < start:
                    gaps.append(_gap(cursor, start - 1))
                cursor = end + 1
            if cursor <= last:
                gaps.append(_gap(cursor, last))
            groups.append(dict(currency=group["currency"], covered_days=covered["covered_days"],
                uncovered_days=sum(g["days"] for g in gaps), windows=covered["windows"], gaps=gaps))
    return dict(case_id=str(case_id), account_id=str(account_id), start_date=start_date.isoformat(),
        end_date=end_date.isoformat(), requested_days=end_date.toordinal()-start_date.toordinal()+1,
        available=account["available"] and bool(groups),
        reason=account["reason"] or (None if groups else "No eligible printed bounds; date coverage is unknown."),
        periods=account["periods"], currencies=groups, applied=False,
        limitation="Printed statement bounds only, grouped by currency. Uncovered requested dates include dates outside known statements. Covered dates do not prove complete transaction extraction or that no transactions occurred. Missing, derived or excluded statement bounds do not contribute.")


def _gap(start, end):
    return dict(start=date.fromordinal(start).isoformat(), end=date.fromordinal(end).isoformat(), days=end-start+1)
