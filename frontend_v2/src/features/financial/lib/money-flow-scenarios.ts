import type { LedgerTransaction } from "../api"
import { minorAmount, paymentDay } from "./investigator-workspace"
import { currencyMinorUnits } from "./ledger-format"
export type FlowMethod = "fifo" | "lifo"
export type Allocation = {
  receipt: LedgerTransaction
  payment: LedgerTransaction
  amount: bigint
}
export function flowRows(rows: LedgerTransaction[]) {
  return rows
    .filter(
      (r) =>
        r.ledger_status === "admitted" &&
        r.account_type !== "credit_card" &&
        paymentDay(r) &&
        (minorAmount(r.amount_minor) ?? -1n) > 0n
    )
    .sort(
      (a, b) =>
        paymentDay(a)!.localeCompare(paymentDay(b)!) ||
        a.source_document_id.localeCompare(b.source_document_id) ||
        a.row_index - b.row_index ||
        a.key.localeCompare(b.key)
    )
}
// An explicit zero-opening scenario over the imported rows. Unknown funding is
// reported separately and never attributed to a later receipt. Amounts are exact.
export function allocateReceipts(
  rows: LedgerTransaction[],
  method: FlowMethod
) {
  const pools = new Map<
    string,
    { receipt: LedgerTransaction; remaining: bigint }[]
  >()
  const allocations: Allocation[] = []
  const unfunded: { payment: LedgerTransaction; amount: bigint }[] = []
  for (const row of flowRows(rows)) {
    const group = `${row.account_id}:${row.currency}`
    const pool = pools.get(group) ?? []
    pools.set(group, pool)
    let remaining = minorAmount(row.amount_minor)!
    if (row.direction === "credit") {
      pool.push({ receipt: row, remaining })
      continue
    }
    if (row.direction !== "debit") continue
    while (remaining > 0n && pool.length) {
      const index = method === "fifo" ? 0 : pool.length - 1
      const source = pool[index],
        amount = remaining < source.remaining ? remaining : source.remaining
      allocations.push({ receipt: source.receipt, payment: row, amount })
      remaining -= amount
      source.remaining -= amount
      if (source.remaining === 0n) pool.splice(index, 1)
    }
    if (remaining > 0n) unfunded.push({ payment: row, amount: remaining })
  }
  return { allocations, unfunded }
}
export function receiptCluster(
  rows: LedgerTransaction[],
  receipt: LedgerTransaction,
  days: number
) {
  const start = paymentDay(receipt)
  if (!start) return []
  return flowRows(rows).filter(
    (r) =>
      r.account_id === receipt.account_id &&
      r.currency === receipt.currency &&
      r.direction === "debit" &&
      paymentDay(r)! >= start &&
      (Date.parse(paymentDay(r)!) - Date.parse(start)) / 86400000 <= days &&
      minorAmount(r.amount_minor)! < minorAmount(receipt.amount_minor)!
  )
}
export function impliedExchangeRate(
  sent: LedgerTransaction,
  received: LedgerTransaction
) {
  if (
    sent.direction !== "debit" ||
    received.direction !== "credit" ||
    sent.currency === received.currency ||
    !paymentDay(sent) ||
    !paymentDay(received) ||
    paymentDay(received)! < paymentDay(sent)!
  )
    return null
  const a = minorAmount(sent.amount_minor),
    b = minorAmount(received.amount_minor)
  const sa = currencyMinorUnits(sent.currency),
    sb = currencyMinorUnits(received.currency)
  if (
    a === null ||
    b === null ||
    a <= 0n ||
    b <= 0n ||
    sa === null ||
    sb === null
  )
    return null
  const precision = 100000000n
  const rate = (b * 10n ** BigInt(sa) * precision) / (a * 10n ** BigInt(sb))
  return `${rate / precision}.${(rate % precision).toString().padStart(8, "0")}`
}
