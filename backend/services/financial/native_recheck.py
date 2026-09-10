"""Recompute native controls over explicit revised readings, without source writes.

The caller must independently bind the parse to verified source bytes and original
ledger content hashes. This pure calculation is not an admission decision. Source
records which did not map to ledger rows stay in the calculation unchanged.
"""
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from typing import Mapping

from postgres.models.enums import TransactionDirection
from services.financial import bai2, camt053, mt940, nacha
from services.financial.money import Money
from services.financial.native import NativeFormat, NativeReading


@dataclass(frozen=True)
class NativeAmountReading:
    amount: Money
    direction: TransactionDirection


class _Revised:
    """Override arithmetic fields while retaining original record metadata."""
    def __init__(self, original, reading):
        self.original = original
        self.amount = reading.amount
        self.direction = reading.direction

    def __getattr__(self, key):
        return getattr(self.original, key)


def _json(value):
    if isinstance(value, Money):
        return {"minor_units": str(value.minor_units), "currency": value.currency}
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _json(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (tuple, list)):
        return [_json(item) for item in value]
    # Control hashes and raw checksums can exceed JavaScript's exact integer range.
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


def recheck_native_controls(native: NativeReading,
                            readings: Mapping[int, NativeAmountReading]) -> dict:
    """Recheck all format controls for a complete mapped amount/direction set.

    No omitted mapped rows, added rows, currency changes or negative magnitudes
    are allowed. Excluded duplicate readings still belong in source controls:
    their exclusion from analytical totals cannot erase a source record.
    """
    native.check_partition()
    expected = {row.row_index: row for row in native.rows}
    if any(type(key) is not int for key in readings) or set(readings) != set(expected):
        raise ValueError("Native recheck requires exactly every mapped source row")
    for index, reading in readings.items():
        if (not isinstance(reading, NativeAmountReading)
                or not isinstance(reading.amount, Money)
                or reading.amount.minor_units < 0
                or reading.amount.currency != expected[index].reading.currency
                or not isinstance(reading.direction, TransactionDirection)):
            raise ValueError("Native recheck requires same-currency nonnegative readings")
    index = 0

    def revised(records):
        nonlocal index
        result = []
        for record in records:
            reading = readings.get(index)
            result.append(_Revised(record, reading) if reading is not None else record)
            index += 1
        return tuple(result)

    checks = []

    def add(scope, kind, result):
        checks.append({"scope": scope, "kind": kind, "result": _json(result)})

    document = native.document
    if native.format == NativeFormat.camt053:
        for number, statement in enumerate(document.statements):
            scope = f"statement:{number}"
            entries = revised(statement.entries)
            add(scope, "balance", camt053._check_balances(statement.balances, entries, statement.currency))
            add(scope, "summary", camt053._check_summary(statement.summary, entries, statement.currency))
            for batch in camt053._check_batches(entries):
                add(scope, "batch", batch)
    elif native.format == NativeFormat.mt940:
        for number, statement in enumerate(document.statements):
            add(f"statement:{number}", "balance", mt940._check_balance_identity(
                statement.opening_balance, statement.closing_balance,
                revised(statement.lines), statement.currency))
    elif native.format == NativeFormat.nacha:
        batches = []
        for number, batch in enumerate(document.batches):
            entries = revised(batch.entries)
            control = batch.control_total
            result = nacha._check_batch_control(
                service_class=batch.service_class, entries=entries,
                addenda_count=len(batch.addenda),
                declared_entry_addenda_count=control.declared_entry_addenda_count,
                declared_entry_hash=control.declared_entry_hash,
                declared_debits=control.declared_debit_total,
                declared_credits=control.declared_credit_total)
            add(f"batch:{number}", "control", result)
            batches.append(replace(batch, entries=entries, control_total=result))
        control = document.control_total
        add("file", "control", nacha._check_file_control(
            batches=batches, declared_batch_count=control.declared_batch_count,
            declared_block_count=control.declared_block_count,
            declared_entry_addenda_count=control.declared_entry_addenda_count,
            declared_entry_hash=control.declared_entry_hash,
            declared_debits=control.declared_debit_total,
            declared_credits=control.declared_credit_total,
            physical_record_count=document.physical_record_count))
    elif native.format == NativeFormat.bai2:
        def trailer(scope, control, amount_delta=0):
            add(scope, "control", bai2._check_control_total(
                level=control.level, basis=control.basis,
                declared=control.declared_minor_units,
                computed=(None if control.computed_minor_units is None else
                          control.computed_minor_units + amount_delta),
                currency=control.currency,
                declared_record_count=control.declared_record_count,
                computed_record_count=control.computed_record_count,
                declared_child_count=control.declared_child_count,
                computed_child_count=control.computed_child_count,
                computed_reason=control.unavailable_reason))
        for group_number, group in enumerate(document.groups):
            for number, account in enumerate(group.accounts):
                scope = f"group:{group_number}/account:{number}"
                transactions = revised(account.transactions)
                add(scope, "balance", bai2._check_balance_identity(account.summaries, transactions, account.currency))
                add(scope, "summary", bai2._check_summary_identity(account.summaries, transactions, account.currency))
                delta = sum(new.amount.minor_units - old.amount.minor_units
                            for new, old in zip(transactions, account.transactions))
                trailer(scope, account.control_total, delta)
            trailer(f"group:{group_number}", group.control_total)
        trailer("file", document.control_total)
    else:
        raise ValueError("Unsupported native format")
    return {
        "format": native.format.value, "checks": checks,
        "mapped_rows": len(readings), "unmapped_rows_retained": len(native.unmapped),
        "basis": "Current amount/direction readings against unchanged source controls; unmapped source records retained. Higher-level trailers compare declared child trailers.",
        "changes_proof_class": False,
    }
