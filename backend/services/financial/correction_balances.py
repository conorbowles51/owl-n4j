"""Conditional printed running-balance comparisons, never an admission proof.

Both source row orders are reported. Stored post-transaction balances and row
order need source confirmation; a matching interpretation cannot establish them.
Excluded rows interrupt the chain instead of silently bridging missing movements.
"""
from services.financial.periods import read_opening


def correction_running_balances(period, rows, *, transaction_id, amount_minor, direction):
    if type(amount_minor) is not int or not 0 <= amount_minor <= 9223372036854775807 or direction not in ("credit", "debit"):
        raise ValueError("A correction requires an exact nonnegative ledger amount and direction.")
    if len(rows) > 1000:
        return dict(available=False, reason="More than 1,000 period rows; running-balance comparison was not performed.", interpretations=[])
    current = [r for r in rows if r.ledger_status != "superseded" and not r.superseded_by_id]
    if any(type(r.row_index) is not int or r.row_index < 0 or
           type(r.amount_minor) is not int or r.amount_minor < 0 or
           r.direction not in ("credit", "debit") or
           (r.running_balance_minor is not None and type(r.running_balance_minor) is not int)
           for r in current):
        return dict(available=False, reason="Stored row arithmetic or order is malformed.", interpretations=[])
    indices = [r.row_index for r in current]
    if len(indices) != len(set(indices)):
        return dict(available=False, reason="Current rows share source positions; running-balance order is ambiguous.", interpretations=[])
    if any(r.currency != period.currency or r.account_id != period.account_id for r in current):
        return dict(available=False, reason="Row account or currency differs from the period.", interpretations=[])
    if not any(r.running_balance_minor is not None for r in current):
        return dict(available=False, reason="No current row has a stored running balance.", interpretations=[])
    opening = read_opening(period)
    # Carry-forward or computed openings do not independently anchor this source.
    anchor = opening.amount.minor_units if opening.is_independent else None
    ordered = sorted(current, key=lambda r: r.row_index)
    return dict(available=True, reason=None, currency=period.currency,
        limitation="Conditional comparisons assuming balances follow each transaction. Neither row order, source accuracy nor complete coverage is established. No proof class is raised.",
        interpretations=[dict(order=order,
            current=_walk(sequence, anchor),
            proposed=_walk(sequence, anchor, transaction_id=transaction_id, amount_minor=amount_minor, direction=direction))
            for order, sequence in (("source_row_order", ordered), ("reverse_source_row_order", list(reversed(ordered))))])


def _walk(rows, opening, *, transaction_id=None, amount_minor=None, direction=None):
    previous, before_ref, pending = opening, None, 0
    checked, mismatches, unanchored, excluded, trailing = 0, 0, 0, 0, 0
    findings = []
    for row in rows:
        if row.ledger_status != "admitted":
            previous, before_ref, pending, trailing = None, None, 0, 0
            excluded += 1
            continue
        amount = amount_minor if row.id == transaction_id else row.amount_minor
        sign = direction if row.id == transaction_id else row.direction
        pending += amount if sign == "credit" else -amount
        trailing += 1
        if row.running_balance_minor is None:
            continue
        if previous is None:
            unanchored += 1
        else:
            checked += 1
            expected = previous + pending
            delta = row.running_balance_minor - expected
            if delta:
                mismatches += 1
                if len(findings) < 100:
                    findings.append(dict(before_ref=before_ref, after_ref=row.ref_id, after_transaction_id=str(row.id),
                        expected_minor=str(expected), printed_minor=str(row.running_balance_minor), delta_minor=str(delta)))
        previous, before_ref, pending, trailing = row.running_balance_minor, row.ref_id, 0, 0
    return dict(compared_intervals=checked, mismatch_count=mismatches,
        unanchored_balances=unanchored, excluded_rows=excluded,
        trailing_rows_without_balance=trailing, findings=findings,
        findings_truncated=mismatches > len(findings))
