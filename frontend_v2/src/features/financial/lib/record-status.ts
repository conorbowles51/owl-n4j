/** One plain status per record: is it in the ledger, and if not, what is still needed. */
export function recordStatus(record: {
  awaiting_reconciliation: boolean
  can_enter_now: boolean
  missing_fields: string[]
  hold_reason?: string | null
  repeat_of?: unknown
}) {
  if (!record.awaiting_reconciliation)
    return `Not in the ledger: ${record.missing_fields.join(", ") || "a value"} missing. Open the record to fix it.`
  if (record.can_enter_now)
    return "Fixed and it checks out: not in the ledger yet. One click: Add to ledger."
  if (record.repeat_of)
    return "Saved but held: it looks like a repeat of another row."
  return `Saved but held outside totals${record.hold_reason ? `: ${record.hold_reason}` : " until the statement reconciles."}`
}
