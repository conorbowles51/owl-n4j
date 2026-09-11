type BalanceRow = {
  id: string
  excluded: boolean
  amount_minor: string
  direction: "credit" | "debit"
  balance_minor: string | null
}
type Original = { id: string; kind: string; fields: Record<string, string> }

// Compare the selected movements with printed controls without treating the
// last transaction's running balance as an independently printed closing total.
export function reviewSelectionBalance(
  rows: BalanceRow[],
  originals: Original[],
  creditCard: boolean
) {
  const byId = new Map(rows.map((row) => [row.id, row]))
  const opening = originals.filter(
    (row) =>
      row.kind === "balance" &&
      row.fields.description?.trim().toLowerCase() === "opening balance"
  )
  const closing = originals.filter(
    (row) =>
      row.kind === "balance" &&
      row.fields.description?.trim().toLowerCase() === "closing balance"
  )
  if (opening.length !== 1) return null
  const open = byId.get(opening[0].id)
  if (
    !open?.excluded ||
    open.balance_minor === null ||
    !/^-?\d+$/.test(open.balance_minor)
  )
    return null
  let final = closing.length === 1 ? byId.get(closing[0].id) : undefined
  let independent = !!final?.excluded
  if (!independent) {
    const transactions = originals.filter((row) => row.kind === "transaction")
    const dates = transactions.map(
      (row) =>
        row.fields.date ||
        row.fields.booking_date ||
        row.fields.value_date ||
        ""
    )
    if (
      !dates.length ||
      dates.some(
        (date, index) => !date || (index > 0 && date < dates[index - 1])
      )
    )
      return null
    final = byId.get(transactions.at(-1)!.id)
    independent = false
  }
  if (
    !final ||
    final.balance_minor === null ||
    !/^-?\d+$/.test(final.balance_minor)
  )
    return null
  let expected = BigInt(open.balance_minor)
  for (const row of rows) {
    if (row.excluded) continue
    if (!/^\d+$/.test(row.amount_minor)) return null
    const sign = row.direction === "credit" ? 1n : -1n
    expected += BigInt(row.amount_minor) * sign * (creditCard ? -1n : 1n)
  }
  return {
    expected: String(expected),
    printed: final.balance_minor,
    difference: String(expected - BigInt(final.balance_minor)),
    sourceId: final.id,
    independent,
  }
}
